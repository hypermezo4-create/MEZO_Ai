"""
mezo-control-plane/src/plugins/docker_plugin.py

Docker operations for MEZO AI agents.
ALL actions route through PermissionGuard.

Requires: docker Python SDK. Plugin is a no-op if Docker is unavailable.
"""

import asyncio
import os
from typing import Optional

from src.orchestrator.permission_guard import (
    PermissionGuard, PluginAction, Tier, ExecutionResult
)

# ---------------------------------------------------------------------------
# Action declarations
# ---------------------------------------------------------------------------

ACTION_LIST_CONTAINERS = PluginAction(
    name="docker.list",
    description="List Docker containers",
    tier=Tier.READ,
)
ACTION_GET_LOGS = PluginAction(
    name="docker.logs",
    description="Get container logs",
    tier=Tier.READ,
)
ACTION_INSPECT = PluginAction(
    name="docker.inspect",
    description="Inspect a container",
    tier=Tier.READ,
)
ACTION_START = PluginAction(
    name="docker.start",
    description="Start a stopped container",
    tier=Tier.REVERSIBLE_WRITE,
    target_description="Starts the specified container (can be stopped again)",
)
ACTION_STOP = PluginAction(
    name="docker.stop",
    description="Stop a running container",
    tier=Tier.REVERSIBLE_WRITE,
    target_description="Stops the specified container (can be restarted)",
)
ACTION_BUILD = PluginAction(
    name="docker.build",
    description="Build a Docker image from a Dockerfile",
    tier=Tier.REVERSIBLE_WRITE,
    target_description="Builds a Docker image (can be removed later)",
)
ACTION_REMOVE_CONTAINER = PluginAction(
    name="docker.remove",
    description="Remove a Docker container",
    tier=Tier.IRREVERSIBLE,
    target_description="Permanently removes the container and its data (not the image)",
)
ACTION_PRUNE = PluginAction(
    name="docker.prune",
    description="Prune stopped containers and dangling images",
    tier=Tier.IRREVERSIBLE,
    target_description="Permanently removes stopped containers and dangling images",
)


class DockerPlugin:
    """
    Docker operations via the docker Python SDK.

    Lazy-loads docker SDK so the plugin doesn't crash if Docker is not installed.
    """

    def __init__(self, guard: PermissionGuard):
        self._guard = guard
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import docker
            except ImportError:
                raise RuntimeError("docker SDK not installed. Run: pip install docker")
            try:
                self._client = docker.from_env()
            except Exception as e:
                raise RuntimeError(f"Cannot connect to Docker daemon: {e}")
        return self._client

    async def list_containers(
        self, actor_user_id: str, session_id: str = "", all_containers: bool = False
    ) -> ExecutionResult:
        async def _exec():
            client = self._get_client()
            containers = await asyncio.to_thread(client.containers.list, all=all_containers)
            return {
                "containers": [
                    {
                        "id": c.short_id,
                        "name": c.name,
                        "image": c.image.tags[0] if c.image.tags else c.image.short_id,
                        "status": c.status,
                    }
                    for c in containers
                ]
            }

        return await self._guard.execute_if_permitted(
            action=ACTION_LIST_CONTAINERS, actor_user_id=actor_user_id,
            target="docker-containers", executor=_exec, session_id=session_id,
        )

    async def get_logs(
        self, container_id: str, actor_user_id: str, session_id: str = "", tail: int = 100
    ) -> ExecutionResult:
        async def _exec():
            client = self._get_client()
            container = await asyncio.to_thread(client.containers.get, container_id)
            log_bytes = await asyncio.to_thread(
                container.logs, tail=tail, timestamps=True
            )
            return {
                "container": container_id,
                "logs": log_bytes.decode("utf-8", errors="replace"),
                "tail": tail,
            }

        return await self._guard.execute_if_permitted(
            action=ACTION_GET_LOGS, actor_user_id=actor_user_id,
            target=container_id, executor=_exec, session_id=session_id,
        )

    async def stop_container(
        self, container_id: str, actor_user_id: str, session_id: str = "", timeout: int = 10
    ) -> ExecutionResult:
        async def _exec():
            client = self._get_client()
            container = await asyncio.to_thread(client.containers.get, container_id)
            await asyncio.to_thread(container.stop, timeout=timeout)
            container.reload()
            return {"container": container_id, "status": container.status}

        return await self._guard.execute_if_permitted(
            action=ACTION_STOP, actor_user_id=actor_user_id,
            target=container_id, executor=_exec, session_id=session_id,
        )

    async def start_container(
        self, container_id: str, actor_user_id: str, session_id: str = ""
    ) -> ExecutionResult:
        async def _exec():
            client = self._get_client()
            container = await asyncio.to_thread(client.containers.get, container_id)
            await asyncio.to_thread(container.start)
            container.reload()
            return {"container": container_id, "status": container.status}

        return await self._guard.execute_if_permitted(
            action=ACTION_START, actor_user_id=actor_user_id,
            target=container_id, executor=_exec, session_id=session_id,
        )

    async def remove_container(
        self,
        container_id: str,
        actor_user_id: str,
        confirm_callback,
        session_id: str = "",
        task_id: Optional[str] = None,
    ) -> ExecutionResult:
        async def _exec():
            client = self._get_client()
            container = await asyncio.to_thread(client.containers.get, container_id)
            await asyncio.to_thread(container.remove, force=True)
            return {"container": container_id, "removed": True}

        return await self._guard.execute_if_permitted(
            action=ACTION_REMOVE_CONTAINER, actor_user_id=actor_user_id,
            target=container_id, executor=_exec,
            confirm_callback=confirm_callback, session_id=session_id, task_id=task_id,
        )
