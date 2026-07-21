"""
mezo-control-plane/src/plugins/shell_plugin.py

Whitelisted shell command execution for MEZO AI agents.
ALL actions route through PermissionGuard.

Rules:
  - Whitelisted commands: REVERSIBLE_WRITE tier (logged, captured, audited)
  - Unlisted commands: escalated to IRREVERSIBLE by PermissionGuard (confirmation required)
  - Hard-blocked patterns: never allowed regardless of whitelist (rm -rf, sudo, etc.)
  - 30s timeout (configurable via MEZO_SHELL_TIMEOUT env var)
  - stdout + stderr captured; never silently swallowed
  - No shell=True; commands are split and passed as list to subprocess
"""

import os
import re
import asyncio
import subprocess
import shlex
from typing import Optional

from src.orchestrator.permission_guard import (
    PermissionGuard, PluginAction, Tier, ExecutionResult
)

# ---------------------------------------------------------------------------
# Hard-blocked patterns — NEVER executable regardless of whitelist
# ---------------------------------------------------------------------------
_HARD_BLOCKED_PATTERNS = [
    re.compile(r"\brm\s+-[a-z]*r", re.IGNORECASE),           # rm -rf, rm -r
    re.compile(r"\bsudo\b"),                                   # privilege escalation
    re.compile(r"\bsu\s"),                                     # switch user
    re.compile(r">\s*/dev/sd"),                                # overwrite block devices
    re.compile(r"\bdd\s+if="),                                 # raw disk write
    re.compile(r"\bmkfs\b"),                                   # format filesystem
    re.compile(r"\bchmod\s+777\b"),                            # world-writable
    re.compile(r"\bcurl\b.*\|\s*(bash|sh)\b"),                 # curl | bash
    re.compile(r"\bwget\b.*-O\s*-.*\|\s*(bash|sh)\b"),        # wget | bash
]

# ---------------------------------------------------------------------------
# Whitelist (commands that stay at REVERSIBLE_WRITE tier — see permission_guard.py)
# ---------------------------------------------------------------------------
SHELL_WHITELIST = frozenset([
    "git status",
    "git diff",
    "git log",
    "git add",
    "git commit",
    "git stash",
    "npm test",
    "npm run test",
    "python -m pytest",
    "pytest",
    "pip list",
    "pip show",
])

_TIMEOUT = int(os.environ.get("MEZO_SHELL_TIMEOUT", "30"))


def _is_hard_blocked(command: str) -> Optional[str]:
    """Returns the matched pattern description if hard-blocked, else None."""
    for pattern in _HARD_BLOCKED_PATTERNS:
        if pattern.search(command):
            return pattern.pattern
    return None


def _make_action(command: str) -> PluginAction:
    """Declare tier for this command. Guard may escalate further."""
    for wl_cmd in SHELL_WHITELIST:
        if command.strip().startswith(wl_cmd):
            tier = Tier.REVERSIBLE_WRITE
            break
    else:
        tier = Tier.IRREVERSIBLE  # unlisted = always needs confirmation

    return PluginAction(
        name="shell.run",
        description=f"Run shell command: {command[:80]}",
        tier=tier,
        target_description=f"Executes: {command}",
        requires_path_check=False,
    )


class ShellPlugin:
    """
    Runs whitelisted shell commands with captured stdout/stderr.

    Usage:
        result = await shell.run(
            command="git status",
            cwd="/path/to/repo",
            actor_user_id="u1",
            confirm_callback=ask_user,   # needed for unlisted commands
        )
    """

    def __init__(self, guard: PermissionGuard):
        self._guard = guard

    async def run(
        self,
        command: str,
        cwd: str,
        actor_user_id: str,
        session_id: str = "",
        confirm_callback=None,
        task_id: Optional[str] = None,
        timeout: int = _TIMEOUT,
        env: Optional[dict] = None,
    ) -> ExecutionResult:
        """
        Execute a shell command.

        Hard-blocked commands are rejected immediately without hitting PermissionGuard.
        Unlisted commands are escalated to IRREVERSIBLE and require confirm_callback.
        All executions (success, failure, blocked) are audited.
        """
        # Hard-blocked check (happens before guard so it's never even offered for confirmation)
        blocked_pattern = _is_hard_blocked(command)
        if blocked_pattern:
            return ExecutionResult(
                ok=False,
                action_name="shell.run",
                tier=Tier.IRREVERSIBLE.value,
                target=command,
                blocked_reason=(
                    f"Command matches hard-blocked pattern and cannot be approved: "
                    f"{blocked_pattern!r}"
                ),
            )

        action = _make_action(command)

        async def _exec():
            args = shlex.split(command)
            env_merged = {**os.environ, **(env or {})}
            proc = await asyncio.create_subprocess_exec(
                *args,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env_merged,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                raise TimeoutError(
                    f"Command timed out after {timeout}s: {command!r}"
                )

            return {
                "command": command,
                "cwd": cwd,
                "returncode": proc.returncode,
                "stdout": stdout_bytes.decode("utf-8", errors="replace"),
                "stderr": stderr_bytes.decode("utf-8", errors="replace"),
                "success": proc.returncode == 0,
            }

        return await self._guard.execute_if_permitted(
            action=action,
            actor_user_id=actor_user_id,
            target=command,
            executor=_exec,
            confirm_callback=confirm_callback,
            session_id=session_id,
            task_id=task_id,
        )
