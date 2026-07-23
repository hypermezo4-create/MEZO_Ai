from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """Postgres store with a SQLite-only local-test fallback."""

    def __init__(self) -> None:
        self.url = os.getenv("WEB_DATABASE_URL", os.getenv("DATABASE_URL", "")).strip()
        self.sqlite_path = Path(os.getenv("MEZO_SQLITE_PATH", "/tmp/mezo-cluster-test.db"))
        self.postgres = self.url.startswith(("postgresql://", "postgres://"))
        self._write_lock = threading.Lock()

    def _sql(self, statement: str) -> str:
        return statement.replace("?", "%s") if self.postgres else statement

    @contextmanager
    def connect(self) -> Iterator[Any]:
        if self.postgres:
            import psycopg
            from psycopg.rows import dict_row
            connection = psycopg.connect(self.url, autocommit=False, row_factory=dict_row)
        else:
            self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.sqlite_path, timeout=30, check_same_thread=False)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
        finally:
            connection.close()

    def migrate(self) -> None:
        event_id = "BIGSERIAL PRIMARY KEY" if self.postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
        message_id = event_id
        ddl = f"""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
            id {message_id}, conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, repository_url TEXT NOT NULL,
            default_branch TEXT NOT NULL DEFAULT 'main', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY, conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            prompt TEXT NOT NULL, mode TEXT NOT NULL DEFAULT 'auto', status TEXT NOT NULL,
            cancel_requested INTEGER NOT NULL DEFAULT 0, changed_files TEXT NOT NULL DEFAULT '[]',
            diff_text TEXT NOT NULL DEFAULT '', workspace_id TEXT, runner_id TEXT, reviewer_chain TEXT,
            error TEXT, decision TEXT, created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT
        );
        CREATE TABLE IF NOT EXISTS task_events (
            id {event_id}, task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            event_type TEXT NOT NULL, payload TEXT NOT NULL DEFAULT '{{}}', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS machine_registry (
            machine_id TEXT PRIMARY KEY, role TEXT NOT NULL, app TEXT NOT NULL, region TEXT NOT NULL,
            size TEXT NOT NULL, memory_mb INTEGER NOT NULL, status TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{{}}', last_heartbeat_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_events (
            id {event_id}, action TEXT NOT NULL, subject TEXT, details TEXT NOT NULL DEFAULT '{{}}', created_at TEXT NOT NULL
        );
        """
        with self._write_lock, self.connect() as db:
            if self.postgres:
                with db.cursor() as cursor:
                    for statement in ddl.split(";"):
                        if statement.strip():
                            cursor.execute(statement)
            else:
                db.executescript("PRAGMA journal_mode=WAL;" + ddl)
            db.commit()

    def execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> None:
        with self._write_lock, self.connect() as db:
            db.execute(self._sql(sql), parameters)
            db.commit()

    def one(self, sql: str, parameters: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(self._sql(sql), parameters).fetchone()
        return dict(row) if row else None

    def all(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(self._sql(sql), parameters).fetchall()]

    def event(self, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        self.execute(
            "INSERT INTO task_events(task_id,event_type,payload,created_at) VALUES(?,?,?,?)",
            (task_id, event_type, json.dumps(payload, separators=(",", ":")), now()),
        )

    def lease(self, task_id: str, runner_id: str) -> dict[str, Any] | None:
        with self._write_lock, self.connect() as db:
            row = db.execute(
                self._sql("SELECT t.*,p.repository_url,p.default_branch FROM tasks t JOIN projects p ON p.id=t.project_id WHERE t.id=? AND t.status='queued' FOR UPDATE" if self.postgres else "SELECT t.*,p.repository_url,p.default_branch FROM tasks t JOIN projects p ON p.id=t.project_id WHERE t.id=? AND t.status='queued'"),
                (task_id,),
            ).fetchone()
            if not row:
                db.rollback()
                return None
            db.execute(self._sql("UPDATE tasks SET status='running',runner_id=?,started_at=? WHERE id=?"), (runner_id, now(), task_id))
            db.commit()
            return dict(row)

    @staticmethod
    def identifier() -> str:
        return uuid.uuid4().hex


database = Database()
