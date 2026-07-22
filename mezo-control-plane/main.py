from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

sys.path.insert(0, os.path.dirname(__file__))

from src.api import router
from src.config import get_settings
from src.database import SessionLocal


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for name in (
            "request_id", "task_id", "runner_id", "duration_ms", "queue_latency_ms",
            "task_duration_ms", "failure_category",
        ):
            value = getattr(record, name, None)
            if value is not None:
                payload[name] = value
        return json.dumps(payload, separators=(",", ":"))


handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), handlers=[handler], force=True)
logger = logging.getLogger("mezo.api")
settings = get_settings()

app = FastAPI(title="MEZO AI API", version="1.0.0", docs_url="/docs" if not settings.production else None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-MEZO-Bootstrap-Token", "X-Runner-Registration-Token"],
    expose_headers=["X-Request-ID"],
)
app.include_router(router)


@app.middleware("http")
async def request_context(request: Request, call_next):
    started = time.monotonic()
    incoming = request.headers.get("x-request-id", "")
    request_id = incoming if incoming and len(incoming) <= 64 else str(uuid.uuid4())
    request.state.request_id = request_id
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "unhandled request error",
            extra={"request_id": request_id, "failure_category": "unhandled_exception"},
        )
        raise
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "%s %s %s",
        request.method,
        request.url.path,
        response.status_code,
        extra={"request_id": request_id, "duration_ms": round((time.monotonic() - started) * 1000)},
    )
    return response


@app.get("/healthz")
def health():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "unhealthy", "database": "unavailable"})
    return {"status": "ok", "database": "available", "service": "mezo-api", "version": app.version}


frontend_dist = Path(os.getenv("MEZO_FRONTEND_DIST", "/app/frontend"))
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
else:
    @app.get("/")
    def root():
        return {"service": "mezo-api", "version": app.version}
