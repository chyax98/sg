"""Firecrawl provider — uses official firecrawl-py SDK."""

import time

from ..models.search import (
    ExtractRequest,
    ExtractResponse,
    ExtractResult,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from .base import ExtractProvider, ProviderInfo, SearchProvider


class FirecrawlProvider(SearchProvider, ExtractProvider):
    """Firecrawl: search + content extraction with clean markdown.

    Free 500/month.
    """

    info = ProviderInfo(
        type="firecrawl",
        display_name="Firecrawl",
        capabilities=("search", "extract"),
        search_features=("include_domains", "exclude_domains", "time_range"),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._client = None

    async def initialize(self) -> bool:
        if not self.api_key:
            return False
        from firecrawl import AsyncFirecrawl

        self._client = AsyncFirecrawl(api_key=self.api_key)
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

        query = self.apply_domain_operators(
            request.query,
            request.include_domains,
            request.exclude_domains,
        )
        kwargs = {
            "query": query,
            "limit": request.max_results,
        }
        if request.time_range:
            tbs_map = {"day": "qdr:d", "week": "qdr:w", "month": "qdr:m", "year": "qdr:y"}
            if request.time_range in tbs_map:
                kwargs["tbs"] = tbs_map[request.time_range]

        data = await self._client.search(
            **kwargs,
        )
        latency = (time.perf_counter() - start) * 1000

        items = data if isinstance(data, list) else data.get("data", data.get("results", []))
        results = []
        for item in items:
            if isinstance(item, dict):
                results.append(
                    SearchResult(
                        title=item.get("title") or "",
                        url=item.get("url") or item.get("link") or "",
                        content=item.get("markdown")
                        or item.get("content")
                        or item.get("description")
                        or "",
                        snippet=item.get("description") or "",
                        score=float(item.get("score", 0)),
                        source=self.name,
                    )
                )
            else:
                results.append(
                    SearchResult(
                        title=getattr(item, "title", "") or "",
                        url=getattr(item, "url", "") or "",
                        content=getattr(item, "markdown", "") or getattr(item, "content", "") or "",
                        source=self.name,
                    )
                )

        return SearchResponse(
            query=request.query,
            provider=self.name,
            results=results[: request.max_results],
            total=len(results),
            latency_ms=latency,
        )

    async def extract(self, request: ExtractRequest) -> ExtractResponse:
        if not self._client:
            raise RuntimeError("Not initialized")

        start = time.perf_counter()
        results = []

        for url in request.urls:
            try:
                data = await self._client.scrape_url(url, formats=["markdown"])
                if isinstance(data, dict):
                    content = data.get("markdown", data.get("data", {}).get("markdown", ""))
                    title = data.get("metadata", {}).get("title", "")
                else:
                    content = getattr(data, "markdown", "") or ""
                    title = ""
                results.append(ExtractResult(url=url, content=content, title=title))
            except Exception as e:
                results.append(ExtractResult(url=url, content="", error=str(e)))

        latency = (time.perf_counter() - start) * 1000
        return ExtractResponse(results=results, provider=self.name, latency_ms=latency)
