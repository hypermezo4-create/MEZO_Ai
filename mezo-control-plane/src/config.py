from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _required(name: str, *, testing: bool) -> str:
    value = os.getenv(name, "").strip()
    if not value and not testing:
        raise RuntimeError(f"{name} is required")
    return value


@dataclass(frozen=True)
class Settings:
    environment: str
    testing: bool
    database_url: str
    jwt_secret: str
    audit_hmac_key: str
    bootstrap_token: str
    runner_registration_token: str
    cors_origins: tuple[str, ...]
    access_token_minutes: int
    task_lease_seconds: int
    runner_offline_seconds: int
    approval_minutes: int
    github_app_id: str
    github_installation_id: str
    github_private_key: str
    github_api_url: str

    @property
    def production(self) -> bool:
        return self.environment == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    testing = os.getenv("MEZO_TESTING", "").lower() in {"1", "true", "yes"}
    environment = os.getenv("MEZO_ENV", "test" if testing else "production").lower()
    database_url = os.getenv("DATABASE_URL", "sqlite+pysqlite:///:memory:" if testing else "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    if environment == "production" and not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise RuntimeError("Production DATABASE_URL must use PostgreSQL")

    jwt_secret = _required("JWT_SECRET", testing=testing) or "test-jwt-secret-that-is-at-least-32-bytes"
    audit_key = _required("AUDIT_HMAC_KEY", testing=testing) or "test-audit-hmac-key-that-is-long-enough"
    if not testing and (len(jwt_secret) < 32 or len(audit_key) < 32):
        raise RuntimeError("JWT_SECRET and AUDIT_HMAC_KEY must each be at least 32 characters")

    origin_value = os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "" if environment == "production" else "http://localhost:5173,tauri://localhost",
    )
    origins = tuple(
        origin.strip()
        for origin in origin_value.split(",")
        if origin.strip()
    )
    if environment == "production" and (not origins or "*" in origins):
        raise RuntimeError("Production CORS_ALLOWED_ORIGINS must be an explicit allowlist")

    return Settings(
        environment=environment,
        testing=testing,
        database_url=database_url,
        jwt_secret=jwt_secret,
        audit_hmac_key=audit_key,
        bootstrap_token=_required("MEZO_BOOTSTRAP_TOKEN", testing=testing) or "test-bootstrap-token",
        runner_registration_token=_required("RUNNER_REGISTRATION_TOKEN", testing=testing) or "test-runner-registration-token",
        cors_origins=origins,
        access_token_minutes=int(os.getenv("ACCESS_TOKEN_MINUTES", "30")),
        task_lease_seconds=int(os.getenv("TASK_LEASE_SECONDS", "120")),
        runner_offline_seconds=int(os.getenv("RUNNER_OFFLINE_SECONDS", "45")),
        approval_minutes=int(os.getenv("APPROVAL_EXPIRATION_MINUTES", "30")),
        github_app_id=os.getenv("GITHUB_APP_ID", "").strip(),
        github_installation_id=os.getenv("GITHUB_INSTALLATION_ID", "").strip(),
        github_private_key=os.getenv("GITHUB_APP_PRIVATE_KEY", "").replace("\\n", "\n").strip(),
        github_api_url=os.getenv("GITHUB_API_URL", "https://api.github.com").rstrip("/"),
    )
