from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx

from runner.command import CommandRunner
from runner.workspace import Workspace


EventSink = Callable[[str, dict[str, Any]], Awaitable[None]]

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List tracked and unignored files in the repository.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a UTF-8 text file within the repository.",
            "parameters": {
                "type": "object", "properties": {"path": {"type": "string"}},
                "required": ["path"], "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or replace one UTF-8 text file inside the repository.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"], "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_text",
            "description": "Search repository text with ripgrep.",
            "parameters": {
                "type": "object", "properties": {"pattern": {"type": "string"}},
                "required": ["pattern"], "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a bounded argv command in the repository. Shell syntax is not accepted.",
            "parameters": {
                "type": "object",
                "properties": {
                    "argv": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 80},
                    "timeout": {"type": "integer", "minimum": 1, "maximum": 900},
                },
                "required": ["argv"], "additionalProperties": False,
            },
        },
    },
]


class AgentLoop:
    def __init__(self, workspace: Workspace, events: EventSink) -> None:
        self.workspace = workspace
        self.events = events
        self.commands = CommandRunner(workspace, self._command_event)
        self.model_url = os.getenv("ROUTER_URL", "http://mezo-router.internal:8080/v1").rstrip("/")
        self.model_name = "coding"
        self.model_token = os.environ["ORCHESTRATOR_INTERNAL_TOKEN"]
        self.max_turns = int(os.getenv("AGENT_MAX_TURNS", "40"))

    async def _command_event(self, event: dict[str, Any]) -> None:
        await self.events(event.pop("event_type"), event)

    def _path(self, relative: str, *, allow_missing: bool = False) -> Path:
        candidate = self.workspace.repo / relative
        if allow_missing and not candidate.exists():
            parent = candidate.parent
            parent.mkdir(parents=True, exist_ok=True)
            return self.workspace.resolve(candidate, allow_missing=True)
        return self.workspace.resolve(candidate)

    async def tool(self, name: str, arguments: dict[str, Any]) -> str:
        if name == "list_files":
            result = await self.commands.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=self.workspace.repo, timeout=30)
            return result.stdout[:200_000]
        if name == "read_file":
            path = self._path(str(arguments["path"]))
            if not path.is_file() or path.stat().st_size > 1_000_000:
                raise ValueError("File is missing, non-text, or larger than 1 MB")
            return path.read_text(encoding="utf-8")
        if name == "write_file":
            content = str(arguments["content"])
            if len(content.encode()) > 1_000_000:
                raise ValueError("File content exceeds 1 MB")
            path = self._path(str(arguments["path"]), allow_missing=True)
            if path.exists() and path.is_symlink():
                raise ValueError("Refusing to write through a symlink")
            path.write_text(content, encoding="utf-8", newline="")
            return f"wrote {path.relative_to(self.workspace.repo)}"
        if name == "search_text":
            result = await self.commands.run(["rg", "--line-number", "--", str(arguments["pattern"]), "."], cwd=self.workspace.repo, timeout=60)
            return (result.stdout + result.stderr)[:200_000]
        if name == "run_command":
            argv = [str(item) for item in arguments["argv"]]
            timeout = int(arguments.get("timeout", 300))
            result = await self.commands.run(argv, cwd=self.workspace.repo, timeout=timeout)
            return json.dumps({"exit_code": result.exit_code, "stdout": result.stdout, "stderr": result.stderr})[:500_000]
        raise ValueError(f"Unknown tool: {name}")

    async def run(self, prompt: str, repository_url: str, default_branch: str) -> str:
        files = await self.commands.run(["git", "ls-files"], cwd=self.workspace.repo, timeout=30)
        system = (
            "You are MEZO, a careful coding agent operating in an isolated repository workspace. "
            "Use tools to inspect before editing, keep changes scoped to the request, run relevant tests, "
            "and never push, create pull requests, read credentials, or access paths outside the repository. "
            "Commands are argv arrays without shell evaluation. Finish with a concise summary and test results."
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Repository: {repository_url}\nBase branch: {default_branch}\nFiles:\n{files.stdout[:100_000]}\n\nTask:\n{prompt}"},
        ]
        headers = {"Authorization": f"Bearer {self.model_token}"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(900, connect=30)) as client:
            for turn in range(self.max_turns):
                await self.events("agent_turn", {"turn": turn + 1})
                response = await client.post(
                    f"{self.model_url}/chat/completions",
                    headers=headers,
                    json={"model": self.model_name, "mezo_mode": "coding", "messages": messages, "tools": TOOLS, "tool_choice": "auto", "temperature": 0.1},
                )
                response.raise_for_status()
                message = response.json()["choices"][0]["message"]
                messages.append(message)
                calls = message.get("tool_calls") or []
                if not calls:
                    return message.get("content") or "Task completed."
                for call in calls:
                    name = call["function"]["name"]
                    try:
                        arguments = json.loads(call["function"].get("arguments") or "{}")
                        await self.events("tool_call", {"name": name})
                        output = await self.tool(name, arguments)
                    except Exception as exc:
                        output = f"Tool error: {type(exc).__name__}: {exc}"
                    messages.append({"role": "tool", "tool_call_id": call["id"], "content": output})
        raise RuntimeError("Agent exceeded its maximum turn count")
