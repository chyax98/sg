"""Firecrawl v2 call mapping tests (mocked client)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from sg.models.search import ExtractRequest, SearchRequest
from sg.providers.firecrawl import FirecrawlProvider


@pytest.mark.asyncio
async def test_search_uses_native_domain_filters_and_web_results():
    p = FirecrawlProvider(name="fc", api_key="k")
    p._client = SimpleNamespace(
        search=AsyncMock(
            return_value=SimpleNamespace(
                web=[
                    SimpleNamespace(
                        title="T",
                        url="https://example.com",
                        description="desc",
                        position=1,
                    )
                ]
            )
        )
    )
    resp = await p.search(
        SearchRequest(
            query="q",
            limit=3,
            domains=["example.com"],
            exclude_domains=["bad.com"],
            time_range="week",
        )
    )
    kwargs = p._client.search.await_args.kwargs
    assert kwargs["include_domains"] == ["example.com"]
    assert kwargs["exclude_domains"] == ["bad.com"]
    assert kwargs["tbs"] == "qdr:w"
    assert "site:" not in kwargs["query"]
    assert resp.results[0].url == "https://example.com"
    assert resp.results[0].snippet == "desc"


@pytest.mark.asyncio
async def test_extract_uses_scrape_not_scrape_url():
    p = FirecrawlProvider(name="fc", api_key="k")
    doc = SimpleNamespace(
        markdown="# Hello",
        metadata=SimpleNamespace(title="Hello"),
    )
    p._client = SimpleNamespace(scrape=AsyncMock(return_value=doc))
    resp = await p.extract(ExtractRequest(urls=["https://a.com"], format="markdown"))
    p._client.scrape.assert_awaited()
    assert p._client.scrape.await_args.args[0] == "https://a.com"
    assert resp.results[0].content == "# Hello"
    assert resp.results[0].title == "Hello"
