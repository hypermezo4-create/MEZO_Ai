from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from src.api import checks_passed
from src.config import get_settings
from src.providers import Provider, ProviderCapabilities, ProviderChunk, ProviderRouter, ProviderUnavailable
from src.redaction import redact, redact_text


def test_secret_redaction_covers_headers_tokens_and_nested_values():
    github_token = "ghp_" + "abcdefghijklmnopqrstuvwxyz012345"
    text = f"Authorization: Bearer top-secret-token\napi_key=secret-value {github_token}"
    redacted = redact_text(text)
    assert "top-secret-token" not in redacted
    assert "secret-value" not in redacted
    assert "ghp_" not in redacted
    nested = redact({"access_token": "secret", "safe": ["password=hunter2"]})
    assert nested["access_token"] == "[REDACTED]"
    assert "hunter2" not in nested["safe"][0]


class ControlledProvider(Provider):
    def __init__(self, chunks: list[ProviderChunk], failure: Exception | None = None):
        self.chunks = chunks
        self.failure = failure

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities("controlled", "test-model", True, True, True)

    async def health(self) -> dict:
        return {"healthy": True}

    async def stream(self, *, messages, system, tools) -> AsyncIterator[ProviderChunk]:
        for chunk in self.chunks:
            yield chunk
        if self.failure:
            raise self.failure


@pytest.mark.asyncio
async def test_provider_router_falls_back_before_output_and_preserves_tool_calls():
    unavailable = ControlledProvider([], ProviderUnavailable("offline"))
    tool_chunk = ProviderChunk("", tool_calls=[{"name": "read_file", "args": {"path": "README.md"}}])
    available = ControlledProvider([tool_chunk])
    router = ProviderRouter({"first": unavailable, "second": available})
    chunks = [
        chunk
        async for chunk in router.stream(
            selected="auto", fallback=["first", "second"], messages=[], system=None, tools=[]
        )
    ]
    assert chunks == [tool_chunk]


@pytest.mark.asyncio
async def test_provider_router_does_not_mix_fallback_after_partial_output():
    partial = ControlledProvider([ProviderChunk("partial")], ProviderUnavailable("disconnected"))
    fallback = ControlledProvider([ProviderChunk("must not appear")])
    router = ProviderRouter({"first": partial, "second": fallback})
    received = []
    with pytest.raises(ProviderUnavailable):
        async for chunk in router.stream(
            selected="auto", fallback=["first", "second"], messages=[], system=None, tools=None
        ):
            received.append(chunk.text)
    assert received == ["partial"]


def test_applicable_guards_cannot_be_reported_as_skipped():
    report = {
        "commands": [{"exit_code": 0}],
        "guards": [
            {"name": "clean-code-guard", "status": "passed"},
            {"name": "test-guard", "status": "skipped_not_applicable"},
            {"name": "docs-guard", "status": "skipped_not_applicable"},
        ],
    }
    assert not checks_passed(report, [{"path": "tests/test_policy.py"}])
    assert not checks_passed(report, [{"path": "docs/security.md"}])


def test_expired_access_token_is_rejected(client):
    expired = jwt.encode(
        {
            "sub": "missing-user",
            "role": "owner",
            "iat": datetime.now(timezone.utc) - timedelta(minutes=10),
            "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
            "iss": "mezo-api",
            "aud": "mezo-web",
        },
        get_settings().jwt_secret,
        algorithm="HS256",
    )
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
