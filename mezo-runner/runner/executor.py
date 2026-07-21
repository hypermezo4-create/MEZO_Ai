from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any

from runner.api_client import ApiClient, ApiError
from runner.command import CommandResult, CommandRunner
from runner.workspace import Workspace


logger = logging.getLogger("mezo.runner.executor")


class TaskExecutionError(RuntimeError):
    pass


class TaskExecutor:
    def __init__(self, api: ApiClient, workspace_root: str, task: dict[str, Any]) -> None:
        self.api = api
        self.task = task
        self.task_id = task["id"]
        self.workspace = Workspace(workspace_root, task["user_id"], self.task_id)
        self.runner = CommandRunner(self.workspace, self._event, base_env={"HOME": str(self.workspace.task_root / ".home")})
        self.repo = self.workspace.repo
        self.commands: list[dict[str, Any]] = []
        self.tests: list[dict[str, Any]] = []
        self.guards: list[dict[str, Any]] = []

    async def _event(self, event: dict) -> None:
        await self.api.event(self.task_id, event)

    async def run(self) -> None:
        try:
            await self._workspace()
            await self._clone()
            instructions = await self._instructions()
            plan = await self._plan(instructions)
            await self._implement(instructions, plan)
            await self.api.transition(self.task_id, "validating", current_step="validation")
            await self._validate()
            await self._run_guards()
            await self._validate(after_guards=True)
            await self._commit_and_report()
            await self._wait_for_publish()
        except asyncio.CancelledError:
            await self.runner.cancel()
            await self._terminal_transition("cancelled", "Task cancelled")
            raise
        except Exception as exc:
            await self.runner.cancel()
            await self._terminal_transition("failed", str(exc))
            raise

    async def _terminal_transition(self, status: str, error: str) -> None:
        try:
            await self.api.transition(self.task_id, status, error=error[:4000])
        except ApiError as exc:
            logger.error("failed to persist terminal task state: %s", exc, extra={"task_id": self.task_id})

    async def _workspace(self) -> None:
        await self.api.step(self.task_id, 0, "running")
        self.workspace.create()
        (self.workspace.task_root / ".home").mkdir(mode=0o700)
        bundled_skills = Path(os.getenv("MEZO_SKILLS_ROOT", "/opt/mezo/skills"))
        if not bundled_skills.is_dir():
            raise TaskExecutionError("Required guard skills are not installed in the runner image")
        shutil.copytree(bundled_skills, self.workspace.task_root / ".home" / ".kilo" / "skills")
        self.workspace.grant_task_user()
        await self.api.transition(
            self.task_id,
            "planning",
            current_step="workspace",
            workspace_id=str(self.workspace.task_root.relative_to(self.workspace.allowed_root)),
        )
        await self.api.step(self.task_id, 0, "completed", result_summary="Isolated workspace created and contained")

    async def _clone(self) -> None:
        await self.api.step(self.task_id, 1, "running")
        clone_url = f"https://github.com/{self.task['repository']}.git"
        credentials = await self.api.request("GET", f"/api/runner/tasks/{self.task_id}/clone-credential")
        env = {
            "GIT_TERMINAL_PROMPT": "0",
            **self._askpass_env(credentials["username"], credentials["token"]),
        }
        try:
            result = await self.runner.run(["git", "clone", "--no-tags", clone_url, str(self.repo)], cwd=self.workspace.task_root, timeout=600, env=env)
            self._record(result, "clone")
            self._require_success(result)
        finally:
            self._remove_askpass()
        result = await self._command(["git", "switch", "-c", self.task["working_branch"], f"origin/{self.task['base_branch']}"], timeout=60)
        self._require_success(result)
        await self.api.step(self.task_id, 1, "completed", result_summary=f"Cloned {self.task['repository']} and created {self.task['working_branch']}")

    def _askpass_env(self, username: str, token: str) -> dict[str, str]:
        askpass = self.workspace.secrets / "git-askpass.sh"
        askpass.write_text('#!/bin/sh\ncase "$1" in *Username*) printf "%s" "$MEZO_GIT_USERNAME";; *) printf "%s" "$MEZO_GIT_TOKEN";; esac\n')
        askpass.chmod(0o700)
        if os.geteuid() == 0:
            os.chown(askpass, self.workspace.task_uid, self.workspace.task_gid)
        return {"GIT_ASKPASS": str(askpass), "MEZO_GIT_USERNAME": username, "MEZO_GIT_TOKEN": token}

    def _remove_askpass(self) -> None:
        askpass = self.workspace.secrets / "git-askpass.sh"
        if askpass.exists():
            askpass.unlink()

    async def _instructions(self) -> str:
        await self.api.step(self.task_id, 2, "running")
        candidates: list[Path] = []
        for name in ("AGENTS.md", "CONTRIBUTING.md", "README.md", "README.rst"):
            candidates.extend(path for path in self.repo.rglob(name) if ".git" not in path.parts)
        chunks: list[str] = []
        size = 0
        for path in sorted(set(candidates), key=lambda value: (len(value.parts), str(value))):
            resolved = self.workspace.resolve(path)
            text = resolved.read_text(errors="replace")
            if size + len(text) > 200_000:
                break
            chunks.append(f"\n## {resolved.relative_to(self.repo)}\n{text}")
            size += len(text)
        result = "".join(chunks) or "No repository instruction files were found."
        await self.api.event(self.task_id, {"event_type": "progress", "timestamp": _now(), "message": f"Read {len(chunks)} repository instruction files"})
        await self.api.step(self.task_id, 2, "completed", result_summary=f"Read {len(chunks)} repository instruction files")
        return result

    async def _plan(self, instructions: str) -> str:
        await self.api.step(self.task_id, 3, "running")
        self._write_kilo_config(read_only=True)
        prompt = (
            "Analyze the repository and the requested task. Do not modify files. Return a concise execution plan grounded in files you inspected. "
            "Do not claim any command ran unless you ran it.\n\n"
            f"Task title: {self.task['title']}\nTask: {self.task['description']}\nRepository instructions:\n{instructions[:120000]}"
        )
        result = await self._kilo(prompt, timeout=900)
        self._require_success(result)
        plan = _kilo_text(result.stdout)
        if not plan:
            raise TaskExecutionError("Kilo returned an empty execution plan")
        await self.api.step(self.task_id, 3, "completed", result_summary=plan[-4000:])
        return plan

    async def _implement(self, instructions: str, plan: str) -> None:
        await self.api.transition(self.task_id, "running", current_step="implementation")
        await self.api.step(self.task_id, 4, "running")
        self._write_kilo_config(read_only=False)
        prompt = (
            "Implement the requested change inside this repository. Follow the repository instructions and the supplied plan. "
            "Do not push, create a PR, deploy, access paths outside the workspace, or print secrets. Run only locally safe checks. "
            "Leave the working tree with the completed implementation.\n\n"
            f"Task title: {self.task['title']}\nTask: {self.task['description']}\nPlan:\n{plan[-30000:]}\nInstructions:\n{instructions[:100000]}"
        )
        result = await self._kilo(prompt, timeout=int(os.getenv("KILO_TASK_TIMEOUT_SECONDS", "3600")))
        self._require_success(result)
        status = await self._command(["git", "status", "--short"], timeout=30)
        self._require_success(status)
        if not status.stdout.strip():
            raise TaskExecutionError("Kilo completed without producing repository changes")
        await self.api.step(self.task_id, 4, "completed", result_summary="Kilo completed with repository changes")

    def _write_kilo_config(self, *, read_only: bool) -> None:
        config_dir = self.workspace.task_root / ".home" / ".config" / "kilo"
        config_dir.mkdir(parents=True, exist_ok=True)
        edit_permission: Any = "deny" if read_only else {"*": "allow"}
        config = {
            "$schema": "https://app.kilo.ai/config.json",
            "permission": {
                "*": "deny",
                "read": "allow",
                "glob": "allow",
                "grep": "allow",
                "list": "allow",
                "skill": "allow",
                "edit": edit_permission,
                "write": "deny" if read_only else "allow",
                "apply_patch": "deny" if read_only else "allow",
                "external_directory": {"*": "deny"},
                "bash": {
                    "*": "deny",
                    "git status*": "allow",
                    "git diff*": "allow",
                    "git log*": "allow",
                    "git show*": "allow",
                    "git grep*": "allow",
                },
            },
        }
        self.kilo_config_content = json.dumps(config)
        (config_dir / "kilo.json").write_text(self.kilo_config_content)

    async def _kilo(self, prompt: str, *, timeout: int) -> CommandResult:
        model = os.getenv("KILO_MODEL", "").strip()
        if not model:
            raise TaskExecutionError("KILO_MODEL must explicitly select a provider/model")
        credential_names = ("KILOCODE_API_KEY", "KILO_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY")
        kilo_env = {name: os.environ[name] for name in credential_names if os.getenv(name)}
        kilo_env.update({
            "KILO_CONFIG_CONTENT": self.kilo_config_content,
            "KILO_DISABLE_AUTO_UPDATE": "true",
            "KILO_DISABLE_PROJECT_CONFIG": "true",
        })
        result = await self.runner.run(
            ["kilo", "run", "--pure", "--auto", "--format", "json", "--model", model, prompt],
            cwd=self.repo,
            timeout=timeout,
            env=kilo_env,
        )
        self._record(result, "kilo")
        return result

    async def _validate(self, *, after_guards: bool = False) -> None:
        if not after_guards:
            await self.api.step(self.task_id, 5, "running")
        commands = self._validation_commands(install=not after_guards)
        if not commands:
            commands = [["git", "diff", "--check"]]
        for argv in commands:
            result = await self._command(argv, timeout=1200)
            self.tests.append({"command": " ".join(argv), "exit_code": result.exit_code, "duration_ms": result.duration_ms, "phase": "post_guard" if after_guards else "project"})
            self._require_success(result)
        if not after_guards:
            await self.api.step(self.task_id, 5, "completed", result_summary=f"Completed {len(commands)} repository validation commands")

    def _validation_commands(self, *, install: bool) -> list[list[str]]:
        commands: list[list[str]] = []
        package_json = self.repo / "package.json"
        if package_json.exists():
            package = json.loads(package_json.read_text())
            if install and (self.repo / "package-lock.json").exists():
                commands.append(["npm", "ci"])
            scripts = package.get("scripts", {})
            for name in ("lint", "typecheck", "test", "build"):
                if name in scripts:
                    commands.append(["npm", "run", name])
        python_tests = list(self.repo.glob("test_*.py")) + list(self.repo.glob("tests/test_*.py"))
        if python_tests:
            if install and (self.repo / "requirements.txt").exists():
                commands.append(["pip3", "install", "--user", "-r", "requirements.txt"])
            commands.append(["python3", "-m", "pytest", "-q"])
        shell_files = [path for path in self.repo.rglob("*.sh") if ".git" not in path.parts]
        if shell_files:
            commands.append(["shellcheck", *[str(path.relative_to(self.repo)) for path in shell_files[:200]]])
        commands.append(["git", "diff", "--check"])
        return commands

    async def _run_guards(self) -> None:
        await self.api.step(self.task_id, 6, "running")
        changed = await self._command(["git", "diff", "--name-only"], timeout=30)
        self._require_success(changed)
        names = [name for name in changed.stdout.splitlines() if name]
        guard_names = ["clean-code-guard"]
        if any(_is_test(name) for name in names):
            guard_names.append("test-guard")
        if any(_is_docs(name) for name in names):
            guard_names.append("docs-guard")
        self._write_kilo_config(read_only=True)
        for guard in guard_names:
            prompt = (
                f"Use ${guard} on the current uncommitted diff. Review only; do not modify files. "
                "Follow the skill exactly. End with one machine-readable line: MEZO_GUARD_RESULT: PASS if no blocking findings, "
                "otherwise MEZO_GUARD_RESULT: FAIL."
            )
            result = await self._kilo(prompt, timeout=900)
            guard_text = _kilo_text(result.stdout) if result.exit_code == 0 else ""
            marker = re.findall(r"MEZO_GUARD_RESULT:\s*(PASS|FAIL)", guard_text, flags=re.IGNORECASE)
            skill_loaded = _kilo_used_skill(result.stdout, guard) if result.exit_code == 0 else False
            passed = result.exit_code == 0 and skill_loaded and marker and marker[-1].upper() == "PASS"
            summary = ("Verified Kilo skill-tool invocation.\n" if skill_loaded else "Kilo did not verify skill-tool invocation.\n") + guard_text
            self.guards.append({"name": guard, "status": "passed" if passed else "failed", "exit_code": result.exit_code, "summary": summary[-4000:]})
            if not passed:
                raise TaskExecutionError(f"{guard} did not pass or did not emit a verifiable result marker")
        for guard in ({"test-guard", "docs-guard"} - set(guard_names)):
            self.guards.append({"name": guard, "status": "skipped_not_applicable", "exit_code": 0, "summary": "No applicable files changed"})
        await self.api.step(self.task_id, 6, "completed", result_summary=f"Guards passed: {', '.join(guard_names)}")

    async def _commit_and_report(self) -> None:
        await self._command(["git", "config", "user.name", "MEZO AI Runner"], timeout=30)
        await self._command(["git", "config", "user.email", "mezo-runner@users.noreply.github.com"], timeout=30)
        self._require_success(await self._command(["git", "add", "-A"], timeout=60))
        commit = await self._command(["git", "commit", "-m", self.task["title"][:200]], timeout=120)
        self._require_success(commit)
        diff = await self._command(["git", "diff", "--no-ext-diff", f"origin/{self.task['base_branch']}...HEAD"], timeout=120)
        self._require_success(diff)
        if not diff.stdout.strip():
            raise TaskExecutionError("Validated commit has an empty diff")
        if len(diff.stdout.encode()) > 2_000_000:
            raise TaskExecutionError("Diff exceeds the Phase 1 two-megabyte review limit")
        stats = await self._command(["git", "diff", "--numstat", f"origin/{self.task['base_branch']}...HEAD"], timeout=60)
        self._require_success(stats)
        commit_sha = await self._command(["git", "rev-parse", "HEAD"], timeout=30)
        self._require_success(commit_sha)
        changed_files = []
        for line in stats.stdout.splitlines():
            added, deleted, path = line.split("\t", 2)
            changed_files.append({"path": path, "additions": None if added == "-" else int(added), "deletions": None if deleted == "-" else int(deleted)})
        await self.api.step(self.task_id, 7, "running")
        report = {
            "diff_summary": {"files": len(changed_files), "additions": sum(item["additions"] or 0 for item in changed_files), "deletions": sum(item["deletions"] or 0 for item in changed_files)},
            "commands": self.commands,
            "tests": self.tests,
            "guards": self.guards,
            "known_risks": [],
        }
        body = _pull_request_body(self.task, report)
        await self.api.request(
            "POST", f"/api/runner/tasks/{self.task_id}/analysis-complete",
            json={
                "diff_text": diff.stdout,
                "changed_files": changed_files,
                "validation_report": report,
                "pull_request_title": self.task["title"],
                "pull_request_body": body,
                "commit_sha": commit_sha.stdout.strip(),
            },
        )

    async def _wait_for_publish(self) -> None:
        while True:
            command = await self.api.request("GET", f"/api/runner/tasks/{self.task_id}/publish-command")
            if command.get("action") == "cancel":
                raise asyncio.CancelledError
            if command.get("action") == "push_branch":
                local_sha = await self._command(["git", "rev-parse", "HEAD"], timeout=30)
                self._require_success(local_sha)
                if local_sha.stdout.strip() != command.get("commit_sha"):
                    raise TaskExecutionError("Local commit changed after approval; publish authorization is invalid")
                await self.api.step(self.task_id, 7, "completed", result_summary="Approval verified for the exact diff")
                await self.api.step(self.task_id, 8, "running")
                env = {"GIT_TERMINAL_PROMPT": "0", **self._askpass_env(command["username"], command["token"])}
                try:
                    result = await self.runner.push_approved_branch(
                        repository=self.task["repository"],
                        branch=self.task["working_branch"],
                        cwd=self.repo,
                        env=env,
                    )
                finally:
                    self._remove_askpass()
                self._require_success(result)
                sha = await self._command(["git", "rev-parse", "HEAD"], timeout=30)
                self._require_success(sha)
                response = await self.api.request(
                    "POST", f"/api/runner/tasks/{self.task_id}/branch-pushed", json={"commit_sha": sha.stdout.strip()}
                )
                await self.api.step(self.task_id, 8, "completed", result_summary=f"Draft Pull Request: {response['pull_request_url']}")
                return
            await asyncio.sleep(5)

    async def _command(self, argv: list[str], *, timeout: int) -> CommandResult:
        result = await self.runner.run(argv, cwd=self.repo, timeout=timeout)
        self._record(result, "validation")
        return result

    def _record(self, result: CommandResult, category: str) -> None:
        self.commands.append({"command": " ".join(result.argv), "exit_code": result.exit_code, "duration_ms": result.duration_ms, "category": category})

    @staticmethod
    def _require_success(result: CommandResult) -> None:
        if result.exit_code != 0:
            raise TaskExecutionError(f"Command failed with exit code {result.exit_code}: {' '.join(result.argv)}")


def _is_test(path: str) -> bool:
    name = path.lower()
    return "/tests/" in f"/{name}" or re.search(r"(?:test_|_test\.|\.test\.|\.spec\.)", name) is not None


def _is_docs(path: str) -> bool:
    name = path.lower()
    return name.endswith((".md", ".mdx", ".rst")) or name.startswith("docs/")


def _kilo_text(output: str) -> str:
    text_parts: list[str] = []
    for event in _kilo_events(output):
        if event.get("type") == "text":
            part = event.get("part") or {}
            text = part.get("text")
            if isinstance(text, str):
                text_parts.append(text)
    return "".join(text_parts).strip()


def _kilo_used_skill(output: str, skill_name: str) -> bool:
    for event in _kilo_events(output):
        part = event.get("part") or {}
        state = part.get("state") or {}
        inputs = state.get("input") or {}
        if (
            event.get("type") == "tool_use"
            and part.get("tool") == "skill"
            and state.get("status") == "completed"
            and (inputs.get("name") == skill_name or inputs.get("skill") == skill_name)
        ):
            return True
    return False


def _kilo_events(output: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TaskExecutionError("Kilo emitted malformed structured output") from exc
        if not isinstance(event, dict):
            raise TaskExecutionError("Kilo emitted a structured event that was not an object")
        events.append(event)
    return events


def _pull_request_body(task: dict[str, Any], report: dict[str, Any]) -> str:
    commands = "\n".join(f"- `{item['command']}` — exit {item['exit_code']}" for item in report["commands"])
    guards = "\n".join(f"- {item['name']}: {item['status']}" for item in report["guards"])
    return (
        f"## Summary\n\n{task['description']}\n\n"
        f"## Validation\n\n{commands}\n\n"
        f"## Guards\n\n{guards}\n\n"
        "## Rollback\n\nRevert this Pull Request commit. No deployment is performed by this task.\n\n"
        "## Known limitations\n\nGenerated by the Phase 1 runner and intentionally left as a Draft for human review."
    )


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
