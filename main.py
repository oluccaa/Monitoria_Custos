from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Optional

# IMPORTANTE:
# - Ajuste o pacote para o nome real do seu projeto (ex.: Monitoria_Custos ou balanco)
# - Mantive "balanco" aqui porque foi seu exemplo original.
from balanco.application.use_cases import ExtractBalanceUseCase, UseCaseConfig, ExtractBalanceError
from balanco.domain.ports import SourceSpec
from balanco.infrastructure.excel_reader import ExcelBalanceReader
from balanco.infrastructure.json_writer import JsonFileWriter
from balanco.infrastructure.logging_factory import build_logger
from balanco.infrastructure.timer import step


@dataclass(frozen=True, slots=True)
class AppConfig:
    """
    Config centralizada para produção.
    - permite sobrepor por ENV sem mexer no código
    """
    base_dir: str
    workbook_hint: str
    sheet_name: str
    prefer_unc_path: Optional[str]
    tolerance: Decimal
    competence_prefix: Optional[str]
    fail_on_warn: bool
    fail_on_error: bool

    @staticmethod
    def from_env() -> "AppConfig":
        def env(name: str, default: str) -> str:
            return (os.getenv(name) or default).strip()

        def env_bool(name: str, default: str) -> bool:
            v = env(name, default).lower()
            return v in ("1", "true", "yes", "y", "on")

        return AppConfig(
            base_dir=env("BALANCO_BASE_DIR", r"Z:\Financeiro\Bolivia - Projeto\Larissa\2025"),
            workbook_hint=env("BALANCO_WORKBOOK_HINT", "BALANÇO - 2025 - POWERBI"),
            sheet_name=env("BALANCO_SHEET", "Balanço Anual 2025"),
            prefer_unc_path=(os.getenv("BALANCO_PREFER_UNC") or "").strip() or None,
            tolerance=Decimal(env("BALANCO_TOLERANCE", "0.01")),
            competence_prefix=(os.getenv("BALANCO_COMPETENCE_PREFIX") or "2025-").strip() or None,
            fail_on_warn=env_bool("BALANCO_FAIL_ON_WARN", "0"),
            fail_on_error=env_bool("BALANCO_FAIL_ON_ERROR", "1"),
        )


def main() -> int:
    cfg = AppConfig.from_env()

    logger = build_logger("balanco_reader", Path("./logs"))

    logger.info("Config carregada:")
    logger.info(f" - base_dir: {cfg.base_dir}")
    logger.info(f" - prefer_unc_path: {cfg.prefer_unc_path}")
    logger.info(f" - workbook_hint: {cfg.workbook_hint}")
    logger.info(f" - sheet: {cfg.sheet_name}")
    logger.info(f" - tolerance: {cfg.tolerance}")
    logger.info(f" - competence_prefix: {cfg.competence_prefix}")
    logger.info(f" - fail_on_warn: {cfg.fail_on_warn}")
    logger.info(f" - fail_on_error: {cfg.fail_on_error}")

    spec = SourceSpec(
        base_dir=cfg.base_dir,
        workbook_name_hint=cfg.workbook_hint,
        sheet_name=cfg.sheet_name,
        prefer_unc_path=cfg.prefer_unc_path,
        allowed_sheet_name="Balanço Anual 2025",  # blindagem: só esta aba
    )

    use_case = ExtractBalanceUseCase(
        reader=ExcelBalanceReader(logger=logger, default_year=2025),
        writer=JsonFileWriter(output_dir=Path("./output")),
        tolerance=cfg.tolerance,
        logger=logger,
        config=UseCaseConfig(
            competence_prefix=cfg.competence_prefix,
            fail_on_warn=cfg.fail_on_warn,
            fail_on_error=cfg.fail_on_error,
            include_section_totals=True,
            include_items_summary=True,
        ),
    )

    try:
        with step(logger, "Executar caso de uso: ExtractBalanceUseCase", warn_if_seconds_gt=10.0):
            result = use_case.execute(spec)

        out_path = result.get("meta", {}).get("output_path")
        logger.info("Execução concluída com sucesso.")
        if out_path:
            logger.info(f"Saída JSON: {out_path}")

        audit = result.get("audit", {})
        warn_count = int(audit.get("warn_count", 0) or 0)
        err_count = int(audit.get("error_count", 0) or 0)

        if warn_count or err_count:
            logger.warning(f"Issues detectadas: WARN={warn_count} ERROR={err_count}. Verifique log/JSON.")
            # Se não estiver fail-fast, ainda podemos refletir isso no exit code:
            # 0 = ok
            # 10 = warnings
            # 20 = errors
            return 20 if err_count else 10

        return 0

    except ExtractBalanceError as e:
        logger.error(f"Falha controlada do UseCase: {e}")
        return 2
    except Exception as e:
        logger.exception(f"Falha inesperada: {e}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())