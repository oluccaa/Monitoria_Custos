from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Optional


@dataclass(slots=True)
class JsonFileWriter:
    """
    Writer "blindado" para JSON.

    Melhorias:
    - aceita Mapping (não exige dict mutável)
    - escrita atômica (tmp + replace) => evita arquivo corrompido em queda/kill
    - nome de arquivo determinístico opcional (prefix + conteúdo hash)
    - timestamps em UTC
    - validação mínima do diretório
    """
    output_dir: Path
    filename_prefix: str = "balanco_extraido"
    indent: int = 2
    ensure_ascii: bool = False
    atomic: bool = True
    include_hash_in_filename: bool = True
    fixed_filename: Optional[str] = None  # se definido, ignora prefix/hash/timestamp

    def write(self, report: Mapping[str, Any]) -> str:
        out_dir = Path(self.output_dir)

        # Blindagem de diretório
        out_dir.mkdir(parents=True, exist_ok=True)
        if not out_dir.is_dir():
            raise NotADirectoryError(f"output_dir não é um diretório: {out_dir}")

        # Serialização (se falhar, não cria arquivo)
        payload = json.dumps(
            report,
            ensure_ascii=self.ensure_ascii,
            indent=self.indent,
            sort_keys=True,  # determinístico (bom p/ diff e auditoria)
            default=str,     # evita quebrar com Decimal/datetime/etc (melhor que explodir)
        )

        # Nome do arquivo
        if self.fixed_filename:
            filename = self.fixed_filename
        else:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            h = sha256(payload.encode("utf-8")).hexdigest()[:12] if self.include_hash_in_filename else None
            suffix = f"_{h}" if h else ""
            filename = f"{self.filename_prefix}_{ts}{suffix}.json"

        final_path = out_dir / filename

        # Escrita atômica
        if self.atomic:
            return self._atomic_write(final_path, payload)

        final_path.write_text(payload, encoding="utf-8")
        return str(final_path.resolve())

    def _atomic_write(self, final_path: Path, payload: str) -> str:
        """
        Escreve em arquivo temporário no mesmo diretório e faz replace atômico.
        """
        tmp_dir = final_path.parent
        fd, tmp_name = tempfile.mkstemp(prefix=final_path.stem + "_", suffix=".tmp", dir=str(tmp_dir))
        tmp_path = Path(tmp_name)

        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())

            tmp_path.replace(final_path)  # atômico no mesmo filesystem
            return str(final_path.resolve())
        finally:
            # limpeza se algo deu ruim antes do replace
            try:
                if tmp_path.exists() and tmp_path != final_path:
                    tmp_path.unlink()
            except Exception:
                pass