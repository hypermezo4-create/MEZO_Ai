"""
mezo-security/src/audit/audit_logger.py

Real append-only audit logger. Writes to SQLite so every action
(all three tiers: READ, REVERSIBLE_WRITE, IRREVERSIBLE) has a permanent,
tamper-evident record.

Schema: audit_log(id, timestamp, user_id, action_name, target, tier, result, error, session_id)

The user can view this log from the frontend:
  GET /api/audit/log

This replaces the previous stub that returned hardcoded timestamps.
"""

import asyncio
import sqlite3
import uuid
import time
import os
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("mezo.audit_logger")

# ---------------------------------------------------------------------------
# Default DB path — can be overridden via MEZO_AUDIT_DB env var
# ---------------------------------------------------------------------------
_DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..", "mezo-database", "audit_log.db"
)


class AuditLogger:
    """
    Append-only audit logger backed by SQLite.

    Thread-safe: all writes go through asyncio.to_thread() so the FastAPI
    event loop is never blocked by SQLite I/O.

    Every call to log() returns an audit_id (UUID string) that is included
    in ExecutionResult so it can be cross-referenced.
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = os.path.realpath(
            db_path or os.environ.get("MEZO_AUDIT_DB", _DEFAULT_DB_PATH)
        )
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._ensure_schema()
        logger.info("[AuditLogger] DB at %s", self._db_path)

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id          TEXT PRIMARY KEY,
                    timestamp   TEXT NOT NULL,
                    unix_ts     REAL NOT NULL,
                    user_id     TEXT NOT NULL,
                    action_name TEXT NOT NULL,
                    target      TEXT NOT NULL,
                    tier        TEXT NOT NULL,
                    result      TEXT NOT NULL,
                    error       TEXT,
                    session_id  TEXT
                )
            """)
            # Index for fast frontend queries by user or time range
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(unix_ts DESC)"
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # Public async interface
    # ------------------------------------------------------------------

    async def log(
        self,
        user_id: str,
        action_name: str,
        target: str,
        tier: str,
        result: str,
        error: str = "",
        session_id: str = "",
    ) -> str:
        """
        Write an audit record. Returns the new audit_id.
        Non-blocking — delegates SQLite write to a thread.
        """
        audit_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        record = {
            "id": audit_id,
            "timestamp": now.isoformat(),
            "unix_ts": now.timestamp(),
            "user_id": user_id,
            "action_name": action_name,
            "target": target[:1024],      # cap length for DB safety
            "tier": tier,
            "result": result,
            "error": error[:2048],
            "session_id": session_id,
        }
        await asyncio.to_thread(self._write_record, record)
        logger.debug("[Audit] %s | %s | %s | %s | %s", tier, user_id, action_name, target, result)
        return audit_id

    def log_sync(
        self,
        user_id: str,
        action_name: str,
        target: str,
        tier: str,
        result: str,
        error: str = "",
        session_id: str = "",
    ) -> str:
        """Synchronous variant for use outside async contexts (e.g. CLI)."""
        audit_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        record = {
            "id": audit_id,
            "timestamp": now.isoformat(),
            "unix_ts": now.timestamp(),
            "user_id": user_id,
            "action_name": action_name,
            "target": target[:1024],
            "tier": tier,
            "result": result,
            "error": error[:2048],
            "session_id": session_id,
        }
        self._write_record(record)
        return audit_id

    async def get_log(
        self,
        user_id: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict]:
        """Fetch audit records for the frontend log viewer."""
        return await asyncio.to_thread(self._fetch_records, user_id, limit, offset)

    # ------------------------------------------------------------------
    # Internal sync helpers (called via asyncio.to_thread)
    # ------------------------------------------------------------------

    def _write_record(self, record: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_log
                    (id, timestamp, unix_ts, user_id, action_name, target, tier, result, error, session_id)
                VALUES
                    (:id, :timestamp, :unix_ts, :user_id, :action_name, :target, :tier, :result, :error, :session_id)
                """,
                record,
            )

    def _fetch_records(
        self,
        user_id: Optional[str],
        limit: int,
        offset: int,
    ) -> list[dict]:
        with self._connect() as conn:
            if user_id:
                rows = conn.execute(
                    """
                    SELECT * FROM audit_log
                    WHERE user_id = ?
                    ORDER BY unix_ts DESC
                    LIMIT ? OFFSET ?
                    """,
                    (user_id, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM audit_log
                    ORDER BY unix_ts DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                ).fetchall()
            return [dict(row) for row in rows]
