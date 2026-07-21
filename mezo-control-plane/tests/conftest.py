import os

os.environ.setdefault("MEZO_TESTING", "1")
os.environ.setdefault("MEZO_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:////tmp/mezo-api-tests.sqlite")

import pytest
from fastapi.testclient import TestClient

from main import app
from src.config import get_settings
from src.database import Base, engine


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def owner_headers(client):
    response = client.post(
        "/api/auth/bootstrap",
        headers={"X-MEZO-Bootstrap-Token": get_settings().bootstrap_token},
        json={"email": "owner@example.com", "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def repository(client, owner_headers):
    response = client.post(
        "/api/repositories",
        headers=owner_headers,
        json={"full_name": "hypermezo4-create/DeadZone_xiaomi-Lite", "default_branch": "main"},
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def runner(client):
    response = client.post(
        "/api/runners/register",
        headers={"X-Runner-Registration-Token": get_settings().runner_registration_token},
        json={"name": "runner-one", "version": "1.0.0", "capabilities": {"max_concurrency": 1}},
    )
    assert response.status_code == 201
    data = response.json()
    return {"id": data["runner_id"], "headers": {"Authorization": f"Bearer {data['runner_token']}"}}


@pytest.fixture
def task(client, owner_headers, repository):
    response = client.post(
        "/api/tasks",
        headers=owner_headers,
        json={"repository_id": repository["id"], "title": "Improve validation", "description": "Make one safe maintainability improvement"},
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def ready_task(client, task, runner):
    leased = client.post("/api/runner/tasks/lease", headers=runner["headers"])
    assert leased.status_code == 200 and leased.json()["task"]["id"] == task["id"]
    for state in ("planning", "running", "validating"):
        response = client.post(
            f"/api/runner/tasks/{task['id']}/transition",
            headers=runner["headers"],
            json={"status": state},
        )
        assert response.status_code == 200
    report = {
        "commands": [{"command": "pytest -q", "exit_code": 0}],
        "tests": [{"command": "pytest -q", "exit_code": 0}],
        "guards": [
            {"name": "clean-code-guard", "status": "passed", "exit_code": 0},
            {"name": "test-guard", "status": "skipped_not_applicable", "exit_code": 0},
            {"name": "docs-guard", "status": "skipped_not_applicable", "exit_code": 0},
        ],
        "known_risks": [],
    }
    response = client.post(
        f"/api/runner/tasks/{task['id']}/analysis-complete",
        headers=runner["headers"],
        json={
            "diff_text": "diff --git a/a.py b/a.py\n+safe = True\n",
            "changed_files": [{"path": "a.py", "additions": 1, "deletions": 0}],
            "validation_report": report,
            "pull_request_title": "Improve validation",
            "pull_request_body": "Validated safe improvement",
            "commit_sha": "a" * 40,
        },
    )
    assert response.status_code == 200
    return {**task, "diff_hash": response.json()["diff_hash"], "runner": runner}
