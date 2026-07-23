from fastapi.testclient import TestClient

import main


def test_auto_routing_understands_arabic_specialists(monkeypatch):
    monkeypatch.setitem(main.ENDPOINTS, "debug", ["http://reviewer.internal/v1"])

    review = {
        "mezo_mode": "auto",
        "messages": [{"role": "user", "content": "راجع الكود وابحث عن الثغرات"}],
    }
    vision = {
        "mezo_mode": "auto",
        "messages": [{"role": "user", "content": "حلل صورة الواجهة ولقطة الشاشة"}],
    }
    coding = {
        "mezo_mode": "auto",
        "messages": [{"role": "user", "content": "اصلح اختبارات المشروع وعدل الكود"}],
    }

    assert main.classify(review) == "debug"
    assert main.classify(vision) == "vision"
    assert main.classify(coding) == "coding"


def test_models_endpoint_exposes_specialist_metadata(monkeypatch):
    monkeypatch.setattr(main, "ORCHESTRATOR_TOKEN", "test-token")
    monkeypatch.setitem(main.ENDPOINTS, "coding", ["http://coder.internal/v1"])
    client = TestClient(main.app)

    response = client.get("/v1/models", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200
    models = {item["id"]: item for item in response.json()["data"]}
    assert models["coding"]["configured"] is True
    assert models["coding"]["label"] == "Qwen Coder"
    assert "repository" in models["coding"]["purpose"].lower()
    assert models["vision"]["label"] == "Qwen Vision"


def test_explicit_mode_is_not_reclassified():
    body = {
        "mezo_mode": "deep",
        "messages": [{"role": "user", "content": "write code"}],
    }

    assert main.classify(body) == "deep"
