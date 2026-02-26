from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List

from ..domain.model import BalanceReport
from ..domain.services import TotalsCalculator
from ..infrastructure.hashing import make_fact_hash
from ..infrastructure.sqlite_cache import SqliteDedupCache
from ..infrastructure.supabase_writer import SupabaseReportWriter


@dataclass(slots=True)
class SupabasePublisher:
    cache: SqliteDedupCache
    writer: SupabaseReportWriter

    def publish(self, report: BalanceReport) -> Dict[str, Any]:
        # 1) transformar report em fatos
        facts: List[Dict[str, Any]] = []

        def emit_section(sec_name: str, section) -> None:
            for item in section.items:
                for m in section.months:
                    val = item.by_month[m].amount
                    # opcional: skip zeros para reduzir volume
                    if val == Decimal("0.00"):
                        continue

                    h = make_fact_hash(
                        competencia_ym=m.raw,   # (no seu model melhorado, raw = "YYYY-MM")
                        secao=sec_name,
                        linha=item.label,
                        valor=val,
                        workbook_path=report.source_workbook_path,
                        sheet=report.source_sheet,
                    )

                    payload = {
                        "hash": h,
                        "competencia_ym": m.raw,
                        "secao": sec_name,
                        "linha": item.label,
                        "valor": str(val),
                        "workbook_path": report.source_workbook_path,
                        "sheet": report.source_sheet,
                    }

                    # registra no cache como "seen"
                    self.cache.upsert_seen(h, payload)

        emit_section("entradas", report.entradas)
        emit_section("outras_saidas", report.outras_saidas)
        emit_section("despesas", report.despesas)

        # 2) agrega e publica agregados (sempre recalculado no python)
        total_geral = TotalsCalculator.total_geral_by_month(report)
        deficit = TotalsCalculator.deficit_superavit_by_month(report)

        aggregates: List[Dict[str, Any]] = []
        for m in report.entradas.months:
            aggregates.append(
                {
                    "competencia_ym": m.raw,
                    "total_geral": str(total_geral[m].amount),
                    "deficit_superavit": str(deficit[m].amount),
                    "workbook_path": report.source_workbook_path,
                    "sheet": report.source_sheet,
                }
            )

        # 3) envia somente os não enviados
        pending = self.cache.get_unsent(limit=5000)
        pending_rows = [payload for _, payload in pending]

        self.writer.upsert_facts(pending_rows)
        for key, _ in pending:
            self.cache.mark_sent(key, supabase_ref="upsert_ok")

        self.writer.upsert_aggregates(aggregates)

        return {
            "facts_total": len(pending_rows),
            "aggregates_total": len(aggregates),
        }