"""SQLite-backed index of run metadata for fast listing and status queries.

The JSON files in data/runs/ remain authoritative for run content.
This index caches status, timestamps, and repo_path for O(1) lookups.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

_DDL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    repo_path   TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'unknown',
    created_at  TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL DEFAULT '',
    error       TEXT
);
"""


class RunIndex:
    """Thread-safe SQLite index for run metadata."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_DDL)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def upsert(
        self,
        run_id: str,
        status: str,
        repo_path: str = "",
        created_at: str = "",
        updated_at: str = "",
        error: str | None = None,
    ) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO runs (run_id, repo_path, status, created_at, updated_at, error)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id) DO UPDATE SET
                        status     = excluded.status,
                        updated_at = excluded.updated_at,
                        error      = excluded.error
                    """,
                    (run_id, repo_path, status, created_at, updated_at, error),
                )

    def get(self, run_id: str) -> dict | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM runs WHERE run_id = ?", (run_id,)
                ).fetchone()
                return dict(row) if row else None

    def list_all(self, limit: int = 200) -> list[dict]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
                return [dict(r) for r in rows]

    def delete(self, run_id: str) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
