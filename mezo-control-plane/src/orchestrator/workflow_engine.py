"""
mezo-control-plane/src/orchestrator/workflow_engine.py

Multi-step agentic workflow engine for MEZO AI.

Every step:
  1. Checks the kill switch before advancing.
  2. Routes through PermissionGuard.
  3. Updates TaskManager with live step status (SSE broadcast).
  4. On Tier.IRREVERSIBLE: pauses with BLOCKED_ON_CONFIRMATION, waits for confirmation.
  5. On failure: marks step FAILED, reports exactly which step failed, does NOT silently retry.

This replaces the previous stub that looped steps with hardcoded "success."
"""

import asyncio
import logging
from typing import Callable, Optional, Any

import src.orchestrator.kill_switch as ks_module
from src.orchestrator.kill_switch import KillSwitchDisarmedException
from src.orchestrator.task_manager import TaskManager, Task, WorkflowStep, StepStatus
from src.orchestrator.permission_guard import PermissionGuard, PluginAction, ConfirmationRequest

logger = logging.getLogger("mezo.workflow_engine")


class WorkflowEngine:
    """
    Executes a Task's WorkflowSteps sequentially through the PermissionGuard.

    Each step specifies its plugin action. The engine:
    - Updates step status live via TaskManager.
    - Pauses on Tier.IRREVERSIBLE steps for confirmation.
    - Aborts the entire workflow if the kill switch fires.
    - Never silently retries failed irreversible actions.
    """

    def __init__(
        self,
        task_manager: TaskManager,
        permission_guard: PermissionGuard,
    ):
        self._tm = task_manager
        self._guard = permission_guard

    async def run_workflow(
        self,
        task: Task,
        step_executors: list[Callable[[], Any]],
        actor_user_id: str,
        session_id: str = "",
        confirmation_callback: Optional[Callable[[ConfirmationRequest], asyncio.Future]] = None,
    ) -> bool:
        """
        Execute the workflow steps defined in task.steps.

        step_executors: list of async callables, one per step, that do the actual work.
        confirmation_callback: called for Tier.IRREVERSIBLE steps; should return an awaitable bool.

        Returns True if all steps completed successfully, False if any failed or was aborted.
        """
        if len(step_executors) != len(task.steps):
            raise ValueError(
                f"step_executors length ({len(step_executors)}) must match "
                f"task.steps length ({len(task.steps)})"
            )

        for i, (step, executor) in enumerate(zip(task.steps, step_executors)):
            # Kill switch check before every step
            try:
                ks_module.kill_switch.assert_armed()
            except KillSwitchDisarmedException as e:
                self._tm.update_step_status(
                    task, i, StepStatus.FAILED,
                    error=f"Kill switch disarmed before step could run: {e}"
                )
                # Mark remaining steps as skipped
                for j in range(i + 1, len(task.steps)):
                    self._tm.update_step_status(task, j, StepStatus.SKIPPED,
                                                error="Workflow aborted by kill switch")
                logger.warning("[WorkflowEngine] Task %s aborted by kill switch at step[%d]", task.id, i)
                return False

            # Mark step as running
            self._tm.update_step_status(task, i, StepStatus.RUNNING)

            # Build a confirmation callback that updates step status to BLOCKED first
            async def make_confirm_cb(step_idx: int, step_obj: WorkflowStep):
                async def cb(req: ConfirmationRequest) -> bool:
                    # Pause the step in BLOCKED_ON_CONFIRMATION
                    self._tm.update_step_status(
                        task, step_idx, StepStatus.BLOCKED_ON_CONFIRMATION,
                        confirmation_request={
                            "action_name": req.action_name,
                            "tier": req.tier,
                            "target": req.target,
                            "description": req.description,
                            "impact": req.impact,
                        }
                    )
                    if confirmation_callback is None:
                        return False  # no way to confirm = blocked
                    # Re-mark as running once confirmed
                    confirmed = await confirmation_callback(req)
                    if confirmed:
                        self._tm.update_step_status(task, step_idx, StepStatus.RUNNING)
                    return confirmed
                return cb

            confirm_cb = await make_confirm_cb(i, step)

            # Execute through PermissionGuard
            action = PluginAction(
                name=step.action_name,
                description=step.description,
                tier=self._guard._effective_tier(
                    PluginAction(name=step.action_name, description=step.description,
                                 tier=PluginAction.__dataclass_fields__['tier'].default if hasattr(PluginAction, '__dataclass_fields__') else __import__('src.orchestrator.permission_guard', fromlist=['Tier']).Tier.REVERSIBLE_WRITE),
                    step.args.get("target", "")
                ),
                target_description=step.description,
                requires_path_check=step.args.get("requires_path_check", False),
            )

            result = await self._guard.execute_if_permitted(
                action=action,
                actor_user_id=actor_user_id,
                target=str(step.args.get("target", step.action_name)),
                executor=executor,
                confirm_callback=confirm_cb,
                session_id=session_id,
                task_id=task.id,
            )

            if result.ok:
                self._tm.update_step_status(task, i, StepStatus.DONE, result=result.result)
            else:
                self._tm.update_step_status(
                    task, i, StepStatus.FAILED,
                    error=result.error or result.blocked_reason
                )
                # Mark remaining steps as skipped — do NOT silently retry irreversible failures
                for j in range(i + 1, len(task.steps)):
                    self._tm.update_step_status(
                        task, j, StepStatus.SKIPPED,
                        error=f"Skipped because step[{i}] '{step.name}' failed"
                    )
                logger.error(
                    "[WorkflowEngine] Task %s failed at step[%d] '%s': %s",
                    task.id, i, step.name, result.error or result.blocked_reason
                )
                return False

        return True
