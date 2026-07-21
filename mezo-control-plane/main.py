"""
mezo-control-plane/main.py

Control plane FastAPI app — adds:
  - Kill switch routes (POST /api/control/kill-switch/disarm, /arm, GET /status)
  - Task routes (GET /api/tasks, GET /api/tasks/{id}, GET /api/tasks/{id}/stream, POST /api/tasks/{id}/confirm)
  - User memory routes (GET /api/user/memory, DELETE /api/user/memory, DELETE /api/user/memory/{id})
  - Audit log route (GET /api/audit/log)
"""

import json
import asyncio
import logging
import sys
import os

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, os.path.dirname(__file__))

import src.orchestrator.kill_switch as ks_module
from src.orchestrator.task_manager import TaskManager
from src.interfaces.api import router as api_router
from src.interfaces.webhook import router as webhook_router

# Shared singletons
task_manager = TaskManager()
logger = logging.getLogger("mezo.control_plane")

app = FastAPI(title="MEZO AI Control Plane", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(webhook_router)


@app.get("/")
def read_root():
    return {
        "service": "MEZO AI Control Plane",
        "version": "2.0.0",
        "status": "running",
        "kill_switch": ks_module.kill_switch.status(),
    }


# ============================================================
# Kill Switch Routes
# ============================================================

@app.get("/api/control/kill-switch/status")
def kill_switch_status():
    return ks_module.kill_switch.status()


@app.post("/api/control/kill-switch/disarm")
def kill_switch_disarm(request: Request):
    # In production: extract actor from JWT token
    actor = request.headers.get("X-User-ID", "api-caller")
    status = ks_module.kill_switch.disarm(actor=actor)
    logger.warning("[KillSwitch] Disarmed via API by %s", actor)
    return {"message": "Kill switch DISARMED. All plugin executions are now blocked.", "status": status}


@app.post("/api/control/kill-switch/arm")
def kill_switch_arm(request: Request):
    actor = request.headers.get("X-User-ID", "api-caller")
    status = ks_module.kill_switch.arm(actor=actor)
    logger.info("[KillSwitch] Armed via API by %s", actor)
    return {"message": "Kill switch ARMED. Plugin executions are now allowed.", "status": status}


# ============================================================
# Task / Workflow Routes
# ============================================================

@app.get("/api/tasks")
def list_tasks(user_id: str = None):
    return {"tasks": task_manager.list_tasks(user_id=user_id)}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    task = task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.to_dict()


@app.get("/api/tasks/{task_id}/stream")
async def stream_task(task_id: str):
    """SSE endpoint for live per-step task status updates."""
    return StreamingResponse(
        task_manager.stream_task(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )


@app.post("/api/tasks/{task_id}/confirm")
async def confirm_step(task_id: str, request: Request):
    """
    Receives user confirmation for Tier.IRREVERSIBLE steps.
    The WorkflowEngine pauses on a Future — this resolves it.
    """
    body = await request.json()
    step_index = body.get("step_index")
    confirmed = body.get("confirmed", False)
    task = task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    # Look for the pending confirmation future on the task (set by WorkflowEngine)
    confirm_future = getattr(task, "_confirm_futures", {}).get(step_index)
    if confirm_future and not confirm_future.done():
        confirm_future.set_result(confirmed)
        return {"confirmed": confirmed, "step_index": step_index}
    return {"confirmed": False, "error": "No pending confirmation for that step"}


# ============================================================
# User Memory Routes
# ============================================================

@app.get("/api/user/memory")
async def get_user_memory(request: Request, include_sensitive: bool = False):
    from mezo_training.src.auto_learning.user_model import UserModel
    user_id = request.headers.get("X-User-ID", "default")
    model = UserModel()
    facts = await model.get_all_facts(user_id, include_sensitive=include_sensitive)
    return {"facts": facts, "user_id": user_id}


@app.delete("/api/user/memory/{fact_id}")
async def delete_memory_fact(fact_id: str, request: Request):
    from mezo_training.src.auto_learning.user_model import UserModel
    user_id = request.headers.get("X-User-ID", "default")
    model = UserModel()
    deleted = await model.delete_fact(user_id, fact_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Fact not found or already deleted")
    return {"deleted": True, "fact_id": fact_id}


@app.delete("/api/user/memory")
async def wipe_user_memory(request: Request):
    from mezo_training.src.auto_learning.user_model import UserModel
    user_id = request.headers.get("X-User-ID", "default")
    model = UserModel()
    count = await model.wipe_model(user_id)
    logger.warning("[Memory] Wiped %d facts for user %s", count, user_id)
    return {"wiped": True, "fact_count": count, "user_id": user_id}


# ============================================================
# Audit Log Routes
# ============================================================

@app.get("/api/audit/log")
async def get_audit_log(request: Request, limit: int = 100, offset: int = 0, user_id: str = None):
    from mezo_security.src.audit.audit_logger import AuditLogger
    actor = user_id or request.headers.get("X-User-ID")
    audit = AuditLogger()
    records = await audit.get_log(user_id=actor, limit=limit, offset=offset)
    return {"records": records, "limit": limit, "offset": offset}
