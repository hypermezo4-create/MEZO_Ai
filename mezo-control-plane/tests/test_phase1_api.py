from datetime import timedelta

from src.database import SessionLocal
from src.models import Approval, AuditLog, Task, TaskStatus, User, utcnow
from src.security import hash_password, issue_access_token
from src.task_state import transition_task


def test_authentication_rejects_bad_credentials_and_returns_expiring_token(client, owner_headers):
    bad = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "wrong"})
    assert bad.status_code == 401
    good = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "correct-horse-battery-staple"})
    assert good.status_code == 200
    assert good.json()["expires_in"] == 1800
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {good.json()['access_token']}"}).status_code == 200


def test_viewer_cannot_create_tasks_or_control_kill_switch(client, repository):
    with SessionLocal() as db:
        viewer = User(email="viewer@example.com", password_hash=hash_password("viewer-password-long"), role="viewer")
        db.add(viewer); db.commit()
        token, _ = issue_access_token(viewer)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post("/api/tasks", headers=headers, json={"repository_id": repository["id"], "title": "Not allowed", "description": "viewer task"})
    assert response.status_code == 403
    assert client.post("/api/admin/kill-switch/disarm", headers=headers).status_code == 403


def test_owner_can_create_role_bound_user_but_viewer_cannot(client, owner_headers):
    created = client.post(
        "/api/users",
        headers=owner_headers,
        json={"email": "operator@example.com", "password": "operator-password-long", "role": "operator"},
    )
    assert created.status_code == 201
    login = client.post(
        "/api/auth/login", json={"email": "operator@example.com", "password": "operator-password-long"}
    )
    assert login.status_code == 200
    operator_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.post(
        "/api/users",
        headers=operator_headers,
        json={"email": "viewer-two@example.com", "password": "viewer-password-long", "role": "viewer"},
    ).status_code == 403


def test_task_is_persisted_and_visible_to_new_client(client, owner_headers, task):
    from main import app
    from fastapi.testclient import TestClient
    with TestClient(app) as restarted:
        response = restarted.get(f"/api/tasks/{task['id']}", headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "queued"


def test_invalid_task_transition_fails_explicitly(task):
    with SessionLocal() as db:
        model = db.get(Task, task["id"])
        try:
            transition_task(model, TaskStatus.COMPLETED.value)
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 409
        else:
            raise AssertionError("invalid transition was accepted")


def test_runner_assignment_heartbeat_and_single_task_lease(client, task, runner):
    lease = client.post("/api/runner/tasks/lease", headers=runner["headers"])
    assert lease.json()["task"]["id"] == task["id"]
    second = client.post("/api/runner/tasks/lease", headers=runner["headers"])
    assert second.json()["reason"] == "runner_already_busy"
    heartbeat = client.post(
        "/api/runner/heartbeat",
        headers=runner["headers"],
        json={"status": "busy", "current_task_id": task["id"], "disk_total_bytes": 1000, "disk_free_bytes": 500},
    )
    assert heartbeat.status_code == 200
    rows = client.get("/api/runners", headers=_owner_token(client)).json()
    assert rows[0]["disk_free_bytes"] == 500


def test_expired_lease_is_recovered_by_another_runner(client, task, runner):
    client.post("/api/runner/tasks/lease", headers=runner["headers"])
    with SessionLocal() as db:
        model = db.get(Task, task["id"])
        model.status = "running"
        model.current_step = "implementation"
        model.steps[0].status = "completed"
        model.steps[1].status = "running"
        model.lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    second = client.post(
        "/api/runners/register",
        headers={"X-Runner-Registration-Token": "test-runner-registration-token"},
        json={"name": "runner-two", "version": "1.0.0", "capabilities": {}},
    ).json()
    response = client.post("/api/runner/tasks/lease", headers={"Authorization": f"Bearer {second['runner_token']}"})
    assert response.json()["task"]["id"] == task["id"]
    recovered = client.get(f"/api/tasks/{task['id']}", headers=_owner_token(client)).json()
    assert recovered["runner_id"] == second["runner_id"]
    assert all(step["status"] == "pending" for step in recovered["steps"])
    audit = client.get(f"/api/audit?task_id={task['id']}", headers=_owner_token(client)).json()
    assert any(row["action"] == "task.lease_recover" for row in audit["records"])


def test_approval_is_bound_to_diff_and_invalidated_on_change(client, owner_headers, ready_task):
    task_id = ready_task["id"]
    approval = client.get(f"/api/tasks/{task_id}/approval", headers=owner_headers).json()
    assert approval["diff_hash"] == ready_task["diff_hash"]
    assert client.post(f"/api/tasks/{task_id}/approval", headers=owner_headers, json={"decision": "approve"}).status_code == 200
    with SessionLocal() as db:
        model = db.get(Task, task_id); model.diff_hash = "f" * 64; db.commit()
    response = client.post(f"/api/tasks/{task_id}/pull-request", headers=owner_headers)
    assert response.status_code == 409
    assert client.get(f"/api/tasks/{task_id}/approval", headers=owner_headers).json()["state"] == "invalidated"


def test_approval_expiration_is_enforced(client, owner_headers, ready_task):
    with SessionLocal() as db:
        approval = db.query(Approval).filter(Approval.task_id == ready_task["id"]).one()
        approval.expires_at = utcnow() - timedelta(seconds=1); db.commit()
    response = client.post(f"/api/tasks/{ready_task['id']}/approval", headers=owner_headers, json={"decision": "approve"})
    assert response.status_code == 409
    assert client.get(f"/api/tasks/{ready_task['id']}/approval", headers=owner_headers).json()["state"] == "expired"


def test_failed_checks_prevent_approval_request(client, task, runner):
    client.post("/api/runner/tasks/lease", headers=runner["headers"])
    for state in ("planning", "running", "validating"):
        client.post(f"/api/runner/tasks/{task['id']}/transition", headers=runner["headers"], json={"status": state})
    response = client.post(
        f"/api/runner/tasks/{task['id']}/analysis-complete",
        headers=runner["headers"],
        json={
            "diff_text": "diff",
            "changed_files": [],
            "validation_report": {"commands": [{"exit_code": 1}], "guards": []},
            "pull_request_title": "Failed checks",
            "pull_request_body": "Must not publish",
            "commit_sha": "a" * 40,
        },
    )
    assert response.status_code == 409
    assert client.get(f"/api/tasks/{task['id']}", headers=_owner_token(client)).json()["status"] == "failed"


def test_pull_request_requires_explicit_approval(client, owner_headers, ready_task):
    response = client.post(f"/api/tasks/{ready_task['id']}/pull-request", headers=owner_headers)
    assert response.status_code == 409
    client.post(f"/api/tasks/{ready_task['id']}/approval", headers=owner_headers, json={"decision": "approve"})
    response = client.post(f"/api/tasks/{ready_task['id']}/pull-request", headers=owner_headers)
    assert response.status_code == 202
    assert response.json()["status"] == "creating_pull_request"


def test_owner_only_kill_switch_and_audit_integrity(client, owner_headers):
    response = client.post("/api/admin/kill-switch/disarm", headers=owner_headers)
    assert response.status_code == 200 and response.json()["armed"] is False
    audit = client.get("/api/audit", headers=owner_headers).json()
    assert audit["integrity_valid"] is True
    assert any(row["action"] == "kill_switch.disarm" for row in audit["records"])

    with SessionLocal() as db:
        record = db.query(AuditLog).order_by(AuditLog.id.asc()).first()
        record.details = {"altered": True}
        db.commit()
    assert client.get("/api/audit", headers=owner_headers).json()["integrity_valid"] is False


def _owner_token(client):
    response = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "correct-horse-battery-staple"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
