"""
mezo-training/src/auto_learning/user_model.py

Per-user working pattern model for MEZO AI personalization.

Two strictly separated categories:
  A. Working-pattern memory (category: workflow | preference | project_context)
     → Returned by get_relevant_context() and silently enriches the system prompt.
  B. Sensitive personal content (category: sensitive)
     → health, relationships, finances, emotional state.
     → MUST NOT appear in normal retrieval.
     → MUST NOT be exported or shared.
     → Requires explicit user opt-in to view.

Storage: JSON-lines file per user at:
  {MEZO_DB_DIR}/user_models/{user_id}.jsonl

Each line is a Fact JSON object. File is append-only; facts are marked
deleted by adding "deleted": true (not by removing lines — append-only audit).

Multi-user: facts are keyed by user_id, never shared or merged across accounts.
"""

import os
import uuid
import json
import re
import asyncio
from datetime import datetime, timezone
from typing import Optional

# ---------------------------------------------------------------------------
# Sensitive content detection patterns
# ---------------------------------------------------------------------------
_SENSITIVE_KEYWORDS = re.compile(
    r"\b(health|illness|sick|cancer|hospital|depression|anxiety|therapy|"
    r"divorce|relationship|marriage|grief|trauma|salary|debt|mortgage|"
    r"bankruptcy|finance|insurance|diagnosis|medication|pregnant|pregnancy)\b",
    re.IGNORECASE,
)

VALID_CATEGORIES = frozenset(["workflow", "preference", "project_context", "sensitive"])

_DEFAULT_DB_DIR = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..", "mezo-database", "user_models"
)


class Fact:
    """A single learned fact about a user."""

    __slots__ = ["id", "user_id", "category", "content", "source", "created_at", "deleted"]

    def __init__(
        self,
        user_id: str,
        category: str,
        content: str,
        source: str = "observation",
        fact_id: Optional[str] = None,
        created_at: Optional[str] = None,
        deleted: bool = False,
    ):
        self.id = fact_id or str(uuid.uuid4())
        self.user_id = user_id
        self.category = category if category in VALID_CATEGORIES else "preference"
        self.content = content
        self.source = source
        self.created_at = created_at or datetime.now(timezone.utc).isoformat()
        self.deleted = deleted

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "category": self.category,
            "content": self.content,
            "source": self.source,
            "created_at": self.created_at,
            "deleted": self.deleted,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Fact":
        return cls(
            user_id=d["user_id"],
            category=d.get("category", "preference"),
            content=d.get("content", ""),
            source=d.get("source", "observation"),
            fact_id=d.get("id"),
            created_at=d.get("created_at"),
            deleted=d.get("deleted", False),
        )


class Observation:
    """A raw observation fed to the user model for processing."""

    def __init__(
        self,
        event_type: str,
        content: str,
        accepted: Optional[bool] = None,
        metadata: Optional[dict] = None,
    ):
        self.event_type = event_type  # "tool_run" | "suggestion_accept" | "suggestion_reject" | "explicit_feedback"
        self.content = content
        self.accepted = accepted
        self.metadata = metadata or {}


class UserModel:
    """
    Per-user working pattern memory.

    Usage:
        model = UserModel()
        await model.observe("user-123", Observation("tool_run", "git status"))
        facts = await model.get_relevant_context("user-123", task_type="code_review")
        await model.delete_fact("user-123", fact_id)
        await model.wipe_model("user-123")
    """

    def __init__(self, db_dir: Optional[str] = None):
        self._db_dir = os.path.realpath(
            db_dir or os.environ.get("MEZO_USER_MODELS_DIR", _DEFAULT_DB_DIR)
        )
        os.makedirs(self._db_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # File helpers
    # ------------------------------------------------------------------

    def _path(self, user_id: str) -> str:
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", user_id)
        return os.path.join(self._db_dir, f"{safe_id}.jsonl")

    def _read_facts(self, user_id: str) -> list[Fact]:
        path = self._path(user_id)
        if not os.path.exists(path):
            return []
        # Keep track of latest state per fact_id (tombstone semantics)
        latest: dict[str, Fact] = {}
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    fact = Fact.from_dict(json.loads(line))
                    latest[fact.id] = fact  # later lines overwrite earlier ones
                except (json.JSONDecodeError, KeyError):
                    continue
        return list(latest.values())


    def _append_fact(self, fact: Fact) -> None:
        path = self._path(fact.user_id)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(fact.to_dict()) + "\n")

    # ------------------------------------------------------------------
    # Sensitive content detection
    # ------------------------------------------------------------------

    def _is_sensitive(self, content: str) -> bool:
        """Returns True if content appears to contain sensitive personal information."""
        return bool(_SENSITIVE_KEYWORDS.search(content))

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    async def observe(self, user_id: str, obs: Observation) -> Optional[Fact]:
        """
        Process an observation and potentially create a new Fact.

        Observations that appear sensitive are tagged as category='sensitive'
        and will never surface in normal retrieval.

        Returns the Fact if one was created, else None.
        """
        content = obs.content
        if not content:
            return None

        # Determine category
        if self._is_sensitive(content):
            category = "sensitive"
        elif obs.event_type in ("tool_run",):
            category = "workflow"
        elif obs.event_type in ("suggestion_accept", "suggestion_reject", "explicit_feedback"):
            category = "preference"
        else:
            category = "project_context"

        # Deduplicate: don't add the same content twice
        existing = await asyncio.to_thread(self._read_facts, user_id)
        for f in existing:
            if not f.deleted and f.content == content and f.category == category:
                return None  # already known

        fact = Fact(
            user_id=user_id,
            category=category,
            content=content,
            source=obs.event_type,
        )
        await asyncio.to_thread(self._append_fact, fact)
        return fact

    async def get_relevant_context(
        self,
        user_id: str,
        task_type: str = "general",
        include_sensitive: bool = False,
        max_facts: int = 10,
    ) -> list[dict]:
        """
        Returns a list of relevant facts for enriching the system prompt.

        NEVER returns sensitive facts unless include_sensitive=True
        (which requires explicit user opt-in — not for automatic prompt enrichment).
        """
        facts = await asyncio.to_thread(self._read_facts, user_id)
        active = [f for f in facts if not f.deleted]

        if not include_sensitive:
            active = [f for f in active if f.category != "sensitive"]

        # Simple relevance: workflow and project_context first, then preferences
        priority = {"workflow": 0, "project_context": 1, "preference": 2, "sensitive": 99}
        active.sort(key=lambda f: priority.get(f.category, 10))

        return [f.to_dict() for f in active[:max_facts]]

    async def get_all_facts(
        self,
        user_id: str,
        include_sensitive: bool = False,
    ) -> list[dict]:
        """Returns all facts for the user-facing Settings / MemoryPanel view."""
        facts = await asyncio.to_thread(self._read_facts, user_id)
        active = [f for f in facts if not f.deleted]
        if not include_sensitive:
            active = [f for f in active if f.category != "sensitive"]
        return [f.to_dict() for f in active]

    async def delete_fact(self, user_id: str, fact_id: str) -> bool:
        """
        Mark a fact as deleted. Returns True if found and deleted.
        The JSONL file is append-only; deletion is a tombstone record.
        """
        facts = await asyncio.to_thread(self._read_facts, user_id)
        target = next((f for f in facts if f.id == fact_id and not f.deleted), None)
        if target is None:
            return False

        target.deleted = True
        await asyncio.to_thread(self._append_fact, target)
        return True

    async def wipe_model(self, user_id: str) -> int:
        """
        Delete all facts for a user. Returns the count of facts wiped.
        Writes a tombstone for every active fact (append-only).
        """
        facts = await asyncio.to_thread(self._read_facts, user_id)
        active = [f for f in facts if not f.deleted]
        for fact in active:
            fact.deleted = True
            await asyncio.to_thread(self._append_fact, fact)
        return len(active)
