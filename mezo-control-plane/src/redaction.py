from __future__ import annotations

import re
from typing import Any


SECRET_PATTERNS = (
    (re.compile(r"(?i)(authorization:\s*(?:bearer|token)\s+)[^\s]+"), True),
    (re.compile(r"(?i)\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}\b"), False),
    (re.compile(r"(?i)\bsk-[A-Za-z0-9_-]{20,}\b"), False),
    (re.compile(r"(?i)((?:api[_-]?key|token|password|secret)\s*[=:]\s*)[^\s,;]+"), True),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), False),
)


def redact_text(value: str) -> str:
    redacted = value
    for pattern, preserve_prefix in SECRET_PATTERNS:
        redacted = pattern.sub(lambda match: (match.group(1) if preserve_prefix else "") + "[REDACTED]", redacted)
    return redacted


def redact(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        output = {}
        for key, item in value.items():
            if any(word in key.lower() for word in ("password", "secret", "token", "private_key", "authorization")):
                output[key] = "[REDACTED]"
            else:
                output[key] = redact(item)
        return output
    return value
