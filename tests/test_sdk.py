"""Tests for SDK client."""

import pytest
from unittest.mock import patch, MagicMock

from sg.sdk.client import SearchClient, AsyncSearchClient
from sg.models.search import SearchResponse


class TestSearchClient:
    @pytest.fixture
    def mock_response(self):
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
        }

    @patch("httpx.Client.post")
    def test_search(self, mock_post, mock_response):
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

    @patch("httpx.Client.post")
    def test_search_with_params(self, mock_post, mock_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_response
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        client = SearchClient()
        client.search(
            "test",
            provider="tavily-main",
            max_results=5,
            include_domains=["example.com"],
            time_range="week",
            search_depth="advanced",
        )

        call_args = mock_post.call_args
        body = call_args[1]["json"]
        assert body["query"] == "test"
        assert body["provider"] == "tavily-main"
        assert body["max_results"] == 5
        assert body["include_domains"] == ["example.com"]
        assert body["time_range"] == "week"
        assert body["search_depth"] == "advanced"

    @patch("httpx.Client.post")
    def test_extract(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": [{"url": "https://example.com", "content": "extracted"}],
            "provider": "jina",
            "latency_ms": 200.0,
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        client = SearchClient()
        result = client.extract(["https://example.com"])

        assert result.provider == "jina"
        assert len(result.results) == 1

    @patch("httpx.Client.post")
    def test_research(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "topic": "AI",
            "content": "Research content",
            "sources": ["https://example.com"],
            "provider": "tavily",
            "latency_ms": 5000.0,
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        client = SearchClient()
        result = client.research("AI")

        assert result.topic == "AI"
        assert result.provider == "tavily"

    @patch("httpx.Client.get")
    def test_list_providers(self, mock_get):
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
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "running": True,
            "port": 8100,
            "strategy": "priority",
            "providers": {"total": 1, "available": ["duckduckgo"]},
            "metrics": {},
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        client = SearchClient()
        status = client.get_status()

        assert status["running"] is True
        assert status["strategy"] == "priority"

    @patch("httpx.Client.post")
    def test_health_check(self, mock_post):
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

    def test_context_manager(self):
        with SearchClient() as client:
            assert client._client is not None


class TestAsyncSearchClient:
    @pytest.fixture
    def mock_response(self):
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
    @patch("httpx.AsyncClient.post")
    async def test_search_with_search_depth(self, mock_post, mock_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_response
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        client = AsyncSearchClient()
        await client.search("test query", search_depth="advanced")

        body = mock_post.call_args[1]["json"]
        assert body["search_depth"] == "advanced"
        await client.close()

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_list_providers(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"name": "duckduckgo", "healthy": True}]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        client = AsyncSearchClient()
        providers = await client.list_providers()

        assert len(providers) == 1

        await client.close()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        async with AsyncSearchClient() as client:
            assert client._client is not None
