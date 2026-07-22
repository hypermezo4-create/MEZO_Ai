import asyncio
import os
from pathlib import Path

import httpx
import pytest

from runner.api_client import ApiClient, ApiError
from runner.command import CommandRejected, CommandRunner
from runner.executor import TaskExecutionError, _kilo_text, _kilo_used_skill
from runner.main import remove_stale_workspaces
from runner.workspace import Workspace, WorkspaceViolation


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    workspace = Workspace(str(root), "user-1", "task-1")
    workspace.create()
    workspace.repo.mkdir()
    return workspace


def test_path_traversal_is_rejected(workspace):
    with pytest.raises(WorkspaceViolation):
        workspace.resolve("../../../outside", allow_missing=True)


def test_symlink_escape_is_rejected(workspace, tmp_path):
    outside = tmp_path / "outside"; outside.mkdir()
    (workspace.task_root / "escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(WorkspaceViolation):
        workspace.resolve("escape")


def test_workspace_cleanup_removes_only_task_root(workspace):
    root = workspace.allowed_root
    workspace.cleanup()
    assert root.exists()
    assert not workspace.task_root.exists()


@pytest.mark.asyncio
async def test_prohibited_git_push_and_force_are_blocked(workspace):
    async def sink(_):
        return None

    runner = CommandRunner(workspace, sink)
    with pytest.raises(CommandRejected):
        runner.validate(["git", "push", "origin", "main"], workspace.repo)
    with pytest.raises(CommandRejected):
        runner.validate(["git", "reset", "--hard"], workspace.repo)


def test_approved_push_is_bound_to_github_repository_and_safe_branch():
    argv = CommandRunner.approved_push_argv("owner/repository", "mezo/task-123")
    assert "https://github.com/owner/repository.git" in argv
    assert "core.hooksPath=/dev/null" in argv
    assert "credential.helper=" in argv
    with pytest.raises(CommandRejected):
        CommandRunner.approved_push_argv("attacker.example/repository/extra", "mezo/task-123")
    with pytest.raises(CommandRejected):
        CommandRunner.approved_push_argv("owner/repository", "../main")


@pytest.mark.asyncio
async def test_command_timeout_kills_process_tree_and_logs_events(workspace):
    events = []

    async def sink(event):
        events.append(event)

    runner = CommandRunner(workspace, sink)
    with pytest.raises(TimeoutError):
        await runner.run(["python3", "-c", "import time; time.sleep(30)"], cwd=workspace.repo, timeout=1)
    assert events[0]["event_type"] == "command_start"


@pytest.mark.asyncio
async def test_cancellation_terminates_running_process(workspace):
    async def sink(_):
        return None

    runner = CommandRunner(workspace, sink)
    future = asyncio.create_task(runner.run(["python3", "-c", "import time; time.sleep(30)"], cwd=workspace.repo, timeout=60))
    await asyncio.sleep(0.2)
    await runner.cancel()
    result = await future
    assert result.exit_code != 0


@pytest.mark.asyncio
async def test_background_descendant_is_terminated_when_parent_exits(workspace):
    events = []

    async def sink(event):
        events.append(event)

    runner = CommandRunner(workspace, sink)
    command = (
        "import subprocess; child = subprocess.Popen(['python3', '-c', "
        "'import time; time.sleep(30)']); print(child.pid, flush=True)"
    )
    with pytest.raises(TimeoutError):
        await runner.run(["python3", "-c", command], cwd=workspace.repo, timeout=1)
    child_pid = int(next(event["message"] for event in events if event["event_type"] == "stdout").strip())
    process_state = f"/proc/{child_pid}/stat"
    try:
        state = Path(process_state).read_text().split()[2]
    except FileNotFoundError:
        state = "terminated"
    assert state in {"Z", "terminated"}


@pytest.mark.asyncio
async def test_runner_secrets_are_not_inherited_by_repository_commands(workspace, monkeypatch):
    async def sink(_):
        return None

    monkeypatch.setenv("RUNNER_REGISTRATION_TOKEN", "must-not-reach-child")
    runner = CommandRunner(workspace, sink)
    result = await runner.run(
        ["python3", "-c", "import os; print(os.getenv('RUNNER_REGISTRATION_TOKEN', 'missing'))"],
        cwd=workspace.repo,
        timeout=5,
    )
    assert result.stdout.strip() == "missing"


def test_startup_recovery_removes_only_task_workspaces(tmp_path):
    root = tmp_path / "workspaces"
    task = root / "user-1" / "task-1"
    task.mkdir(parents=True)
    (task / "file.txt").write_text("stale")
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    assert remove_stale_workspaces(str(root)) == 1
    assert root.exists()
    assert unrelated.exists()


def test_kilo_structured_output_extracts_text_and_rejects_malformed_events():
    output = '\n'.join([
        '{"type":"step_start","part":{}}',
        '{"type":"tool_use","part":{"tool":"skill","state":{"status":"completed","input":{"name":"clean-code-guard"}}}}',
        '{"type":"text","part":{"text":"validated plan"}}',
        '{"type":"step_finish","part":{}}',
    ])
    assert _kilo_text(output) == "validated plan"
    assert _kilo_used_skill(output, "clean-code-guard")
    assert not _kilo_used_skill(output, "docs-guard")
    with pytest.raises(TaskExecutionError):
        _kilo_text("not-json")


@pytest.mark.asyncio
async def test_invalid_control_plane_response_fails_explicitly(monkeypatch, tmp_path):
    class InvalidJsonClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def request(self, *_args, **_kwargs):
            request = httpx.Request("GET", "http://mezo.invalid/health")
            return httpx.Response(200, content=b"not-json", request=request)

    monkeypatch.setattr(httpx, "AsyncClient", InvalidJsonClient)
    client = ApiClient("http://mezo.invalid", str(tmp_path / "identity.json"))

    with pytest.raises(ApiError, match="invalid JSON") as error:
        await client.request("GET", "/health")

    assert error.value.status_code == 502
