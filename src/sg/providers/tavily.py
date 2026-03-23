"""Tavily provider — uses official tavily-python SDK."""

import os
import time

from ..models.search import (
    ExtractRequest, ExtractResponse, ExtractResult,
    ResearchRequest, ResearchResponse,
    SearchRequest, SearchResponse, SearchResult,
)
from .base import ExtractProvider, ProviderInfo, ResearchProvider, SearchProvider


class TavilyProvider(SearchProvider, ExtractProvider, ResearchProvider):
    """Tavily: AI-optimized search + extract + research.

    Free 1,000/month, Pro from $29/month.
    """

    info = ProviderInfo(
        type="tavily",
        display_name="Tavily",
        capabilities=("search", "extract", "research"),
        search_features=("include_domains", "exclude_domains", "time_range", "search_depth"),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._client = None

    async def initialize(self) -> bool:
        api_key = self.api_key or os.environ.get("TAVILY_API_KEY")
        if not api_key:
            return False
        from tavily import AsyncTavilyClient
        self._client = AsyncTavilyClient(api_key=api_key)
        return True

    async def shutdown(self) -> None:
        self._client = None

    async def health_check(self) -> tuple[bool, str | None]:
        if not self._client:
            return (False, "Not initialized")
        return (True, None)

    async def search(self, request: SearchRequest) -> SearchResponse:
        if not self._client:
            raise RuntimeError("Not initialized")
        self.validate_search_request(request)

        start = time.perf_counter()

        kwargs = {
            "query": request.query,
            "max_results": request.max_results,
            "search_depth": request.search_depth,
        }
        if request.include_domains:
            kwargs["include_domains"] = request.include_domains
        if request.exclude_domains:
            kwargs["exclude_domains"] = request.exclude_domains
        if request.time_range:
            kwargs["time_range"] = request.time_range
        if request.extra.get("topic"):
            kwargs["topic"] = request.extra["topic"]
        if request.extra.get("include_images"):
            kwargs["include_images"] = True
        if request.extra.get("include_raw_content"):
            kwargs["include_raw_content"] = True

        data = await self._client.search(**kwargs)
        latency = (time.perf_counter() - start) * 1000

        results = [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("content", ""),
                score=r.get("score", 0.0),
                source=self.name,
                raw_content=r.get("raw_content"),
            )
            for r in data.get("results", [])
        ]

        return SearchResponse(
            query=request.query, provider=self.name,
            results=results, total=len(results), latency_ms=latency,
        )

    async def extract(self, request: ExtractRequest) -> ExtractResponse:
        if not self._client:
            raise RuntimeError("Not initialized")

        start = time.perf_counter()
        data = await self._client.extract(urls=request.urls)
        latency = (time.perf_counter() - start) * 1000

        results = [
            ExtractResult(
                url=r.get("url", ""),
                content=r.get("raw_content", ""),
                title=r.get("title"),
            )
            for r in data.get("results", [])
        ]

        return ExtractResponse(results=results, provider=self.name, latency_ms=latency)

    async def research(self, request: ResearchRequest) -> ResearchResponse:
        if not self._client:
            raise RuntimeError("Not initialized")

        start = time.perf_counter()

        # tavily-python SDK handles the polling internally
        data = await self._client.search(
            query=request.topic,
            search_depth="advanced",
            max_results=request.max_sources,
            include_raw_content=True,
        )
        latency = (time.perf_counter() - start) * 1000

        contents = []
        sources = []
        for r in data.get("results", []):
            if r.get("raw_content"):
                contents.append(r["raw_content"][:2000])
            sources.append(r.get("url", ""))

        return ResearchResponse(
            topic=request.topic,
            content="\n\n---\n\n".join(contents),
            sources=sources,
            provider=self.name,
            latency_ms=latency,
        )
