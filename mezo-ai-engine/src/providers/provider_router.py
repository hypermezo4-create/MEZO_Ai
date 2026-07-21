import time
import logging
from typing import AsyncGenerator, Dict, Any, List, Optional
from src.providers.base_provider import BaseAIProvider, ProviderCapabilities, GenerationChunk, GenerationResponse
from src.providers.local_provider import LocalAIProvider
from src.providers.gemini_provider import GeminiAIProvider, GeminiQuotaException

logger = logging.getLogger("mezo.provider_router")
logging.basicConfig(level=logging.INFO)

class ProviderRouter:
    def __init__(self, local_provider: Optional[LocalAIProvider] = None, gemini_provider: Optional[GeminiAIProvider] = None):
        self.local_provider = local_provider or LocalAIProvider()
        self.gemini_provider = gemini_provider or GeminiAIProvider()

    async def get_active_provider(self, preferred_provider: Optional[str] = "auto") -> tuple[BaseAIProvider, str, str]:
        """
        Determines the appropriate provider based on user preference and health check.
        Returns tuple of (provider_instance, provider_name, routing_reason).
        """
        pref = (preferred_provider or "auto").lower()

        if pref == "local":
            is_healthy = await self.local_provider.health_check()
            if not is_healthy:
                raise RuntimeError("Local AI engine is offline/unreachable on http://localhost:11434.")
            return self.local_provider, "local", "Explicit user selection (Local)"

        if pref == "gemini":
            is_healthy = await self.gemini_provider.health_check()
            if not is_healthy and not self.gemini_provider.api_key:
                raise RuntimeError("GEMINI_API_KEY environment variable is not configured.")
            return self.gemini_provider, "gemini", "Explicit user selection (Gemini Cloud)"

        # Auto fallback logic
        is_local_healthy = await self.local_provider.health_check()
        if is_local_healthy:
            return self.local_provider, "local", "Auto-routed to Local AI Engine (Healthy)"

        # Local unavailable -> Fallback to Gemini
        is_gemini_healthy = await self.gemini_provider.health_check()
        if self.gemini_provider.api_key:
            return self.gemini_provider, "gemini", "Local engine offline -> Auto fallback to Gemini Cloud"

        raise RuntimeError("No active AI provider available. Local engine is offline and GEMINI_API_KEY is not configured.")

    async def route_and_generate(
        self,
        prompt: str,
        preferred_provider: Optional[str] = "auto",
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        stream: bool = True
    ) -> tuple[AsyncGenerator[GenerationChunk, None] | GenerationResponse, str, str]:

        start_time = time.time()
        provider, provider_name, reason = await self.get_active_provider(preferred_provider)

        logger.info(f"[ROUTER] Chosen Provider: {provider_name} | Reason: {reason}")

        try:
            generator = await provider.generate(prompt, system_prompt=system_prompt, tools=tools, stream=stream)
            latency_ms = (time.time() - start_time) * 1000
            logger.info(f"[ROUTER] Generation initialized via {provider_name} in {latency_ms:.2f}ms")
            return generator, provider_name, reason
        except GeminiQuotaException as e:
            logger.error(f"[ROUTER] Gemini Quota Exceeded: {str(e)}")
            raise e
        except Exception as e:
            logger.error(f"[ROUTER] Provider {provider_name} failed: {str(e)}")
            raise e
