from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Iterable, List, Optional


# ============================================================
# VALUE OBJECTS
# ============================================================

@dataclass(frozen=True, slots=True)
class MonthRef:
    """
    Identificador de competência/cabeçalho.

    Produção:
    - usar sempre formato canônico "YYYY-MM" (ex.: "2025-12")
    """

    key: str  # ex: "2025-03", "2025-12"

    def __post_init__(self) -> None:
        k = (self.key or "").strip()
        if not k:
            raise ValueError("MonthRef.key não pode ser vazio.")
        object.__setattr__(self, "key", k)

    # ✅ Compatibilidade com versões antigas do código (que usam .raw)
    @property
    def raw(self) -> str:
        return self.key

    def __str__(self) -> str:
        return self.key

    # (dataclass frozen já cria hash/eq por campo, mas deixo explícito pra blindar contrato)
    def __hash__(self) -> int:
        return hash(self.key)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MonthRef):
            return False
        return self.key == other.key


@dataclass(frozen=True, slots=True)
class Money:
    """
    Valor monetário com Decimal.

    - Nunca use float.
    - Quantiza em 0.01 para consistência.
    """

    amount: Decimal

    def __post_init__(self) -> None:
        if self.amount is None:
            raise ValueError("Money.amount não pode ser None.")
        if not isinstance(self.amount, Decimal):
            raise TypeError(f"Money.amount deve ser Decimal, veio: {type(self.amount)}")
        object.__setattr__(
            self,
            "amount",
            self.amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        )

    @staticmethod
    def zero() -> Money:
        return Money(Decimal("0"))

    def __add__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        return Money(self.amount + other.amount)

    def __sub__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        return Money(self.amount - other.amount)

    def __neg__(self) -> Money:
        return Money(-self.amount)

    def abs(self) -> Money:
        return Money(abs(self.amount))

    def is_zero(self) -> bool:
        return self.amount == Decimal("0.00")


# ============================================================
# ENTITIES
# ============================================================

@dataclass(slots=True)
class LineItem:
    """
    Uma linha de uma seção (ex.: "Compras de Material...") com valores por competência.
    """

    label: str
    by_month: Dict[MonthRef, Money]
    total_excel: Optional[Money] = None  # diagnóstico (coluna M), nunca fonte de verdade

    def __post_init__(self) -> None:
        self.label = (self.label or "").strip()
        if not self.label:
            raise ValueError("LineItem.label não pode ser vazio.")
        if self.by_month is None:
            raise ValueError("LineItem.by_month não pode ser None.")
        if not isinstance(self.by_month, dict):
            raise TypeError("LineItem.by_month deve ser Dict[MonthRef, Money].")

        # Blindagem: garante tipos corretos
        for k, v in self.by_month.items():
            if not isinstance(k, MonthRef):
                raise TypeError(f"LineItem.by_month chave deve ser MonthRef, veio: {type(k)}")
            if not isinstance(v, Money):
                raise TypeError(f"LineItem.by_month valor deve ser Money, veio: {type(v)}")

        if self.total_excel is not None and not isinstance(self.total_excel, Money):
            raise TypeError("LineItem.total_excel deve ser Money ou None.")

    def value_for(self, month: MonthRef) -> Money:
        return self.by_month.get(month, Money.zero())

    def total_calc(self, months: Iterable[MonthRef]) -> Money:
        total = Money.zero()
        for m in months:
            total = total + self.value_for(m)
        return total


@dataclass(slots=True)
class LedgerSection:
    """
    Seção do balanço: Entradas, Outras Saídas/Investimento, Despesas.
    """

    name: str
    months: List[MonthRef]  # ordem importa
    items: List[LineItem]

    def __post_init__(self) -> None:
        self.name = (self.name or "").strip()
        if not self.name:
            raise ValueError("LedgerSection.name não pode ser vazio.")
        if self.months is None or len(self.months) == 0:
            raise ValueError(f"LedgerSection.months vazio para seção '{self.name}'.")
        if self.items is None:
            raise ValueError(f"LedgerSection.items não pode ser None para seção '{self.name}'.")

        # Blindagem: garante tipos corretos
        for m in self.months:
            if not isinstance(m, MonthRef):
                raise TypeError(f"LedgerSection.months deve conter MonthRef, veio: {type(m)}")
        for it in self.items:
            if not isinstance(it, LineItem):
                raise TypeError(f"LedgerSection.items deve conter LineItem, veio: {type(it)}")

        # Dedup mantendo ordem determinística
        seen = set()
        ordered: List[MonthRef] = []
        for m in self.months:
            if m.key in seen:
                continue
            seen.add(m.key)
            ordered.append(m)
        self.months = ordered

    @property
    def month_keys(self) -> List[str]:
        return [m.key for m in self.months]

    def totals_by_month(self) -> Dict[MonthRef, Money]:
        totals: Dict[MonthRef, Money] = {m: Money.zero() for m in self.months}
        for item in self.items:
            for m in self.months:
                totals[m] = totals[m] + item.value_for(m)
        return totals

    def total_calc(self) -> Money:
        t = Money.zero()
        for v in self.totals_by_month().values():
            t = t + v
        return t


# ============================================================
# AGGREGATES
# ============================================================

@dataclass(frozen=True, slots=True)
class ManualTotals:
    """
    Totais manuais preenchidos pelo usuário no Excel.
    Devem vir normalizados por MonthRef.key no adapter.
    """

    amaurilio: Dict[MonthRef, Money]
    acos_vital: Dict[MonthRef, Money]

    def __post_init__(self) -> None:
        if self.amaurilio is None or self.acos_vital is None:
            raise ValueError("ManualTotals não pode ter dicts None.")
        for k, v in self.amaurilio.items():
            if not isinstance(k, MonthRef) or not isinstance(v, Money):
                raise TypeError("ManualTotals.amaurilio deve ser Dict[MonthRef, Money].")
        for k, v in self.acos_vital.items():
            if not isinstance(k, MonthRef) or not isinstance(v, Money):
                raise TypeError("ManualTotals.acos_vital deve ser Dict[MonthRef, Money].")

    def value_amaurilio(self, month: MonthRef) -> Money:
        return self.amaurilio.get(month, Money.zero())

    def value_acos_vital(self, month: MonthRef) -> Money:
        return self.acos_vital.get(month, Money.zero())


@dataclass(frozen=True, slots=True)
class BalanceReport:
    """
    Aggregate Root.
    """

    entradas: LedgerSection
    outras_saidas: LedgerSection
    despesas: LedgerSection
    manual: ManualTotals

    # metadados de auditoria
    source_base_dir: str
    source_workbook_path: str
    source_sheet: str

    def __post_init__(self) -> None:
        if not (self.source_sheet or "").strip():
            raise ValueError("BalanceReport.source_sheet não pode ser vazio.")
        if not (self.source_workbook_path or "").strip():
            raise ValueError("BalanceReport.source_workbook_path não pode ser vazio.")
        if self.entradas.months is None or len(self.entradas.months) == 0:
            raise ValueError("BalanceReport.entradas.months vazio.")