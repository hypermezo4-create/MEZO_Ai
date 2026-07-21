import os
import json
import httpx
from typing import AsyncGenerator, Dict, Any, List, Optional
from src.providers.base_provider import BaseAIProvider, ProviderCapabilities, GenerationChunk, GenerationResponse
from src.persona.system_prompt import get_system_prompt

class LocalAIProvider(BaseAIProvider):
    def __init__(self, base_url: Optional[str] = None, model: str = "llama3"):
        self.base_url = base_url or os.getenv("LOCAL_OLLAMA_URL", "http://localhost:11434")
        self.model = os.getenv("LOCAL_MODEL", model)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_tools=True,
            supports_streaming=True,
            max_context_tokens=8192
        )

    async def health_check(self) -> bool:
        """Ping local Ollama version endpoint with a fast 1-second timeout."""
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                res = await client.get(f"{self.base_url}/api/version")
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

        # Always use the persona module as source of truth — never inline persona text
        resolved_system_prompt = system_prompt or get_system_prompt()
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": stream,
            "system": resolved_system_prompt,
        }

        if not stream:
            async with httpx.AsyncClient(timeout=60.0) as client:
                res = await client.post(f"{self.base_url}/api/generate", json=payload)
                res.raise_for_request()
                data = res.json()
                return GenerationResponse(
                    text=data.get("response", ""),
                    provider="local",
                    usage={"eval_count": data.get("eval_count", 0)}
                )

        async def chunk_generator():
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", f"{self.base_url}/api/generate", json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                            chunk_text = data.get("response", "")
                            is_done = data.get("done", False)
                            yield GenerationChunk(
                                text=chunk_text,
                                is_final=is_done,
                                provider="local"
                            )
                        except json.JSONDecodeError:
                            continue

        return chunk_generator()
