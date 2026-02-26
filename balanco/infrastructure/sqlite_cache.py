from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True, slots=True)
class CacheHit:
    key: str
    first_seen_at: float
    last_seen_at: float
    sent_at: Optional[float]


class SqliteDedupCache:
    """
    Cache local para idempotência:
    - key = hash do item (PRIMARY KEY)
    - status: seen/sent
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.db_path))
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA synchronous=NORMAL;")
        con.execute("PRAGMA foreign_keys=ON;")
        return con

    def _init_db(self) -> None:
        with self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS dedup_items (
                    key TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    first_seen_at REAL NOT NULL,
                    last_seen_at REAL NOT NULL,
                    sent_at REAL NULL,
                    supabase_ref TEXT NULL
                );
                """
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_dedup_sent_at ON dedup_items(sent_at);")

    def seen(self, key: str) -> bool:
        with self._connect() as con:
            row = con.execute("SELECT key FROM dedup_items WHERE key = ?", (key,)).fetchone()
            return row is not None

    def upsert_seen(self, key: str, payload: Dict[str, Any]) -> None:
        now = time.time()
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO dedup_items (key, payload_json, first_seen_at, last_seen_at, sent_at, supabase_ref)
                VALUES (?, ?, ?, ?, NULL, NULL)
                ON CONFLICT(key) DO UPDATE SET
                    last_seen_at=excluded.last_seen_at,
                    payload_json=excluded.payload_json
                """,
                (key, payload_json, now, now),
            )

    def mark_sent(self, key: str, supabase_ref: Optional[str] = None) -> None:
        now = time.time()
        with self._connect() as con:
            con.execute(
                """
                UPDATE dedup_items
                SET sent_at=?, supabase_ref=?, last_seen_at=?
                WHERE key=?
                """,
                (now, supabase_ref, now, key),
            )

    def get_unsent(self, limit: int = 500) -> List[Tuple[str, Dict[str, Any]]]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT key, payload_json
                FROM dedup_items
                WHERE sent_at IS NULL
                ORDER BY first_seen_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        out: List[Tuple[str, Dict[str, Any]]] = []
        for key, payload_json in rows:
            out.append((key, json.loads(payload_json)))
        return out