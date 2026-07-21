from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import signal
import socket
from pathlib import Path

from runner.api_client import ApiClient, ApiError
from runner.executor import TaskExecutor


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for name in ("task_id", "runner_id", "duration_ms", "failure_category"):
            value = getattr(record, name, None)
            if value is not None:
                payload[name] = value
        return json.dumps(payload, separators=(",", ":"))


handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), handlers=[handler], force=True)
logger = logging.getLogger("mezo.runner")


def remove_stale_workspaces(root: str) -> int:
    allowed_root = Path(root).resolve(strict=True)
    removed = 0
    for user_directory in allowed_root.iterdir():
        if user_directory.name.startswith(".") or user_directory.is_symlink() or not user_directory.is_dir():
            continue
        for task_directory in user_directory.iterdir():
            if task_directory.is_symlink() or not task_directory.is_dir():
                continue
            resolved = task_directory.resolve(strict=True)
            if resolved.parent.parent != allowed_root:
                raise RuntimeError(f"Refusing stale cleanup outside workspace root: {resolved}")
            shutil.rmtree(resolved)
            removed += 1
        try:
            user_directory.rmdir()
        except OSError:
            pass
    return removed


class RunnerDaemon:
    def __init__(self) -> None:
        self.workspace_root = os.getenv("WORKSPACE_ROOT", "/workspaces")
        self.data_root = os.getenv("RUNNER_DATA_ROOT", "/data")
        self.api = ApiClient(os.environ["MEZO_API_URL"], f"{self.data_root}/runner-identity.json")
        self.current: TaskExecutor | None = None
        self.current_future: asyncio.Task | None = None
        self.stop = asyncio.Event()

    async def start(self) -> None:
        Path(self.workspace_root).mkdir(parents=True, exist_ok=True)
        Path(self.data_root).mkdir(parents=True, exist_ok=True)
        removed = remove_stale_workspaces(self.workspace_root)
        if removed:
            logger.info("removed %s stale task workspaces during startup recovery", removed)
        if os.geteuid() == 0:
            os.chown(self.data_root, 0, 0)
            os.chmod(self.data_root, 0o700)
        skills_root = Path(os.getenv("MEZO_SKILLS_ROOT", "/opt/mezo/skills"))
        installed_skills = [
            name
            for name in ("clean-code-guard", "test-guard", "docs-guard")
            if (skills_root / name / "SKILL.md").is_file()
        ]
        await self.api.register(
            os.getenv("RUNNER_NAME", socket.gethostname()),
            os.getenv("MEZO_RUNNER_VERSION", "1.0.0"),
            {
                "kilo": shutil.which("kilo") is not None,
                "skills": installed_skills,
                "max_concurrency": 1,
                "docker_cli": shutil.which("docker") is not None,
                "shellcheck": shutil.which("shellcheck") is not None,
            },
        )
        heartbeat = asyncio.create_task(self._heartbeats())
        try:
            while not self.stop.is_set():
                if self.current_future is None:
                    await self._lease_once()
                elif self.current_future.done():
                    await self._finish_current()
                await asyncio.sleep(float(os.getenv("RUNNER_POLL_SECONDS", "2")))
        finally:
            if self.current_future and not self.current_future.done():
                self.current_future.cancel()
                await asyncio.gather(self.current_future, return_exceptions=True)
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)

    async def _lease_once(self) -> None:
        try:
            response = await self.api.lease()
        except ApiError as exc:
            if exc.status_code != 423:
                logger.error("task lease failed: %s", exc)
            return
        task = response.get("task")
        if not task:
            return
        self.current = TaskExecutor(self.api, self.workspace_root, task)
        self.current_future = asyncio.create_task(self.current.run(), name=f"task-{task['id']}")
        logger.info("leased task", extra={"task_id": task["id"], "runner_id": self.api.runner_id})

    async def _finish_current(self) -> None:
        assert self.current_future is not None
        executor = self.current
        try:
            await self.current_future
            outcome = "completed"
        except asyncio.CancelledError:
            outcome = "cancelled"
        except Exception as exc:
            outcome = "failed"
            logger.error(
                "task execution failed: %s",
                exc,
                extra={"task_id": executor.task_id if executor else None, "failure_category": type(exc).__name__},
            )
        if executor is not None:
            keep_failed = os.getenv("FAILED_WORKSPACE_RETENTION", "delete") == "keep"
            if outcome != "failed" or not keep_failed:
                try:
                    await self.api.event(executor.task_id, {"event_type": "cleanup", "timestamp": _now(), "message": "Deleting task workspace"})
                    executor.workspace.cleanup()
                except (ApiError, OSError, RuntimeError) as exc:
                    logger.error("workspace cleanup failed for %s: %s", executor.task_id, exc)
            else:
                try:
                    executor.workspace.lock_for_retention()
                    await self.api.event(executor.task_id, {"event_type": "cleanup", "timestamp": _now(), "message": "Retained failed workspace with root-only permissions"})
                except (ApiError, OSError, RuntimeError) as exc:
                    logger.error("workspace retention lock failed for %s: %s", executor.task_id, exc)
        self.current = None
        self.current_future = None

    async def _heartbeats(self) -> None:
        while True:
            usage = shutil.disk_usage(self.workspace_root)
            current_id = self.current.task_id if self.current else None
            try:
                response = await self.api.heartbeat(
                    status="busy" if current_id else "online",
                    current_task_id=current_id,
                    disk_total=usage.total,
                    disk_free=usage.free,
                )
                if current_id and response.get("cancel_task_id") == current_id and self.current:
                    await self.current.runner.cancel()
                    if self.current_future:
                        self.current_future.cancel()
            except ApiError as exc:
                logger.error("heartbeat failed: %s", exc)
            await asyncio.sleep(float(os.getenv("RUNNER_HEARTBEAT_SECONDS", "10")))

    async def shutdown(self) -> None:
        self.stop.set()
        if self.current:
            await self.current.runner.cancel()


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


async def amain() -> None:
    daemon = RunnerDaemon()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, lambda: asyncio.create_task(daemon.shutdown()))
    await daemon.start()


if __name__ == "__main__":
    asyncio.run(amain())
