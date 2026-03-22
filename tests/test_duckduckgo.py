"""Tests for DuckDuckGo provider."""

import pytest
from unittest.mock import patch, MagicMock

from sg.providers.duckduckgo import DuckDuckGoProvider
from sg.models.search import SearchRequest


class TestDuckDuckGoProvider:
    """Test DuckDuckGo provider."""

    def test_provider_attributes(self):
        """Test provider basic attributes."""
        provider = DuckDuckGoProvider()
        assert provider.name == "duckduckgo"
        assert provider.is_fallback is True
        assert "search" in provider.capabilities
        assert provider.priority == 100

    @pytest.mark.asyncio
    async def test_initialize(self):
        """Test provider initialization."""
        provider = DuckDuckGoProvider()
        result = await provider.initialize()
        assert result is True
        assert provider.healthy is True
        assert provider._ddgs is not None

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test provider shutdown."""
        provider = DuckDuckGoProvider()
        await provider.initialize()
        await provider.shutdown()
        assert provider._ddgs is None

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test health check always returns healthy."""
        provider = DuckDuckGoProvider()
        healthy, error = await provider.health_check()
        assert healthy is True
        assert error is None

    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        """Test search returns results."""
        provider = DuckDuckGoProvider()
        await provider.initialize()

        request = SearchRequest(query="Python programming", max_results=3)
        response = await provider.search(request)

        assert response.query == "Python programming"
        assert response.provider == "duckduckgo"
        assert response.total > 0
        assert len(response.results) > 0

        # Check result structure
        result = response.results[0]
        assert result.title
        assert result.url
        assert result.source == "duckduckgo"

    @pytest.mark.asyncio
    async def test_search_with_time_range(self):
        """Test search with time range filter."""
        provider = DuckDuckGoProvider()
        await provider.initialize()

        request = SearchRequest(
            query="Python news",
            max_results=3,
            time_range="week"
        )
        response = await provider.search(request)

        assert response.query == "Python news"
        assert response.total >= 0

    @pytest.mark.asyncio
    async def test_search_empty_results_on_error(self):
        """Test search returns empty results on error."""
        provider = DuckDuckGoProvider()
        await provider.initialize()

        # Mock DDGS to raise exception
        with patch.object(provider, '_ddgs') as mock_ddgs:
            mock_ddgs.text.side_effect = Exception("Test error")

            request = SearchRequest(query="test", max_results=3)
            response = await provider.search(request)

            assert response.total == 0
            assert len(response.results) == 0
