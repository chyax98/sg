"""Tests for SDK client."""

import pytest
from unittest.mock import patch, MagicMock
import httpx

from sg.sdk.client import SearchClient, AsyncSearchClient
from sg.models.search import SearchResponse


class TestSearchClient:
    """Test synchronous SDK client."""

    @pytest.fixture
    def mock_response(self):
        """Create mock search response."""
        return {
            "query": "test query",
            "provider": "duckduckgo",
            "results": [
                {
                    "title": "Test Result",
                    "url": "https://example.com",
                    "content": "Test content",
                    "snippet": "Test content",
                    "score": 0.9,
                    "source": "duckduckgo",
                }
            ],
            "total": 1,
            "latency_ms": 100.0,
            "cached": False,
        }

    @patch("httpx.Client.post")
    def test_search(self, mock_post, mock_response):
        """Test search method."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_response
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        client = SearchClient()
        result = client.search("test query")

        assert isinstance(result, SearchResponse)
        assert result.query == "test query"
        assert result.provider == "duckduckgo"
        assert result.total == 1

    @patch("httpx.Client.get")
    def test_list_providers(self, mock_get):
        """Test list_providers method."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"name": "duckduckgo", "healthy": True, "capabilities": ["search"]}
        ]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        client = SearchClient()
        providers = client.list_providers()

        assert len(providers) == 1
        assert providers[0]["name"] == "duckduckgo"

    @patch("httpx.Client.get")
    def test_get_status(self, mock_get):
        """Test get_status method."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "running": True,
            "port": 8100,
            "providers": {"total": 1, "healthy": 1},
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        client = SearchClient()
        status = client.get_status()

        assert status["running"] is True

    @patch("httpx.Client.post")
    def test_health_check(self, mock_post):
        """Test health_check method."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "healthy": ["duckduckgo"],
            "unhealthy": [],
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        client = SearchClient()
        result = client.health_check()

        assert "duckduckgo" in result["healthy"]


class TestAsyncSearchClient:
    """Test asynchronous SDK client."""

    @pytest.fixture
    def mock_response(self):
        """Create mock search response."""
        return {
            "query": "test query",
            "provider": "duckduckgo",
            "results": [],
            "total": 0,
            "latency_ms": 100.0,
        }

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.post")
    async def test_search(self, mock_post, mock_response):
        """Test async search method."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_response
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        client = AsyncSearchClient()
        result = await client.search("test query")

        assert isinstance(result, SearchResponse)
        assert result.query == "test query"

        await client.close()

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_list_providers(self, mock_get):
        """Test async list_providers method."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"name": "duckduckgo", "healthy": True}
        ]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        client = AsyncSearchClient()
        providers = await client.list_providers()

        assert len(providers) == 1

        await client.close()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test async context manager."""
        async with AsyncSearchClient() as client:
            assert client._client is not None
        # Client should be closed after context
