"""Firecrawl provider - Search + Extract combined."""

import logging
import time

import httpx

from ..models.search import ExtractRequest, ExtractResult, ExtractResponse, SearchRequest, SearchResponse, SearchResult
from .base import ExtractProvider, SearchProvider

logger = logging.getLogger(__name__)


class FirecrawlProvider(SearchProvider, ExtractProvider):
    """Firecrawl - Combined search and content extraction.

    Returns clean markdown content, not just snippets.
    """

    name = "firecrawl"
    capabilities = ["search", "extract"]
    BASE_URL = "https://api.firecrawl.dev/v1"

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key
        self.priority = kwargs.get("priority", 15)

    async def initialize(self) -> bool:
        if not self.api_key:
            logger.warning("Firecrawl: No API key provided")
            return False
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=self.timeout / 1000,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        return True

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> tuple[bool, str | None]:
        if not self.api_key:
            return False, "No API key"
        # Firecrawl doesn't have a dedicated health endpoint, just check key format
        return True, None

    async def search(self, request: SearchRequest) -> SearchResponse:
        """Search and return results with full content."""
        start = time.perf_counter()

        resp = await self._client.post(
            "/search",
            json={
                "query": request.query,
                "limit": request.max_results,
            },
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("data", data.get("results", [])):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", item.get("link", "")),
                content=item.get("markdown", item.get("content", item.get("description", ""))),
                snippet=item.get("description", ""),
                score=item.get("score", 0),
                source=self.name,
            ))

        latency = (time.perf_counter() - start) * 1000
        return SearchResponse(
            query=request.query,
            provider=self.name,
            results=results[:request.max_results],
            total=len(results),
            latency_ms=latency,
        )

    async def extract(self, request: ExtractRequest) -> ExtractResponse:
        """Extract content from URLs using scrape endpoint."""
        start = time.perf_counter()
        results = []

        for url in request.urls:
            try:
                resp = await self._client.post(
                    "/scrape",
                    json={"url": url},
                )
                resp.raise_for_status()
                data = resp.json()

                results.append(ExtractResult(
                    url=url,
                    content=data.get("data", {}).get("markdown", data.get("markdown", "")),
                    title=data.get("data", {}).get("metadata", {}).get("title", ""),
                ))
            except Exception as e:
                results.append(ExtractResult(url=url, content="", error=str(e)))

        latency = (time.perf_counter() - start) * 1000
        return ExtractResponse(results=results, provider=self.name, latency_ms=latency)
