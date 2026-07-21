"""
Tests for permission_guard.py
Run: python mezo-control-plane/tests/test_permission_guard.py
"""

import sys
import os
import asyncio
import tempfile
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'mezo-security')))

import src.orchestrator.kill_switch as ks_module
from src.orchestrator.permission_guard import (
    PermissionGuard, PluginAction, Tier, ConfirmationRequest, max_tier
)

class StubAuditLogger:
    def __init__(self):
        self.records = []

    async def log(self, **kwargs) -> str:
        self.records.append(kwargs)
        return f"audit-{len(self.records)}"


def arm_kill_switch():
    """Re-arm the module-level singleton that permission_guard actually imports."""
    ks_module.kill_switch.arm(actor="test-setup")


async def ok_executor():
    return {"data": "done"}

async def fail_executor():
    raise RuntimeError("Simulated execution failure")

async def confirm_yes(req: ConfirmationRequest) -> bool:
    return True

async def confirm_no(req: ConfirmationRequest) -> bool:
    return False


async def test_read_action_auto_approved():
    arm_kill_switch()
    tmpdir = tempfile.mkdtemp()
    try:
        audit = StubAuditLogger()
        guard = PermissionGuard(audit_logger=audit, allowed_root=tmpdir)
        action = PluginAction(name="fs.read", description="Read file", tier=Tier.READ)
        result = await guard.execute_if_permitted(
            action=action, actor_user_id="u1", target=tmpdir,
            executor=ok_executor, session_id="s1"
        )
        assert result.ok, f"READ should be auto-approved: {result}"
        assert len(audit.records) == 1
        assert audit.records[0]["result"] == "success"
        print("[OK] test_read_action_auto_approved")
    finally:
        shutil.rmtree(tmpdir)


async def test_path_outside_root_blocked():
    arm_kill_switch()
    tmpdir = tempfile.mkdtemp()
    try:
        audit = StubAuditLogger()
        guard = PermissionGuard(audit_logger=audit, allowed_root=tmpdir)
        action = PluginAction(
            name="fs.write", description="Write file", tier=Tier.REVERSIBLE_WRITE,
            requires_path_check=True
        )
        outside_path = os.path.join(os.path.dirname(tmpdir), "evil_path", "file.txt")
        result = await guard.execute_if_permitted(
            action=action, actor_user_id="u1", target=outside_path,
            executor=ok_executor, session_id="s1"
        )
        assert not result.ok
        assert "outside the allowed root" in result.blocked_reason
        assert audit.records[0]["result"] == "blocked_path_containment"
        print("[OK] test_path_outside_root_blocked")
    finally:
        shutil.rmtree(tmpdir)


async def test_irreversible_no_callback_blocked():
    arm_kill_switch()
    tmpdir = tempfile.mkdtemp()
    try:
        audit = StubAuditLogger()
        guard = PermissionGuard(audit_logger=audit, allowed_root=tmpdir)
        action = PluginAction(
            name="fs.delete", description="Delete file", tier=Tier.IRREVERSIBLE,
            requires_path_check=True
        )
        target = os.path.join(tmpdir, "file.txt")
        result = await guard.execute_if_permitted(
            action=action, actor_user_id="u1", target=target,
            executor=ok_executor, confirm_callback=None, session_id="s1"
        )
        assert not result.ok
        assert "no_confirm_callback" in audit.records[0]["result"]
        print("[OK] test_irreversible_no_callback_blocked")
    finally:
        shutil.rmtree(tmpdir)


async def test_irreversible_rejected_by_user():
    arm_kill_switch()
    tmpdir = tempfile.mkdtemp()
    try:
        audit = StubAuditLogger()
        guard = PermissionGuard(audit_logger=audit, allowed_root=tmpdir)
        action = PluginAction(
            name="fs.delete", description="Delete file", tier=Tier.IRREVERSIBLE,
            requires_path_check=True
        )
        target = os.path.join(tmpdir, "file.txt")
        result = await guard.execute_if_permitted(
            action=action, actor_user_id="u1", target=target,
            executor=ok_executor, confirm_callback=confirm_no, session_id="s1"
        )
        assert not result.ok
        assert "rejected" in result.blocked_reason.lower()
        assert audit.records[0]["result"] == "rejected_by_user"
        print("[OK] test_irreversible_rejected_by_user")
    finally:
        shutil.rmtree(tmpdir)


async def test_irreversible_confirmed_executes():
    arm_kill_switch()
    tmpdir = tempfile.mkdtemp()
    try:
        audit = StubAuditLogger()
        guard = PermissionGuard(audit_logger=audit, allowed_root=tmpdir)
        action = PluginAction(
            name="fs.delete", description="Delete file", tier=Tier.IRREVERSIBLE,
            requires_path_check=True
        )
        target = os.path.join(tmpdir, "file.txt")
        result = await guard.execute_if_permitted(
            action=action, actor_user_id="u1", target=target,
            executor=ok_executor, confirm_callback=confirm_yes, session_id="s1"
        )
        assert result.ok, f"Confirmed irreversible should execute: {result}"
        assert audit.records[0]["result"] == "success_after_confirmation"
        print("[OK] test_irreversible_confirmed_executes")
    finally:
        shutil.rmtree(tmpdir)


async def test_kill_switch_blocks_all():
    arm_kill_switch()
    tmpdir = tempfile.mkdtemp()
    try:
        ks_module.kill_switch.disarm(actor="test")
        audit = StubAuditLogger()
        guard = PermissionGuard(audit_logger=audit, allowed_root=tmpdir)
        action = PluginAction(name="fs.read", description="Read file", tier=Tier.READ)
        result = await guard.execute_if_permitted(
            action=action, actor_user_id="u1", target=tmpdir,
            executor=ok_executor, session_id="s1"
        )
        assert not result.ok, f"Expected blocked, got: {result}"
        assert "DISARMED" in result.blocked_reason
        assert audit.records[0]["result"] == "blocked_kill_switch"
        print("[OK] test_kill_switch_blocks_all")
    finally:
        ks_module.kill_switch.arm(actor="test-cleanup")
        shutil.rmtree(tmpdir)


async def test_shell_whitelist_stays_reversible():
    arm_kill_switch()
    tmpdir = tempfile.mkdtemp()
    try:
        audit = StubAuditLogger()
        guard = PermissionGuard(audit_logger=audit, allowed_root=tmpdir)
        action = PluginAction(
            name="shell.run", description="Run shell command", tier=Tier.REVERSIBLE_WRITE
        )
        effective = guard._effective_tier(action, "git status")
        assert effective == Tier.REVERSIBLE_WRITE, f"Expected REVERSIBLE_WRITE, got {effective}"
        print("[OK] test_shell_whitelist_stays_reversible")
    finally:
        shutil.rmtree(tmpdir)


async def test_shell_non_whitelist_escalated():
    arm_kill_switch()
    tmpdir = tempfile.mkdtemp()
    try:
        audit = StubAuditLogger()
        guard = PermissionGuard(audit_logger=audit, allowed_root=tmpdir)
        action = PluginAction(
            name="shell.run", description="Run shell command", tier=Tier.REVERSIBLE_WRITE
        )
        effective = guard._effective_tier(action, "rm -rf /tmp/test")
        assert effective == Tier.IRREVERSIBLE, f"Expected IRREVERSIBLE, got {effective}"
        print("[OK] test_shell_non_whitelist_escalated")
    finally:
        shutil.rmtree(tmpdir)


async def test_executor_error_in_audit():
    arm_kill_switch()
    tmpdir = tempfile.mkdtemp()
    try:
        audit = StubAuditLogger()
        guard = PermissionGuard(audit_logger=audit, allowed_root=tmpdir)
        action = PluginAction(name="fs.read", description="Read file", tier=Tier.READ)
        result = await guard.execute_if_permitted(
            action=action, actor_user_id="u1", target=tmpdir,
            executor=fail_executor, session_id="s1"
        )
        assert not result.ok
        assert "Simulated execution failure" in result.error
        assert audit.records[0]["result"] == "error"
        print("[OK] test_executor_error_in_audit")
    finally:
        shutil.rmtree(tmpdir)


async def test_max_tier():
    assert max_tier(Tier.READ, Tier.REVERSIBLE_WRITE) == Tier.REVERSIBLE_WRITE
    assert max_tier(Tier.REVERSIBLE_WRITE, Tier.IRREVERSIBLE) == Tier.IRREVERSIBLE
    assert max_tier(Tier.READ, Tier.IRREVERSIBLE) == Tier.IRREVERSIBLE
    assert max_tier(Tier.READ, Tier.READ) == Tier.READ
    print("[OK] test_max_tier")


if __name__ == "__main__":
    tests = [
        test_read_action_auto_approved,
        test_path_outside_root_blocked,
        test_irreversible_no_callback_blocked,
        test_irreversible_rejected_by_user,
        test_irreversible_confirmed_executes,
        test_kill_switch_blocks_all,
        test_shell_whitelist_stays_reversible,
        test_shell_non_whitelist_escalated,
        test_executor_error_in_audit,
        test_max_tier,
    ]
    for t in tests:
        asyncio.run(t())
    print(f"\n[PASS] All {len(tests)} permission_guard tests passed!")
