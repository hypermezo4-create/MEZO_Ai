from __future__ import annotations

import asyncio
import io
import json
import os
import re
import secrets
import zipfile
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
import redis
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from src.open_source_db import database, now


router = APIRouter(prefix="/api")
RUNNER_TOKEN = os.getenv("RUNNER_INTERNAL_TOKEN", "")
ORCHESTRATOR_TOKEN = os.getenv("ORCHESTRATOR_INTERNAL_TOKEN", "")
APP_NAME = os.getenv("MEZO_APP_NAME", "mezo-ai")
ROUTER_URL = os.getenv("ROUTER_URL", f"http://router.process.{APP_NAME}.internal:8080").rstrip("/")
VALKEY_URL = os.getenv("VALKEY_URL", f"redis://queue.process.{APP_NAME}.internal:6379/0")

Mode = Literal["auto", "fast", "coding", "deep", "vision", "multi"]
Interaction = Literal["auto", "chat", "agent"]

EXPECTED_MACHINE_SLOTS = [
    (role, role, "mezo-ai", "performance-16x", 131072)
    for role in (
        "control", "runner-1", "runner-2", "coder-1", "coder-2",
        "reasoning", "reviewer", "vision", "utility",
    )
]

AGENT_PATTERNS = (
    r"\b(fix|implement|modify|edit|change|create|delete|remove|add|refactor|debug|patch|commit|deploy)\b",
    r"\b(run|execute)\s+(the\s+)?(tests?|commands?|build|lint|formatter)\b",
    r"\b(inspect|analy[sz]e|review|check|explain)\s+(this\s+|the\s+)?(repo|repository|project|codebase|file|module|function|readme)\b",
    r"(صلح|اصلح|عدّل|عدل|غيّر|غير|أنشئ|انشئ|احذف|أضف|اضف|نفّذ|نفذ|ارفع|انشر)",
    r"(افحص|حلل|راجع|اشرح).{0,24}(المشروع|المستودع|الكود|الملف|الدالة|README)",
    r"(شغّل|شغل|نفّذ|نفذ).{0,20}(الاختبارات|التست|الأوامر|البناء)",
)


def router_root() -> str:
    return ROUTER_URL.removesuffix("/v1")


def machine_slots(registrations: list[dict[str, Any]], router_state: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the fixed nine-slot topology, merging live Machine and model health."""
    live_by_role: dict[str, list[dict[str, Any]]] = {}
    generic_runner_position = 0
    for machine in registrations:
        normalized = dict(machine)
        role = str(normalized.get("role", ""))
        if role == "runner":
            generic_runner_position += 1
            role = f"runner-{min(generic_runner_position, 2)}"
        normalized["role"] = role
        live_by_role.setdefault(role, []).append(normalized)

    model_health = router_state.get("models", {}) if router_state.get("healthy") else {}
    model_role = {
        "coder-1": "coding",
        "coder-2": "coding",
        "reasoning": "deep",
        "reviewer": "debug",
        "vision": "vision",
        "utility": "fast",
    }
    slots = []
    role_position: dict[str, int] = {}
    for slot_id, role, app, size, memory_mb in EXPECTED_MACHINE_SLOTS:
        position = role_position.get(role, 0)
        role_position[role] = position + 1
        live = live_by_role.get(role, [])
        if position < len(live):
            registered = dict(live[position])
            registered.setdefault("app", app)
            registered.setdefault("region", "ord")
            registered.setdefault("size", size)
            registered.setdefault("memory_mb", memory_mb)
            registered["slot_id"] = slot_id
            registered["role"] = role
            slots.append(registered)
            continue
        health = model_health.get(model_role.get(role, role), {}) if isinstance(model_health, dict) else {}
        slots.append({
            "slot_id": slot_id,
            "machine_id": None,
            "role": role,
            "app": app,
            "region": "ord",
            "size": size,
            "memory_mb": memory_mb,
            "status": "online" if health.get("healthy") else "unavailable",
        })
    return slots


def queue() -> redis.Redis:
    return redis.Redis.from_url(VALKEY_URL, decode_responses=True, socket_timeout=5)


def runner_only(authorization: str | None) -> None:
    expected = f"Bearer {RUNNER_TOKEN}"
    if not RUNNER_TOKEN or not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(401, "Invalid runner credential")


def unpack(row: dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        raise HTTPException(404, "Resource not found")
    for key, fallback in (("changed_files", "[]"), ("payload", "{}"), ("reviewer_chain", "[]"), ("metadata", "{}")):
        if key in row and isinstance(row[key], str):
            row[key] = json.loads(row[key] or fallback)
    if "cancel_requested" in row:
        row["cancel_requested"] = bool(row["cancel_requested"])
    return row


def ensure_conversation(conversation_id: str | None, title: str) -> tuple[str, bool]:
    timestamp = now()
    if conversation_id:
        if database.one("SELECT id FROM conversations WHERE id=?", (conversation_id,)) is None:
            raise HTTPException(404, "Conversation not found")
        return conversation_id, False
    identifier = database.identifier()
    database.execute(
        "INSERT INTO conversations(id,title,created_at,updated_at) VALUES(?,?,?,?)",
        (identifier, title[:80] or "New conversation", timestamp, timestamp),
    )
    return identifier, True


def save_message(conversation_id: str, role: str, content: str, timestamp: str | None = None) -> dict[str, Any]:
    created_at = timestamp or now()
    database.execute(
        "INSERT INTO messages(conversation_id,role,content,created_at) VALUES(?,?,?,?)",
        (conversation_id, role, content, created_at),
    )
    database.execute("UPDATE conversations SET updated_at=? WHERE id=?", (created_at, conversation_id))
    return database.one(
        "SELECT * FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT 1",
        (conversation_id,),
    ) or {"conversation_id": conversation_id, "role": role, "content": content, "created_at": created_at}


def conversation_messages(conversation_id: str, limit: int = 40) -> list[dict[str, str]]:
    rows = database.all(
        "SELECT role,content FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?",
        (conversation_id, limit),
    )
    rows.reverse()
    return [
        {"role": str(row["role"]), "content": str(row["content"])}
        for row in rows
        if row.get("role") in {"system", "user", "assistant"}
    ]


def classify_interaction(prompt: str, project_id: str | None, requested: Interaction) -> Literal["chat", "agent"]:
    if requested != "auto":
        return requested
    if not project_id:
        return "chat"
    normalized = prompt.strip().lower()
    if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in AGENT_PATTERNS):
        return "agent"
    return "chat"


async def chat_completion(conversation_id: str, mode: Mode) -> str:
    payload = {
        "model": "local",
        "messages": conversation_messages(conversation_id),
        "temperature": 0.2,
        "mezo_mode": mode,
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(900, connect=10)) as client:
            response = await client.post(
                f"{router_root()}/v1/chat/completions",
                headers={"Authorization": f"Bearer {ORCHESTRATOR_TOKEN}"},
                json=payload,
            )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = "MEZO model request failed"
        try:
            detail = str(exc.response.json().get("detail", detail))
        except (ValueError, AttributeError):
            pass
        raise HTTPException(exc.response.status_code, detail) from exc
    except httpx.RequestError as exc:
        raise HTTPException(503, f"MEZO router unavailable: {type(exc).__name__}") from exc

    result = response.json()
    try:
        content = str(result["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise HTTPException(502, "MEZO model returned an invalid response") from exc
    if not content:
        raise HTTPException(502, "MEZO model returned an empty response")
    return content


def enqueue_task(project_id: str, prompt: str, conversation_id: str, mode: Mode) -> dict[str, Any]:
    if database.one("SELECT id FROM projects WHERE id=?", (project_id,)) is None:
        raise HTTPException(404, "Project not found")
    if len(database.all("SELECT id FROM tasks WHERE status IN ('queued','running')")) >= 4:
        raise HTTPException(409, "The four-runner task capacity is full")
    identifier, timestamp = database.identifier(), now()
    database.execute(
        "INSERT INTO tasks(id,conversation_id,project_id,prompt,mode,status,created_at) VALUES(?,?,?,?,?,?,?)",
        (identifier, conversation_id, project_id, prompt, mode, "queued", timestamp),
    )
    try:
        queue().rpush("mezo:tasks", identifier)
    except redis.RedisError as exc:
        database.execute(
            "UPDATE tasks SET status='failed',error=?,finished_at=? WHERE id=?",
            ("Queue unavailable", now(), identifier),
        )
        raise HTTPException(503, "Task queue unavailable") from exc
    database.event(identifier, "task_queued", {"mode": mode})
    return task(identifier)


class ProjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    repository_url: str = Field(min_length=10, max_length=2048)
    default_branch: str = Field(default="main", min_length=1, max_length=255)

    @field_validator("repository_url")
    @classmethod
    def public_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Use a credential-free HTTPS repository URL")
        return value.rstrip("/")


class ConversationInput(BaseModel):
    title: str = Field(default="New conversation", min_length=1, max_length=200)


class TaskInput(BaseModel):
    project_id: str
    prompt: str = Field(min_length=1, max_length=100_000)
    conversation_id: str | None = None
    mode: Mode = "auto"


class DispatchInput(BaseModel):
    prompt: str = Field(min_length=1, max_length=100_000)
    conversation_id: str | None = None
    project_id: str | None = None
    interaction: Interaction = "auto"
    mode: Mode = "auto"


class RunnerEvent(BaseModel):
    event_type: str = Field(min_length=1, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)


class TaskResult(BaseModel):
    status: Literal["completed", "failed", "cancelled"]
    changed_files: list[dict[str, Any]] = Field(default_factory=list)
    diff_text: str = Field(default="", max_length=5_000_000)
    workspace_id: str | None = None
    error: str | None = Field(default=None, max_length=20_000)
    assistant_message: str | None = Field(default=None, max_length=200_000)
    reviewer_chain: list[str] = Field(default_factory=list)


@router.get("/status")
async def status() -> dict[str, Any]:
    registrations = [unpack(row) for row in database.all("SELECT * FROM machine_registry ORDER BY role,machine_id")]
    router_state: dict[str, Any] = {"healthy": False, "models": {}}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                f"{router_root()}/cluster",
                headers={"Authorization": f"Bearer {ORCHESTRATOR_TOKEN}"},
            )
            if response.status_code == 200:
                router_state = {"healthy": True, **response.json()}
    except httpx.HTTPError:
        pass
    valkey_ok = False
    try:
        valkey_ok = bool(queue().ping())
    except redis.RedisError:
        pass
    return {
        "api": "ok", "database": "postgres", "valkey": "ok" if valkey_ok else "unavailable",
        "router": router_state, "machines": machine_slots(registrations, router_state),
        "github_configured": bool(os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_APP_ID")),
    }


@router.get("/conversations")
def conversations() -> list[dict[str, Any]]:
    return database.all("SELECT * FROM conversations ORDER BY updated_at DESC")


@router.post("/conversations", status_code=201)
def create_conversation(body: ConversationInput) -> dict[str, Any]:
    conversation_id, _ = ensure_conversation(None, body.title)
    return database.one("SELECT * FROM conversations WHERE id=?", (conversation_id,)) or {}


@router.get("/conversations/{conversation_id}/messages")
def messages(conversation_id: str) -> list[dict[str, Any]]:
    if database.one("SELECT id FROM conversations WHERE id=?", (conversation_id,)) is None:
        raise HTTPException(404, "Conversation not found")
    return database.all("SELECT * FROM messages WHERE conversation_id=? ORDER BY id", (conversation_id,))


@router.post("/dispatch", status_code=201)
async def dispatch(body: DispatchInput) -> dict[str, Any]:
    interaction = classify_interaction(body.prompt, body.project_id, body.interaction)
    if interaction == "agent" and not body.project_id:
        raise HTTPException(400, "Choose a project before running an agent task")

    conversation_id, _ = ensure_conversation(body.conversation_id, body.prompt)
    user_message = save_message(conversation_id, "user", body.prompt)

    if interaction == "agent":
        task_row = enqueue_task(body.project_id, body.prompt, conversation_id, body.mode)
        return {
            "kind": "agent",
            "interaction": interaction,
            "conversation_id": conversation_id,
            "message": user_message,
            "task": task_row,
        }

    assistant_content = await chat_completion(conversation_id, body.mode)
    assistant_message = save_message(conversation_id, "assistant", assistant_content)
    return {
        "kind": "chat",
        "interaction": interaction,
        "conversation_id": conversation_id,
        "message": assistant_message,
        "task": None,
    }


@router.get("/projects")
def projects() -> list[dict[str, Any]]:
    return database.all("SELECT * FROM projects ORDER BY created_at DESC")


@router.post("/projects", status_code=201)
def create_project(body: ProjectInput) -> dict[str, Any]:
    identifier = database.identifier()
    database.execute(
        "INSERT INTO projects(id,name,repository_url,default_branch,created_at) VALUES(?,?,?,?,?)",
        (identifier, body.name, body.repository_url, body.default_branch, now()),
    )
    return database.one("SELECT * FROM projects WHERE id=?", (identifier,)) or {}


@router.get("/tasks")
def tasks() -> list[dict[str, Any]]:
    return [unpack(row) for row in database.all("SELECT * FROM tasks ORDER BY created_at DESC LIMIT 200")]


@router.get("/tasks/{task_id}")
def task(task_id: str) -> dict[str, Any]:
    return unpack(database.one("SELECT * FROM tasks WHERE id=?", (task_id,)))


@router.post("/tasks", status_code=201)
def create_task(body: TaskInput) -> dict[str, Any]:
    conversation_id, _ = ensure_conversation(body.conversation_id, body.prompt)
    save_message(conversation_id, "user", body.prompt)
    return enqueue_task(body.project_id, body.prompt, conversation_id, body.mode)


@router.post("/tasks/{task_id}/cancel")
def cancel(task_id: str) -> dict[str, Any]:
    current = task(task_id)
    if current["status"] in {"completed", "failed", "cancelled"}:
        raise HTTPException(409, "Task is already terminal")
    database.execute("UPDATE tasks SET cancel_requested=1 WHERE id=?", (task_id,))
    try:
        queue().publish(f"mezo:cancel:{task_id}", "cancel")
    except redis.RedisError:
        pass
    database.event(task_id, "cancellation_requested", {})
    return task(task_id)


@router.post("/tasks/{task_id}/decision")
def decision(task_id: str, value: Literal["accept", "reject"] = Query(...)) -> dict[str, Any]:
    current = task(task_id)
    if current["status"] != "completed":
        raise HTTPException(409, "Only completed changes can be accepted or rejected")
    database.execute("UPDATE tasks SET decision=? WHERE id=?", (value, task_id))
    database.event(task_id, f"changes_{value}ed", {})
    return task(task_id)


@router.get("/tasks/{task_id}/patch", response_class=PlainTextResponse)
def patch(task_id: str) -> PlainTextResponse:
    current = task(task_id)
    return PlainTextResponse(current["diff_text"], headers={"Content-Disposition": f'attachment; filename="mezo-{task_id[:8]}.patch"'})


@router.get("/tasks/{task_id}/archive")
def archive(task_id: str) -> Response:
    current = task(task_id)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("changes.patch", current["diff_text"])
        bundle.writestr("changed-files.json", json.dumps(current["changed_files"], indent=2))
    return Response(buffer.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="mezo-{task_id[:8]}.zip"'})


@router.get("/tasks/{task_id}/events")
async def events(task_id: str, after: int = 0) -> StreamingResponse:
    task(task_id)

    async def stream():
        cursor = after
        while True:
            rows = database.all("SELECT * FROM task_events WHERE task_id=? AND id>? ORDER BY id LIMIT 200", (task_id, cursor))
            for row in rows:
                cursor = row["id"]
                yield f"id: {cursor}\ndata: {json.dumps(unpack(row), separators=(',', ':'))}\n\n"
            current = database.one("SELECT status FROM tasks WHERE id=?", (task_id,))
            if current and current["status"] in {"completed", "failed", "cancelled"} and not rows:
                return
            await asyncio.sleep(0.75)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.post("/runner/heartbeat")
def heartbeat(body: dict[str, Any], authorization: str | None = Header(default=None)) -> dict[str, str]:
    runner_only(authorization)
    role = str(body.get("role", "runner"))
    app_name = str(body.get("app", APP_NAME))
    database.execute(
        """INSERT INTO machine_registry(machine_id,role,app,region,size,memory_mb,status,metadata,last_heartbeat_at)
           VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(machine_id) DO UPDATE SET role=excluded.role,
           app=excluded.app,region=excluded.region,size=excluded.size,memory_mb=excluded.memory_mb,
           status=excluded.status,metadata=excluded.metadata,last_heartbeat_at=excluded.last_heartbeat_at""",
        (body["machine_id"], role, app_name, body.get("region", "unknown"), body.get("size", "performance-8x"),
         int(body.get("memory_mb", 65536)), body.get("status", "online"), json.dumps(body), now()),
    )
    return {"status": "ok"}


@router.post("/runner/lease")
def lease(runner_id: str = Query(...), authorization: str | None = Header(default=None)) -> dict[str, Any] | None:
    runner_only(authorization)
    try:
        task_id = queue().lpop("mezo:tasks")
    except redis.RedisError as exc:
        raise HTTPException(503, "Task queue unavailable") from exc
    if not task_id:
        return None
    result = database.lease(task_id, runner_id)
    return unpack(result) if result else None


@router.get("/runner/tasks/{task_id}/cancelled")
def cancelled(task_id: str, authorization: str | None = Header(default=None)) -> dict[str, bool]:
    runner_only(authorization)
    current = database.one("SELECT cancel_requested FROM tasks WHERE id=?", (task_id,))
    if current is None:
        raise HTTPException(404, "Task not found")
    return {"cancelled": bool(current["cancel_requested"])}


@router.post("/runner/tasks/{task_id}/events")
def runner_event(task_id: str, body: RunnerEvent, authorization: str | None = Header(default=None)) -> dict[str, str]:
    runner_only(authorization)
    task(task_id)
    database.event(task_id, body.event_type, body.payload)
    return {"status": "ok"}


@router.post("/runner/tasks/{task_id}/complete")
def complete(task_id: str, body: TaskResult, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    runner_only(authorization)
    current, timestamp = task(task_id), now()
    database.execute(
        "UPDATE tasks SET status=?,changed_files=?,diff_text=?,workspace_id=?,error=?,reviewer_chain=?,finished_at=? WHERE id=?",
        (body.status, json.dumps(body.changed_files), body.diff_text, body.workspace_id, body.error, json.dumps(body.reviewer_chain), timestamp, task_id),
    )
    if body.assistant_message:
        save_message(current["conversation_id"], "assistant", body.assistant_message, timestamp)
    database.event(task_id, f"task_{body.status}", {"error": body.error} if body.error else {})
    return task(task_id)
