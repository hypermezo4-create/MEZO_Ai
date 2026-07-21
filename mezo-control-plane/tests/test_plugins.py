"""
Tests for filesystem_plugin.py and shell_plugin.py
Run: python mezo-control-plane/tests/test_plugins.py
"""

import sys
import os
import asyncio
import tempfile
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'mezo-security')))

import src.orchestrator.kill_switch as ks_module
from src.orchestrator.permission_guard import PermissionGuard, Tier
from src.plugins.filesystem_plugin import FilesystemPlugin
from src.plugins.shell_plugin import ShellPlugin, _is_hard_blocked, _make_action


class StubAuditLogger:
    def __init__(self):
        self.records = []
    async def log(self, **kwargs) -> str:
        self.records.append(kwargs)
        return f"audit-{len(self.records)}"


def arm():
    ks_module.kill_switch.arm(actor="test-setup")


async def confirm_yes(req) -> bool:
    return True

async def confirm_no(req) -> bool:
    return False


# ============================================================
# Filesystem Plugin Tests
# ============================================================

async def test_fs_list_dir():
    arm()
    tmpdir = tempfile.mkdtemp()
    try:
        audit = StubAuditLogger()
        guard = PermissionGuard(audit_logger=audit, allowed_root=tmpdir)
        plugin = FilesystemPlugin(guard)

        open(os.path.join(tmpdir, "test.txt"), "w").close()
        result = await plugin.list_dir(tmpdir, actor_user_id="u1", session_id="s1")
        assert result.ok, f"list_dir failed: {result}"
        assert any(e["name"] == "test.txt" for e in result.result["entries"])
        assert audit.records[0]["tier"] == "read"
        print("[OK] test_fs_list_dir")
    finally:
        shutil.rmtree(tmpdir)


async def test_fs_read_file():
    arm()
    tmpdir = tempfile.mkdtemp()
    try:
        audit = StubAuditLogger()
        guard = PermissionGuard(audit_logger=audit, allowed_root=tmpdir)
        plugin = FilesystemPlugin(guard)

        fpath = os.path.join(tmpdir, "hello.txt")
        with open(fpath, "w") as f:
            f.write("hello MEZO AI")

        result = await plugin.read_file(fpath, actor_user_id="u1")
        assert result.ok
        assert result.result["content"] == "hello MEZO AI"
        assert "sha256" in result.result
        print("[OK] test_fs_read_file")
    finally:
        shutil.rmtree(tmpdir)


async def test_fs_write_file_atomic():
    arm()
    tmpdir = tempfile.mkdtemp()
    try:
        audit = StubAuditLogger()
        guard = PermissionGuard(audit_logger=audit, allowed_root=tmpdir)
        plugin = FilesystemPlugin(guard)

        fpath = os.path.join(tmpdir, "output.py")
        result = await plugin.write_file(fpath, "print('hello')", actor_user_id="u1")
        assert result.ok, f"write_file failed: {result}"
        assert os.path.exists(fpath)
        with open(fpath) as f:
            assert f.read() == "print('hello')"
        assert "sha256" in result.result
        # No temp files left behind
        tmps = [f for f in os.listdir(tmpdir) if f.endswith(".tmp")]
        assert len(tmps) == 0, f"Temp files remain: {tmps}"
        print("[OK] test_fs_write_file_atomic")
    finally:
        shutil.rmtree(tmpdir)


async def test_fs_write_blocks_secrets():
    arm()
    tmpdir = tempfile.mkdtemp()
    try:
        audit = StubAuditLogger()
        guard = PermissionGuard(audit_logger=audit, allowed_root=tmpdir)
        plugin = FilesystemPlugin(guard)

        fpath = os.path.join(tmpdir, "bad.env")
        content_with_secret = 'API_KEY = "sk-abcdefgh1234567890abcdef"'
        result = await plugin.write_file(fpath, content_with_secret, actor_user_id="u1")
        assert not result.ok
        assert "Secret scan" in result.blocked_reason
        assert not os.path.exists(fpath), "File should not have been written"
        print("[OK] test_fs_write_blocks_secrets")
    finally:
        shutil.rmtree(tmpdir)


async def test_fs_delete_requires_confirmation():
    arm()
    tmpdir = tempfile.mkdtemp()
    try:
        audit = StubAuditLogger()
        guard = PermissionGuard(audit_logger=audit, allowed_root=tmpdir)
        plugin = FilesystemPlugin(guard)

        fpath = os.path.join(tmpdir, "deleteme.txt")
        with open(fpath, "w") as f:
            f.write("delete me")

        # Reject confirmation
        result = await plugin.delete_file(fpath, actor_user_id="u1", confirm_callback=confirm_no)
        assert not result.ok
        assert os.path.exists(fpath), "File should not be deleted when confirmation rejected"

        # Accept confirmation
        result = await plugin.delete_file(fpath, actor_user_id="u1", confirm_callback=confirm_yes)
        assert result.ok
        assert not os.path.exists(fpath), "File should be deleted after confirmation"
        print("[OK] test_fs_delete_requires_confirmation")
    finally:
        shutil.rmtree(tmpdir)


async def test_fs_path_outside_root_blocked():
    arm()
    tmpdir = tempfile.mkdtemp()
    try:
        audit = StubAuditLogger()
        guard = PermissionGuard(audit_logger=audit, allowed_root=tmpdir)
        plugin = FilesystemPlugin(guard)

        outside = os.path.join(os.path.dirname(tmpdir), "evil.txt")
        result = await plugin.read_file(outside, actor_user_id="u1")
        assert not result.ok
        assert "outside the allowed root" in result.blocked_reason
        print("[OK] test_fs_path_outside_root_blocked")
    finally:
        shutil.rmtree(tmpdir)


# ============================================================
# Shell Plugin Tests
# ============================================================

async def test_shell_hard_blocked():
    arm()
    tmpdir = tempfile.mkdtemp()
    try:
        audit = StubAuditLogger()
        guard = PermissionGuard(audit_logger=audit, allowed_root=tmpdir)
        plugin = ShellPlugin(guard)

        result = await plugin.run("rm -rf /tmp", cwd=tmpdir, actor_user_id="u1")
        assert not result.ok
        assert "hard-blocked" in result.blocked_reason
        print("[OK] test_shell_hard_blocked")
    finally:
        shutil.rmtree(tmpdir)


async def test_shell_sudo_hard_blocked():
    arm()
    tmpdir = tempfile.mkdtemp()
    try:
        audit = StubAuditLogger()
        guard = PermissionGuard(audit_logger=audit, allowed_root=tmpdir)
        plugin = ShellPlugin(guard)

        result = await plugin.run("sudo apt-get update", cwd=tmpdir, actor_user_id="u1")
        assert not result.ok
        assert "hard-blocked" in result.blocked_reason
        print("[OK] test_shell_sudo_hard_blocked")
    finally:
        shutil.rmtree(tmpdir)


async def test_shell_unlisted_needs_confirmation():
    arm()
    tmpdir = tempfile.mkdtemp()
    try:
        audit = StubAuditLogger()
        guard = PermissionGuard(audit_logger=audit, allowed_root=tmpdir)
        plugin = ShellPlugin(guard)

        # Unlisted command without confirm_callback -> blocked
        result = await plugin.run("echo hello", cwd=tmpdir, actor_user_id="u1", confirm_callback=None)
        assert not result.ok
        print("[OK] test_shell_unlisted_needs_confirmation")
    finally:
        shutil.rmtree(tmpdir)


async def test_shell_whitelisted_runs():
    arm()
    tmpdir = tempfile.mkdtemp()
    try:
        # Init a git repo so git status works
        import subprocess
        subprocess.run(["git", "init"], cwd=tmpdir, check=True, capture_output=True)

        audit = StubAuditLogger()
        guard = PermissionGuard(audit_logger=audit, allowed_root=tmpdir)
        plugin = ShellPlugin(guard)

        result = await plugin.run("git status", cwd=tmpdir, actor_user_id="u1")
        assert result.ok, f"git status failed: {result}"
        assert result.result["returncode"] == 0
        assert "branch" in result.result["stdout"].lower() or "nothing" in result.result["stdout"].lower()
        print("[OK] test_shell_whitelisted_runs")
    finally:
        shutil.rmtree(tmpdir)


def test_shell_tier_declarations():
    from src.plugins.shell_plugin import _make_action
    # Whitelisted -> REVERSIBLE_WRITE
    action = _make_action("git status")
    assert action.tier == Tier.REVERSIBLE_WRITE

    # Unlisted -> IRREVERSIBLE
    action2 = _make_action("echo hello")
    assert action2.tier == Tier.IRREVERSIBLE

    # Hard-blocked check
    assert _is_hard_blocked("rm -rf /") is not None
    assert _is_hard_blocked("sudo apt install vim") is not None
    assert _is_hard_blocked("git status") is None
    print("[OK] test_shell_tier_declarations")


if __name__ == "__main__":
    async_tests = [
        test_fs_list_dir,
        test_fs_read_file,
        test_fs_write_file_atomic,
        test_fs_write_blocks_secrets,
        test_fs_delete_requires_confirmation,
        test_fs_path_outside_root_blocked,
        test_shell_hard_blocked,
        test_shell_sudo_hard_blocked,
        test_shell_unlisted_needs_confirmation,
        test_shell_whitelisted_runs,
    ]
    for t in async_tests:
        asyncio.run(t())

    test_shell_tier_declarations()
    print(f"\n[PASS] All {len(async_tests) + 1} plugin tests passed!")
