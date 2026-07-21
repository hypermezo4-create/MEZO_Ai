"""
Tests for audit_logger.py
Run: python mezo-security/tests/test_audit_logger.py
"""

import sys
import os
import asyncio
import tempfile
import shutil
import gc

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.audit.audit_logger import AuditLogger


def cleanup(tmpdir, logger=None):
    """Close all connections before removing the temp dir."""
    if logger is not None:
        try:
            # Close lingering connections
            del logger
        except Exception:
            pass
    gc.collect()
    import time; time.sleep(0.1)  # allow SQLite to release on Windows
    try:
        shutil.rmtree(tmpdir)
    except Exception:
        pass  # best-effort cleanup in tests


async def test_log_creates_record():
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmpdir, "audit.db")
        logger = AuditLogger(db_path=db_path)
        audit_id = await logger.log(
            user_id="u1",
            action_name="fs.read",
            target="/path/to/file.py",
            tier="read",
            result="success",
            session_id="s1",
        )
        assert isinstance(audit_id, str) and len(audit_id) == 36
        records = await logger.get_log(user_id="u1")
        assert len(records) == 1
        assert records[0]["action_name"] == "fs.read"
        assert records[0]["tier"] == "read"
        assert records[0]["result"] == "success"
        print("[OK] test_log_creates_record")
    finally:
        cleanup(tmpdir, logger)


async def test_log_returns_unique_ids():
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmpdir, "audit.db")
        logger = AuditLogger(db_path=db_path)
        ids = set()
        for i in range(5):
            audit_id = await logger.log(
                user_id="u1", action_name="fs.read", target=f"/file{i}.py",
                tier="read", result="success"
            )
            ids.add(audit_id)
        assert len(ids) == 5, "All audit IDs should be unique"
        print("[OK] test_log_returns_unique_ids")
    finally:
        cleanup(tmpdir, logger)


async def test_get_log_filters_by_user():
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmpdir, "audit.db")
        logger = AuditLogger(db_path=db_path)
        await logger.log(user_id="u1", action_name="fs.read", target="/a.py", tier="read", result="success")
        await logger.log(user_id="u2", action_name="fs.write", target="/b.py", tier="reversible_write", result="success")
        await logger.log(user_id="u1", action_name="fs.delete", target="/c.py", tier="irreversible", result="success_after_confirmation")

        u1_records = await logger.get_log(user_id="u1")
        assert len(u1_records) == 2
        assert all(r["user_id"] == "u1" for r in u1_records)

        u2_records = await logger.get_log(user_id="u2")
        assert len(u2_records) == 1
        print("[OK] test_get_log_filters_by_user")
    finally:
        cleanup(tmpdir, logger)


async def test_get_log_pagination():
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmpdir, "audit.db")
        logger = AuditLogger(db_path=db_path)
        for i in range(10):
            await logger.log(user_id="u1", action_name="fs.read", target=f"/file{i}.py",
                             tier="read", result="success")

        first_page = await logger.get_log(user_id="u1", limit=5, offset=0)
        second_page = await logger.get_log(user_id="u1", limit=5, offset=5)

        assert len(first_page) == 5
        assert len(second_page) == 5
        first_ids = {r["id"] for r in first_page}
        second_ids = {r["id"] for r in second_page}
        assert first_ids.isdisjoint(second_ids), "Pages should not overlap"
        print("[OK] test_get_log_pagination")
    finally:
        cleanup(tmpdir, logger)


def test_log_sync():
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmpdir, "audit.db")
        logger = AuditLogger(db_path=db_path)
        audit_id = logger.log_sync(
            user_id="u1", action_name="shell.run", target="git status",
            tier="reversible_write", result="success"
        )
        assert audit_id is not None
        print("[OK] test_log_sync")
    finally:
        cleanup(tmpdir, logger)


async def test_error_field_stored():
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmpdir, "audit.db")
        logger = AuditLogger(db_path=db_path)
        await logger.log(
            user_id="u1", action_name="docker.remove", target="container-abc",
            tier="irreversible", result="error",
            error="Container not found"
        )
        records = await logger.get_log(user_id="u1")
        assert records[0]["error"] == "Container not found"
        print("[OK] test_error_field_stored")
    finally:
        cleanup(tmpdir, logger)


if __name__ == "__main__":
    async_tests = [
        test_log_creates_record,
        test_log_returns_unique_ids,
        test_get_log_filters_by_user,
        test_get_log_pagination,
        test_error_field_stored,
    ]
    for t in async_tests:
        asyncio.run(t())
    test_log_sync()
    print(f"\n[PASS] All {len(async_tests) + 1} audit_logger tests passed!")
