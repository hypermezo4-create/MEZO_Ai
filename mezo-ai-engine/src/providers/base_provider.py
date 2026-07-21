from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, Any, List, Optional
from pydantic import BaseModel

class ProviderCapabilities(BaseModel):
    supports_tools: bool
    supports_streaming: bool
    max_context_tokens: int

class GenerationChunk(BaseModel):
    text: str
    is_final: bool = False
    provider: str
    metadata: Optional[Dict[str, Any]] = None

class GenerationResponse(BaseModel):
    text: str
    provider: str
    usage: Optional[Dict[str, Any]] = None

class BaseAIProvider(ABC):
    """Abstract interface that every AI provider MUST implement."""

    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """Returns the capabilities of the active provider."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Fast, cheap check returning True if the provider is online and reachable."""
        pass

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        stream: bool = True
    ) -> AsyncGenerator[GenerationChunk, None] | GenerationResponse:
        """Generates text from the provider, supporting real streaming."""
        pass
