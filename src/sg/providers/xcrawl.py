"""Xcrawl provider — search + web scraping with LLM-friendly output."""

import asyncio
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
        search_features=("domains", "exclude_domains"),  # via site: operators
    )

    DEFAULT_BASE_URL = "https://run.xcrawl.com"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._client = None
        self._base_url = self.url or self.DEFAULT_BASE_URL

    async def initialize(self) -> bool:
        api_key = self.api_key or self.env_value("XCRAWL_API_KEY")
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
            request.domains,
            request.exclude_domains,
        )

        payload = {
            "query": query,
            "limit": request.limit,
            "location": request.location or "US",
            "language": request.language or "en",
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
                    snippet=item.get("description", ""),
                    score=0.0,
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

        async def _scrape_one(url: str) -> ExtractResult:
            try:
                fmt = (
                    request.format if request.format in ("markdown", "html", "text") else "markdown"
                )
                out_fmt = "markdown" if fmt == "text" else fmt
                payload = {
                    "url": url,
                    "mode": "sync",
                    "proxy": {"location": "US"},
                    "request": {
                        "locale": "en-US",
                        "device": "desktop",
                        "only_main_content": bool(request.only_main)
                        if request.only_main is not None
                        else True,
                    },
                    "js_render": {"enabled": True},
                    "output": {"formats": [out_fmt]},
                }

                response = await self._client.post("/v1/scrape", json=payload)
                response.raise_for_status()
                data = response.json()

                result_data = data.get("data", {})
                content = ""
                title = None

                if fmt == "html":
                    content = result_data.get("html", "") or ""
                else:
                    content = result_data.get("markdown", "") or result_data.get("text", "") or ""

                metadata = result_data.get("metadata", {}) or {}
                title = metadata.get("title")
                if not str(content).strip():
                    return ExtractResult(url=url, content="", error="empty extract")

                return ExtractResult(url=url, content=content, title=title)

            except Exception as e:
                return ExtractResult(url=url, content="", error=str(e))

        results = await asyncio.gather(*[_scrape_one(url) for url in request.urls])

        latency = (time.perf_counter() - start) * 1000
        return ExtractResponse(results=list(results), provider=self.name, latency_ms=latency)
