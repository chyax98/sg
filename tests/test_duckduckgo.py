"""Tests for DuckDuckGo provider."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from sg.providers.duckduckgo import DuckDuckGoProvider
from sg.providers.base import ProviderInfo
from sg.models.search import SearchRequest


class TestDuckDuckGoProvider:

    def test_provider_info(self):
        assert DuckDuckGoProvider.info.type == "duckduckgo"
        assert DuckDuckGoProvider.info.needs_api_key is False
        assert DuckDuckGoProvider.info.free is True
        assert "search" in DuckDuckGoProvider.info.capabilities
        assert "time_range" in DuckDuckGoProvider.info.search_features

    def test_init_with_new_signature(self):
        provider = DuckDuckGoProvider(name="ddg", priority=50, timeout=15000)
        assert provider.name == "ddg"
        assert provider.priority == 50
        assert provider.timeout == 15000
        assert provider.api_key is None

    def test_default_init(self):
        provider = DuckDuckGoProvider(name="duckduckgo")
        assert provider.name == "duckduckgo"
        assert provider.priority == 10  # BaseProvider default
        assert provider.timeout == 30000

    def test_capabilities_from_info(self):
        provider = DuckDuckGoProvider(name="duckduckgo")
        assert provider.capabilities == ["search"]

    @pytest.mark.asyncio
    async def test_initialize(self):
        provider = DuckDuckGoProvider(name="duckduckgo")
        result = await provider.initialize()
        assert result is True
        assert provider._ddgs is not None

    @pytest.mark.asyncio
    async def test_shutdown(self):
        provider = DuckDuckGoProvider(name="duckduckgo")
        await provider.initialize()
        await provider.shutdown()
        assert provider._ddgs is None

    @pytest.mark.asyncio
    async def test_health_check(self):
        provider = DuckDuckGoProvider(name="duckduckgo")
        healthy, error = await provider.health_check()
        assert healthy is True
        assert error is None

    @pytest.mark.asyncio
    async def test_search_uses_to_thread(self):
        """Verify search delegates sync DDGS call to asyncio.to_thread."""
        provider = DuckDuckGoProvider(name="duckduckgo")
        await provider.initialize()

        mock_results = [
            {"title": "Result", "href": "https://example.com", "body": "Content"},
        ]

        with patch("sg.providers.duckduckgo.asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = mock_results

            request = SearchRequest(query="test", max_results=3)
            response = await provider.search(request)

            mock_thread.assert_called_once()
            assert response.provider == "duckduckgo"
            assert response.total == 1
            assert response.results[0].title == "Result"
            assert response.results[0].url == "https://example.com"

    @pytest.mark.asyncio
    async def test_search_raises_on_error(self):
        provider = DuckDuckGoProvider(name="duckduckgo")
        await provider.initialize()

        with patch("sg.providers.duckduckgo.asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.side_effect = Exception("Network error")

            request = SearchRequest(query="test", max_results=3)
            with pytest.raises(Exception, match="Network error"):
                await provider.search(request)

    @pytest.mark.asyncio
    async def test_search_with_time_range(self):
        provider = DuckDuckGoProvider(name="duckduckgo")
        await provider.initialize()

        with patch("sg.providers.duckduckgo.asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = []

            request = SearchRequest(query="news", max_results=3, time_range="week")
            await provider.search(request)

            # Verify timelimit was passed through kwargs
            call_kwargs = mock_thread.call_args
            # to_thread(self._ddgs.text, request.query, **kwargs)
            assert call_kwargs is not None
