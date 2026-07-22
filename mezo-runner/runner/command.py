from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from runner.redaction import redact
from runner.workspace import Workspace


class CommandRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class CommandResult:
    argv: list[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int


EventSink = Callable[[dict], Awaitable[None]]
MAX_CAPTURE_BYTES = 2_000_000
MAX_EVENT_CHARS = 16_000
logger = logging.getLogger("mezo.runner.command")


class CommandRunner:
    ALLOWED_EXECUTABLES = {
        "git", "kilo", "npm", "npx", "node", "python", "python3", "pytest", "ruff", "mypy",
        "shellcheck", "make", "cmake", "pip", "pip3", "rg",
    }
    FORBIDDEN_GIT = {"push", "fetch-pack", "receive-pack", "update-ref", "replace", "notes"}
    FORBIDDEN_ARGUMENTS = {"--force", "--force-with-lease", "-f", "--hard"}

    def __init__(self, workspace: Workspace, event_sink: EventSink, base_env: dict[str, str] | None = None) -> None:
        self.workspace = workspace
        self.event_sink = event_sink
        self.base_env = base_env or {}
        self.current_process: asyncio.subprocess.Process | None = None
        self.cancelled = False

    def validate(self, argv: list[str], cwd: Path) -> Path:
        if not argv or argv[0] not in self.ALLOWED_EXECUTABLES:
            raise CommandRejected("Executable is not allowed")
        resolved_cwd = self.workspace.resolve(cwd)
        if argv[0] == "git" and len(argv) > 1:
            subcommand = next((arg for arg in argv[1:] if not arg.startswith("-")), "")
            if subcommand in self.FORBIDDEN_GIT:
                raise CommandRejected(f"git {subcommand} is prohibited")
        if any(argument in self.FORBIDDEN_ARGUMENTS for argument in argv):
            raise CommandRejected("Force or destructive argument is prohibited")
        return resolved_cwd

    async def run(
        self,
        argv: list[str],
        *,
        cwd: Path,
        timeout: int,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        resolved_cwd = self.validate(argv, cwd)
        return await self._run_process(argv, resolved_cwd, timeout, env)

    async def push_approved_branch(
        self,
        *,
        repository: str,
        branch: str,
        cwd: Path,
        env: dict[str, str],
    ) -> CommandResult:
        resolved_cwd = self.workspace.resolve(cwd)
        argv = self.approved_push_argv(repository, branch)
        return await self._run_process(argv, resolved_cwd, 300, env)

    @staticmethod
    def approved_push_argv(repository: str, branch: str) -> list[str]:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise CommandRejected("Approved push repository is invalid")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,254}", branch) or ".." in branch or branch.endswith("/"):
            raise CommandRejected("Approved push branch is invalid")
        return [
            "git",
            "-c", "core.hooksPath=/dev/null",
            "-c", "credential.helper=",
            "-c", "http.extraHeader=",
            "push", "--no-verify", f"https://github.com/{repository}.git",
            f"HEAD:refs/heads/{branch}",
        ]

    async def _run_process(
        self,
        argv: list[str],
        resolved_cwd: Path,
        timeout: int,
        env: dict[str, str] | None,
    ) -> CommandResult:
        display = " ".join(redact(part) for part in argv)
        execution_argv = [sys.executable, *argv[1:]] if os.name == "nt" and argv[0] in {"python", "python3"} else argv
        await self.event_sink({"event_type": "command_start", "timestamp": _now(), "working_directory": str(resolved_cwd), "command": display})
        started = time.monotonic()
        process_env = {
            "PATH": os.getenv("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": self.base_env.get("HOME", str(self.workspace.task_root)),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "CI": "true",
            **self.base_env,
            **(env or {}),
        }
        child_setup = None
        if os.name == "posix" and os.geteuid() == 0 and self.workspace.task_uid != 0:
            def child_setup() -> None:
                os.setgroups([])
                os.setgid(self.workspace.task_gid)
                os.setuid(self.workspace.task_uid)
                os.umask(0o077)

        isolated_argv = execution_argv
        use_bwrap = os.getenv("MEZO_USE_BWRAP", "1").lower() not in {"0", "false", "no"}
        if use_bwrap and shutil.which("bwrap") and os.name == "posix":
            isolated_argv = [
                "bwrap", "--die-with-parent", "--new-session", "--unshare-pid", "--unshare-ipc", "--unshare-uts",
                "--ro-bind", "/", "/", "--bind", str(self.workspace.task_root), str(self.workspace.task_root),
                "--tmpfs", "/tmp", "--proc", "/proc", "--dev", "/dev", "--chdir", str(resolved_cwd),
                "--uid", str(self.workspace.task_uid), "--gid", str(self.workspace.task_gid), "--", *execution_argv,
            ]
            child_setup = None
        self.current_process = await asyncio.create_subprocess_exec(
            *isolated_argv,
            cwd=resolved_cwd,
            env=process_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            preexec_fn=child_setup,
        )
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []

        async def consume(stream: asyncio.StreamReader, name: str, collector: list[str]) -> None:
            captured = 0
            truncated = False
            while chunk := await stream.read(MAX_EVENT_CHARS):
                value = redact(chunk.decode(errors="replace"))
                encoded = value.encode()
                remaining = MAX_CAPTURE_BYTES - captured
                if remaining > 0:
                    captured_value = encoded[:remaining].decode(errors="ignore")
                    collector.append(captured_value)
                    captured += len(captured_value.encode())
                elif not truncated:
                    truncated = True
                    collector.append("\n[MEZO output capture truncated at 2 MB]\n")
                await self.event_sink({
                    "event_type": name,
                    "stream": name,
                    "timestamp": _now(),
                    "message": value[:MAX_EVENT_CHARS],
                })

        consumers = [
            asyncio.create_task(consume(self.current_process.stdout, "stdout", stdout_parts)),
            asyncio.create_task(consume(self.current_process.stderr, "stderr", stderr_parts)),
        ]
        timed_out = False
        try:
            await asyncio.wait_for(self.current_process.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            timed_out = True
        finally:
            await self._terminate_tree()
            await asyncio.gather(*consumers)
        exit_code = self.current_process.returncode if self.current_process.returncode is not None else -1
        duration_ms = round((time.monotonic() - started) * 1000)
        await self.event_sink({
            "event_type": "command_finish", "timestamp": _now(), "working_directory": str(resolved_cwd),
            "command": display, "exit_code": exit_code, "duration_ms": duration_ms,
        })
        logger.info("command finished", extra={"duration_ms": duration_ms})
        self.current_process = None
        if timed_out:
            raise TimeoutError(f"Command timed out after {timeout} seconds: {display}")
        return CommandResult(argv, exit_code, "".join(stdout_parts), "".join(stderr_parts), duration_ms)

    async def cancel(self) -> None:
        self.cancelled = True
        await self._terminate_tree()

    async def _terminate_tree(self) -> None:
        process = self.current_process
        if process is None:
            return
        if os.name == "nt":
            if process.returncode is None:
                try:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=5)
                except (ProcessLookupError, asyncio.TimeoutError):
                    if process.returncode is None:
                        process.kill()
                        await process.wait()
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        if process.returncode is None:
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass
        else:
            await asyncio.sleep(0)
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        if process.returncode is None:
            await process.wait()


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
