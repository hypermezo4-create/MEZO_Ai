from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.config import get_settings
from src.models import AuditChainHead, AuditLog
from src.redaction import redact


GENESIS_HASH = "0" * 64
AUDIT_LOCK_ID = 6_315_069_828


def _signature(value: str) -> str:
    return hmac.new(get_settings().audit_hmac_key.encode(), value.encode(), hashlib.sha256).hexdigest()


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def append_audit(
    db: Session,
    *,
    actor_type: str,
    actor_id: str,
    action: str,
    result: str,
    details: dict[str, Any] | None = None,
    task_id: str | None = None,
    request_id: str | None = None,
) -> AuditLog:
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": AUDIT_LOCK_ID})
    head = db.query(AuditChainHead).filter(AuditChainHead.id == 1).with_for_update().one_or_none()
    previous_hash = head.head_hash if head else GENESIS_HASH
    created_at = datetime.now(timezone.utc)
    body = json.dumps(
        {
            "actor_type": actor_type,
            "actor_id": actor_id,
            "action": action,
            "result": result,
            "details": redact(details or {}),
            "task_id": task_id,
            "request_id": request_id,
            "created_at": _timestamp(created_at),
            "previous_hash": previous_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    entry_hash = _signature(body)
    record = AuditLog(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        task_id=task_id,
        request_id=request_id,
        result=result,
        details=redact(details or {}),
        created_at=created_at,
        previous_hash=previous_hash,
        entry_hash=entry_hash,
    )
    db.add(record)
    if head is None:
        db.add(AuditChainHead(id=1, head_hash=entry_hash, signature=_signature(entry_hash)))
    else:
        head.head_hash = entry_hash
        head.signature = _signature(entry_hash)
    return record


def verify_audit_chain(db: Session) -> bool:
    previous_hash = GENESIS_HASH
    records = db.query(AuditLog).order_by(AuditLog.id.asc()).all()
    for record in records:
        if record.previous_hash != previous_hash:
            return False
        body = json.dumps(
            {
                "actor_type": record.actor_type,
                "actor_id": record.actor_id,
                "action": record.action,
                "result": record.result,
                "details": record.details,
                "task_id": record.task_id,
                "request_id": record.request_id,
                "created_at": _timestamp(record.created_at),
                "previous_hash": record.previous_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        if not hmac.compare_digest(record.entry_hash, _signature(body)):
            return False
        previous_hash = record.entry_hash
    head = db.get(AuditChainHead, 1)
    expected_head = previous_hash
    return bool(
        head
        and hmac.compare_digest(head.head_hash, expected_head)
        and hmac.compare_digest(head.signature, _signature(expected_head))
    )
