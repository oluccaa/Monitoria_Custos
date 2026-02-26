from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

from .model import BalanceReport, LedgerSection, MonthRef, Money, LineItem


# ============================================================
# ISSUES / SEVERITY
# ============================================================

class Severity(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    severity: Severity
    message: str
    code: str = "UNSPECIFIED"          # ex: "MONTH_MISMATCH", "EXCEL_TOTAL_DIVERGENCE"
    section: str = ""                 # ex: "Despesas"
    item_label: str = ""              # ex: "Compras de Material..."
    month_key: str = ""               # ex: "2025-12" quando fizer sentido

    def as_dict(self) -> Dict[str, str]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "section": self.section,
            "item_label": self.item_label,
            "month_key": self.month_key,
        }


# ============================================================
# HELPERS
# ============================================================

def money0() -> Money:
    return Money.zero() if hasattr(Money, "zero") else Money(Decimal("0"))  # compat


def sort_months(months: Sequence[MonthRef]) -> List[MonthRef]:
    # Se MonthRef.key for "YYYY-MM", lex sort é o correto.
    key_attr = "key" if hasattr(months[0], "key") else "raw"
    return sorted(months, key=lambda m: getattr(m, key_attr, str(m)))


def month_id(m: MonthRef) -> str:
    return getattr(m, "key", None) or getattr(m, "raw", None) or str(m)


def safe_get(mapping: Mapping[MonthRef, Money], m: MonthRef) -> Money:
    return mapping.get(m, money0())


# ============================================================
# CALCULATORS
# ============================================================

class TotalsCalculator:
    """
    Regras de cálculo puras (domínio).
    - não lê Excel
    - não grava banco
    - só calcula
    """

    @staticmethod
    def line_total(months: Iterable[MonthRef], by_month: Mapping[MonthRef, Money]) -> Money:
        total = money0()
        for m in months:
            total = total + safe_get(by_month, m)
        return total

    @staticmethod
    def section_totals_by_month(section: LedgerSection, months: Sequence[MonthRef] | None = None) -> Dict[MonthRef, Money]:
        months_use = list(months) if months is not None else list(section.months)
        totals: Dict[MonthRef, Money] = {m: money0() for m in months_use}

        for item in section.items:
            for m in months_use:
                totals[m] = totals[m] + item.by_month.get(m, money0())

        return totals

    @staticmethod
    def total_geral_by_month(
        report: BalanceReport,
        months: Sequence[MonthRef] | None = None,
    ) -> Dict[MonthRef, Money]:
        months_use = list(months) if months is not None else list(report.entradas.months)

        ent = TotalsCalculator.section_totals_by_month(report.entradas, months_use)
        out = TotalsCalculator.section_totals_by_month(report.outras_saidas, months_use)
        desp = TotalsCalculator.section_totals_by_month(report.despesas, months_use)

        return {
            m: (ent.get(m, money0()) + out.get(m, money0()) + desp.get(m, money0()))
            for m in months_use
        }

    @staticmethod
    def deficit_superavit_by_month(
        report: BalanceReport,
        months: Sequence[MonthRef] | None = None,
    ) -> Dict[MonthRef, Money]:
        months_use = list(months) if months is not None else list(report.entradas.months)
        ent = TotalsCalculator.section_totals_by_month(report.entradas, months_use)

        return {
            m: (
                ent.get(m, money0())
                - report.manual.amaurilio.get(m, money0())
                - report.manual.acos_vital.get(m, money0())
            )
            for m in months_use
        }

    @staticmethod
    def total_amount(by_month: Mapping[MonthRef, Money], months: Sequence[MonthRef] | None = None) -> Money:
        total = money0()
        if months is None:
            for v in by_month.values():
                total = total + v
        else:
            for m in months:
                total = total + by_month.get(m, money0())
        return total

    @staticmethod
    def months_union(*sections: LedgerSection) -> List[MonthRef]:
        """
        União determinística de meses (útil quando Entradas/Outras/Despesas têm headers diferentes).
        """
        seen: Dict[str, MonthRef] = {}
        for sec in sections:
            for m in sec.months:
                seen.setdefault(month_id(m), m)
        # ordena pelo id
        return [seen[k] for k in sorted(seen.keys())]


# ============================================================
# VALIDATORS
# ============================================================

class BalanceValidator:
    @staticmethod
    def validate_excel_totals(section: LedgerSection, tolerance: Decimal) -> List[ValidationIssue]:
        """
        Confere divergência entre Total Excel (coluna "Total Geral") vs soma dos meses da própria seção.
        Excel NÃO é fonte de verdade; só diagnóstico.
        """
        issues: List[ValidationIssue] = []

        for item in section.items:
            if item.total_excel is None:
                continue

            calc = TotalsCalculator.line_total(section.months, item.by_month).amount
            diff = (item.total_excel.amount - calc).copy_abs()

            if diff > tolerance:
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARN,
                        code="EXCEL_TOTAL_DIVERGENCE",
                        section=section.name,
                        item_label=item.label,
                        message=(
                            f"[DIVERGÊNCIA] {section.name} | '{item.label}': "
                            f"excel={item.total_excel.amount} calc={calc} diff={diff} tol={tolerance}"
                        ),
                    )
                )

        return issues

    @staticmethod
    def validate_month_alignment(report: BalanceReport) -> List[ValidationIssue]:
        """
        Alerta quando os meses entre seções diferem do padrão (Entradas).
        Isso NÃO bloqueia, porque o cálculo pode usar união/alinhamento por chave.
        """
        issues: List[ValidationIssue] = []
        ref = [month_id(m) for m in report.entradas.months]

        def check(name: str, months: List[MonthRef]):
            other = [month_id(m) for m in months]
            if other != ref:
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARN,
                        code="MONTH_MISMATCH",
                        section=name,
                        message=f"[MESES DIFERENTES] '{name}' meses={other} vs entradas={ref}.",
                    )
                )

        check(report.outras_saidas.name, report.outras_saidas.months)
        check(report.despesas.name, report.despesas.months)
        return issues

    @staticmethod
    def validate_missing_month_values(section: LedgerSection) -> List[ValidationIssue]:
        """
        Detecta linhas que não possuem nenhuma coluna preenchida (tudo zero),
        útil para achar linhas quebradas/labels erradas.
        """
        issues: List[ValidationIssue] = []
        for item in section.items:
            total = TotalsCalculator.line_total(section.months, item.by_month)
            if total.is_zero() if hasattr(total, "is_zero") else total.amount == Decimal("0"):
                issues.append(
                    ValidationIssue(
                        severity=Severity.INFO,
                        code="LINE_TOTAL_ZERO",
                        section=section.name,
                        item_label=item.label,
                        message=f"[INFO] {section.name} | '{item.label}' total calculado é zero (verifique se era esperado).",
                    )
                )
        return issues