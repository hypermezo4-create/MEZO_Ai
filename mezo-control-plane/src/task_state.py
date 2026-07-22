from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException

from src.models import StepStatus, Task, TaskStatus


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    TaskStatus.QUEUED.value: {TaskStatus.PROVISIONING.value, TaskStatus.CANCELLED.value, TaskStatus.FAILED.value},
    TaskStatus.PROVISIONING.value: {TaskStatus.PLANNING.value, TaskStatus.CANCELLED.value, TaskStatus.FAILED.value},
    TaskStatus.PLANNING.value: {TaskStatus.RUNNING.value, TaskStatus.CANCELLED.value, TaskStatus.FAILED.value},
    TaskStatus.RUNNING.value: {TaskStatus.VALIDATING.value, TaskStatus.CANCELLED.value, TaskStatus.FAILED.value},
    TaskStatus.VALIDATING.value: {TaskStatus.WAITING_FOR_APPROVAL.value, TaskStatus.CANCELLED.value, TaskStatus.FAILED.value},
    TaskStatus.WAITING_FOR_APPROVAL.value: {TaskStatus.CREATING_PULL_REQUEST.value, TaskStatus.CANCELLED.value, TaskStatus.FAILED.value},
    TaskStatus.CREATING_PULL_REQUEST.value: {TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value, TaskStatus.FAILED.value},
    TaskStatus.COMPLETED.value: set(),
    TaskStatus.FAILED.value: set(),
    TaskStatus.CANCELLED.value: set(),
}

RECOVERABLE_LEASE_STATES = {
    TaskStatus.PROVISIONING.value,
    TaskStatus.PLANNING.value,
    TaskStatus.RUNNING.value,
    TaskStatus.VALIDATING.value,
}


def transition_task(task: Task, target: str, *, error: str | None = None) -> None:
    if target == task.status:
        return
    if target not in ALLOWED_TRANSITIONS.get(task.status, set()):
        raise HTTPException(status_code=409, detail=f"Invalid task transition: {task.status} -> {target}")
    now = datetime.now(timezone.utc)
    task.status = target
    if target == TaskStatus.PROVISIONING.value and task.started_at is None:
        task.started_at = now
    if target in {TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value}:
        task.finished_at = now
    if error:
        task.error = error


def recover_expired_lease(task: Task) -> None:
    if task.status not in RECOVERABLE_LEASE_STATES:
        raise HTTPException(status_code=409, detail=f"Task in {task.status} cannot recover an expired lease")
    task.status = TaskStatus.QUEUED.value
    task.runner_id = None
    task.workspace_id = None
    task.lease_expires_at = None
    task.current_step = None
    task.error = None
    for step in task.steps:
        step.status = StepStatus.PENDING.value
        step.started_at = None
        step.finished_at = None
        step.command = None
        step.exit_code = None
        step.result_summary = None
        step.error = None
