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
ENDPOINTS = {
    "fast": "http://mezo-fast.internal:8080/v1",
    "coding": "http://mezo-qwen-coder.internal:8080/v1",
    "deep": "http://mezo-glm.internal:8080/v1",
    "debug": "http://mezo-deepseek.internal:8080/v1",
    "vision": "http://mezo-vision.internal:8080/v1",
}
failures: dict[str, int] = defaultdict(int)
open_until: dict[str, float] = defaultdict(float)


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
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10)) as client:
            response = await client.post(
                f"{ENDPOINTS[kind]}/chat/completions",
                headers={"Authorization": f"Bearer {MODEL_TOKEN}"},
                json=payload,
            )
        response.raise_for_status()
        failures[kind] = 0
        return response.json()
    except (httpx.HTTPError, KeyError) as exc:
        failures[kind] += 1
        if failures[kind] >= 3:
            open_until[kind] = time.monotonic() + 30
        raise HTTPException(503, f"{kind} model unavailable: {type(exc).__name__}") from exc


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/cluster")
async def cluster(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    authorize(authorization)
    async def probe(kind: str, url: str) -> tuple[str, dict[str, Any]]:
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=4) as client:
                response = await client.get(f"{url}/models", headers={"Authorization": f"Bearer {MODEL_TOKEN}"})
            return kind, {"healthy": response.status_code == 200, "latency_ms": round((time.monotonic() - started) * 1000), "circuit_open": open_until[kind] > time.monotonic()}
        except httpx.HTTPError as exc:
            return kind, {"healthy": False, "error": type(exc).__name__, "circuit_open": open_until[kind] > time.monotonic()}
    values = await asyncio.gather(*(probe(kind, url) for kind, url in ENDPOINTS.items()))
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
    response = await call_model("debug", {"messages": [{"role": "user", "content": prompt}], "temperature": 0.1})
    return {"reviewer": "deepseek", "content": response["choices"][0]["message"].get("content", "")}
