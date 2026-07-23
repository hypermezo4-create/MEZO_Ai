from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import open_source_api
from src.open_source_db import Database


class FakeQueue:
    def __init__(self):
        self.items = []
    def rpush(self, _name, value): self.items.append(value); return len(self.items)
    def lpop(self, _name): return self.items.pop(0) if self.items else None
    def publish(self, _name, _value): return 1
    def ping(self): return True


def test_single_user_task_flow_has_no_login(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("MEZO_SQLITE_PATH", str(tmp_path / "cluster.db"))
    store = Database(); store.migrate(); broker = FakeQueue()
    monkeypatch.setattr(open_source_api, "database", store)
    monkeypatch.setattr(open_source_api, "queue", lambda: broker)
    monkeypatch.setattr(open_source_api, "RUNNER_TOKEN", "runner-test-token")
    app = FastAPI(); app.include_router(open_source_api.router)
    client = TestClient(app)
    paths = {route.path for route in app.routes}
    assert not any("login" in path or "bootstrap" in path or "register" in path for path in paths)
    project = client.post("/api/projects", json={"name": "demo", "repository_url": "https://github.com/example/demo", "default_branch": "main"}).json()
    task = client.post("/api/tasks", json={"project_id": project["id"], "prompt": "Make a safe change", "mode": "coding"})
    assert task.status_code == 201
    leased = client.post("/api/runner/lease?runner_id=runner-one", headers={"Authorization": "Bearer runner-test-token"})
    assert leased.status_code == 200 and leased.json()["id"] == task.json()["id"]
    finished = client.post(
        f"/api/runner/tasks/{task.json()['id']}/complete",
        headers={"Authorization": "Bearer runner-test-token"},
        json={"status": "completed", "changed_files": [{"path": "README.md"}], "diff_text": "diff", "reviewer_chain": ["qwen-coder", "deepseek"]},
    )
    assert finished.status_code == 200
    assert finished.json()["reviewer_chain"] == ["qwen-coder", "deepseek"]


def test_cluster_status_always_describes_exactly_nine_slots():
    slots = open_source_api.machine_slots(
        [
            {
                "machine_id": "runner-machine",
                "role": "runner-1",
                "app": "mezo-ai",
                "status": "online",
            }
        ],
        {"healthy": True, "models": {}},
    )

    expected_slot_ids = {
        "control",
        "runner-1",
        "runner-2",
        "coder-1",
        "coder-2",
        "reasoning",
        "reviewer",
        "vision",
        "utility",
    }

    assert len(slots) == 9
    assert {slot["slot_id"] for slot in slots} == expected_slot_ids
    assert sum(slot["role"].startswith("runner-") for slot in slots) == 2
    assert sum(slot["role"].startswith("coder-") for slot in slots) == 2
    assert next(
        slot for slot in slots if slot["slot_id"] == "runner-1"
    )["machine_id"] == "runner-machine"
    assert all(slot["app"] == "mezo-ai" for slot in slots)
    assert all(slot["region"] == "ord" for slot in slots)
    assert all(slot["memory_mb"] == 131072 for slot in slots)
