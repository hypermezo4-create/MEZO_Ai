from __future__ import annotations

import re


PATTERNS = (
    (re.compile(r"(?i)(authorization:\s*(?:bearer|token)\s+)[^\s]+"), True),
    (re.compile(r"(?i)\b(?:gh[pousr]_|github_pat_|sk-)[A-Za-z0-9_-]{20,}\b"), False),
    (re.compile(r"(?i)((?:api[_-]?key|token|password|secret)\s*[=:]\s*)[^\s,;]+"), True),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), False),
)


def redact(value: str) -> str:
    output = value
    for pattern, preserve_prefix in PATTERNS:
        output = pattern.sub(lambda match: (match.group(1) if preserve_prefix else "") + "[REDACTED]", output)
    for name in ("KILOCODE_API_KEY", "KILO_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY", "MEZO_GIT_TOKEN"):
        secret = __import__("os").environ.get(name, "")
        if len(secret) >= 8:
            output = output.replace(secret, "[REDACTED]")
    return output
