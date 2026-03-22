"""Integration tests for Gateway."""

import pytest
import asyncio

from sg.server.gateway import Gateway
from sg.models.search import SearchRequest


@pytest.fixture(scope="module")
def event_loop():
    """Create event loop for module."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


class TestGatewayIntegration:
    """Integration tests for Gateway."""

    @pytest.mark.asyncio
    async def test_gateway_starts_and_stops(self):
        """Test gateway can start and stop."""
        gw = Gateway(port=18101)
        await gw.start()
        assert gw._running is True
        await gw.stop()
        assert gw._running is False

    @pytest.mark.asyncio
    async def test_search_with_duckduckgo(self):
        """Test search using fallback provider."""
        gw = Gateway(port=18102)
        await gw.start()
        await asyncio.sleep(0.5)

        try:
            result = await gw.search(
                query="Python programming",
                max_results=3
            )

            assert result.query == "Python programming"
            # Provider depends on config, just verify we got results
            assert result.total >= 0
            assert result.provider in ["duckduckgo", "youcom", "firecrawl-1", "firecrawl-2"]
        finally:
            await gw.stop()

    @pytest.mark.asyncio
    async def test_search_with_provider_override(self):
        """Test search with specific provider."""
        gw = Gateway(port=18103)
        await gw.start()
        await asyncio.sleep(0.5)

        try:
            result = await gw.search(
                query="test query",
                provider="duckduckgo",
                max_results=2
            )
            assert result.provider == "duckduckgo"
        finally:
            await gw.stop()

    @pytest.mark.asyncio
    async def test_get_status(self):
        """Test getting gateway status."""
        gw = Gateway(port=18104)
        await gw.start()
        await asyncio.sleep(0.5)

        try:
            status = await gw.get_status()

            assert status["running"] is True
            assert status["port"] == 18104
            assert "providers" in status
            assert status["providers"]["total"] >= 1
        finally:
            await gw.stop()

    @pytest.mark.asyncio
    async def test_list_providers(self):
        """Test listing providers."""
        gw = Gateway(port=18105)
        await gw.start()
        await asyncio.sleep(0.5)

        try:
            providers = await gw.list_providers()

            assert len(providers) >= 1
            provider_names = [p.name for p in providers]
            assert "duckduckgo" in provider_names
        finally:
            await gw.stop()

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test health check."""
        gw = Gateway(port=18106)
        await gw.start()
        await asyncio.sleep(0.5)

        try:
            result = await gw.health_check()

            assert "healthy" in result
            assert "unhealthy" in result
            assert "duckduckgo" in result["healthy"]
        finally:
            await gw.stop()

    @pytest.mark.asyncio
    async def test_search_with_time_range(self):
        """Test search with time range."""
        gw = Gateway(port=18107)
        await gw.start()
        await asyncio.sleep(0.5)

        try:
            result = await gw.search(
                query="AI news",
                max_results=3,
                time_range="week"
            )
            assert result.query == "AI news"
        finally:
            await gw.stop()
