from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Optional
import logging


@dataclass(frozen=True, slots=True)
class StepResult:
    name: str
    seconds: float
    ok: bool
    error: Optional[str] = None


@contextmanager
def step(
    logger: logging.Logger,
    name: str,
    *,
    level_start: int = logging.INFO,
    level_ok: int = logging.INFO,
    level_fail: int = logging.ERROR,
    warn_if_seconds_gt: Optional[float] = None,
    include_perf_counter_ns: bool = False,
) -> Iterator[StepResult]:
    """
    Context manager de etapa (blindado).

    Melhorias:
    - retorna StepResult (permite coletar métricas/telemetria)
    - opcional warn por etapa lenta
    - níveis configuráveis
    - opção de usar perf_counter_ns (mais precisão)
    - logs consistentes e fáceis de grep

    Uso:
        with step(logger, "Ler Excel", warn_if_seconds_gt=1.5) as r:
            ...
        # r.ok, r.seconds etc.
    """
    logger.log(level_start, f"[START] {name}")
    t0_ns = time.perf_counter_ns()
    t0 = time.perf_counter()

    result = StepResult(name=name, seconds=0.0, ok=False)

    try:
        yield result
        if include_perf_counter_ns:
            dt = (time.perf_counter_ns() - t0_ns) / 1_000_000_000
        else:
            dt = time.perf_counter() - t0

        object.__setattr__(result, "seconds", float(dt))
        object.__setattr__(result, "ok", True)

        if warn_if_seconds_gt is not None and dt > warn_if_seconds_gt:
            logger.warning(f"[SLOW] {name} (tempo: {dt:.3f}s > {warn_if_seconds_gt:.3f}s)")
        logger.log(level_ok, f"[ OK ] {name} (tempo: {dt:.3f}s)")

    except Exception as e:
        if include_perf_counter_ns:
            dt = (time.perf_counter_ns() - t0_ns) / 1_000_000_000
        else:
            dt = time.perf_counter() - t0

        object.__setattr__(result, "seconds", float(dt))
        object.__setattr__(result, "ok", False)
        object.__setattr__(result, "error", repr(e))

        # exception() já inclui stacktrace
        logger.exception(f"[FAIL] {name} (tempo: {dt:.3f}s) erro: {e}")
        raise