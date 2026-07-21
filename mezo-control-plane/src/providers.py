from __future__ import annotations

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx


logger = logging.getLogger("mezo.provider")


class ProviderError(RuntimeError):
    category = "provider_error"


class ProviderRateLimit(ProviderError):
    category = "rate_limit"


class ProviderTimeout(ProviderError):
    category = "timeout"


class ProviderUnavailable(ProviderError):
    category = "unavailable"


@dataclass(frozen=True)
class ProviderCapabilities:
    name: str
    model: str
    streaming: bool
    tool_calls: bool
    configured: bool


@dataclass(frozen=True)
class ProviderChunk:
    text: str
    tool_calls: list[dict[str, Any]] | None = None
    usage: dict[str, Any] | None = None
    finish_reason: str | None = None


class Provider(ABC):
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities: ...

    @abstractmethod
    async def health(self) -> dict[str, Any]: ...

    @abstractmethod
    async def stream(
        self,
        *,
        messages: list[dict[str, str]],
        system: str | None,
        tools: list[dict[str, Any]] | None,
    ) -> AsyncIterator[ProviderChunk]: ...


def _map_http_error(response: httpx.Response, provider: str) -> None:
    if response.status_code == 429:
        raise ProviderRateLimit(f"{provider} rate limit exceeded")
    if response.status_code >= 500:
        raise ProviderUnavailable(f"{provider} is unavailable (HTTP {response.status_code})")
    if response.status_code >= 400:
        raise ProviderError(f"{provider} request failed with HTTP {response.status_code}")


class GeminiProvider(Provider):
    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        self.model = model or os.getenv("GEMINI_MODEL", "")
        self.base_url = (base_url or os.getenv("GEMINI_API_URL", "https://generativelanguage.googleapis.com/v1beta")).rstrip("/")

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities("gemini", self.model, True, True, bool(self.api_key and self.model))

    async def health(self) -> dict[str, Any]:
        if not self.api_key or not self.model:
            return {"healthy": False, "configured": False, "model": self.model, "error": "not_configured"}
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self.base_url}/models/{self.model}", headers={"x-goog-api-key": self.api_key}
                )
            return {
                "healthy": response.status_code == 200,
                "configured": True,
                "model": self.model,
                "latency_ms": round((time.monotonic() - started) * 1000),
                "http_status": response.status_code,
            }
        except httpx.TimeoutException:
            return {"healthy": False, "configured": True, "model": self.model, "error": "timeout"}
        except httpx.RequestError:
            return {"healthy": False, "configured": True, "model": self.model, "error": "unreachable"}

    async def stream(self, *, messages, system, tools) -> AsyncIterator[ProviderChunk]:
        if not self.api_key or not self.model:
            raise ProviderError("Gemini is not configured")
        contents = [
            {"role": "model" if message["role"] == "assistant" else "user", "parts": [{"text": message["content"]}]}
            for message in messages
            if message["role"] != "system"
        ]
        payload: dict[str, Any] = {"contents": contents}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            payload["tools"] = tools
        url = f"{self.base_url}/models/{self.model}:streamGenerateContent?alt=sse"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0)) as client:
                async with client.stream("POST", url, headers={"x-goog-api-key": self.api_key}, json=payload) as response:
                    _map_http_error(response, "Gemini")
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = json.loads(line[6:])
                        candidates = data.get("candidates") or []
                        if not candidates:
                            continue
                        candidate = candidates[0]
                        parts = candidate.get("content", {}).get("parts", [])
                        text = "".join(part.get("text", "") for part in parts)
                        tool_calls = [part["functionCall"] for part in parts if "functionCall" in part]
                        usage = data.get("usageMetadata")
                        yield ProviderChunk(
                            text=text,
                            tool_calls=tool_calls or None,
                            usage=usage,
                            finish_reason=candidate.get("finishReason"),
                        )
        except httpx.TimeoutException as exc:
            raise ProviderTimeout("Gemini request timed out") from exc
        except httpx.RequestError as exc:
            raise ProviderUnavailable("Gemini request could not reach the provider") from exc
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ProviderError("Gemini returned an invalid streaming response") from exc


class OpenAICompatibleProvider(Provider):
    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("LOCAL_OPENAI_BASE_URL", "http://127.0.0.1:11434/v1")).rstrip("/")
        self.api_key = os.getenv("LOCAL_OPENAI_API_KEY", "")
        self.model = model or os.getenv("LOCAL_OPENAI_MODEL", "")

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities("local", self.model, True, True, bool(self.base_url and self.model))

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    async def health(self) -> dict[str, Any]:
        if not self.model:
            return {"healthy": False, "configured": False, "model": None, "error": "not_configured"}
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/models", headers=self._headers())
            return {
                "healthy": response.status_code == 200,
                "configured": True,
                "model": self.model,
                "latency_ms": round((time.monotonic() - started) * 1000),
                "http_status": response.status_code,
            }
        except httpx.TimeoutException:
            return {"healthy": False, "configured": True, "model": self.model, "error": "timeout"}
        except httpx.RequestError:
            return {"healthy": False, "configured": True, "model": self.model, "error": "unreachable"}

    async def stream(self, *, messages, system, tools) -> AsyncIterator[ProviderChunk]:
        if not self.model:
            raise ProviderError("Local OpenAI-compatible provider is not configured")
        provider_messages = list(messages)
        if system:
            provider_messages.insert(0, {"role": "system", "content": system})
        payload: dict[str, Any] = {"model": self.model, "messages": provider_messages, "stream": True, "stream_options": {"include_usage": True}}
        if tools:
            payload["tools"] = tools
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0)) as client:
                async with client.stream("POST", f"{self.base_url}/chat/completions", headers=self._headers(), json=payload) as response:
                    _map_http_error(response, "Local provider")
                    async for line in response.aiter_lines():
                        if not line.startswith("data: ") or line == "data: [DONE]":
                            continue
                        data = json.loads(line[6:])
                        choices = data.get("choices") or []
                        delta = choices[0].get("delta", {}) if choices else {}
                        finish_reason = choices[0].get("finish_reason") if choices else None
                        yield ProviderChunk(
                            text=delta.get("content", ""),
                            tool_calls=delta.get("tool_calls"),
                            usage=data.get("usage"),
                            finish_reason=finish_reason,
                        )
        except httpx.TimeoutException as exc:
            raise ProviderTimeout("Local provider request timed out") from exc
        except httpx.RequestError as exc:
            raise ProviderUnavailable("Local provider could not be reached") from exc
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ProviderError("Local provider returned an invalid streaming response") from exc


class ProviderRouter:
    def __init__(self, providers: dict[str, Provider] | None = None) -> None:
        self.providers = providers if providers is not None else {"local": OpenAICompatibleProvider(), "gemini": GeminiProvider()}

    async def health(self) -> dict[str, Any]:
        output = {}
        for name, provider in self.providers.items():
            output[name] = await provider.health()
            output[name]["capabilities"] = provider.capabilities().__dict__
        return output

    async def stream(self, *, selected: str, fallback: list[str], messages, system, tools) -> AsyncIterator[ProviderChunk]:
        candidates = [selected] if selected != "auto" else fallback
        errors: list[str] = []
        for name in candidates:
            provider = self.providers.get(name)
            if provider is None:
                errors.append(f"unknown provider: {name}")
                continue
            health = await provider.health()
            if not health.get("healthy"):
                errors.append(f"{name}: {health.get('error') or health.get('http_status')}")
                if selected != "auto":
                    break
                continue
            try:
                emitted = False
                started = time.monotonic()
                async for chunk in provider.stream(messages=messages, system=system, tools=tools):
                    emitted = True
                    yield chunk
                logger.info(
                    "provider request completed: %s",
                    name,
                    extra={"duration_ms": round((time.monotonic() - started) * 1000)},
                )
                return
            except ProviderError as exc:
                logger.warning(
                    "provider request failed: %s (%s)",
                    name,
                    exc.category,
                    extra={
                        "duration_ms": round((time.monotonic() - started) * 1000),
                        "failure_category": exc.category,
                    },
                )
                errors.append(f"{name}: {exc}")
                if emitted:
                    raise
                if selected != "auto":
                    break
        raise ProviderError("No provider completed the request: " + "; ".join(errors))
