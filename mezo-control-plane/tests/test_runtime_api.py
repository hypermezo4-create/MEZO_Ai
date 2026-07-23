from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src import open_source_api, runtime_api
from src.open_source_db import Database, now


class FakeQueue:
    def __init__(self) -> None:
        self.items: list[str] = []

    def rpush(self, _name: str, value: str) -> int:
        self.items.append(value)
        return len(self.items)

    def ping(self) -> bool:
        return True


def client_with_store(monkeypatch, tmp_path) -> tuple[TestClient, Database]:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("WEB_DATABASE_URL", raising=False)
    monkeypatch.setenv("MEZO_SQLITE_PATH", str(tmp_path / "runtime.db"))
    store = Database()
    store.migrate()
    monkeypatch.setattr(open_source_api, "database", store)
    monkeypatch.setattr(open_source_api, "queue", lambda: FakeQueue())
    app = FastAPI()
    app.include_router(runtime_api.router)
    return TestClient(app), store


def test_failed_new_chat_is_rolled_back(monkeypatch, tmp_path):
    client, store = client_with_store(monkeypatch, tmp_path)

    async def fail_chat(_conversation_id: str, _mode: open_source_api.Mode) -> str:
        raise HTTPException(503, "router unavailable")

    monkeypatch.setattr(open_source_api, "chat_completion", fail_chat)
    response = client.post(
        "/api/dispatch",
        json={"prompt": "hello", "interaction": "chat", "mode": "fast"},
    )

    assert response.status_code == 503
    assert store.all("SELECT * FROM conversations") == []
    assert store.all("SELECT * FROM messages") == []


def test_failed_existing_chat_removes_only_failed_message(monkeypatch, tmp_path):
    client, store = client_with_store(monkeypatch, tmp_path)
    conversation_id, _ = open_source_api.ensure_conversation(None, "Existing")
    original = open_source_api.save_message(conversation_id, "assistant", "Ready")

    async def fail_chat(_conversation_id: str, _mode: open_source_api.Mode) -> str:
        raise HTTPException(503, "router unavailable")

    monkeypatch.setattr(open_source_api, "chat_completion", fail_chat)
    response = client.post(
        "/api/dispatch",
        json={
            "prompt": "try again",
            "conversation_id": conversation_id,
            "interaction": "chat",
            "mode": "fast",
        },
    )

    assert response.status_code == 503
    assert store.one("SELECT id FROM conversations WHERE id=?", (conversation_id,)) is not None
    messages = store.all("SELECT * FROM messages WHERE conversation_id=? ORDER BY id", (conversation_id,))
    assert [message["id"] for message in messages] == [original["id"]]
    assert messages[0]["content"] == "Ready"


def test_successful_chat_persists_one_conversation(monkeypatch, tmp_path):
    client, store = client_with_store(monkeypatch, tmp_path)

    async def complete_chat(_conversation_id: str, _mode: open_source_api.Mode) -> str:
        return "Hello from MEZO"

    monkeypatch.setattr(open_source_api, "chat_completion", complete_chat)
    response = client.post(
        "/api/dispatch",
        json={"prompt": "hello", "interaction": "chat", "mode": "fast"},
    )

    assert response.status_code == 201
    conversation_id = response.json()["conversation_id"]
    assert len(store.all("SELECT * FROM conversations")) == 1
    messages = store.all("SELECT * FROM messages WHERE conversation_id=? ORDER BY id", (conversation_id,))
    assert [message["role"] for message in messages] == ["user", "assistant"]


def test_projects_are_idempotent_and_deduplicated(monkeypatch, tmp_path):
    client, store = client_with_store(monkeypatch, tmp_path)
    repository_url = "https://github.com/example/demo"
    for identifier in ("old", "new"):
        store.execute(
            "INSERT INTO projects(id,name,repository_url,default_branch,created_at) VALUES(?,?,?,?,?)",
            (identifier, "Demo", repository_url, "main", now()),
        )

    listed = client.get("/api/projects")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    created = client.post(
        "/api/projects",
        json={"name": "Demo", "repository_url": repository_url, "default_branch": "main"},
    )
    assert created.status_code == 201
    assert len(store.all("SELECT * FROM projects")) == 2
