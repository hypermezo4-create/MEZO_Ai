import os
import json
import httpx
from typing import AsyncGenerator, Dict, Any, List, Optional
from src.providers.base_provider import BaseAIProvider, ProviderCapabilities, GenerationChunk, GenerationResponse
from src.persona.system_prompt import get_system_prompt

class GeminiQuotaException(Exception):
    """Raised when Gemini API quota or rate limit (429) is exceeded."""
    pass

class GeminiAIProvider(BaseAIProvider):
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        self.endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_tools=True,
            supports_streaming=True,
            max_context_tokens=1048576  # 1M tokens context
        )

    async def health_check(self) -> bool:
        """Checks API key presence and endpoint availability."""
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            return False
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                url = f"{self.endpoint}?key={self.api_key}"
                res = await client.get(url)
                return res.status_code == 200
        except Exception:
            return False

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        stream: bool = True
    ) -> AsyncGenerator[GenerationChunk, None] | GenerationResponse:

        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable is missing or empty.")

        # Always use the persona module as source of truth — never inline persona text
        resolved_system_prompt = system_prompt or get_system_prompt()

        contents = []
        # Inject MEZO AI persona as the system instruction via the conversation turn pattern
        contents.append({"role": "user", "parts": [{"text": f"System Instruction:\n{resolved_system_prompt}"}]})
        contents.append({"role": "model", "parts": [{"text": "Understood. I am MEZO AI and will follow these instructions."}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})


        payload = {"contents": contents}

        if not stream:
            url = f"{self.endpoint}:generateContent?key={self.api_key}"
            async with httpx.AsyncClient(timeout=60.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 429:
                    raise GeminiQuotaException("Gemini API Quota / Rate Limit Exceeded (429).")
                res.raise_for_status()
                data = res.json()
                text = ""
                candidates = data.get("candidates", [])
                if candidates and "content" in candidates[0]:
                    parts = candidates[0]["content"].get("parts", [])
                    text = "".join([p.get("text", "") for p in parts])
                return GenerationResponse(text=text, provider="gemini")

        async def chunk_generator():
            url = f"{self.endpoint}:streamGenerateContent?key={self.api_key}&alt=sse"
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code == 429:
                        raise GeminiQuotaException("Gemini API Quota / Rate Limit Exceeded (429).")
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            raw_data = line[5:].strip()
                            if not raw_data:
                                continue
                            try:
                                data = json.loads(raw_data)
                                candidates = data.get("candidates", [])
                                if candidates and "content" in candidates[0]:
                                    parts = candidates[0]["content"].get("parts", [])
                                    chunk_text = "".join([p.get("text", "") for p in parts])
                                    finish_reason = candidates[0].get("finishReason")
                                    yield GenerationChunk(
                                        text=chunk_text,
                                        is_final=finish_reason is not None,
                                        provider="gemini"
                                    )
                            except json.JSONDecodeError:
                                continue

        return chunk_generator()
