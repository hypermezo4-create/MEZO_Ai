from __future__ import annotations

import os
import re
import shutil
from pathlib import Path


SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


class WorkspaceViolation(RuntimeError):
    pass


class Workspace:
    def __init__(self, root: str, user_id: str, task_id: str) -> None:
        if not SAFE_ID.fullmatch(user_id) or not SAFE_ID.fullmatch(task_id):
            raise WorkspaceViolation("Unsafe user or task identifier")
        self.allowed_root = Path(root).resolve(strict=True)
        self.task_root = self.allowed_root / user_id / task_id
        self.repo = self.task_root / "repo"
        self.secrets = self.task_root / ".runtime"
        self.task_uid = int(os.getenv("MEZO_TASK_UID", str(os.getuid())))
        self.task_gid = int(os.getenv("MEZO_TASK_GID", str(os.getgid())))

    def create(self) -> Path:
        self.task_root.mkdir(parents=True, mode=0o700, exist_ok=False)
        os.chmod(self.task_root, 0o700)
        self.secrets.mkdir(mode=0o700)
        self._assert_contained(self.task_root, allow_missing=False)
        return self.repo

    def grant_task_user(self) -> None:
        if os.geteuid() != 0:
            return
        for root, directories, files in os.walk(self.task_root):
            os.chown(root, self.task_uid, self.task_gid, follow_symlinks=False)
            for name in directories:
                os.chown(Path(root) / name, self.task_uid, self.task_gid, follow_symlinks=False)
            for name in files:
                os.chown(Path(root) / name, self.task_uid, self.task_gid, follow_symlinks=False)

    def lock_for_retention(self) -> None:
        if os.geteuid() != 0:
            raise WorkspaceViolation("Retaining a workspace safely requires root ownership")
        for root, directories, files in os.walk(self.task_root):
            os.chown(root, 0, 0, follow_symlinks=False)
            os.chmod(root, 0o700)
            for name in directories:
                path = Path(root) / name
                os.chown(path, 0, 0, follow_symlinks=False)
                if not path.is_symlink():
                    os.chmod(path, 0o700)
            for name in files:
                path = Path(root) / name
                os.chown(path, 0, 0, follow_symlinks=False)
                if not path.is_symlink():
                    os.chmod(path, 0o600)

    def resolve(self, path: str | Path, *, allow_missing: bool = False) -> Path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.task_root / candidate
        return self._assert_contained(candidate, allow_missing=allow_missing)

    def _assert_contained(self, candidate: Path, *, allow_missing: bool) -> Path:
        if allow_missing:
            parent = candidate.parent.resolve(strict=True)
            resolved = parent / candidate.name
        else:
            resolved = candidate.resolve(strict=True)
        try:
            resolved.relative_to(self.task_root.resolve(strict=True))
        except ValueError as exc:
            raise WorkspaceViolation(f"Path escapes task workspace: {candidate}") from exc
        current = self.task_root.resolve(strict=True)
        relative_parts = resolved.relative_to(current).parts
        for part in relative_parts:
            current = current / part
            if current.exists() and current.is_symlink():
                raise WorkspaceViolation(f"Symlink path component is forbidden: {current}")
        return resolved

    def cleanup(self) -> None:
        resolved = self.task_root.resolve(strict=True)
        self._assert_contained(resolved, allow_missing=False)
        if resolved == self.allowed_root or len(resolved.parts) <= len(self.allowed_root.parts) + 1:
            raise WorkspaceViolation("Refusing broad workspace cleanup")
        shutil.rmtree(resolved)
