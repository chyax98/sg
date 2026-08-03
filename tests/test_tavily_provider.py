"""Unit tests for Tavily provider call mapping (mocked SDK)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from sg.models.search import ExtractRequest, ResearchRequest, SearchRequest
from sg.providers.tavily import TavilyProvider


@pytest.fixture
def provider():
    p = TavilyProvider(name="tavily-1", api_key="test-key")
    client = MagicMock()
    client.search = AsyncMock()
    client.extract = AsyncMock()
    client.research = AsyncMock()
    client.get_research = AsyncMock()
    p._client = client
    return p


class TestTavilySearch:
    @pytest.mark.asyncio
    async def test_search_passes_core_params(self, provider):
        provider._client.search.return_value = {
            "results": [
                {
                    "title": "Hello",
                    "url": "https://example.com",
                    "content": "snippet body",
                    "score": 0.9,
                    "raw_content": "full body",
                }
            ]
        }
        req = SearchRequest(
            query="q",
            limit=5,
            domains=["example.com"],
            exclude_domains=["spam.com"],
            time_range="week",
            depth="advanced",
            want_raw=True,
        )
        resp = await provider.search(req)
        kwargs = provider._client.search.await_args.kwargs
        assert kwargs["query"] == "q"
        assert kwargs["max_results"] == 5
        assert kwargs["include_domains"] == ["example.com"]
        assert kwargs["exclude_domains"] == ["spam.com"]
        assert kwargs["time_range"] == "week"
        assert kwargs["search_depth"] == "advanced"
        assert kwargs.get("include_raw_content") in (True, "markdown")
        assert resp.results[0].snippet == "snippet body"
        assert resp.results[0].raw == "full body"
        assert resp.results[0].url == "https://example.com"


class TestTavilyExtract:
    @pytest.mark.asyncio
    async def test_extract_uses_format_and_full_content(self, provider):
        provider._client.extract.return_value = {
            "results": [
                {"url": "https://a.com", "title": "A", "raw_content": "FULL-A"},
            ],
            "failed_results": [{"url": "https://b.com", "error": "boom"}],
        }
        resp = await provider.extract(
            ExtractRequest(urls=["https://a.com", "https://b.com"], format="markdown")
        )
        kwargs = provider._client.extract.await_args.kwargs
        assert kwargs["urls"] == ["https://a.com", "https://b.com"]
        assert kwargs["format"] == "markdown"
        assert resp.results[0].content == "FULL-A"
        assert resp.results[1].error == "boom"


class TestTavilyResearch:
    @pytest.mark.asyncio
    async def test_research_uses_sdk_research_not_search(self, provider):
        provider._client.research.return_value = {
            "status": "completed",
            "content": "Full research report without truncation",
            "sources": [
                {"url": "https://src1.com"},
                "https://src2.com",
            ],
        }
        resp = await provider.research(ResearchRequest(topic="AI agents", depth="pro"))
        provider._client.search.assert_not_called()
        kwargs = provider._client.research.await_args.kwargs
        assert kwargs["input"] == "AI agents"
        assert kwargs["model"] == "pro"
        assert resp.report == "Full research report without truncation"
        assert resp.sources == ["https://src1.com", "https://src2.com"]
        assert "2000" not in resp.report

    @pytest.mark.asyncio
    async def test_research_polls_get_research_when_pending(self, provider):
        provider._client.research.return_value = {
            "request_id": "req-1",
            "status": "pending",
        }
        provider._client.get_research.side_effect = [
            {"request_id": "req-1", "status": "pending"},
            {
                "request_id": "req-1",
                "status": "completed",
                "content": "polled report",
                "sources": [],
            },
        ]
        # speed up sleep
        import sg.providers.tavily as mod

        original = mod.asyncio.sleep
        mod.asyncio.sleep = AsyncMock()
        try:
            resp = await provider.research(ResearchRequest(topic="x", depth="mini"))
        finally:
            mod.asyncio.sleep = original
        assert resp.report == "polled report"
        assert provider._client.get_research.await_count == 2

    @pytest.mark.asyncio
    async def test_research_empty_content_fails(self, provider):
        provider._client.research.return_value = {"status": "completed", "content": ""}
        with pytest.raises(RuntimeError, match="empty report"):
            await provider.research(ResearchRequest(topic="x"))
