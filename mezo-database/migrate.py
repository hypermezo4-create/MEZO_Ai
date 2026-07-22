from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg


MIGRATIONS = Path(__file__).parent / "migrations"
LOCK_ID = 6_315_069_827


def psycopg_url(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def migrate(database_url: str) -> None:
    with psycopg.connect(psycopg_url(database_url)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
            cursor.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version VARCHAR(255) PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)")
            cursor.execute("SELECT version FROM schema_migrations")
            applied = {row[0] for row in cursor.fetchall()}
            for path in sorted(MIGRATIONS.glob("*.up.sql")):
                version = path.name.removesuffix(".up.sql")
                if version in applied:
                    continue
                cursor.execute(path.read_text())
                cursor.execute("INSERT INTO schema_migrations(version) VALUES (%s)", (version,))


def rollback(database_url: str, version: str) -> None:
    down = MIGRATIONS / f"{version}.down.sql"
    if not down.exists():
        raise RuntimeError(f"No rollback migration for {version}")
    with psycopg.connect(psycopg_url(database_url)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
            cursor.execute("SELECT 1 FROM schema_migrations WHERE version = %s", (version,))
            if cursor.fetchone() is None:
                raise RuntimeError(f"Migration {version} is not applied")
            cursor.execute(down.read_text())
            cursor.execute("DELETE FROM schema_migrations WHERE version = %s", (version,))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("up", "down"))
    parser.add_argument("--version", default="001_agent_mvp")
    args = parser.parse_args()
    database_url = os.environ["DATABASE_URL"]
    migrate(database_url) if args.command == "up" else rollback(database_url, args.version)
