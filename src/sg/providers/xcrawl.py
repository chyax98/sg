"""Xcrawl provider — search + web scraping with LLM-friendly output."""

import os
import time

import httpx

from ..models.search import (
    ExtractRequest,
    ExtractResponse,
    ExtractResult,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from .base import ExtractProvider, ProviderInfo, SearchProvider


class XcrawlProvider(SearchProvider, ExtractProvider):
    """Xcrawl: Search + web scraping with LLM-friendly output.

    Docs: https://docs.xcrawl.com/doc/introduction/

    Capabilities:
    - Search: Keyword search with region/language controls
    - Scrape: Single-page extraction (markdown/html/json/screenshot)
    - Crawl: Full-site async crawling
    - Map: List all URLs within a site
    """

    info = ProviderInfo(
        type="xcrawl",
        display_name="Xcrawl",
        needs_api_key=True,
        capabilities=("search", "extract"),
        search_features=("include_domains", "exclude_domains"),  # via site: operators
    )

    DEFAULT_BASE_URL = "https://run.xcrawl.com"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._client = None
        self._base_url = self.url or self.DEFAULT_BASE_URL

    async def initialize(self) -> bool:
        api_key = self.api_key or os.environ.get("XCRAWL_API_KEY")
        if not api_key:
            return False
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=self.timeout / 1000,
        )
        return True

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> tuple[bool, str | None]:
        if not self._client:
            return (False, "Not initialized")
        return (True, None)

    async def search(self, request: SearchRequest) -> SearchResponse:
        """Search using Xcrawl SERP API."""
        if not self._client:
            raise RuntimeError("Not initialized")
        self.validate_search_request(request)

        start = time.perf_counter()

        # Build query with domain operators
        query = self.apply_domain_operators(
            request.query,
            request.include_domains,
            request.exclude_domains,
        )

        payload = {
            "query": query,
            "limit": request.max_results,
            "location": request.extra.get("location", "US"),
            "language": request.extra.get("language", "en"),
        }

        response = await self._client.post("/v1/search", json=payload)
        response.raise_for_status()
        data = response.json()

        latency = (time.perf_counter() - start) * 1000

        # Parse search results
        search_data = data.get("data", {})
        items = search_data.get("data", [])

        results = []
        for item in items:
            results.append(
                SearchResult(
                    title=item.get("title") or "",
                    url=item.get("url", ""),
                    content=item.get("description", ""),
                    snippet=item.get("description", ""),
                    score=0.0,  # Xcrawl doesn't provide relevance score
                    source=self.name,
                )
            )

        return SearchResponse(
            query=request.query,
            provider=self.name,
            results=results,
            total=len(results),
            latency_ms=latency,
        )

    async def extract(self, request: ExtractRequest) -> ExtractResponse:
        """Extract content using Xcrawl Scrape API."""
        if not self._client:
            raise RuntimeError("Not initialized")

        start = time.perf_counter()
        results = []

        for url in request.urls:
            try:
                payload = {
                    "url": url,
                    "mode": "sync",
                    "proxy": {"location": request.extra.get("proxy_location", "US")},
                    "request": {
                        "locale": request.extra.get("locale", "en-US"),
                        "device": request.extra.get("device", "desktop"),
                        "only_main_content": request.extra.get("only_main_content", False),
                    },
                    "js_render": {"enabled": request.extra.get("js_render", True)},
                    "output": {"formats": [request.format] if request.format else ["markdown"]},
                }

                response = await self._client.post("/v1/scrape", json=payload)
                response.raise_for_status()
                data = response.json()

                result_data = data.get("data", {})
                content = ""
                title = None

                # Extract content based on format
                if request.format == "markdown":
                    content = result_data.get("markdown", "")
                elif request.format == "html":
                    content = result_data.get("html", "")
                elif request.format == "json":
                    content = str(result_data.get("json", ""))
                else:
                    content = result_data.get("markdown", "")

                # Extract title from metadata
                metadata = result_data.get("metadata", {})
                title = metadata.get("title")

                results.append(ExtractResult(url=url, content=content, title=title))

            except Exception as e:
                results.append(ExtractResult(url=url, content="", error=str(e)))

        latency = (time.perf_counter() - start) * 1000
        return ExtractResponse(results=results, provider=self.name, latency_ms=latency)
