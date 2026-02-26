from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple, Protocol

from ..domain.ports import BalanceReader, ReportWriter, SourceSpec
from ..domain.services import TotalsCalculator, BalanceValidator, ValidationIssue
from ..domain.model import MonthRef, Money, BalanceReport


class Logger(Protocol):
    def debug(self, msg: str) -> None: ...
    def info(self, msg: str) -> None: ...
    def warning(self, msg: str) -> None: ...
    def error(self, msg: str) -> None: ...
    def exception(self, msg: str) -> None: ...


@dataclass(frozen=True)
class UseCaseConfig:
    """
    Melhorias aplicadas:
    - Ordenação determinística dos meses
    - Filtro opcional por competência (ex.: só 2025-*)
    - Modo "fail-fast" para bloquear pipeline em WARN/ERROR
    - Payload mais rico (totais por seção, checagens, contagens)
    - Evita somas implícitas com ordem arbitrária
    """
    competence_prefix: Optional[str] = "2025-"   # None => não filtra
    fail_on_warn: bool = False
    fail_on_error: bool = True
    include_section_totals: bool = True
    include_items_summary: bool = True


class ExtractBalanceError(RuntimeError):
    pass


def _severity_rank(sev: str) -> int:
    s = (sev or "").strip().upper()
    if s == "ERROR":
        return 3
    if s == "WARN":
        return 2
    if s == "INFO":
        return 1
    return 0


def _sort_monthrefs(months: Sequence[MonthRef]) -> List[MonthRef]:
    """
    Ordena de forma determinística.
    Se o MonthRef.raw for 'YYYY-MM', a ordenação lexicográfica funciona.
    Caso contrário, ainda será estável, mas recomenda-se normalizar no adapter.
    """
    return sorted(months, key=lambda m: (m.raw or ""))


def _filter_months(months: Sequence[MonthRef], prefix: Optional[str]) -> List[MonthRef]:
    if not prefix:
        return list(months)
    return [m for m in months if (m.raw or "").startswith(prefix)]


def _sum_money_by_month(by_month: Dict[MonthRef, Money], months: Sequence[MonthRef]) -> Money:
    total = Decimal("0")
    for m in months:
        total += by_month.get(m, Money(Decimal("0"))).amount
    return Money(total)


@dataclass
class ExtractBalanceUseCase:
    reader: BalanceReader
    writer: ReportWriter
    tolerance: Decimal
    logger: Optional[Logger] = None
    config: UseCaseConfig = UseCaseConfig()

    def execute(self, spec: SourceSpec) -> Dict[str, Any]:
        log = self.logger
        if log:
            log.info("UseCase iniciado: ExtractBalanceUseCase.execute()")
            log.info(f"Spec: base_dir={spec.base_dir} workbook_hint={spec.workbook_name_hint} sheet={spec.sheet_name}")

        # 1) Leitura
        try:
            report: BalanceReport = self.reader.read(spec)
        except Exception as e:
            if log:
                log.exception(f"Falha ao ler fonte (reader.read): {e}")
            raise ExtractBalanceError(f"Falha ao ler fonte: {e}") from e

        # 2) Validações
        issues: List[ValidationIssue] = []
        try:
            issues += BalanceValidator.validate_month_alignment(report)
            issues += BalanceValidator.validate_excel_totals(report.entradas, self.tolerance)
            issues += BalanceValidator.validate_excel_totals(report.outras_saidas, self.tolerance)
            issues += BalanceValidator.validate_excel_totals(report.despesas, self.tolerance)
        except Exception as e:
            if log:
                log.exception(f"Falha na validação: {e}")
            raise ExtractBalanceError(f"Falha na validação: {e}") from e

        # Ordena issues por severidade (desc) e mensagem (para ser determinístico)
        issues_sorted = sorted(
            issues,
            key=lambda i: (-_severity_rank(i.severity), (i.message or "")),
        )

        # 3) Meses canônicos do relatório (assume que adapter já normalizou p/ 'YYYY-MM')
        #    - usa referência de Entradas, mas filtra por competência se solicitado
        ref_months_all = _sort_monthrefs(report.entradas.months)
        ref_months = _filter_months(ref_months_all, self.config.competence_prefix)

        if log:
            log.info(f"Meses (ref) total={len(ref_months_all)} | filtrados={len(ref_months)} | prefix={self.config.competence_prefix}")

        # 4) Cálculos (sempre no Python, nunca confiando em Total Geral do Excel)
        try:
            total_geral_by_month_all = TotalsCalculator.total_geral_by_month(report)
            deficit_by_month_all = TotalsCalculator.deficit_superavit_by_month(report)

            # filtra por competência no payload (sem perder o total real do range filtrado)
            total_geral_by_month = {m: total_geral_by_month_all.get(m, Money(Decimal("0"))) for m in ref_months}
            deficit_by_month = {m: deficit_by_month_all.get(m, Money(Decimal("0"))) for m in ref_months}

            total_geral_calc = sum((v.amount for v in total_geral_by_month.values()), Decimal("0"))
            deficit_total = sum((v.amount for v in deficit_by_month.values()), Decimal("0"))
        except Exception as e:
            if log:
                log.exception(f"Falha no cálculo: {e}")
            raise ExtractBalanceError(f"Falha no cálculo: {e}") from e

        # 5) Totais por seção (útil pra auditoria e debug)
        section_totals: Dict[str, Any] = {}
        if self.config.include_section_totals:
            try:
                ent_tot = TotalsCalculator.section_totals_by_month(report.entradas)
                out_tot = TotalsCalculator.section_totals_by_month(report.outras_saidas)
                desp_tot = TotalsCalculator.section_totals_by_month(report.despesas)

                def pick_filtered(d: Dict[MonthRef, Money]) -> Dict[str, str]:
                    return {m.raw: str(d.get(m, Money(Decimal("0"))).amount) for m in ref_months}

                section_totals = {
                    "entradas_by_month": pick_filtered(ent_tot),
                    "outras_saidas_by_month": pick_filtered(out_tot),
                    "despesas_by_month": pick_filtered(desp_tot),
                }
            except Exception as e:
                # não derruba o processamento, mas registra
                if log:
                    log.warning(f"Não foi possível incluir totais por seção: {e}")

        # 6) Resumo de itens (quantidade de linhas por seção, etc.)
        items_summary: Dict[str, Any] = {}
        if self.config.include_items_summary:
            items_summary = {
                "entradas_items": len(report.entradas.items),
                "outras_saidas_items": len(report.outras_saidas.items),
                "despesas_items": len(report.despesas.items),
            }

        payload: Dict[str, Any] = {
            "meta": {
                "base_dir": report.source_base_dir,
                "workbook_path": report.source_workbook_path,
                "sheet": report.source_sheet,
                "tolerance": str(self.tolerance),
                "competence_prefix": self.config.competence_prefix,
                "generated_by": "ExtractBalanceUseCase",
            },
            "issues": [{"severity": i.severity, "message": i.message} for i in issues_sorted],
            "computed": {
                # Sempre ordenado por mês para previsibilidade
                "months": [m.raw for m in ref_months],
                "total_geral_by_month": {m.raw: str(total_geral_by_month[m].amount) for m in ref_months},
                "deficit_by_month": {m.raw: str(deficit_by_month[m].amount) for m in ref_months},
                "total_geral_calc": str(total_geral_calc),
                "deficit_total": str(deficit_total),
            },
            "audit": {
                **items_summary,
                **({"section_totals": section_totals} if section_totals else {}),
                "issues_count": len(issues_sorted),
                "warn_count": sum(1 for i in issues_sorted if _severity_rank(i.severity) == 2),
                "error_count": sum(1 for i in issues_sorted if _severity_rank(i.severity) == 3),
            },
        }

        # 7) Fail-fast (pipeline blindado)
        warn_count = payload["audit"]["warn_count"]
        error_count = payload["audit"]["error_count"]

        if self.config.fail_on_error and error_count > 0:
            if log:
                log.error(f"Abortando: {error_count} ERROR(s) encontrados.")
            raise ExtractBalanceError(f"Abortado por {error_count} ERROR(s). Verifique 'issues'.")

        if self.config.fail_on_warn and warn_count > 0:
            if log:
                log.error(f"Abortando: {warn_count} WARN(s) encontrados (fail_on_warn=True).")
            raise ExtractBalanceError(f"Abortado por {warn_count} WARN(s). Verifique 'issues'.")

        # 8) Persistência (writer)
        try:
            out_path = self.writer.write(payload)
        except Exception as e:
            if log:
                log.exception(f"Falha ao persistir (writer.write): {e}")
            raise ExtractBalanceError(f"Falha ao persistir: {e}") from e

        payload["meta"]["output_path"] = out_path

        if log:
            log.info(f"UseCase finalizado. output_path={out_path}")
            log.info(f"Computed: total_geral_calc={payload['computed']['total_geral_calc']} deficit_total={payload['computed']['deficit_total']}")

        return payload