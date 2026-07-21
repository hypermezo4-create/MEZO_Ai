"""
mezo-control-plane/src/orchestrator/permission_guard.py

The central gatekeeper for ALL plugin actions in MEZO AI.

Every plugin call routes through PermissionGuard.execute_if_permitted()
before any filesystem, shell, git, or docker operation runs.

Tier model:
  Tier.READ            — auto-approved, always logged
  Tier.REVERSIBLE_WRITE — auto-approved if inside allow-listed root, logged, undoable via git
  Tier.IRREVERSIBLE     — MUST block pending explicit user confirmation; never auto-execute

Design principles (from reference-audit-phase-f.md):
  - Tier is DECLARED at registration, not inferred at runtime
  - Path containment: os.path.realpath(target) must start with realpath(MEZO_ALLOWED_ROOT)
  - Kill switch checked before every execution
  - 100% audit coverage: every execution writes to AuditLogger regardless of tier or result
"""

import os
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Optional
from src.orchestrator.kill_switch import kill_switch, KillSwitchDisarmedException
from src.audit.audit_logger import AuditLogger

logger = logging.getLogger("mezo.permission_guard")

# ---------------------------------------------------------------------------
# Tier definitions
# ---------------------------------------------------------------------------

class Tier(str, Enum):
    READ = "read"
    REVERSIBLE_WRITE = "reversible_write"
    IRREVERSIBLE = "irreversible"


# ---------------------------------------------------------------------------
# PluginAction — the contract every plugin registers
# ---------------------------------------------------------------------------

@dataclass
class PluginAction:
    """
    Metadata that every plugin declares at registration time.
    Tier is hard-declared, not inferred.
    """
    name: str                        # dot-notation: "fs.read", "shell.run", "git.pr_open"
    description: str
    tier: Tier                       # declared by plugin author, not computed at runtime
    target_description: str = ""     # human-readable description of what is affected
    requires_path_check: bool = False  # True if 'target' is a filesystem path


# ---------------------------------------------------------------------------
# ExecutionResult
# ---------------------------------------------------------------------------

@dataclass
class ExecutionResult:
    ok: bool
    action_name: str
    tier: str
    target: str
    result: Any = None
    error: str = ""
    blocked_reason: str = ""
    audit_id: str = ""


# ---------------------------------------------------------------------------
# ConfirmationRequest — sent back to caller for Tier.IRREVERSIBLE actions
# ---------------------------------------------------------------------------

@dataclass
class ConfirmationRequest:
    action_name: str
    tier: str
    target: str
    description: str
    impact: str
    task_id: Optional[str] = None


# ---------------------------------------------------------------------------
# PermissionGuard
# ---------------------------------------------------------------------------

class PermissionGuard:
    """
    Central gatekeeper. All plugin actions route through execute_if_permitted().

    Usage:
        guard = PermissionGuard(audit_logger=AuditLogger(), allowed_root="/path/to/project")
        result = await guard.execute_if_permitted(
            action=PluginAction(name="fs.delete", tier=Tier.IRREVERSIBLE, ...),
            actor_user_id="user-123",
            target="/path/to/file.py",
            executor=my_delete_func,
            confirm_callback=ask_user_for_confirmation,   # only called for IRREVERSIBLE
            session_id="sess-abc",
        )
    """

    # Hard-coded tier overrides — these are IRREVERSIBLE regardless of what
    # a plugin author declares. Safety floor, not a ceiling.
    _ALWAYS_IRREVERSIBLE_PREFIXES = {
        "git.push",         # any push (force or not)
        "git.force_push",
        "git.merge_pr",
        "shell.",           # all shell actions are at minimum REVERSIBLE; some are IRREVERSIBLE
        "fs.delete",
        "docker.remove",
        "docker.prune",
        "deploy.",
        "db.drop",
    }

    # shell actions that are whitelisted stay REVERSIBLE_WRITE; unlisted shell
    # actions are escalated to IRREVERSIBLE (confirmation required)
    SHELL_WHITELIST: frozenset[str] = frozenset([
        "git status",
        "git diff",
        "git log",
        "git add",
        "git commit",
        "npm test",
        "npm run test",
        "python -m pytest",
        "pytest",
        "pip list",
        "pip show",
    ])

    def __init__(
        self,
        audit_logger: "AuditLogger",
        allowed_root: Optional[str] = None,
    ):
        self._audit = audit_logger
        self._allowed_root = (
            os.path.realpath(allowed_root)
            if allowed_root
            else os.path.realpath(os.environ.get("MEZO_ALLOWED_ROOT", "."))
        )
        logger.info("[PermissionGuard] allowed_root = %s", self._allowed_root)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def execute_if_permitted(
        self,
        action: PluginAction,
        actor_user_id: str,
        target: str,
        executor: Callable[[], Awaitable[Any]],
        confirm_callback: Optional[Callable[[ConfirmationRequest], Awaitable[bool]]] = None,
        session_id: str = "",
        task_id: Optional[str] = None,
    ) -> ExecutionResult:
        """
        The one and only entrypoint for all plugin executions.

        Flow:
          1. Check kill switch — raise immediately if disarmed.
          2. Path containment check (if action.requires_path_check).
          3. Determine effective tier (may escalate above declared tier).
          4. READ / REVERSIBLE_WRITE → execute immediately, write audit log.
          5. IRREVERSIBLE → call confirm_callback, execute only if confirmed, write audit log.
          6. All outcomes (ok / blocked / error) are written to audit log.
        """
        # --- 1. Kill switch ---
        try:
            kill_switch.assert_armed()
        except KillSwitchDisarmedException as e:
            audit_id = await self._audit.log(
                user_id=actor_user_id,
                action_name=action.name,
                target=target,
                tier=action.tier.value,
                result="blocked_kill_switch",
                error=str(e),
                session_id=session_id,
            )
            return ExecutionResult(
                ok=False,
                action_name=action.name,
                tier=action.tier.value,
                target=target,
                blocked_reason=str(e),
                audit_id=audit_id,
            )

        # --- 2. Path containment ---
        if action.requires_path_check:
            containment_error = self._check_path_containment(target)
            if containment_error:
                audit_id = await self._audit.log(
                    user_id=actor_user_id,
                    action_name=action.name,
                    target=target,
                    tier=action.tier.value,
                    result="blocked_path_containment",
                    error=containment_error,
                    session_id=session_id,
                )
                return ExecutionResult(
                    ok=False,
                    action_name=action.name,
                    tier=action.tier.value,
                    target=target,
                    blocked_reason=containment_error,
                    audit_id=audit_id,
                )

        # --- 3. Effective tier (may escalate) ---
        effective_tier = self._effective_tier(action, target)

        # --- 4 & 5. Execute based on tier ---
        if effective_tier == Tier.IRREVERSIBLE:
            return await self._execute_irreversible(
                action=action,
                effective_tier=effective_tier,
                actor_user_id=actor_user_id,
                target=target,
                executor=executor,
                confirm_callback=confirm_callback,
                session_id=session_id,
                task_id=task_id,
            )
        else:
            # READ or REVERSIBLE_WRITE — auto-approved
            return await self._execute_auto(
                action=action,
                effective_tier=effective_tier,
                actor_user_id=actor_user_id,
                target=target,
                executor=executor,
                session_id=session_id,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_path_containment(self, target: str) -> Optional[str]:
        """
        Returns an error string if target is outside the allowed root.
        Returns None if the path is safe.
        """
        try:
            real_target = os.path.realpath(os.path.abspath(target))
        except (ValueError, OSError) as e:
            return f"Cannot resolve path: {e}"

        if not real_target.startswith(self._allowed_root + os.sep) and \
           real_target != self._allowed_root:
            return (
                f"Path '{real_target}' is outside the allowed root "
                f"'{self._allowed_root}'. Expanding scope is a Tier-3 action "
                f"requiring explicit confirmation."
            )
        return None

    def _effective_tier(self, action: PluginAction, target: str) -> Tier:
        """
        Compute the effective tier. The guard may escalate above the declared
        tier but never lower it. Safety floor: certain action prefixes and
        shell commands outside the whitelist are always IRREVERSIBLE.
        """
        declared = action.tier

        # Check hard-coded IRREVERSIBLE floor
        for prefix in self._ALWAYS_IRREVERSIBLE_PREFIXES:
            if action.name.startswith(prefix):
                # Shell actions on the whitelist stay at REVERSIBLE_WRITE
                if action.name == "shell.run" and any(
                    target.startswith(cmd) for cmd in self.SHELL_WHITELIST
                ):
                    return max_tier(declared, Tier.REVERSIBLE_WRITE)
                return Tier.IRREVERSIBLE

        return declared

    async def _execute_auto(
        self,
        action: PluginAction,
        effective_tier: Tier,
        actor_user_id: str,
        target: str,
        executor: Callable,
        session_id: str,
    ) -> ExecutionResult:
        """Execute a READ or REVERSIBLE_WRITE action — no confirmation needed."""
        try:
            result = await executor()
            audit_id = await self._audit.log(
                user_id=actor_user_id,
                action_name=action.name,
                target=target,
                tier=effective_tier.value,
                result="success",
                session_id=session_id,
            )
            return ExecutionResult(
                ok=True,
                action_name=action.name,
                tier=effective_tier.value,
                target=target,
                result=result,
                audit_id=audit_id,
            )
        except Exception as e:
            audit_id = await self._audit.log(
                user_id=actor_user_id,
                action_name=action.name,
                target=target,
                tier=effective_tier.value,
                result="error",
                error=str(e),
                session_id=session_id,
            )
            return ExecutionResult(
                ok=False,
                action_name=action.name,
                tier=effective_tier.value,
                target=target,
                error=str(e),
                audit_id=audit_id,
            )

    async def _execute_irreversible(
        self,
        action: PluginAction,
        effective_tier: Tier,
        actor_user_id: str,
        target: str,
        executor: Callable,
        confirm_callback: Optional[Callable],
        session_id: str,
        task_id: Optional[str],
    ) -> ExecutionResult:
        """
        Block an IRREVERSIBLE action on user confirmation.
        If no confirm_callback is provided, reject immediately.
        """
        if confirm_callback is None:
            audit_id = await self._audit.log(
                user_id=actor_user_id,
                action_name=action.name,
                target=target,
                tier=effective_tier.value,
                result="blocked_no_confirm_callback",
                session_id=session_id,
            )
            return ExecutionResult(
                ok=False,
                action_name=action.name,
                tier=effective_tier.value,
                target=target,
                blocked_reason="Irreversible action requires a confirmation callback. None was provided.",
                audit_id=audit_id,
            )

        confirmation_req = ConfirmationRequest(
            action_name=action.name,
            tier=effective_tier.value,
            target=target,
            description=action.description,
            impact=action.target_description,
            task_id=task_id,
        )

        confirmed = await confirm_callback(confirmation_req)

        if not confirmed:
            audit_id = await self._audit.log(
                user_id=actor_user_id,
                action_name=action.name,
                target=target,
                tier=effective_tier.value,
                result="rejected_by_user",
                session_id=session_id,
            )
            return ExecutionResult(
                ok=False,
                action_name=action.name,
                tier=effective_tier.value,
                target=target,
                blocked_reason="User rejected the confirmation.",
                audit_id=audit_id,
            )

        # Confirmed — check kill switch one more time (user may have disarmed while waiting)
        try:
            kill_switch.assert_armed()
        except KillSwitchDisarmedException as e:
            audit_id = await self._audit.log(
                user_id=actor_user_id,
                action_name=action.name,
                target=target,
                tier=effective_tier.value,
                result="blocked_kill_switch_after_confirm",
                error=str(e),
                session_id=session_id,
            )
            return ExecutionResult(
                ok=False,
                action_name=action.name,
                tier=effective_tier.value,
                target=target,
                blocked_reason=str(e),
                audit_id=audit_id,
            )

        try:
            result = await executor()
            audit_id = await self._audit.log(
                user_id=actor_user_id,
                action_name=action.name,
                target=target,
                tier=effective_tier.value,
                result="success_after_confirmation",
                session_id=session_id,
            )
            return ExecutionResult(
                ok=True,
                action_name=action.name,
                tier=effective_tier.value,
                target=target,
                result=result,
                audit_id=audit_id,
            )
        except Exception as e:
            audit_id = await self._audit.log(
                user_id=actor_user_id,
                action_name=action.name,
                target=target,
                tier=effective_tier.value,
                result="error_after_confirmation",
                error=str(e),
                session_id=session_id,
            )
            return ExecutionResult(
                ok=False,
                action_name=action.name,
                tier=effective_tier.value,
                target=target,
                error=str(e),
                audit_id=audit_id,
            )


def max_tier(a: Tier, b: Tier) -> Tier:
    """Return the higher (more restrictive) of two tiers."""
    order = [Tier.READ, Tier.REVERSIBLE_WRITE, Tier.IRREVERSIBLE]
    return order[max(order.index(a), order.index(b))]
