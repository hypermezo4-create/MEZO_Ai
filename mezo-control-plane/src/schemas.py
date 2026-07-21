from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class BootstrapRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class UserView(OrmModel):
    id: str
    email: str
    role: str


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
    role: Literal["owner", "operator", "viewer"]


class RepositoryCreate(BaseModel):
    full_name: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", max_length=255)
    default_branch: str = Field(default="main", min_length=1, max_length=255)
    github_installation_id: str | None = None


class RepositoryView(OrmModel):
    id: str
    full_name: str
    default_branch: str
    active: bool


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    repository_id: str


class ProjectView(OrmModel):
    id: str
    name: str
    repository_id: str
    owner_id: str


class TaskCreate(BaseModel):
    repository_id: str
    project_id: str | None = None
    base_branch: str | None = Field(default=None, max_length=255)
    title: str = Field(min_length=3, max_length=240)
    description: str = Field(min_length=3, max_length=20_000)

    @field_validator("base_branch")
    @classmethod
    def safe_branch(cls, value: str | None) -> str | None:
        if value and (value.startswith("-") or ".." in value or any(c.isspace() for c in value)):
            raise ValueError("invalid base branch")
        return value


class StepView(OrmModel):
    id: str
    step_index: int
    name: str
    description: str
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    command: str | None
    exit_code: int | None
    result_summary: str | None
    error: str | None
    requires_approval: bool


class TaskView(OrmModel):
    id: str
    user_id: str
    repository: str
    base_branch: str
    working_branch: str
    title: str
    description: str
    status: str
    current_step: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    runner_id: str | None
    workspace_id: str | None
    error: str | None
    approval_state: str
    pull_request_url: str | None
    changed_files: list[Any]
    diff_text: str | None
    diff_hash: str | None
    commit_sha: str | None
    validation_report: dict[str, Any]
    steps: list[StepView]


class RunnerRegister(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    version: str = Field(min_length=1, max_length=64)
    capabilities: dict[str, Any]


class RunnerHeartbeat(BaseModel):
    status: Literal["online", "busy", "draining"]
    current_task_id: str | None = None
    disk_total_bytes: int | None = Field(default=None, ge=0)
    disk_free_bytes: int | None = Field(default=None, ge=0)


class RunnerEvent(BaseModel):
    event_type: Literal["command_start", "stdout", "stderr", "command_finish", "progress", "cleanup"]
    stream: Literal["stdout", "stderr"] | None = None
    timestamp: datetime
    working_directory: str | None = Field(default=None, max_length=4096)
    command: str | None = Field(default=None, max_length=16_000)
    exit_code: int | None = None
    message: str | None = Field(default=None, max_length=16_000)
    duration_ms: int | None = Field(default=None, ge=0)


class StepUpdate(BaseModel):
    step_index: int = Field(ge=0)
    status: Literal["pending", "running", "completed", "failed", "skipped", "blocked", "waiting_for_approval"]
    command: str | None = Field(default=None, max_length=16_000)
    exit_code: int | None = None
    result_summary: str | None = Field(default=None, max_length=16_000)
    error: str | None = Field(default=None, max_length=16_000)


class TaskTransitionRequest(BaseModel):
    status: Literal[
        "provisioning", "planning", "running", "waiting_for_approval", "validating",
        "creating_pull_request", "completed", "failed", "cancelled"
    ]
    current_step: str | None = None
    workspace_id: str | None = None
    error: str | None = None


class ChangedFile(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    additions: int | None = Field(default=None, ge=0)
    deletions: int | None = Field(default=None, ge=0)

    @field_validator("path")
    @classmethod
    def contained_path(cls, value: str) -> str:
        if value.startswith(("/", "\\")) or ".." in value.replace("\\", "/").split("/"):
            raise ValueError("changed file must be repository-relative")
        return value


class AnalysisComplete(BaseModel):
    diff_text: str = Field(max_length=2_000_000)
    changed_files: list[ChangedFile] = Field(max_length=10_000)
    validation_report: dict[str, Any]
    pull_request_title: str = Field(min_length=3, max_length=240)
    pull_request_body: str = Field(min_length=3, max_length=60_000)
    commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")


class ApprovalDecision(BaseModel):
    decision: Literal["approve", "reject"]


class BranchPushed(BaseModel):
    commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")


class ProviderUpdate(BaseModel):
    model: str = Field(min_length=1, max_length=160)
    base_url: str | None = Field(default=None, pattern=r"^https?://")
    enabled: bool = True
    priority: int = Field(default=100, ge=0, le=1000)


class ProviderMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1, max_length=100_000)


class ProviderGenerate(BaseModel):
    provider: Literal["auto", "local", "gemini"] = "auto"
    model: str | None = Field(default=None, min_length=1, max_length=160)
    messages: list[ProviderMessage] = Field(min_length=1, max_length=500)
    system: str | None = Field(default=None, max_length=100_000)
    tools: list[dict[str, Any]] | None = Field(default=None, max_length=200)
