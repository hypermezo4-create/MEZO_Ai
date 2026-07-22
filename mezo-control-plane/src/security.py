from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from src.config import get_settings
from src.database import get_db
from src.models import Role, Runner, User


password_hasher = PasswordHasher()
bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def issue_access_token(user: User) -> tuple[str, int]:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.access_token_minutes)
    token = jwt.encode(
        {"sub": user.id, "role": user.role, "iat": now, "exp": expires, "iss": "mezo-api", "aud": "mezo-web"},
        settings.jwt_secret,
        algorithm="HS256",
    )
    return token, int((expires - now).total_seconds())


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        payload = jwt.decode(
            credentials.credentials,
            get_settings().jwt_secret,
            algorithms=["HS256"],
            audience="mezo-web",
            issuer="mezo-api",
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc
    user = db.get(User, payload.get("sub"))
    if user is None or not user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is not active")
    return user


def require_roles(*roles: Role):
    allowed = {role.value for role in roles}

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return dependency


def new_runner_token() -> str:
    return secrets.token_urlsafe(48)


def hash_runner_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def get_current_runner(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Runner:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Runner authentication required")
    token_hash = hash_runner_token(credentials.credentials)
    runner = db.query(Runner).filter(Runner.auth_token_hash == token_hash).one_or_none()
    if runner is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid runner token")
    request.state.runner_id = runner.id
    return runner
