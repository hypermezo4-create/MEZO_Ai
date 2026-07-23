from __future__ import annotations

import logging
import os
from json import JSONDecodeError
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles


logger = logging.getLogger("mezo.control")
legacy = os.getenv("MEZO_LEGACY_MODE", "").lower() in {"1", "true", "yes"}
app = FastAPI(title="MEZO AI", version="2.1.0", docs_url=None, redoc_url=None)


@app.exception_handler(JSONDecodeError)
async def malformed_upstream_response(request: Request, exc: JSONDecodeError) -> JSONResponse:
    logger.exception("MEZO received malformed JSON while serving %s", request.url.path)
    return JSONResponse(
        {
            "detail": "MEZO router returned a non-JSON response",
            "error_type": type(exc).__name__,
        },
        status_code=502,
    )


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled MEZO error while serving %s", request.url.path)
    return JSONResponse(
        {
            "detail": f"MEZO internal error: {type(exc).__name__}",
            "error_type": type(exc).__name__,
        },
        status_code=500,
    )


if legacy:
    from sqlalchemy import text
    from sqlalchemy.exc import SQLAlchemyError
    from src.api import router
    from src.database import SessionLocal

    app.include_router(router)

    @app.get("/healthz", response_model=None)
    def health():
        try:
            with SessionLocal() as db:
                db.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return JSONResponse({"status": "unhealthy"}, status_code=503)
        return {"status": "ok", "mode": "legacy-test-only"}
else:
    from src.open_source_api import router
    from src.open_source_db import database

    database.migrate()
    app.include_router(router)

    @app.get("/healthz", response_model=None)
    def health():
        try:
            database.one("SELECT 1 AS healthy")
        except Exception:
            return JSONResponse({"status": "unhealthy", "database": "unavailable"}, status_code=503)
        return {"status": "ok", "database": "postgres", "mode": "single-user-cluster"}

    frontend = Path(os.getenv("MEZO_FRONTEND_DIST", "/app/frontend"))
    if frontend.is_dir():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
