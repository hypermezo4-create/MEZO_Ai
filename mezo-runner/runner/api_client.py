from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx


class ApiError(RuntimeError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


class ApiClient:
    def __init__(self, base_url: str, state_path: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.state_path = Path(state_path)
        self.runner_id: str | None = None
        self.token: str | None = os.getenv("MEZO_RUNNER_TOKEN") or None
        if self.state_path.exists() and not self.token:
            self._load_state()

    def _load_state(self) -> None:
        import json
        data = json.loads(self.state_path.read_text())
        self.runner_id = data["runner_id"]
        self.token = data["runner_token"]

    def _save_state(self) -> None:
        import json
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps({"runner_id": self.runner_id, "runner_token": self.token}))
        self.state_path.chmod(0o600)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def request(self, method: str, path: str, *, json: dict | None = None, headers: dict | None = None) -> Any:
        try:
            async with httpx.AsyncClient(timeout=40.0) as client:
                response = await client.request(
                    method,
                    f"{self.base_url}{path}",
                    json=json,
                    headers={**self._headers(), **(headers or {})},
                )
        except httpx.RequestError as exc:
            raise ApiError(503, f"MEZO API request failed: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", f"HTTP {response.status_code}")
            except ValueError:
                detail = f"HTTP {response.status_code}"
            raise ApiError(response.status_code, str(detail))
        try:
            return response.json()
        except ValueError as exc:
            raise ApiError(502, "MEZO API returned an invalid JSON response") from exc

    async def register(self, name: str, version: str, capabilities: dict) -> None:
        if self.token:
            return
        registration_token = os.environ["RUNNER_REGISTRATION_TOKEN"]
        data = await self.request(
            "POST",
            "/api/runners/register",
            json={"name": name, "version": version, "capabilities": capabilities},
            headers={"X-Runner-Registration-Token": registration_token},
        )
        self.runner_id = data["runner_id"]
        self.token = data["runner_token"]
        self._save_state()

    async def heartbeat(self, *, status: str, current_task_id: str | None, disk_total: int, disk_free: int) -> dict:
        return await self.request(
            "POST", "/api/runner/heartbeat",
            json={"status": status, "current_task_id": current_task_id, "disk_total_bytes": disk_total, "disk_free_bytes": disk_free},
        )

    async def lease(self) -> dict:
        return await self.request("POST", "/api/runner/tasks/lease")

    async def transition(self, task_id: str, status: str, *, current_step: str | None = None, workspace_id: str | None = None, error: str | None = None) -> dict:
        return await self.request(
            "POST", f"/api/runner/tasks/{task_id}/transition",
            json={"status": status, "current_step": current_step, "workspace_id": workspace_id, "error": error},
        )

    async def step(self, task_id: str, step_index: int, status: str, **fields: Any) -> dict:
        return await self.request(
            "POST", f"/api/runner/tasks/{task_id}/steps",
            json={"step_index": step_index, "status": status, **fields},
        )

    async def event(self, task_id: str, event: dict) -> None:
        await self.request("POST", f"/api/runner/tasks/{task_id}/events", json=event)
