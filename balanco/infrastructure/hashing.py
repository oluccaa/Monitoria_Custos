from __future__ import annotations

from decimal import Decimal
from hashlib import sha256
from typing import Any


def _norm_str(s: Any) -> str:
    return str(s or "").strip().lower()


def _norm_decimal(d: Any) -> str:
    if isinstance(d, Decimal):
        # fixo 2 casas
        return format(d.quantize(Decimal("0.01")), "f")
    return str(d)


def make_fact_hash(
    *,
    competencia_ym: str,
    secao: str,
    linha: str,
    valor: Decimal,
    workbook_path: str,
    sheet: str,
) -> str:
    raw = "|".join(
        [
            _norm_str(competencia_ym),
            _norm_str(secao),
            _norm_str(linha),
            _norm_decimal(valor),
            _norm_str(workbook_path),
            _norm_str(sheet),
        ]
    )
    return sha256(raw.encode("utf-8")).hexdigest()