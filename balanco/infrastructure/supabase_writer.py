from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Mapping, Optional

from supabase import create_client


@dataclass(slots=True)
class SupabaseWriterConfig:
    url: str
    key: str  # service role no backend
    table_facts: str = "balanco_fatos"
    table_aggregates: str = "balanco_agregados"


class SupabaseReportWriter:
    """
    Persiste fatos e agregados no Supabase via upsert.
    """
    def __init__(self, cfg: SupabaseWriterConfig):
        self.cfg = cfg
        self.sb = create_client(cfg.url, cfg.key)  # :contentReference[oaicite:1]{index=1}

    def upsert_facts(self, rows: List[Dict[str, Any]]) -> str:
        if not rows:
            return "no-op"
        resp = (
            self.sb.table(self.cfg.table_facts)
            .upsert(
                rows,
                on_conflict="hash"  # sugiro UNIQUE(hash) no banco
            )
            .execute()
        )  # :contentReference[oaicite:2]{index=2}
        return "ok"

    def upsert_aggregates(self, rows: List[Dict[str, Any]]) -> str:
        if not rows:
            return "no-op"
        resp = (
            self.sb.table(self.cfg.table_aggregates)
            .upsert(
                rows,
                on_conflict="competencia_ym,workbook_path,sheet"
            )
            .execute()
        )  # :contentReference[oaicite:3]{index=3}
        return "ok"