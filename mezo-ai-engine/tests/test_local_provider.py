import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from src.providers.local_provider import LocalAIProvider


@pytest.mark.asyncio
async def test_local_provider_capabilities():
    provider = LocalAIProvider()
    caps = provider.capabilities()
    assert caps.supports_streaming is True
    assert caps.supports_tools is True
    assert caps.max_context_tokens == 8192

@pytest.mark.asyncio
async def test_local_provider_health_check_online():
    provider = LocalAIProvider()
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_res = AsyncMock()
        mock_res.status_code = 200
        mock_get.return_value = mock_res
        
        is_healthy = await provider.health_check()
        assert is_healthy is True

@pytest.mark.asyncio
async def test_local_provider_health_check_offline():
    provider = LocalAIProvider()
    with patch("httpx.AsyncClient.get", side_effect=Exception("Connection refused")):
        is_healthy = await provider.health_check()
        assert is_healthy is False

if __name__ == "__main__":
    asyncio.run(test_local_provider_capabilities())
    asyncio.run(test_local_provider_health_check_online())
    asyncio.run(test_local_provider_health_check_offline())
    print("[OK] All LocalAIProvider unit tests passed!")
