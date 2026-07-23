from fastapi import HTTPException
import pytest

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


def test_model_catalog_exposes_specialist_metadata(monkeypatch):
    monkeypatch.setitem(main.ENDPOINTS, "coding", ["http://coder.internal/v1"])

    assert bool(main.ENDPOINTS["coding"]) is True
    assert main.MODEL_CATALOG["coding"]["label"] == "Qwen Coder"
    assert "repository" in main.MODEL_CATALOG["coding"]["purpose"].lower()
    assert main.MODEL_CATALOG["vision"]["label"] == "Qwen Vision"


def test_internal_credentials_are_enforced(monkeypatch):
    monkeypatch.setattr(main, "ORCHESTRATOR_TOKEN", "test-token")

    main.authorize("Bearer test-token")
    with pytest.raises(HTTPException) as exc:
        main.authorize("Bearer wrong-token")

    assert exc.value.status_code == 401


def test_explicit_mode_is_not_reclassified():
    body = {
        "mezo_mode": "deep",
        "messages": [{"role": "user", "content": "write code"}],
    }

    assert main.classify(body) == "deep"
