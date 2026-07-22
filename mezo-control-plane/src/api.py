from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from src.audit import append_audit, verify_audit_chain
from src.config import get_settings
from src.database import SessionLocal, get_db
from src.github_app import GitHubAppClient, GitHubAppError
from src.models import (
    Approval,
    ApprovalState,
    AuditLog,
    Project,
    ProviderConfig,
    Repository,
    Role,
    Runner,
    StepStatus,
    SystemSetting,
    Task,
    TaskEvent,
    TaskStatus,
    TaskStep,
    User,
    utcnow,
)
from src.providers import ProviderError, ProviderRouter
from src.redaction import redact
from src.schemas import (
    AnalysisComplete,
    ApprovalDecision,
    BootstrapRequest,
    BranchPushed,
    LoginRequest,
    ProjectCreate,
    ProjectView,
    ProviderUpdate,
    ProviderGenerate,
    RepositoryCreate,
    RepositoryView,
    RunnerEvent,
    RunnerHeartbeat,
    RunnerRegister,
    StepUpdate,
    TaskCreate,
    TaskTransitionRequest,
    TaskView,
    TokenResponse,
    UserView,
    UserCreate,
)
from src.security import (
    get_current_runner,
    get_current_user,
    hash_password,
    hash_runner_token,
    issue_access_token,
    new_runner_token,
    require_roles,
    verify_password,
)
from src.task_state import recover_expired_lease, transition_task


router = APIRouter(prefix="/api")
logger = logging.getLogger("mezo.task")
STEP_DEFINITIONS = (
    ("workspace", "Create and verify the isolated workspace", False),
    ("clone", "Clone the authorized repository and create the working branch", False),
    ("instructions", "Read repository instructions and inspect project structure", False),
    ("plan", "Generate a bounded execution plan", False),
    ("implementation", "Run Kilo inside the isolated workspace", False),
    ("validation", "Run repository lint, type checks, and tests", False),
    ("guards", "Run clean-code-guard and conditional test/docs guards", False),
    ("approval", "Wait for approval bound to the validated diff", True),
    ("draft_pull_request", "Push the working branch and create a Draft Pull Request", True),
)


def request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def add_event(db: Session, task_id: str, event_type: str, payload: dict[str, Any], stream: str | None = None) -> None:
    db.add(TaskEvent(task_id=task_id, event_type=event_type, stream=stream, payload=redact(payload)))


def task_for_user(db: Session, task_id: str, user: User) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if user.role != Role.OWNER.value and task.user_id != user.id:
        raise HTTPException(status_code=403, detail="Task is not accessible")
    return task


def runner_task(db: Session, task_id: str, runner: Runner) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.runner_id != runner.id:
        raise HTTPException(status_code=403, detail="Task is leased to another runner")
    return task


def approval_snapshot(task: Task) -> dict[str, Any]:
    report = task.validation_report or {}
    return {
        "repository": task.repository,
        "base_branch": task.base_branch,
        "working_branch": task.working_branch,
        "changed_files": task.changed_files,
        "diff_hash": task.diff_hash,
        "commit_sha": task.commit_sha,
        "diff_summary": report.get("diff_summary"),
        "commands": report.get("commands", []),
        "tests": report.get("tests", []),
        "guards": report.get("guards", []),
        "known_risks": report.get("known_risks", []),
        "pull_request_title": task.pull_request_title,
        "pull_request_body": task.pull_request_body,
    }


def checks_passed(report: dict[str, Any], changed_files: list[dict[str, Any]] | None = None) -> bool:
    commands = report.get("commands")
    guards = report.get("guards")
    if not isinstance(commands, list) or not commands:
        return False
    if any(item.get("exit_code") != 0 for item in commands):
        return False
    if not isinstance(guards, list) or not any(
        item.get("name") == "clean-code-guard" and item.get("status") == "passed" for item in guards
    ):
        return False
    if not all(item.get("status") in {"passed", "skipped_not_applicable"} for item in guards):
        return False
    paths = [str(item.get("path", "")).lower() for item in (changed_files or [])]
    required = set()
    if any("/tests/" in f"/{path}" or re.search(r"(?:test_|_test\.|\.test\.|\.spec\.)", path) for path in paths):
        required.add("test-guard")
    if any(path.endswith((".md", ".mdx", ".rst")) or path.startswith("docs/") for path in paths):
        required.add("docs-guard")
    return all(any(item.get("name") == name and item.get("status") == "passed" for item in guards) for name in required)


def is_expired(value: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value <= utcnow()


@router.post("/auth/bootstrap", response_model=TokenResponse, status_code=201)
def bootstrap_owner(
    body: BootstrapRequest,
    request: Request,
    x_mezo_bootstrap_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    if db.query(User).count() != 0:
        raise HTTPException(status_code=409, detail="Bootstrap has already completed")
    if not x_mezo_bootstrap_token or not secrets.compare_digest(x_mezo_bootstrap_token, get_settings().bootstrap_token):
        raise HTTPException(status_code=401, detail="Invalid bootstrap token")
    user = User(email=body.email.lower(), password_hash=hash_password(body.password), role=Role.OWNER.value)
    db.add(user)
    db.flush()
    append_audit(
        db,
        actor_type="user",
        actor_id=user.id,
        action="auth.bootstrap_owner",
        result="success",
        request_id=request_id(request),
        details={"email": user.email},
    )
    db.commit()
    token, expires = issue_access_token(user)
    return TokenResponse(access_token=token, expires_in=expires)


@router.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).one_or_none()
    if user is None or not user.active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    append_audit(
        db,
        actor_type="user",
        actor_id=user.id,
        action="auth.login",
        result="success",
        request_id=request_id(request),
    )
    db.commit()
    token, expires = issue_access_token(user)
    return TokenResponse(access_token=token, expires_in=expires)


@router.get("/auth/me", response_model=UserView)
def me(user: User = Depends(get_current_user)):
    return user


@router.get("/users", response_model=list[UserView])
def list_users(_: User = Depends(require_roles(Role.OWNER)), db: Session = Depends(get_db)):
    return db.query(User).order_by(User.email).all()


@router.post("/users", response_model=UserView, status_code=201)
def create_user(
    body: UserCreate,
    request: Request,
    owner: User = Depends(require_roles(Role.OWNER)),
    db: Session = Depends(get_db),
):
    email = body.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="User already exists")
    user = User(email=email, password_hash=hash_password(body.password), role=body.role)
    db.add(user)
    db.flush()
    append_audit(
        db,
        actor_type="user",
        actor_id=owner.id,
        action="user.create",
        result="success",
        request_id=request_id(request),
        details={"created_user_id": user.id, "role": user.role},
    )
    db.commit()
    return user


@router.get("/repositories", response_model=list[RepositoryView])
def list_repositories(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Repository).filter(Repository.active.is_(True)).order_by(Repository.full_name).all()


@router.post("/repositories", response_model=RepositoryView, status_code=201)
def create_repository(
    body: RepositoryCreate,
    request: Request,
    user: User = Depends(require_roles(Role.OWNER)),
    db: Session = Depends(get_db),
):
    if db.query(Repository).filter(Repository.full_name == body.full_name).first():
        raise HTTPException(status_code=409, detail="Repository is already authorized")
    repository = Repository(
        full_name=body.full_name,
        default_branch=body.default_branch,
        github_installation_id=body.github_installation_id,
        created_by=user.id,
    )
    db.add(repository)
    db.flush()
    append_audit(
        db, actor_type="user", actor_id=user.id, action="repository.authorize", result="success",
        details={"repository": repository.full_name}, request_id=request_id(request),
    )
    db.commit()
    return repository


@router.get("/projects", response_model=list[ProjectView])
def list_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(Project)
    if user.role != Role.OWNER.value:
        query = query.filter(Project.owner_id == user.id)
    return query.order_by(Project.created_at.desc()).all()


@router.post("/projects", response_model=ProjectView, status_code=201)
def create_project(
    body: ProjectCreate,
    user: User = Depends(require_roles(Role.OWNER, Role.OPERATOR)),
    db: Session = Depends(get_db),
):
    repository = db.get(Repository, body.repository_id)
    if repository is None or not repository.active:
        raise HTTPException(status_code=404, detail="Authorized repository not found")
    project = Project(name=body.name, repository_id=body.repository_id, owner_id=user.id)
    db.add(project)
    db.commit()
    return project


@router.post("/tasks", response_model=TaskView, status_code=201)
def create_task(
    body: TaskCreate,
    request: Request,
    user: User = Depends(require_roles(Role.OWNER, Role.OPERATOR)),
    db: Session = Depends(get_db),
):
    repository = db.get(Repository, body.repository_id)
    if repository is None or not repository.active:
        raise HTTPException(status_code=404, detail="Authorized repository not found")
    if body.project_id:
        project = db.get(Project, body.project_id)
        if project is None or project.repository_id != repository.id:
            raise HTTPException(status_code=400, detail="Project does not match repository")
    task_id = secrets.token_hex(16)
    working_branch = f"mezo/task-{task_id[:12]}"
    task = Task(
        id=task_id,
        user_id=user.id,
        project_id=body.project_id,
        repository_id=repository.id,
        repository=repository.full_name,
        base_branch=body.base_branch or repository.default_branch,
        working_branch=working_branch,
        title=body.title,
        description=body.description,
    )
    task.steps = [
        TaskStep(step_index=index, name=name, description=description, requires_approval=requires_approval)
        for index, (name, description, requires_approval) in enumerate(STEP_DEFINITIONS)
    ]
    db.add(task)
    add_event(db, task.id, "task_created", {"status": task.status, "repository": task.repository})
    append_audit(
        db, actor_type="user", actor_id=user.id, action="task.create", result="success",
        task_id=task.id, request_id=request_id(request), details={"repository": task.repository},
    )
    db.commit()
    return task


@router.get("/tasks", response_model=list[TaskView])
def list_tasks(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(Task)
    if user.role != Role.OWNER.value:
        query = query.filter(Task.user_id == user.id)
    return query.order_by(Task.created_at.desc()).limit(200).all()


@router.get("/tasks/{task_id}", response_model=TaskView)
def get_task(task_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return task_for_user(db, task_id, user)


@router.post("/tasks/{task_id}/cancel", response_model=TaskView)
def cancel_task(
    task_id: str,
    request: Request,
    user: User = Depends(require_roles(Role.OWNER, Role.OPERATOR)),
    db: Session = Depends(get_db),
):
    task = task_for_user(db, task_id, user)
    if task.status in {TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value}:
        raise HTTPException(status_code=409, detail="Task is already terminal")
    task.cancel_requested = True
    if task.status in {TaskStatus.QUEUED.value, TaskStatus.WAITING_FOR_APPROVAL.value}:
        transition_task(task, TaskStatus.CANCELLED.value)
    add_event(db, task.id, "cancellation_requested", {"status": task.status})
    append_audit(
        db, actor_type="user", actor_id=user.id, action="task.cancel", result="success",
        task_id=task.id, request_id=request_id(request),
    )
    db.commit()
    return task


@router.get("/tasks/{task_id}/events")
async def task_events(
    task_id: str,
    after: int = 0,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task_for_user(db, task_id, user)

    async def stream():
        cursor = after
        idle = 0
        while True:
            with SessionLocal() as poll_db:
                events = (
                    poll_db.query(TaskEvent)
                    .filter(TaskEvent.task_id == task_id, TaskEvent.id > cursor)
                    .order_by(TaskEvent.id.asc())
                    .limit(200)
                    .all()
                )
                task = poll_db.get(Task, task_id)
                for event in events:
                    cursor = event.id
                    data = {
                        "id": event.id,
                        "type": event.event_type,
                        "stream": event.stream,
                        "timestamp": event.created_at.isoformat(),
                        "payload": event.payload,
                    }
                    yield f"id: {event.id}\nevent: {event.event_type}\ndata: {json.dumps(data)}\n\n"
                if events:
                    idle = 0
                else:
                    idle += 1
                if task and task.status in {TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value} and not events:
                    yield f"event: end\ndata: {json.dumps({'status': task.status})}\n\n"
                    return
            if idle >= 15:
                yield ": heartbeat\n\n"
                idle = 0
            await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/tasks/{task_id}/approval")
def get_approval(task_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task = task_for_user(db, task_id, user)
    approval = db.query(Approval).filter(Approval.task_id == task.id).order_by(Approval.created_at.desc()).first()
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if approval.state == ApprovalState.PENDING.value and is_expired(approval.expires_at):
        approval.state = ApprovalState.EXPIRED.value
        task.approval_state = ApprovalState.EXPIRED.value
        db.commit()
    return {
        "id": approval.id,
        "task_id": approval.task_id,
        "diff_hash": approval.diff_hash,
        "action": approval.action,
        "state": approval.state,
        "expires_at": approval.expires_at,
        "request": approval.request_snapshot,
    }


@router.post("/tasks/{task_id}/approval")
def decide_approval(
    task_id: str,
    body: ApprovalDecision,
    request: Request,
    user: User = Depends(require_roles(Role.OWNER, Role.OPERATOR)),
    db: Session = Depends(get_db),
):
    task = task_for_user(db, task_id, user)
    approval = db.query(Approval).filter(Approval.task_id == task.id).order_by(Approval.created_at.desc()).first()
    if approval is None or approval.state != ApprovalState.PENDING.value:
        raise HTTPException(status_code=409, detail="No pending approval exists")
    if is_expired(approval.expires_at):
        approval.state = ApprovalState.EXPIRED.value
        task.approval_state = ApprovalState.EXPIRED.value
        db.commit()
        raise HTTPException(status_code=409, detail="Approval has expired")
    if not task.diff_hash or approval.diff_hash != task.diff_hash:
        approval.state = ApprovalState.INVALIDATED.value
        task.approval_state = ApprovalState.INVALIDATED.value
        db.commit()
        raise HTTPException(status_code=409, detail="Task diff changed; approval was invalidated")
    approval.user_id = user.id
    approval.decided_at = utcnow()
    approval.state = ApprovalState.APPROVED.value if body.decision == "approve" else ApprovalState.REJECTED.value
    task.approval_state = approval.state
    if body.decision == "reject":
        task.cancel_requested = True
        transition_task(task, TaskStatus.CANCELLED.value)
    add_event(db, task.id, "approval_decided", {"decision": body.decision, "diff_hash": task.diff_hash})
    append_audit(
        db, actor_type="user", actor_id=user.id, action=f"approval.{body.decision}", result="success",
        task_id=task.id, request_id=request_id(request), details={"diff_hash": task.diff_hash},
    )
    db.commit()
    return {"state": approval.state, "diff_hash": approval.diff_hash}


@router.post("/tasks/{task_id}/pull-request", status_code=202)
def request_draft_pull_request(
    task_id: str,
    request: Request,
    user: User = Depends(require_roles(Role.OWNER, Role.OPERATOR)),
    db: Session = Depends(get_db),
):
    task = task_for_user(db, task_id, user)
    approval = db.query(Approval).filter(Approval.task_id == task.id).order_by(Approval.created_at.desc()).first()
    if approval is not None and approval.diff_hash != task.diff_hash:
        approval.state = ApprovalState.INVALIDATED.value
        task.approval_state = ApprovalState.INVALIDATED.value
        db.commit()
        raise HTTPException(status_code=409, detail="Task diff changed; approval was invalidated")
    if (
        approval is None
        or approval.state != ApprovalState.APPROVED.value
        or is_expired(approval.expires_at)
    ):
        raise HTTPException(status_code=409, detail="A current, unexpired approval for this exact diff is required")
    if not checks_passed(task.validation_report, task.changed_files):
        raise HTTPException(status_code=409, detail="Validation and guards must pass before Pull Request creation")
    transition_task(task, TaskStatus.CREATING_PULL_REQUEST.value)
    add_event(db, task.id, "pull_request_requested", {"diff_hash": task.diff_hash})
    append_audit(
        db, actor_type="user", actor_id=user.id, action="pull_request.request_draft", result="authorized",
        task_id=task.id, request_id=request_id(request), details={"diff_hash": task.diff_hash},
    )
    db.commit()
    return {"status": task.status}


@router.post("/runners/register", status_code=201)
def register_runner(
    body: RunnerRegister,
    request: Request,
    x_runner_registration_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    expected = get_settings().runner_registration_token
    if not x_runner_registration_token or not secrets.compare_digest(x_runner_registration_token, expected):
        raise HTTPException(status_code=401, detail="Invalid runner registration token")
    if db.query(Runner).filter(Runner.name == body.name).first():
        raise HTTPException(status_code=409, detail="Runner name is already registered")
    raw_token = new_runner_token()
    runner = Runner(
        name=body.name,
        version=body.version,
        capabilities=redact(body.capabilities),
        auth_token_hash=hash_runner_token(raw_token),
    )
    db.add(runner)
    db.flush()
    append_audit(
        db, actor_type="runner", actor_id=runner.id, action="runner.register", result="success",
        request_id=request_id(request), details={"name": runner.name, "version": runner.version},
    )
    db.commit()
    return {"runner_id": runner.id, "runner_token": raw_token}


@router.post("/runner/heartbeat")
def heartbeat(
    body: RunnerHeartbeat,
    runner: Runner = Depends(get_current_runner),
    db: Session = Depends(get_db),
):
    runner.last_heartbeat_at = utcnow()
    runner.status = body.status
    runner.current_task_id = body.current_task_id
    runner.disk_total_bytes = body.disk_total_bytes
    runner.disk_free_bytes = body.disk_free_bytes
    db.commit()
    return {"server_time": utcnow(), "cancel_task_id": _cancel_task_id(db, runner.id)}


def _cancel_task_id(db: Session, runner_id: str) -> str | None:
    task = db.query(Task).filter(Task.runner_id == runner_id, Task.cancel_requested.is_(True)).first()
    return task.id if task else None


@router.post("/runner/tasks/lease")
def lease_task(
    request: Request,
    runner: Runner = Depends(get_current_runner),
    db: Session = Depends(get_db),
):
    kill_switch = db.get(SystemSetting, "kill_switch")
    if kill_switch and not kill_switch.value.get("armed", True):
        raise HTTPException(status_code=423, detail="Kill switch is disarmed")
    active = db.query(Task).filter(
        Task.runner_id == runner.id,
        Task.status.notin_([TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value]),
    ).first()
    if active:
        return {"task": None, "reason": "runner_already_busy"}
    now = utcnow()
    lease_candidates = db.query(Task).filter(
        Task.lease_expires_at.is_not(None),
        Task.status.in_([TaskStatus.PROVISIONING.value, TaskStatus.PLANNING.value, TaskStatus.RUNNING.value, TaskStatus.VALIDATING.value]),
    ).all()
    expired = [task for task in lease_candidates if is_expired(task.lease_expires_at)]
    for task in expired:
        previous_runner_id = task.runner_id
        previous_status = task.status
        recover_expired_lease(task)
        add_event(
            db,
            task.id,
            "lease_recovered",
            {"reason": "expired_lease", "previous_runner_id": previous_runner_id, "previous_status": previous_status},
        )
        append_audit(
            db,
            actor_type="runner",
            actor_id=runner.id,
            action="task.lease_recover",
            result="success",
            task_id=task.id,
            request_id=request_id(request),
            details={"previous_runner_id": previous_runner_id, "previous_status": previous_status},
        )
    if expired:
        db.flush()
    task = (
        db.query(Task)
        .filter(Task.status == TaskStatus.QUEUED.value, Task.cancel_requested.is_(False))
        .order_by(Task.created_at.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if task is None:
        db.commit()
        return {"task": None, "reason": "queue_empty"}
    transition_task(task, TaskStatus.PROVISIONING.value)
    task.runner_id = runner.id
    task.lease_expires_at = now + timedelta(seconds=get_settings().task_lease_seconds)
    runner.status = "busy"
    runner.current_task_id = task.id
    add_event(db, task.id, "task_leased", {"runner_id": runner.id})
    append_audit(
        db, actor_type="runner", actor_id=runner.id, action="task.lease", result="success",
        task_id=task.id, request_id=request_id(request),
    )
    db.commit()
    created_at = task.created_at if task.created_at.tzinfo else task.created_at.replace(tzinfo=timezone.utc)
    logger.info(
        "task leased",
        extra={
            "task_id": task.id,
            "runner_id": runner.id,
            "queue_latency_ms": round((now - created_at).total_seconds() * 1000),
        },
    )
    return {
        "task": {
            "id": task.id,
            "user_id": task.user_id,
            "repository": task.repository,
            "base_branch": task.base_branch,
            "working_branch": task.working_branch,
            "title": task.title,
            "description": task.description,
        },
        "lease_seconds": get_settings().task_lease_seconds,
    }


@router.post("/runner/tasks/{task_id}/transition")
def runner_transition(
    task_id: str,
    body: TaskTransitionRequest,
    runner: Runner = Depends(get_current_runner),
    db: Session = Depends(get_db),
):
    task = runner_task(db, task_id, runner)
    if task.cancel_requested and body.status != TaskStatus.CANCELLED.value:
        raise HTTPException(status_code=409, detail="Task cancellation is required")
    transition_task(task, body.status, error=body.error)
    task.current_step = body.current_step
    task.workspace_id = body.workspace_id or task.workspace_id
    task.lease_expires_at = utcnow() + timedelta(seconds=get_settings().task_lease_seconds)
    add_event(db, task.id, "task_transition", {"status": task.status, "current_step": task.current_step, "error": body.error})
    if task.status in {TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value}:
        runner.status = "online"
        runner.current_task_id = None
    db.commit()
    return {"status": task.status}


@router.get("/runner/tasks/{task_id}/clone-credential")
async def clone_credential(
    task_id: str,
    request: Request,
    runner: Runner = Depends(get_current_runner),
    db: Session = Depends(get_db),
):
    task = runner_task(db, task_id, runner)
    if task.status not in {TaskStatus.PROVISIONING.value, TaskStatus.PLANNING.value}:
        raise HTTPException(status_code=409, detail="Clone credentials are available only during provisioning")
    repository = db.get(Repository, task.repository_id)
    try:
        token, expires_at = await GitHubAppClient().installation_token(
            repository.github_installation_id if repository else None,
            repository=task.repository,
            permissions={"contents": "read"},
        )
    except GitHubAppError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    append_audit(
        db, actor_type="runner", actor_id=runner.id, action="github.issue_clone_token", result="success",
        task_id=task.id, request_id=request_id(request), details={"repository": task.repository, "expires_at": expires_at.isoformat()},
    )
    db.commit()
    return {"username": "x-access-token", "token": token, "expires_at": expires_at}


@router.post("/runner/tasks/{task_id}/steps")
def update_step(
    task_id: str,
    body: StepUpdate,
    runner: Runner = Depends(get_current_runner),
    db: Session = Depends(get_db),
):
    task = runner_task(db, task_id, runner)
    step = db.query(TaskStep).filter(TaskStep.task_id == task.id, TaskStep.step_index == body.step_index).one_or_none()
    if step is None:
        raise HTTPException(status_code=404, detail="Task step not found")
    previous = step.status
    allowed = {
        StepStatus.PENDING.value: {StepStatus.RUNNING.value, StepStatus.SKIPPED.value, StepStatus.BLOCKED.value},
        StepStatus.RUNNING.value: {StepStatus.COMPLETED.value, StepStatus.FAILED.value, StepStatus.WAITING_FOR_APPROVAL.value},
        StepStatus.WAITING_FOR_APPROVAL.value: {StepStatus.COMPLETED.value, StepStatus.FAILED.value},
    }
    if body.status != previous and body.status not in allowed.get(previous, set()):
        raise HTTPException(status_code=409, detail=f"Invalid step transition: {previous} -> {body.status}")
    step.status = body.status
    step.command = redact(body.command) if body.command else step.command
    step.exit_code = body.exit_code
    step.result_summary = redact(body.result_summary) if body.result_summary else None
    step.error = redact(body.error) if body.error else None
    if body.status == StepStatus.RUNNING.value:
        step.started_at = utcnow()
    if body.status in {StepStatus.COMPLETED.value, StepStatus.FAILED.value, StepStatus.SKIPPED.value, StepStatus.BLOCKED.value}:
        step.finished_at = utcnow()
    add_event(db, task.id, "step_update", {"step_index": step.step_index, "name": step.name, "status": step.status, "exit_code": step.exit_code})
    db.commit()
    return {"status": step.status}


@router.post("/runner/tasks/{task_id}/events", status_code=201)
def runner_event(
    task_id: str,
    body: RunnerEvent,
    runner: Runner = Depends(get_current_runner),
    db: Session = Depends(get_db),
):
    task = runner_task(db, task_id, runner)
    payload = body.model_dump(mode="json", exclude_none=True)
    add_event(db, task.id, body.event_type, payload, body.stream)
    task.lease_expires_at = utcnow() + timedelta(seconds=get_settings().task_lease_seconds)
    db.commit()
    return {"stored": True}


@router.post("/runner/tasks/{task_id}/analysis-complete")
def analysis_complete(
    task_id: str,
    body: AnalysisComplete,
    request: Request,
    runner: Runner = Depends(get_current_runner),
    db: Session = Depends(get_db),
):
    task = runner_task(db, task_id, runner)
    if task.status != TaskStatus.VALIDATING.value:
        raise HTTPException(status_code=409, detail="Task must be validating")
    changed_files = [item.model_dump() for item in body.changed_files]
    if not checks_passed(body.validation_report, changed_files):
        transition_task(task, TaskStatus.FAILED.value, error="Required validation or guards failed")
        add_event(db, task.id, "validation_failed", {"report": body.validation_report})
        append_audit(
            db, actor_type="runner", actor_id=runner.id, action="task.validation", result="failed",
            task_id=task.id, request_id=request_id(request),
        )
        db.commit()
        raise HTTPException(status_code=409, detail="Required validation or guards failed")
    diff_hash = hashlib.sha256(body.diff_text.encode()).hexdigest()
    old_pending = db.query(Approval).filter(Approval.task_id == task.id, Approval.state == ApprovalState.PENDING.value).all()
    for approval in old_pending:
        approval.state = ApprovalState.INVALIDATED.value
    task.diff_text = body.diff_text
    task.diff_hash = diff_hash
    task.commit_sha = body.commit_sha
    task.changed_files = changed_files
    task.validation_report = redact(body.validation_report)
    task.pull_request_title = body.pull_request_title
    task.pull_request_body = body.pull_request_body
    transition_task(task, TaskStatus.WAITING_FOR_APPROVAL.value)
    task.approval_state = ApprovalState.PENDING.value
    approval = Approval(
        task_id=task.id,
        diff_hash=diff_hash,
        user_id=task.user_id,
        action="create_draft_pull_request",
        state=ApprovalState.PENDING.value,
        request_snapshot=approval_snapshot(task),
        expires_at=utcnow() + timedelta(minutes=get_settings().approval_minutes),
    )
    db.add(approval)
    add_event(db, task.id, "approval_requested", approval.request_snapshot)
    append_audit(
        db, actor_type="runner", actor_id=runner.id, action="approval.request", result="success",
        task_id=task.id, request_id=request_id(request), details={"diff_hash": diff_hash},
    )
    db.commit()
    return {"status": task.status, "approval_id": approval.id, "diff_hash": diff_hash}


@router.get("/runner/tasks/{task_id}/publish-command")
async def publish_command(
    task_id: str,
    request: Request,
    runner: Runner = Depends(get_current_runner),
    db: Session = Depends(get_db),
):
    task = runner_task(db, task_id, runner)
    if task.status in {TaskStatus.CANCELLED.value, TaskStatus.FAILED.value}:
        return {"action": "cancel"}
    if task.status != TaskStatus.CREATING_PULL_REQUEST.value:
        return {"action": "wait"}
    approval = db.query(Approval).filter(Approval.task_id == task.id).order_by(Approval.created_at.desc()).first()
    if approval is None or approval.state != ApprovalState.APPROVED.value or approval.diff_hash != task.diff_hash or is_expired(approval.expires_at):
        raise HTTPException(status_code=409, detail="Publish authorization is invalid")
    repository = db.get(Repository, task.repository_id)
    try:
        token, expires_at = await GitHubAppClient().installation_token(
            repository.github_installation_id if repository else None,
            repository=task.repository,
            permissions={"contents": "write"},
        )
    except GitHubAppError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    append_audit(
        db, actor_type="runner", actor_id=runner.id, action="github.issue_installation_token", result="success",
        task_id=task.id, request_id=request_id(request), details={"repository": task.repository, "expires_at": expires_at.isoformat()},
    )
    db.commit()
    return {
        "action": "push_branch",
        "repository": task.repository,
        "branch": task.working_branch,
        "username": "x-access-token",
        "token": token,
        "expires_at": expires_at,
        "commit_sha": task.commit_sha,
    }


@router.post("/runner/tasks/{task_id}/branch-pushed")
async def branch_pushed(
    task_id: str,
    body: BranchPushed,
    request: Request,
    runner: Runner = Depends(get_current_runner),
    db: Session = Depends(get_db),
):
    task = runner_task(db, task_id, runner)
    if task.status != TaskStatus.CREATING_PULL_REQUEST.value:
        raise HTTPException(status_code=409, detail="Task is not creating a Pull Request")
    approval = db.query(Approval).filter(Approval.task_id == task.id).order_by(Approval.created_at.desc()).first()
    if (
        approval is None
        or approval.state != ApprovalState.APPROVED.value
        or approval.diff_hash != task.diff_hash
        or is_expired(approval.expires_at)
        or not task.commit_sha
        or body.commit_sha != task.commit_sha
    ):
        raise HTTPException(status_code=409, detail="Approval is not valid for the current diff")
    repository = db.get(Repository, task.repository_id)
    try:
        github = GitHubAppClient()
        remote_sha = await github.branch_sha(
            repository=task.repository,
            branch=task.working_branch,
            installation_id=repository.github_installation_id if repository else None,
        )
        if remote_sha != task.commit_sha:
            raise GitHubAppError("Pushed branch does not match the commit bound to the approval")
        pr_url = await github.create_draft_pull_request(
            repository=task.repository,
            head=task.working_branch,
            base=task.base_branch,
            title=task.pull_request_title or task.title,
            body=task.pull_request_body or task.description,
            installation_id=repository.github_installation_id if repository else None,
        )
    except GitHubAppError as exc:
        transition_task(task, TaskStatus.FAILED.value, error=str(exc))
        append_audit(
            db, actor_type="runner", actor_id=runner.id, action="github.create_draft_pull_request",
            result="failed", task_id=task.id, request_id=request_id(request), details={"error": str(exc)},
        )
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    task.pull_request_url = pr_url
    transition_task(task, TaskStatus.COMPLETED.value)
    runner.status = "online"
    runner.current_task_id = None
    add_event(db, task.id, "pull_request_created", {"url": pr_url, "draft": True, "commit_sha": body.commit_sha})
    append_audit(
        db, actor_type="runner", actor_id=runner.id, action="github.create_draft_pull_request",
        result="success", task_id=task.id, request_id=request_id(request), details={"url": pr_url, "draft": True},
    )
    db.commit()
    started_at = task.started_at if task.started_at and task.started_at.tzinfo else task.started_at.replace(tzinfo=timezone.utc) if task.started_at else None
    logger.info(
        "task completed with Draft Pull Request",
        extra={
            "task_id": task.id,
            "runner_id": runner.id,
            "task_duration_ms": round((utcnow() - started_at).total_seconds() * 1000) if started_at else None,
        },
    )
    return {"pull_request_url": pr_url, "draft": True}


@router.get("/runners")
def runners(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cutoff = utcnow() - timedelta(seconds=get_settings().runner_offline_seconds)
    rows = db.query(Runner).order_by(Runner.name).all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "status": "offline" if (row.last_heartbeat_at.replace(tzinfo=timezone.utc) if row.last_heartbeat_at.tzinfo is None else row.last_heartbeat_at) < cutoff else row.status,
            "version": row.version,
            "current_task_id": row.current_task_id,
            "last_heartbeat_at": row.last_heartbeat_at,
            "disk_total_bytes": row.disk_total_bytes,
            "disk_free_bytes": row.disk_free_bytes,
            "capabilities": row.capabilities,
        }
        for row in rows
    ]


def configured_provider_router(db: Session) -> tuple[ProviderRouter, list[str]]:
    rows = {row.name: row for row in db.query(ProviderConfig).all()}
    defaults = ProviderRouter().providers
    providers = {}
    priorities: list[tuple[int, str]] = []
    for name in ("local", "gemini"):
        configured = rows.get(name)
        if configured is not None and not configured.enabled:
            continue
        if configured is None:
            providers[name] = defaults[name]
            priorities.append((100, name))
        elif name == "local":
            from src.providers import OpenAICompatibleProvider
            providers[name] = OpenAICompatibleProvider(model=configured.model, base_url=configured.base_url)
            priorities.append((configured.priority, name))
        else:
            from src.providers import GeminiProvider
            providers[name] = GeminiProvider(model=configured.model, base_url=configured.base_url)
            priorities.append((configured.priority, name))
    return ProviderRouter(providers), [name for _, name in sorted(priorities)]


@router.get("/providers/health")
async def provider_health(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    configured, _ = configured_provider_router(db)
    return await configured.health()


@router.put("/providers/{name}")
def update_provider(
    name: str,
    body: ProviderUpdate,
    request: Request,
    user: User = Depends(require_roles(Role.OWNER)),
    db: Session = Depends(get_db),
):
    if name not in {"gemini", "local"}:
        raise HTTPException(status_code=404, detail="Unknown provider")
    config = db.get(ProviderConfig, name) or ProviderConfig(name=name, updated_by=user.id)
    config.model = body.model
    config.base_url = body.base_url
    config.enabled = body.enabled
    config.priority = body.priority
    config.updated_by = user.id
    db.add(config)
    append_audit(
        db, actor_type="user", actor_id=user.id, action="provider.configure", result="success",
        request_id=request_id(request), details={"provider": name, "model": body.model, "enabled": body.enabled},
    )
    db.commit()
    return {"name": name, "model": config.model, "base_url": config.base_url, "enabled": config.enabled, "priority": config.priority}


@router.post("/providers/generate")
async def provider_generate(
    body: ProviderGenerate,
    _: User = Depends(require_roles(Role.OWNER, Role.OPERATOR)),
    db: Session = Depends(get_db),
):
    selected = body.provider
    if selected == "auto" and body.model:
        raise HTTPException(status_code=422, detail="Explicit model selection requires an explicit provider")
    configured, fallback = configured_provider_router(db)
    if body.model:
        selected_provider = configured.providers.get(selected)
        if selected_provider is None:
            raise HTTPException(status_code=409, detail=f"Provider {selected} is disabled")
        from src.providers import GeminiProvider, OpenAICompatibleProvider
        if selected == "local":
            configured.providers[selected] = OpenAICompatibleProvider(
                model=body.model, base_url=selected_provider.base_url
            )
        else:
            configured.providers[selected] = GeminiProvider(
                model=body.model, base_url=selected_provider.base_url
            )

    async def stream():
        try:
            async for chunk in configured.stream(
                selected=selected,
                fallback=fallback,
                messages=[message.model_dump() for message in body.messages],
                system=body.system,
                tools=body.tools,
            ):
                yield f"data: {json.dumps({'text': chunk.text, 'tool_calls': chunk.tool_calls, 'usage': chunk.usage, 'finish_reason': chunk.finish_reason})}\n\n"
            yield "data: [DONE]\n\n"
        except ProviderError as exc:
            yield f"event: error\ndata: {json.dumps({'category': exc.category, 'message': str(exc)})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/audit")
def audit_log(
    task_id: str | None = None,
    limit: int = 100,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 500))
    query = db.query(AuditLog)
    if task_id:
        task_for_user(db, task_id, user)
        query = query.filter(AuditLog.task_id == task_id)
    elif user.role != Role.OWNER.value:
        owned_task_ids = db.query(Task.id).filter(Task.user_id == user.id)
        query = query.filter(or_(AuditLog.actor_id == user.id, AuditLog.task_id.in_(owned_task_ids)))
    records = query.order_by(AuditLog.id.desc()).limit(limit).all()
    return {
        "integrity_valid": verify_audit_chain(db),
        "records": [
            {
                "id": row.id,
                "actor_type": row.actor_type,
                "actor_id": row.actor_id,
                "action": row.action,
                "task_id": row.task_id,
                "result": row.result,
                "details": row.details,
                "created_at": row.created_at,
                "previous_hash": row.previous_hash,
                "entry_hash": row.entry_hash,
            }
            for row in records
        ],
    }


@router.get("/admin/kill-switch")
def kill_switch_status(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    setting = db.get(SystemSetting, "kill_switch")
    return setting.value if setting else {"armed": True, "updated_by": None, "updated_at": None}


@router.post("/admin/kill-switch/{action}")
def set_kill_switch(
    action: str,
    request: Request,
    user: User = Depends(require_roles(Role.OWNER)),
    db: Session = Depends(get_db),
):
    if action not in {"arm", "disarm"}:
        raise HTTPException(status_code=404, detail="Unknown kill-switch action")
    value = {"armed": action == "arm", "updated_by": user.id, "updated_at": utcnow().isoformat()}
    setting = db.get(SystemSetting, "kill_switch") or SystemSetting(key="kill_switch", value=value)
    setting.value = value
    db.add(setting)
    append_audit(
        db, actor_type="user", actor_id=user.id, action=f"kill_switch.{action}", result="success",
        request_id=request_id(request),
    )
    db.commit()
    return value


@router.get("/health/database")
def database_health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}
