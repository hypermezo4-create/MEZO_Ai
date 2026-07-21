from src.github_app import GitHubAppClient


def test_task_to_draft_pull_request_integration(client, owner_headers, ready_task, monkeypatch):
    task_id = ready_task["id"]

    async def fake_create(self, **kwargs):
        return "https://github.com/hypermezo4-create/DeadZone_xiaomi-Lite/pull/123"

    async def fake_branch_sha(self, **kwargs):
        return "a" * 40

    monkeypatch.setattr(GitHubAppClient, "create_draft_pull_request", fake_create)
    monkeypatch.setattr(GitHubAppClient, "branch_sha", fake_branch_sha)
    approval = client.post(
        f"/api/tasks/{task_id}/approval",
        headers=owner_headers,
        json={"decision": "approve"},
    )
    assert approval.status_code == 200
    requested = client.post(f"/api/tasks/{task_id}/pull-request", headers=owner_headers)
    assert requested.status_code == 202
    result = client.post(
        f"/api/runner/tasks/{task_id}/branch-pushed",
        headers=ready_task["runner"]["headers"],
        json={"commit_sha": "a" * 40},
    )
    assert result.status_code == 200
    assert result.json() == {
        "pull_request_url": "https://github.com/hypermezo4-create/DeadZone_xiaomi-Lite/pull/123",
        "draft": True,
    }
    stored = client.get(f"/api/tasks/{task_id}", headers=owner_headers).json()
    assert stored["status"] == "completed"
    assert stored["pull_request_url"].endswith("/pull/123")


def test_draft_pull_request_rejects_a_branch_that_changed_after_approval(
    client, owner_headers, ready_task, monkeypatch
):
    async def changed_branch(self, **kwargs):
        return "b" * 40

    monkeypatch.setattr(GitHubAppClient, "branch_sha", changed_branch)
    task_id = ready_task["id"]
    client.post(f"/api/tasks/{task_id}/approval", headers=owner_headers, json={"decision": "approve"})
    client.post(f"/api/tasks/{task_id}/pull-request", headers=owner_headers)
    response = client.post(
        f"/api/runner/tasks/{task_id}/branch-pushed",
        headers=ready_task["runner"]["headers"],
        json={"commit_sha": "a" * 40},
    )
    assert response.status_code == 502
    assert client.get(f"/api/tasks/{task_id}", headers=owner_headers).json()["status"] == "failed"
