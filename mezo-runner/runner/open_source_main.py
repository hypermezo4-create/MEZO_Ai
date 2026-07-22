from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

import httpx

from runner.open_source_agent import AgentLoop
from runner.workspace import Workspace


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("mezo.runner")
API_URL = os.getenv("MEZO_API_URL", "http://mezo-api.internal:8080").rstrip("/")
TOKEN = os.environ.get("RUNNER_INTERNAL_TOKEN", "")
ORCHESTRATOR_TOKEN = os.environ.get("ORCHESTRATOR_INTERNAL_TOKEN", "")
ROOT = os.getenv("WORKSPACE_ROOT", "/workspaces")
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
RUNNER_ID = os.getenv("FLY_MACHINE_ID", os.getenv("HOSTNAME", "runner-local"))


class Api:
    async def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.request(method, f"{API_URL}{path}", headers=HEADERS, json=body)
            response.raise_for_status()
            if not response.content:
                return None
            return response.json()

    async def event(self, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        await self.request("POST", f"/api/runner/tasks/{task_id}/events", {"event_type": event_type, "payload": payload})


api = Api()


async def heartbeat(status: str, task_id: str | None = None) -> None:
    usage = shutil.disk_usage(ROOT)
    await api.request("POST", "/api/runner/heartbeat", {
        "machine_id": RUNNER_ID, "status": status, "current_task_id": task_id,
        "disk_total_bytes": usage.total, "disk_free_bytes": usage.free, "version": "2.0.0-cluster",
        "region": os.getenv("FLY_REGION", "local"), "size": "performance-8x", "memory_mb": 65536,
    })


async def cancelled(task_id: str) -> bool:
    result = await api.request("GET", f"/api/runner/tasks/{task_id}/cancelled")
    return bool(result["cancelled"])


async def execute(task: dict[str, Any]) -> None:
    task_id = task["id"]
    workspace = Workspace(ROOT, "single-user", task_id)
    try:
        workspace.create()
        workspace.grant_task_user()

        async def event(kind: str, payload: dict[str, Any]) -> None:
            await api.event(task_id, kind, payload)

        agent = AgentLoop(workspace, event)
        await event("workspace_created", {"workspace_id": str(workspace.task_root.relative_to(Path(ROOT)))})
        clone = await agent.commands.run(
            ["git", "-c", "credential.helper=", "clone", "--single-branch", "--branch", task["default_branch"], "--", task["repository_url"], str(workspace.repo)],
            cwd=workspace.task_root, timeout=900,
        )
        if clone.exit_code != 0:
            raise RuntimeError(f"Public repository clone failed: {clone.stderr[-2000:]}")

        async def watch_cancel() -> None:
            while True:
                await asyncio.sleep(2)
                if await cancelled(task_id):
                    await agent.commands.cancel()
                    return

        watcher = asyncio.create_task(watch_cancel())
        try:
            assistant = await agent.run(task["prompt"], task["repository_url"], task["default_branch"])
        finally:
            watcher.cancel()
        if await cancelled(task_id):
            await api.request("POST", f"/api/runner/tasks/{task_id}/complete", {"status": "cancelled", "workspace_id": str(workspace.task_root)})
            return
        draft = await agent.commands.run(["git", "diff", "--no-ext-diff", "--binary"], cwd=workspace.repo, timeout=120)
        reviewer_chain = ["qwen-coder"]
        if draft.stdout:
            async with httpx.AsyncClient(timeout=900) as client:
                review_response = await client.post(
                    "http://mezo-router.internal:8080/v1/review",
                    headers={"Authorization": f"Bearer {ORCHESTRATOR_TOKEN}"},
                    json={"diff": draft.stdout},
                )
            review_response.raise_for_status()
            review = review_response.json()["content"]
            reviewer_chain.append("deepseek")
            await event("patch_review", {"reviewer": "deepseek", "message": review[:16000]})
            assistant = await agent.run(
                "Apply any valid findings from this independent review, reject incorrect findings, then rerun relevant tests.\n\n" + review,
                task["repository_url"], task["default_branch"],
            )
            reviewer_chain.append("qwen-coder-correction")
        check = await agent.commands.run(["git", "diff", "--check"], cwd=workspace.repo, timeout=60)
        if check.exit_code != 0:
            raise RuntimeError(f"git diff --check failed: {check.stderr}")
        diff = await agent.commands.run(["git", "diff", "--no-ext-diff", "--binary"], cwd=workspace.repo, timeout=120)
        names = await agent.commands.run(["git", "status", "--short"], cwd=workspace.repo, timeout=30)
        changed = [{"path": line[3:], "status": line[:2].strip()} for line in names.stdout.splitlines() if len(line) > 3]
        await api.request("POST", f"/api/runner/tasks/{task_id}/complete", {
            "status": "completed", "changed_files": changed, "diff_text": diff.stdout,
            "workspace_id": str(workspace.task_root.relative_to(Path(ROOT))), "assistant_message": assistant,
            "reviewer_chain": reviewer_chain,
        })
    except Exception as exc:
        logger.exception("task failed")
        try:
            state = "cancelled" if await cancelled(task_id) else "failed"
            await api.request("POST", f"/api/runner/tasks/{task_id}/complete", {
                "status": state, "workspace_id": str(workspace.task_root),
                "error": f"{type(exc).__name__}: {exc}",
            })
        except Exception:
            logger.exception("could not report task failure")


async def main() -> None:
    if not TOKEN or not ORCHESTRATOR_TOKEN:
        raise RuntimeError("Runner and orchestration tokens are required")
    Path(ROOT).mkdir(parents=True, exist_ok=True)
    poll = float(os.getenv("RUNNER_POLL_SECONDS", "2"))
    while True:
        try:
            await heartbeat("online")
            task = await api.request("POST", f"/api/runner/lease?runner_id={RUNNER_ID}")
            if task:
                await heartbeat("busy", task["id"])
                await execute(task)
                await heartbeat("online")
        except Exception:
            logger.exception("runner loop error")
        await asyncio.sleep(poll)


if __name__ == "__main__":
    asyncio.run(main())
