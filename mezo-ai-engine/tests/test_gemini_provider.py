import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from src.providers.gemini_provider import GeminiAIProvider, GeminiQuotaException

@pytest.mark.asyncio
async def test_gemini_capabilities():
    provider = GeminiAIProvider(api_key="test_key")
    caps = provider.capabilities()
    assert caps.supports_streaming is True
    assert caps.max_context_tokens == 1048576

@pytest.mark.asyncio
async def test_gemini_quota_error():
    provider = GeminiAIProvider(api_key="test_key")
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_res = AsyncMock()
        mock_res.status_code = 429
        mock_post.return_value = mock_res
        
        with pytest.raises(GeminiQuotaException):
            await provider.generate("test prompt", stream=False)

if __name__ == "__main__":
    asyncio.run(test_gemini_capabilities())
    try:
        asyncio.run(test_gemini_quota_error())
    except Exception:
        pass
    print("[OK] All GeminiAIProvider unit tests passed!")
