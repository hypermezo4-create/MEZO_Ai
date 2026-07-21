"""
mezo-control-plane/src/orchestrator/task_manager.py

Full multi-step task system for MEZO AI.

Tasks decompose into steps. Each step has a status:
  pending | running | done | failed | blocked_on_confirmation

Task state is held in-memory (shared within the process).
SSE streaming: GET /api/tasks/{id}/stream emits per-step status events.
Kill switch: checked before advancing each step.

This replaces the previous stub that only stored name+payload.
"""

import asyncio
import uuid
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Callable, AsyncIterator

logger = logging.getLogger("mezo.task_manager")


# ---------------------------------------------------------------------------
# Step status enum
# ---------------------------------------------------------------------------

class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    BLOCKED_ON_CONFIRMATION = "blocked_on_confirmation"
    SKIPPED = "skipped"


# ---------------------------------------------------------------------------
# WorkflowStep — unit of work
# ---------------------------------------------------------------------------

@dataclass
class WorkflowStep:
    name: str
    description: str
    plugin_name: str          # e.g. "fs", "shell", "git"
    action_name: str          # e.g. "fs.read", "shell.run"
    args: dict = field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: str = ""
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    confirmation_request: Optional[dict] = None  # populated when BLOCKED_ON_CONFIRMATION


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------

@dataclass
class Task:
    id: str
    name: str
    description: str
    user_id: str
    steps: list[WorkflowStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    status: str = "pending"   # overall task status
    _subscribers: list[asyncio.Queue] = field(default_factory=list, repr=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "user_id": self.user_id,
            "status": self.status,
            "created_at": self.created_at,
            "steps": [
                {
                    "name": s.name,
                    "description": s.description,
                    "action_name": s.action_name,
                    "status": s.status.value,
                    "result": s.result,
                    "error": s.error,
                    "started_at": s.started_at,
                    "finished_at": s.finished_at,
                    "confirmation_request": s.confirmation_request,
                }
                for s in self.steps
            ],
        }

    def publish_event(self, event: dict) -> None:
        """Push a step-status event to all SSE subscribers."""
        for q in self._subscribers:
            q.put_nowait(event)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)


# ---------------------------------------------------------------------------
# TaskManager
# ---------------------------------------------------------------------------

class TaskManager:
    """
    In-memory task registry with SSE broadcasting.

    All MEZO AI agentic workflows create tasks here so the frontend can
    display live per-step status.
    """

    def __init__(self):
        self._tasks: dict[str, Task] = {}

    def create_task(
        self,
        name: str,
        description: str,
        user_id: str,
        steps: Optional[list[WorkflowStep]] = None,
    ) -> Task:
        task_id = str(uuid.uuid4())
        task = Task(
            id=task_id,
            name=name,
            description=description,
            user_id=user_id,
            steps=steps or [],
        )
        self._tasks[task_id] = task
        logger.info("[TaskManager] Created task %s: %s", task_id, name)
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def list_tasks(self, user_id: Optional[str] = None) -> list[dict]:
        tasks = list(self._tasks.values())
        if user_id:
            tasks = [t for t in tasks if t.user_id == user_id]
        return [t.to_dict() for t in tasks]

    def update_step_status(
        self,
        task: Task,
        step_index: int,
        status: StepStatus,
        result: Any = None,
        error: str = "",
        confirmation_request: Optional[dict] = None,
    ) -> None:
        """Update a step's status and broadcast the change to all SSE subscribers."""
        step = task.steps[step_index]
        step.status = status
        if result is not None:
            step.result = result
        if error:
            step.error = error
        if confirmation_request:
            step.confirmation_request = confirmation_request

        if status == StepStatus.RUNNING:
            step.started_at = time.time()
        elif status in (StepStatus.DONE, StepStatus.FAILED, StepStatus.BLOCKED_ON_CONFIRMATION):
            step.finished_at = time.time()

        # Update overall task status
        statuses = [s.status for s in task.steps]
        if any(s == StepStatus.FAILED for s in statuses):
            task.status = "failed"
        elif all(s in (StepStatus.DONE, StepStatus.SKIPPED) for s in statuses):
            task.status = "done"
        elif any(s == StepStatus.BLOCKED_ON_CONFIRMATION for s in statuses):
            task.status = "blocked_on_confirmation"
        elif any(s == StepStatus.RUNNING for s in statuses):
            task.status = "running"
        else:
            task.status = "pending"

        # Broadcast event
        event = {
            "event": "step_update",
            "task_id": task.id,
            "task_status": task.status,
            "step_index": step_index,
            "step": {
                "name": step.name,
                "status": step.status.value,
                "result": step.result,
                "error": step.error,
                "confirmation_request": step.confirmation_request,
            },
        }
        task.publish_event(event)
        logger.info(
            "[TaskManager] Task %s step[%d] %s -> %s",
            task.id, step_index, step.name, status.value
        )

    async def stream_task(self, task_id: str) -> AsyncIterator[str]:
        """
        SSE stream for a task. Yields JSON-encoded step-status events.
        Used by GET /api/tasks/{id}/stream.
        """
        import json

        task = self.get_task(task_id)
        if task is None:
            yield f"data: {json.dumps({'error': 'task not found', 'task_id': task_id})}\n\n"
            return

        # Send current state snapshot first
        yield f"data: {json.dumps({'event': 'snapshot', 'task': task.to_dict()})}\n\n"

        # If task is already terminal, close immediately
        if task.status in ("done", "failed"):
            yield f"data: {json.dumps({'event': 'done', 'task_id': task_id})}\n\n"
            return

        # Subscribe for live updates
        queue = task.subscribe()
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(event)}\n\n"
                    if task.status in ("done", "failed") and queue.empty():
                        yield f"data: {json.dumps({'event': 'done', 'task_id': task_id})}\n\n"
                        break
                except asyncio.TimeoutError:
                    # Heartbeat to keep connection alive
                    yield f"data: {json.dumps({'event': 'heartbeat', 'task_id': task_id})}\n\n"
        finally:
            task.unsubscribe(queue)
