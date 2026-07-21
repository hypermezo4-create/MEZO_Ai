import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
import asyncio
from unittest.mock import AsyncMock
from src.providers.provider_router import ProviderRouter

@pytest.mark.asyncio
async def test_router_auto_selects_local_when_healthy():
    mock_local = AsyncMock()
    mock_local.health_check.return_value = True

    mock_gemini = AsyncMock()
    mock_gemini.health_check.return_value = True
    mock_gemini.api_key = "key"

    router = ProviderRouter(local_provider=mock_local, gemini_provider=mock_gemini)
    provider, name, reason = await router.get_active_provider("auto")
    
    assert name == "local"
    assert "Healthy" in reason

@pytest.mark.asyncio
async def test_router_auto_falls_back_to_gemini_when_local_offline():
    mock_local = AsyncMock()
    mock_local.health_check.return_value = False

    mock_gemini = AsyncMock()
    mock_gemini.health_check.return_value = True
    mock_gemini.api_key = "valid_key"

    router = ProviderRouter(local_provider=mock_local, gemini_provider=mock_gemini)
    provider, name, reason = await router.get_active_provider("auto")
    
    assert name == "gemini"
    assert "fallback" in reason

if __name__ == "__main__":
    asyncio.run(test_router_auto_selects_local_when_healthy())
    asyncio.run(test_router_auto_falls_back_to_gemini_when_local_offline())
    print("[OK] All ProviderRouter unit tests passed!")
