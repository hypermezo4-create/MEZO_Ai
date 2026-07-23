from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
import redis
from fastapi import APIRouter, HTTPException

from src import open_source_api as core
from src.open_source_db import now


router = APIRouter(prefix="/api")
logger = logging.getLogger("mezo.runtime")


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def _project_key(row: dict[str, Any]) -> tuple[str, str]:
    repository_url = str(row.get("repository_url", "")).strip().rstrip("/").lower()
    default_branch = str(row.get("default_branch", "main")).strip().lower() or "main"
    return repository_url, default_branch


def _rollback_message(conversation_id: str, created: bool, message: dict[str, Any] | None) -> None:
    try:
        if created:
            core.database.execute("DELETE FROM conversations WHERE id=?", (conversation_id,))
            return

        message_id = message.get("id") if message else None
        if message_id is not None:
            core.database.execute(
                "DELETE FROM messages WHERE id=? AND conversation_id=?",
                (message_id, conversation_id),
            )
        latest = core.database.one(
            "SELECT MAX(created_at) AS updated_at FROM messages WHERE conversation_id=?",
            (conversation_id,),
        )
        if latest and latest.get("updated_at"):
            core.database.execute(
                "UPDATE conversations SET updated_at=? WHERE id=?",
                (latest["updated_at"], conversation_id),
            )
        else:
            core.database.execute(
                "UPDATE conversations SET updated_at=created_at WHERE id=?",
                (conversation_id,),
            )
    except Exception:
        logger.exception("Failed to roll back unsuccessful dispatch for conversation %s", conversation_id)


def _enqueue_task(project_id: str, prompt: str, conversation_id: str, mode: core.Mode) -> dict[str, Any]:
    if core.database.one("SELECT id FROM projects WHERE id=?", (project_id,)) is None:
        raise HTTPException(404, "Project not found")

    capacity = _env_int("MEZO_MAX_CONCURRENT_TASKS", 4, 1, 20)
    active = core.database.all("SELECT id FROM tasks WHERE status IN ('queued','running')")
    if len(active) >= capacity:
        raise HTTPException(409, f"MEZO task capacity is full ({capacity})")

    identifier, timestamp = core.database.identifier(), now()
    core.database.execute(
        "INSERT INTO tasks(id,conversation_id,project_id,prompt,mode,status,created_at) VALUES(?,?,?,?,?,?,?)",
        (identifier, conversation_id, project_id, prompt, mode, "queued", timestamp),
    )
    try:
        core.queue().rpush("mezo:tasks", identifier)
    except redis.RedisError as exc:
        core.database.execute("DELETE FROM tasks WHERE id=?", (identifier,))
        raise HTTPException(503, "Task queue unavailable") from exc

    try:
        core.database.event(identifier, "task_queued", {"mode": mode})
    except Exception:
        logger.exception("Task %s was queued but its audit event could not be written", identifier)
    return core.task(identifier)


def _register_control() -> None:
    machine_id = os.getenv("FLY_MACHINE_ID", "").strip()
    if not machine_id:
        return
    metadata = {
        "machine_id": machine_id,
        "role": "control",
        "status": "online",
        "version": "2.2.0-runtime",
        "services": ["api", "router", "indexer", "valkey"],
    }
    core.database.execute(
        """INSERT INTO machine_registry(machine_id,role,app,region,size,memory_mb,status,metadata,last_heartbeat_at)
           VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(machine_id) DO UPDATE SET role=excluded.role,
           app=excluded.app,region=excluded.region,size=excluded.size,memory_mb=excluded.memory_mb,
           status=excluded.status,metadata=excluded.metadata,last_heartbeat_at=excluded.last_heartbeat_at""",
        (
            machine_id,
            "control",
            core.APP_NAME,
            os.getenv("FLY_REGION", "ord"),
            os.getenv("MEZO_MACHINE_SIZE", "performance-16x"),
            _env_int("MEZO_MACHINE_MEMORY_MB", 131072, 1024, 1048576),
            "online",
            json.dumps(metadata, separators=(",", ":")),
            now(),
        ),
    )


@router.get("/status")
async def status() -> dict[str, Any]:
    _register_control()
    registrations = [
        core.unpack(row)
        for row in core.database.all("SELECT * FROM machine_registry ORDER BY role,machine_id")
    ]
    router_state: dict[str, Any] = {
        "reachable": False,
        "healthy": False,
        "models": {},
    }
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                f"{core.router_root()}/cluster",
                headers={"Authorization": f"Bearer {core.ORCHESTRATOR_TOKEN}"},
            )
        if response.status_code == 200:
            payload = response.json()
            router_state = {
                **payload,
                "reachable": True,
                "healthy": bool(payload.get("healthy")),
            }
        else:
            router_state["error"] = f"HTTP {response.status_code}"
    except (httpx.HTTPError, ValueError) as exc:
        router_state["error"] = type(exc).__name__

    valkey_ok = False
    try:
        valkey_ok = bool(core.queue().ping())
    except redis.RedisError:
        pass

    slots = core.machine_slots(registrations, router_state)
    control_slot = next((slot for slot in slots if slot.get("slot_id") == "control"), None)
    if control_slot is not None:
        control_slot["status"] = "online"
        control_slot["machine_id"] = control_slot.get("machine_id") or os.getenv("FLY_MACHINE_ID") or None

    configured_count = sum(
        bool(slot.get("machine_id")) or slot.get("status") in {"online", "busy"}
        for slot in slots
    )
    return {
        "api": "ok",
        "database": "postgres" if core.database.postgres else "sqlite",
        "valkey": "ok" if valkey_ok else "unavailable",
        "router": router_state,
        "machines": slots,
        "configured_machine_count": configured_count,
        "core_machine_count": len(core.EXPECTED_MACHINE_SLOTS),
        "max_machine_count": _env_int("MEZO_MAX_MACHINES", 20, len(core.EXPECTED_MACHINE_SLOTS), 20),
        "max_concurrent_tasks": _env_int("MEZO_MAX_CONCURRENT_TASKS", 4, 1, 20),
        "github_configured": bool(os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_APP_ID")),
    }


@router.get("/conversations")
def conversations() -> list[dict[str, Any]]:
    return core.database.all(
        """SELECT c.* FROM conversations c
           WHERE EXISTS (
               SELECT 1 FROM messages m
               WHERE m.conversation_id=c.id AND m.role='assistant'
           ) OR EXISTS (
               SELECT 1 FROM tasks t WHERE t.conversation_id=c.id
           )
           ORDER BY c.updated_at DESC"""
    )


@router.post("/dispatch", status_code=201)
async def dispatch(body: core.DispatchInput) -> dict[str, Any]:
    interaction = core.classify_interaction(body.prompt, body.project_id, body.interaction)
    if interaction == "agent" and not body.project_id:
        raise HTTPException(400, "Choose a project before running an agent task")

    conversation_id, created = core.ensure_conversation(body.conversation_id, body.prompt)
    user_message = core.save_message(conversation_id, "user", body.prompt)
    try:
        if interaction == "agent":
            task_row = _enqueue_task(
                str(body.project_id),
                body.prompt,
                conversation_id,
                body.mode,
            )
            return {
                "kind": "agent",
                "interaction": interaction,
                "conversation_id": conversation_id,
                "message": user_message,
                "task": task_row,
            }

        assistant_content = await core.chat_completion(conversation_id, body.mode)
        assistant_message = core.save_message(conversation_id, "assistant", assistant_content)
        return {
            "kind": "chat",
            "interaction": interaction,
            "conversation_id": conversation_id,
            "message": assistant_message,
            "task": None,
        }
    except Exception:
        _rollback_message(conversation_id, created, user_message)
        raise


@router.get("/projects")
def projects() -> list[dict[str, Any]]:
    rows = core.database.all("SELECT * FROM projects ORDER BY created_at DESC")
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = _project_key(row)
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


@router.post("/projects", status_code=201)
def create_project(body: core.ProjectInput) -> dict[str, Any]:
    existing = core.database.all(
        "SELECT * FROM projects WHERE repository_url=? ORDER BY created_at DESC",
        (body.repository_url,),
    )
    requested_key = (body.repository_url.lower(), body.default_branch.strip().lower())
    for row in existing:
        if _project_key(row) == requested_key:
            return row

    identifier = core.database.identifier()
    core.database.execute(
        "INSERT INTO projects(id,name,repository_url,default_branch,created_at) VALUES(?,?,?,?,?)",
        (identifier, body.name, body.repository_url, body.default_branch, now()),
    )
    return core.database.one("SELECT * FROM projects WHERE id=?", (identifier,)) or {}
