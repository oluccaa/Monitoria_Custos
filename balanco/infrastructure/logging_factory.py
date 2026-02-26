from __future__ import annotations

import logging
import os
import socket
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


class ContextFilter(logging.Filter):
    """
    Injeta informações úteis em todos os logs:
    - hostname
    - pid
    """

    def __init__(self) -> None:
        super().__init__()
        self.hostname = socket.gethostname()
        self.pid = os.getpid()

    def filter(self, record: logging.LogRecord) -> bool:
        record.hostname = self.hostname
        record.pid = self.pid
        return True


def build_logger(
    name: str,
    log_dir: Path,
    *,
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
    max_bytes: int = 5 * 1024 * 1024,  # 5MB
    backup_count: int = 5,
    use_rotation: bool = True,
    utc: bool = True,
) -> logging.Logger:
    """
    Logger blindado para produção.

    Melhorias:
    - RotatingFileHandler (evita log infinito)
    - Contexto (hostname + PID)
    - Timestamp UTC opcional
    - Evita múltiplos handlers duplicados
    - Falha segura se não conseguir criar arquivo
    """

    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc if utc else None).strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"{name}_{ts}.log"

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # Evita adicionar handlers duplicados
    if logger.handlers:
        return logger

    # Formato enriquecido
    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(hostname)s | PID=%(pid)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(console_level)
    sh.setFormatter(fmt)
    sh.addFilter(ContextFilter())
    logger.addHandler(sh)

    # File handler (rotativo ou simples)
    try:
        if use_rotation:
            fh = RotatingFileHandler(
                log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
        else:
            fh = logging.FileHandler(log_file, encoding="utf-8")

        fh.setLevel(file_level)
        fh.setFormatter(fmt)
        fh.addFilter(ContextFilter())
        logger.addHandler(fh)

    except Exception as e:
        # Se falhar criação do arquivo, continua só com console
        logger.error(f"Não foi possível criar log em arquivo: {e}")

    logger.info("==============================================")
    logger.info("Sistema iniciado (logger configurado).")
    logger.info(f"Arquivo de log: {log_file.resolve()}")
    logger.info(f"Hostname: {socket.gethostname()} | PID: {os.getpid()}")
    logger.info("==============================================")

    return logger