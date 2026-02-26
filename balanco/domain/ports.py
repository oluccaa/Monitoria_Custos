from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Protocol, runtime_checkable

from .model import BalanceReport


@dataclass(frozen=True, slots=True)
class SourceSpec:
    """
    Especifica a origem do dado a ser lido.

    Melhorias:
    - slots=True (mais leve)
    - normalização/validação mínima em __post_init__
    - parâmetros opcionais para "blindagem" de ambiente
    """
    base_dir: str
    workbook_name_hint: str
    sheet_name: str

    # opcional: força somente esta aba (segurança)
    allowed_sheet_name: Optional[str] = "Balanço Anual 2025"

    # opcional: se usar UNC em produção (evita depender de Z:)
    prefer_unc_path: Optional[str] = None

    def __post_init__(self) -> None:
        bd = (self.base_dir or "").strip()
        wh = (self.workbook_name_hint or "").strip()
        sn = (self.sheet_name or "").strip()

        if not bd:
            raise ValueError("SourceSpec.base_dir não pode ser vazio.")
        if not wh:
            raise ValueError("SourceSpec.workbook_name_hint não pode ser vazio.")
        if not sn:
            raise ValueError("SourceSpec.sheet_name não pode ser vazio.")

        object.__setattr__(self, "base_dir", bd)
        object.__setattr__(self, "workbook_name_hint", wh)
        object.__setattr__(self, "sheet_name", sn)

        if self.allowed_sheet_name and sn != self.allowed_sheet_name:
            raise ValueError(
                f"Por segurança, este sistema só pode ler a aba '{self.allowed_sheet_name}'. "
                f"Recebido: '{sn}'."
            )

        if self.prefer_unc_path is not None and not str(self.prefer_unc_path).strip():
            raise ValueError("SourceSpec.prefer_unc_path se informado não pode ser vazio/whitespace.")


@runtime_checkable
class BalanceReader(Protocol):
    """
    Port (entrada): lê um BalanceReport de uma fonte (Excel/API/CSV/etc).
    """
    def read(self, spec: SourceSpec) -> BalanceReport: ...


@runtime_checkable
class ReportWriter(Protocol):
    """
    Port (saída): persiste um relatório (JSON/DB/Supabase/etc).

    Melhorias:
    - aceita Mapping (não exige dict mutável)
    - retorno é uma string com referência útil (path/URL/id)
    """
    def write(self, report: Mapping[str, Any]) -> str: ...


@runtime_checkable
class ReportRepository(Protocol):
    """
    Opcional (se você quiser separar 'writer' de 'repo'):
    - save(): persiste e retorna id/caminho
    - healthcheck(): usado no startup pra falhar cedo
    """
    def save(self, report: Mapping[str, Any]) -> str: ...
    def healthcheck(self) -> None: ...


@runtime_checkable
class Clock(Protocol):
    """
    Opcional: injeta relógio no app para testes determinísticos.
    """
    def now_iso(self) -> str: ...


@runtime_checkable
class IdGenerator(Protocol):
    """
    Opcional: injeta gerador de IDs (para idempotência / rastreio).
    """
    def new_id(self) -> str: ...


def ensure_dict(report: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Helper: garante dict mutável quando necessário.
    """
    return dict(report)