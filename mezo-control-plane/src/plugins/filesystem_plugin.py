"""
mezo-control-plane/src/plugins/filesystem_plugin.py

Filesystem operations for MEZO AI agents.
ALL actions route through PermissionGuard before execution.

Design from reference-audit-phase-f.md:
  - Atomic writes (temp file + rename — never partial writes)
  - Path containment enforced by PermissionGuard (not duplicated here)
  - SHA-256 hash returned after every write (audit trail)
  - Secret scan before writing (blocks accidental credential writes)
  - Tier declared at registration, not inferred at runtime
"""

import os
import re
import uuid
import hashlib
import asyncio
import aiofiles
from datetime import datetime, timezone
from typing import Optional

from src.orchestrator.permission_guard import (
    PermissionGuard, PluginAction, Tier, ExecutionResult
)

# ---------------------------------------------------------------------------
# Secret scan patterns (adapted from Ahmed_AI_Agent_Tools patterns)
# ---------------------------------------------------------------------------
_SECRET_PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "generic_api_key": re.compile(
        r'\b(?:TOKEN|SECRET|PASSWORD|API_KEY)\s*[=:]\s*["\'][^"\']{12,}["\']', re.IGNORECASE
    ),
    "fly_token": re.compile(r"FlyV1\s+[A-Za-z0-9+/=,_-]{40,}"),
    "bearer_token": re.compile(r"Bearer\s+[A-Za-z0-9._-]{30,}"),
}


def _scan_for_secrets(content: str) -> list[str]:
    """Returns list of pattern names that matched. Empty = clean."""
    return [name for name, pattern in _SECRET_PATTERNS.items() if pattern.search(content)]


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


# ---------------------------------------------------------------------------
# Action declarations (tier hard-coded at declaration time)
# ---------------------------------------------------------------------------

ACTION_LIST_DIR = PluginAction(
    name="fs.list_dir",
    description="List contents of a directory",
    tier=Tier.READ,
    requires_path_check=True,
)

ACTION_READ_FILE = PluginAction(
    name="fs.read",
    description="Read the contents of a file",
    tier=Tier.READ,
    requires_path_check=True,
)

ACTION_WRITE_FILE = PluginAction(
    name="fs.write",
    description="Write or create a file (atomic write via temp rename)",
    tier=Tier.REVERSIBLE_WRITE,
    target_description="Creates or overwrites a file in the allowed project root",
    requires_path_check=True,
)

ACTION_MOVE_FILE = PluginAction(
    name="fs.move",
    description="Move or rename a file within the allowed root",
    tier=Tier.REVERSIBLE_WRITE,
    target_description="Moves a file within the allowed project root",
    requires_path_check=True,
)

ACTION_DELETE_FILE = PluginAction(
    name="fs.delete",
    description="Permanently delete a file or empty directory",
    tier=Tier.IRREVERSIBLE,
    target_description="Permanently deletes the file — cannot be undone without git history",
    requires_path_check=True,
)


# ---------------------------------------------------------------------------
# FilesystemPlugin
# ---------------------------------------------------------------------------

class FilesystemPlugin:
    """
    Filesystem operations for MEZO AI.

    All public methods take (guard, actor_user_id, session_id, ...) and return
    ExecutionResult. They never execute filesystem operations directly —
    they compose an executor lambda and pass it to guard.execute_if_permitted().
    """

    def __init__(self, guard: PermissionGuard):
        self._guard = guard

    async def list_dir(
        self,
        path: str,
        actor_user_id: str,
        session_id: str = "",
    ) -> ExecutionResult:
        async def _exec():
            entries = []
            with os.scandir(path) as it:
                for entry in it:
                    stat = entry.stat()
                    entries.append({
                        "name": entry.name,
                        "type": "dir" if entry.is_dir() else "file",
                        "size_bytes": stat.st_size if entry.is_file() else None,
                        "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                    })
            return {"path": path, "entries": entries, "count": len(entries)}

        return await self._guard.execute_if_permitted(
            action=ACTION_LIST_DIR,
            actor_user_id=actor_user_id,
            target=path,
            executor=_exec,
            session_id=session_id,
        )

    async def read_file(
        self,
        path: str,
        actor_user_id: str,
        session_id: str = "",
        max_bytes: int = 1_048_576,  # 1 MB default
    ) -> ExecutionResult:
        async def _exec():
            size = os.path.getsize(path)
            if size > max_bytes:
                raise ValueError(
                    f"File is {size} bytes, exceeds read limit of {max_bytes} bytes. "
                    f"Use a smaller slice or increase max_bytes."
                )
            async with aiofiles.open(path, "r", encoding="utf-8", errors="replace") as f:
                content = await f.read()
            return {
                "path": path,
                "size_bytes": size,
                "sha256": _sha256(content.encode("utf-8", errors="replace")),
                "content": content,
            }

        return await self._guard.execute_if_permitted(
            action=ACTION_READ_FILE,
            actor_user_id=actor_user_id,
            target=path,
            executor=_exec,
            session_id=session_id,
        )

    async def write_file(
        self,
        path: str,
        content: str,
        actor_user_id: str,
        session_id: str = "",
        overwrite: bool = True,
    ) -> ExecutionResult:
        # Secret scan before scheduling execution
        hits = _scan_for_secrets(content)
        if hits:
            return ExecutionResult(
                ok=False,
                action_name=ACTION_WRITE_FILE.name,
                tier=Tier.REVERSIBLE_WRITE.value,
                target=path,
                blocked_reason=(
                    f"Secret scan detected likely credentials in content "
                    f"(patterns: {', '.join(hits)}). "
                    f"Use environment variables or .env files instead."
                ),
            )

        async def _exec():
            if not overwrite and os.path.exists(path):
                raise FileExistsError(f"File already exists and overwrite=False: {path}")

            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            tmp_path = path + f".{uuid.uuid4().hex[:8]}.tmp"
            try:
                async with aiofiles.open(tmp_path, "w", encoding="utf-8") as f:
                    await f.write(content)
                os.replace(tmp_path, path)  # atomic rename
            except Exception:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                raise

            encoded = content.encode("utf-8", errors="replace")
            return {
                "path": path,
                "size_bytes": len(encoded),
                "sha256": _sha256(encoded),
                "lines": content.count("\n") + 1,
            }

        return await self._guard.execute_if_permitted(
            action=ACTION_WRITE_FILE,
            actor_user_id=actor_user_id,
            target=path,
            executor=_exec,
            session_id=session_id,
        )

    async def move_file(
        self,
        src: str,
        dst: str,
        actor_user_id: str,
        session_id: str = "",
        confirm_callback=None,
    ) -> ExecutionResult:
        async def _exec():
            os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
            os.replace(src, dst)
            return {"source": src, "destination": dst}

        return await self._guard.execute_if_permitted(
            action=ACTION_MOVE_FILE,
            actor_user_id=actor_user_id,
            target=f"{src} -> {dst}",
            executor=_exec,
            session_id=session_id,
        )

    async def delete_file(
        self,
        path: str,
        actor_user_id: str,
        confirm_callback,
        session_id: str = "",
        task_id: Optional[str] = None,
    ) -> ExecutionResult:
        """
        Tier.IRREVERSIBLE — always requires explicit confirmation.
        confirm_callback must be provided; passing None causes an immediate block.
        """
        async def _exec():
            if os.path.isfile(path):
                os.remove(path)
            elif os.path.isdir(path):
                os.rmdir(path)  # only if empty; use shutil.rmtree for non-empty (separate action)
            else:
                raise FileNotFoundError(f"Path not found: {path}")
            return {"path": path, "deleted": True}

        return await self._guard.execute_if_permitted(
            action=ACTION_DELETE_FILE,
            actor_user_id=actor_user_id,
            target=path,
            executor=_exec,
            confirm_callback=confirm_callback,
            session_id=session_id,
            task_id=task_id,
        )
