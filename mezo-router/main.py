from __future__ import annotations

import asyncio
import os
import secrets
import time
from collections import defaultdict
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request


app = FastAPI(title="MEZO Router", docs_url=None, redoc_url=None)
ORCHESTRATOR_TOKEN = os.getenv("ORCHESTRATOR_INTERNAL_TOKEN", "")
MODEL_TOKEN = os.getenv("MODEL_INTERNAL_TOKEN", "")
APP_NAME = os.getenv("MEZO_APP_NAME", "mezo-ai")


def endpoint_list(name: str) -> list[str]:
    return [value.strip().rstrip("/") for value in os.getenv(name, "").split(",") if value.strip()]


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


def classify(body: dict[str, Any]) -> str:
    requested = str(body.pop("mezo_mode", "auto"))
    if requested != "auto":
        return requested
    text = " ".join(str(item.get("content", "")) for item in body.get("messages", [])).lower()
    if any(word in text for word in ("screenshot", "image", "dialog", "pixel", "visual")):
        return "vision"
    if any(word in text for word in ("architecture", "migration", "distributed", "long-horizon")):
        return "deep"
    if body.get("tools") or any(word in text for word in ("code", "repository", "test", "fix", "implement")):
        return "coding"
    return "fast"


async def call_model(kind: str, body: dict[str, Any], timeout: float = 900) -> dict[str, Any]:
    if open_until[kind] > time.monotonic():
        raise HTTPException(503, f"{kind} circuit is open")
    payload = dict(body)
    payload["model"] = "local"
    endpoints = ENDPOINTS.get(kind, [])
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
            return response.json()
        except httpx.HTTPError as exc:
            last_error = exc
    failures[kind] += 1
    if failures[kind] >= 3:
        open_until[kind] = time.monotonic() + 30
    raise HTTPException(503, f"{kind} model unavailable: {type(last_error).__name__}") from last_error


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/cluster")
async def cluster(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    authorize(authorization)
    async def probe(kind: str, urls: list[str]) -> tuple[str, dict[str, Any]]:
        started = time.monotonic()
        replicas = []
        for url in urls:
            try:
                async with httpx.AsyncClient(timeout=4) as client:
                    response = await client.get(f"{url}/models", headers={"Authorization": f"Bearer {MODEL_TOKEN}"})
                replicas.append({"endpoint": url, "healthy": response.status_code == 200})
            except httpx.HTTPError as exc:
                replicas.append({"endpoint": url, "healthy": False, "error": type(exc).__name__})
        return kind, {"healthy": any(item["healthy"] for item in replicas), "replicas": replicas, "latency_ms": round((time.monotonic() - started) * 1000), "circuit_open": open_until[kind] > time.monotonic()}
    values = await asyncio.gather(*(probe(kind, urls) for kind, urls in ENDPOINTS.items()))
    return {"models": {kind: value for kind, value in values}}


@app.get("/v1/models")
def models(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    authorize(authorization)
    return {"object": "list", "data": [{"id": kind, "object": "model", "owned_by": "mezo"} for kind in ENDPOINTS]}


@app.post("/v1/chat/completions")
async def completions(request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    authorize(authorization)
    body = await request.json()
    mode = classify(body)
    if mode == "multi" and not body.get("tools"):
        results = await asyncio.gather(
            call_model("deep", body), call_model("coding", body), call_model("debug", body),
            return_exceptions=True,
        )
        candidates = [result["choices"][0]["message"].get("content", "") for result in results if isinstance(result, dict)]
        if not candidates:
            raise HTTPException(503, "All specialist models failed")
        combine = {
            "messages": [
                {"role": "system", "content": "Combine the specialist answers. Prefer concrete, safe, evidence-backed conclusions."},
                {"role": "user", "content": "\n\n--- SPECIALIST ---\n".join(candidates)},
            ], "temperature": 0.1,
        }
        return await call_model("fast", combine)
    target = {"fast": "fast", "coding": "coding", "deep": "deep", "vision": "vision"}.get(mode, "coding")
    return await call_model(target, body)


@app.post("/v1/review")
async def review(request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    authorize(authorization)
    body = await request.json()
    prompt = (
        "Review this proposed patch for correctness, security, missing tests, and unsafe assumptions. "
        "Return actionable findings only.\n\n" + str(body.get("diff", ""))[:400_000]
    )
    payload = {"messages": [{"role": "user", "content": prompt}], "temperature": 0.1}
    try:
        response = await call_model("debug", payload)
        reviewer = "deepseek"
    except HTTPException:
        response = await call_model("coding", payload)
        reviewer = "qwen-stage1-fallback"
    return {"reviewer": reviewer, "content": response["choices"][0]["message"].get("content", "")}
