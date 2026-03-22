"""Brave Search provider - Privacy-focused search with operators."""

import os
import time
from typing import Any

import httpx

from ..models.search import SearchRequest, SearchResponse, SearchResult
from .base import SearchProvider


class BraveProvider(SearchProvider):
    """Brave Search provider.

    Features:
    - Privacy-focused search
    - Rich search operators (site:, filetype:, lang:, etc.)
    - Web, images, news, videos, local search

    Pricing: Free 2,000/month, Pro from $5/month
    """

    name = "brave"
    capabilities = ["search", "images", "news", "videos", "local"]

    BASE_URL = "https://api.search.brave.com/res/v1"

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key or os.environ.get("BRAVE_API_KEY")
        self.priority = kwargs.get("priority", 12)
        self.weight = kwargs.get("weight", 3)
        self._client: httpx.AsyncClient | None = None

    async def initialize(self) -> bool:
        """Initialize Brave client."""
        if not self.api_key:
            self.healthy = False
            return False

        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": self.api_key,
            },
            timeout=30.0,
        )
        self.healthy = True
        return True

    async def shutdown(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> tuple[bool, str | None]:
        """Check API key validity."""
        if not self.api_key:
            return (False, "BRAVE_API_KEY not set")

        try:
            if self._client:
                resp = await self._client.get("/web/search", params={"q": "test", "count": 1})
                if resp.status_code == 200:
                    return (True, None)
                elif resp.status_code == 401:
                    return (False, "Invalid API key")
                else:
                    return (False, f"HTTP {resp.status_code}")
        except Exception as e:
            return (False, str(e))

        return (False, "Client not initialized")

    async def search(self, request: SearchRequest) -> SearchResponse:
        """Execute web search."""
        start_time = time.time()

        if not self._client:
            raise RuntimeError("Provider not initialized")

        # Build query with operators
        query = self._build_query(request)

        params: dict[str, Any] = {
            "q": query,
            "count": request.max_results,
        }

        # Search modifiers
        if request.extra.get("country"):
            params["country"] = request.extra["country"]
        if request.extra.get("search_lang"):
            params["search_lang"] = request.extra["search_lang"]
        if request.extra.get("freshness"):
            params["freshness"] = request.extra["freshness"]

        resp = await self._client.get("/web/search", params=params)
        resp.raise_for_status()
        data = resp.json()

        # Parse results
        results = []
        for r in data.get("web", {}).get("results", []):
            results.append(SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("description", ""),
                snippet=r.get("description", ""),
                source=self.name,
                score=0.0,
            ))

        latency_ms = (time.time() - start_time) * 1000

        return SearchResponse(
            query=request.query,
            provider=self.name,
            results=results,
            total=len(results),
            latency_ms=latency_ms,
        )

    def _build_query(self, request: SearchRequest) -> str:
        """Build query with search operators."""
        query = request.query

        # Add domain filters as operators
        for domain in request.include_domains:
            query += f" site:{domain}"
        for domain in request.exclude_domains:
            query += f" -site:{domain}"

        # Add extra operators
        if request.extra.get("filetype"):
            query += f" filetype:{request.extra['filetype']}"
        if request.extra.get("intitle"):
            query += f" intitle:{request.extra['intitle']}"

        return query

    async def search_images(self, query: str, max_results: int = 10) -> SearchResponse:
        """Search for images."""
        start_time = time.time()

        if not self._client:
            raise RuntimeError("Provider not initialized")

        resp = await self._client.get("/images/search", params={
            "q": query,
            "count": max_results,
        })
        resp.raise_for_status()
        data = resp.json()

        results = []
        for r in data.get("results", []):
            results.append(SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("description", ""),
                source=self.name,
                extra={"image_url": r.get("properties", {}).get("url")},
            ))

        latency_ms = (time.time() - start_time) * 1000

        return SearchResponse(
            query=query,
            provider=self.name,
            results=results,
            total=len(results),
            latency_ms=latency_ms,
        )

    async def search_news(self, query: str, max_results: int = 10) -> SearchResponse:
        """Search for news."""
        start_time = time.time()

        if not self._client:
            raise RuntimeError("Provider not initialized")

        resp = await self._client.get("/news/search", params={
            "q": query,
            "count": max_results,
        })
        resp.raise_for_status()
        data = resp.json()

        results = []
        for r in data.get("results", []):
            results.append(SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("description", ""),
                source=self.name,
                published_date=r.get("age"),
            ))

        latency_ms = (time.time() - start_time) * 1000

        return SearchResponse(
            query=query,
            provider=self.name,
            results=results,
            total=len(results),
            latency_ms=latency_ms,
        )
