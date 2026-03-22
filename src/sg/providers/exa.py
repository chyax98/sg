"""Exa provider - AI semantic search."""

import os
import time
from typing import Any

import httpx

from ..models.search import (
    ExtractRequest,
    ExtractResponse,
    ExtractResult,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from .base import ExtractProvider, SearchProvider


class ExaProvider(SearchProvider, ExtractProvider):
    """Exa search provider.

    Features:
    - AI-powered semantic search
    - Category filtering (company, research paper, people)
    - Content extraction
    - Similar content discovery

    Pricing: Free 1,000/month, Pro from $10/month
    """

    name = "exa"
    capabilities = ["search", "extract", "contents", "similar"]

    BASE_URL = "https://api.exa.ai"

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key or os.environ.get("EXA_API_KEY")
        self.priority = kwargs.get("priority", 15)
        self.weight = kwargs.get("weight", 4)
        self._client: httpx.AsyncClient | None = None

    async def initialize(self) -> bool:
        """Initialize Exa client."""
        if not self.api_key:
            self.healthy = False
            return False

        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
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
            return (False, "EXA_API_KEY not set")

        try:
            if self._client:
                resp = await self._client.post("/search", json={
                    "query": "test",
                    "numResults": 1,
                })
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
        """Execute semantic search."""
        start_time = time.time()

        if not self._client:
            raise RuntimeError("Provider not initialized")

        body: dict[str, Any] = {
            "query": request.query,
            "numResults": request.max_results,
            "type": request.extra.get("type", "auto"),
            "contents": {
                "highlights": True,
                "livecrawl": request.extra.get("livecrawl", "fallback"),
            },
        }

        # Category filter
        if request.extra.get("category"):
            body["category"] = request.extra["category"]

        # Domain filters
        if request.include_domains:
            body["includeDomains"] = request.include_domains
        if request.exclude_domains:
            body["excludeDomains"] = request.exclude_domains

        # Date filters
        if request.extra.get("startPublishedDate"):
            body["startPublishedDate"] = request.extra["startPublishedDate"]
        if request.extra.get("endPublishedDate"):
            body["endPublishedDate"] = request.extra["endPublishedDate"]

        resp = await self._client.post("/search", json=body)
        resp.raise_for_status()
        data = resp.json()

        # Parse results
        results = []
        for r in data.get("results", []):
            highlights = r.get("highlights", [])
            content = "\n".join(highlights) if highlights else ""

            results.append(SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=content,
                snippet=content[:500] if content else "",
                source=self.name,
                score=r.get("score", 0.0),
                published_date=r.get("publishedDate"),
                author=r.get("author"),
            ))

        latency_ms = (time.time() - start_time) * 1000

        return SearchResponse(
            query=request.query,
            provider=self.name,
            results=results,
            total=len(results),
            latency_ms=latency_ms,
        )

    async def extract(self, request: ExtractRequest) -> ExtractResponse:
        """Extract content from URLs using Exa contents API."""
        start_time = time.time()

        if not self._client:
            raise RuntimeError("Provider not initialized")

        body = {
            "urls": request.urls,
            "contents": {
                "text": True,
                "livecrawl": "preferred" if request.extract_depth == "advanced" else "fallback",
            },
        }

        resp = await self._client.post("/contents", json=body)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for r in data.get("results", []):
            results.append(ExtractResult(
                url=r.get("url", ""),
                content=r.get("text", ""),
                title=r.get("title"),
            ))

        latency_ms = (time.time() - start_time) * 1000

        return ExtractResponse(
            results=results,
            provider=self.name,
            latency_ms=latency_ms,
        )

    async def find_similar(self, url: str, max_results: int = 10) -> SearchResponse:
        """Find similar content."""
        start_time = time.time()

        if not self._client:
            raise RuntimeError("Provider not initialized")

        resp = await self._client.post("/findSimilar", json={
            "url": url,
            "numResults": max_results,
            "contents": {"highlights": True},
        })
        resp.raise_for_status()
        data = resp.json()

        results = []
        for r in data.get("results", []):
            highlights = r.get("highlights", [])
            results.append(SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content="\n".join(highlights) if highlights else "",
                source=self.name,
                score=r.get("score", 0.0),
            ))

        latency_ms = (time.time() - start_time) * 1000

        return SearchResponse(
            query=f"similar:{url}",
            provider=self.name,
            results=results,
            total=len(results),
            latency_ms=latency_ms,
        )
