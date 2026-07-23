from __future__ import annotations

import asyncio
import os
import secrets
import time
from collections import defaultdict
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request


app = FastAPI(title="MEZO Router", version="2.1.0", docs_url=None, redoc_url=None)
ORCHESTRATOR_TOKEN = os.getenv("ORCHESTRATOR_INTERNAL_TOKEN", "")
MODEL_TOKEN = os.getenv("MODEL_INTERNAL_TOKEN", "")
APP_NAME = os.getenv("MEZO_APP_NAME", "mezo-ai")


def endpoint_list(name: str) -> list[str]:
    return [value.strip().rstrip("/") for value in os.getenv(name, "").split(",") if value.strip()]


MODEL_CATALOG: dict[str, dict[str, str]] = {
    "fast": {
        "label": "MEZO Fast",
        "purpose": "Fast chat, routing, summaries, and lightweight tasks",
    },
    "coding": {
        "label": "Qwen Coder",
        "purpose": "Repository inspection, code generation, edits, and tests",
    },
    "deep": {
        "label": "GLM Reasoning",
        "purpose": "Architecture, difficult analysis, and long-horizon planning",
    },
    "debug": {
        "label": "DeepSeek Reviewer",
        "purpose": "Independent review, debugging, security, and risk detection",
    },
    "vision": {
        "label": "Qwen Vision",
        "purpose": "Images, screenshots, interfaces, and visual documents",
    },
}

ENDPOINTS = {
    "fast": endpoint_list("FAST_URL"),
    "coding": endpoint_list("CODER_ENDPOINTS"),
    "deep": endpoint_list("REASONING_URL"),
    "debug": endpoint_list("REVIEWER_URL"),
    "vision": endpoint_list("VISION_URL"),
}
failures: dict[str, int] = defaultdict(int)
open_until: dict[str, float] = defaultdict(float)
positions: dict[str, int] = defaultdict(int)


def authorize(value: str | None) -> None:
    expected = f"Bearer {ORCHESTRATOR_TOKEN}"
    if not ORCHESTRATOR_TOKEN or not value or not secrets.compare_digest(value, expected):
        raise HTTPException(401, "Invalid orchestration credential")


def message_text(body: dict[str, Any]) -> str:
    return " ".join(str(item.get("content", "")) for item in body.get("messages", [])).lower()


def classify(body: dict[str, Any]) -> str:
    requested = str(body.pop("mezo_mode", "auto")).strip().lower()
    if requested != "auto":
        return requested

    text = message_text(body)
    if any(word in text for word in (
        "screenshot", "image", "photo", "dialog", "pixel", "visual", "ui mockup",
        "صورة", "صوره", "لقطة شاشة", "سكرين شوت", "واجهة مرئية",
    )):
        return "vision"
    if any(word in text for word in (
        "review", "audit", "security", "vulnerability", "bug hunt", "root cause",
        "راجع", "مراجعة", "امان", "أمان", "ثغرة", "ثغرات", "سبب المشكلة",
    )):
        return "debug" if ENDPOINTS["debug"] else "coding"
    if any(word in text for word in (
        "architecture", "migration", "distributed", "long-horizon", "design system",
        "معمارية", "هندسة النظام", "خطة طويلة", "تصميم النظام", "بنية المشروع",
    )):
        return "deep"
    if body.get("tools") or any(word in text for word in (
        "code", "repository", "test", "fix", "implement", "refactor", "pull request",
        "كود", "مشروع", "مستودع", "اختبار", "اختبارات", "صلح", "اصلح", "نفذ", "عدّل", "عدل",
    )):
        return "coding"
    return "fast"


async def call_model(kind: str, body: dict[str, Any], timeout: float = 900) -> dict[str, Any]:
    if kind not in ENDPOINTS:
        raise HTTPException(400, f"Unknown MEZO mode: {kind}")
    if open_until[kind] > time.monotonic():
        raise HTTPException(503, f"{kind} circuit is open")

    payload = dict(body)
    payload["model"] = "local"
    endpoints = ENDPOINTS[kind]
    if not endpoints:
        raise HTTPException(503, f"{kind} model is not configured")

    start = positions[kind] % len(endpoints)
    positions[kind] += 1
    last_error: Exception | None = None
    for offset in range(len(endpoints)):
        endpoint = endpoints[(start + offset) % len(endpoints)]
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10)) as client:
                response = await client.post(
                    f"{endpoint}/chat/completions",
                    headers={"Authorization": f"Bearer {MODEL_TOKEN}"},
                    json=payload,
                )
            response.raise_for_status()
            failures[kind] = 0
            open_until[kind] = 0
            return response.json()
        except httpx.HTTPError as exc:
            last_error = exc

    failures[kind] += 1
    if failures[kind] >= 3:
        open_until[kind] = time.monotonic() + 30
    raise HTTPException(503, f"{kind} model unavailable: {type(last_error).__name__}") from last_error


@app.get("/healthz")
def health() -> dict[str, Any]:
    configured = sum(bool(urls) for urls in ENDPOINTS.values())
    return {"status": "ok", "configured_specialists": configured, "app": APP_NAME}


@app.get("/cluster")
async def cluster(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    authorize(authorization)

    async def probe(kind: str, urls: list[str]) -> tuple[str, dict[str, Any]]:
        started = time.monotonic()
        replicas: list[dict[str, Any]] = []
        for url in urls:
            try:
                async with httpx.AsyncClient(timeout=4) as client:
                    response = await client.get(
                        f"{url}/models",
                        headers={"Authorization": f"Bearer {MODEL_TOKEN}"},
                    )
                replicas.append({"endpoint": url, "healthy": response.status_code == 200})
            except httpx.HTTPError as exc:
                replicas.append({"endpoint": url, "healthy": False, "error": type(exc).__name__})

        healthy_replicas = sum(1 for item in replicas if item["healthy"])
        metadata = MODEL_CATALOG[kind]
        return kind, {
            "label": metadata["label"],
            "purpose": metadata["purpose"],
            "configured": bool(urls),
            "healthy": healthy_replicas > 0,
            "replica_count": len(replicas),
            "healthy_replicas": healthy_replicas,
            "replicas": replicas,
            "latency_ms": round((time.monotonic() - started) * 1000),
            "circuit_open": open_until[kind] > time.monotonic(),
        }

    values = await asyncio.gather(*(probe(kind, urls) for kind, urls in ENDPOINTS.items()))
    models = {kind: value for kind, value in values}
    return {
        "app": APP_NAME,
        "healthy": any(value["healthy"] for value in models.values()),
        "configured_specialists": sum(bool(urls) for urls in ENDPOINTS.values()),
        "healthy_specialists": sum(bool(value["healthy"]) for value in models.values()),
        "models": models,
    }


@app.get("/v1/models")
def models(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    authorize(authorization)
    return {
        "object": "list",
        "data": [
            {
                "id": kind,
                "object": "model",
                "owned_by": "mezo",
                "configured": bool(ENDPOINTS[kind]),
                **MODEL_CATALOG[kind],
            }
            for kind in ENDPOINTS
        ],
    }


@app.post("/v1/chat/completions")
async def completions(request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    authorize(authorization)
    body = await request.json()
    mode = classify(body)

    if mode == "multi" and not body.get("tools"):
        specialist_order = ["deep", "coding", "debug"]
        available = [kind for kind in specialist_order if ENDPOINTS[kind]]
        if not available:
            return await call_model("fast", body)

        results = await asyncio.gather(
            *(call_model(kind, body) for kind in available),
            return_exceptions=True,
        )
        candidates: list[tuple[str, dict[str, Any], str]] = []
        for kind, result in zip(available, results, strict=True):
            if not isinstance(result, dict):
                continue
            try:
                content = str(result["choices"][0]["message"].get("content", "")).strip()
            except (KeyError, IndexError, TypeError):
                continue
            if content:
                candidates.append((kind, result, content))

        if not candidates:
            raise HTTPException(503, "All configured specialist models failed")
        if len(candidates) == 1 or not ENDPOINTS["fast"]:
            return candidates[0][1]

        combine = {
            "messages": [
                {
                    "role": "system",
                    "content": "Combine the specialist answers into one precise MEZO response. Prefer concrete, safe, evidence-backed conclusions and resolve disagreements explicitly.",
                },
                {
                    "role": "user",
                    "content": "\n\n".join(
                        f"--- {MODEL_CATALOG[kind]['label']} ---\n{content}"
                        for kind, _result, content in candidates
                    ),
                },
            ],
            "temperature": 0.1,
        }
        return await call_model("fast", combine)

    target = {
        "fast": "fast",
        "coding": "coding",
        "deep": "deep",
        "debug": "debug",
        "vision": "vision",
    }.get(mode, "coding")
    return await call_model(target, body)


@app.post("/v1/review")
async def review(request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    authorize(authorization)
    body = await request.json()
    prompt = (
        "Review this proposed patch for correctness, security, missing tests, regressions, and unsafe assumptions. "
        "Return actionable findings only and distinguish blockers from suggestions.\n\n"
        + str(body.get("diff", ""))[:400_000]
    )
    payload = {"messages": [{"role": "user", "content": prompt}], "temperature": 0.1}
    try:
        response = await call_model("debug", payload)
        reviewer = "deepseek"
    except HTTPException:
        response = await call_model("coding", payload)
        reviewer = "qwen-stage1-fallback"
    return {"reviewer": reviewer, "content": response["choices"][0]["message"].get("content", "")}
