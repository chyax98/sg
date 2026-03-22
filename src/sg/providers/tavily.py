"""Tavily provider - AI-optimized search with extract/crawl/research."""

import asyncio
import os
import time
from typing import Any

import httpx

from ..models.search import (
    ExtractRequest,
    ExtractResponse,
    ExtractResult,
    ResearchRequest,
    ResearchResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from .base import ExtractProvider, ResearchProvider, SearchProvider


class TavilyProvider(SearchProvider, ExtractProvider, ResearchProvider):
    """Tavily search provider.

    Features:
    - AI-optimized search results
    - Content extraction from URLs
    - Website crawling
    - Deep research capability

    Pricing: Free 1,000/month, Pro from $29/month
    """

    name = "tavily"
    capabilities = ["search", "extract", "crawl", "research"]

    BASE_URL = "https://api.tavily.com"

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key or os.environ.get("TAVILY_API_KEY")
        self.priority = kwargs.get("priority", 10)
        self.weight = kwargs.get("weight", 5)
        self._client: httpx.AsyncClient | None = None

    async def initialize(self) -> bool:
        """Initialize Tavily client."""
        if not self.api_key:
            self.healthy = False
            return False

        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
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
            return (False, "TAVILY_API_KEY not set")

        try:
            # Simple search to verify API key
            if self._client:
                resp = await self._client.post("/search", json={
                    "query": "test",
                    "max_results": 1,
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
        """Execute search using Tavily API."""
        start_time = time.time()

        if not self._client:
            raise RuntimeError("Provider not initialized")

        # Build request body
        body: dict[str, Any] = {
            "query": request.query,
            "max_results": request.max_results,
            "search_depth": request.extra.get("search_depth", "basic"),
            "topic": request.extra.get("topic", "general"),
        }

        # Domain filters
        if request.include_domains:
            body["include_domains"] = request.include_domains
        if request.exclude_domains:
            body["exclude_domains"] = request.exclude_domains

        # Time filters
        if request.time_range:
            body["time_range"] = request.time_range
        if request.extra.get("start_date"):
            body["start_date"] = request.extra["start_date"]
        if request.extra.get("end_date"):
            body["end_date"] = request.extra["end_date"]

        # Extra options
        if request.extra.get("include_images"):
            body["include_images"] = True
        if request.extra.get("include_raw_content"):
            body["include_raw_content"] = True

        resp = await self._client.post("/search", json=body)
        resp.raise_for_status()
        data = resp.json()

        # Parse results
        results = []
        for r in data.get("results", []):
            results.append(SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("content", ""),
                snippet=r.get("content", ""),
                score=r.get("score", 0.0),
                source=self.name,
                raw_content=r.get("raw_content"),
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
        """Extract content from URLs."""
        start_time = time.time()

        if not self._client:
            raise RuntimeError("Provider not initialized")

        body = {
            "urls": request.urls,
            "extract_depth": request.extract_depth,
            "format": request.format,
        }

        if request.query:
            body["query"] = request.query

        resp = await self._client.post("/extract", json=body)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for r in data.get("results", []):
            results.append(ExtractResult(
                url=r.get("url", ""),
                content=r.get("raw_content", ""),
                title=r.get("title"),
            ))

        latency_ms = (time.time() - start_time) * 1000

        return ExtractResponse(
            results=results,
            provider=self.name,
            latency_ms=latency_ms,
        )

    async def research(self, request: ResearchRequest) -> ResearchResponse:
        """Execute deep research."""
        start_time = time.time()

        if not self._client:
            raise RuntimeError("Provider not initialized")

        # Start research
        resp = await self._client.post("/research", json={
            "input": request.topic,
            "model": request.depth,
        })
        resp.raise_for_status()
        data = resp.json()

        request_id = data.get("request_id")
        if not request_id:
            raise RuntimeError("No request_id returned")

        # Poll for results
        max_wait = 300 if request.depth == "pro" else 60  # seconds
        interval = 2
        elapsed = 0

        while elapsed < max_wait:
            await asyncio.sleep(interval)
            elapsed += interval

            poll_resp = await self._client.get(f"/research/{request_id}")
            poll_data = poll_resp.json()

            status = poll_data.get("status")
            if status == "completed":
                latency_ms = (time.time() - start_time) * 1000
                return ResearchResponse(
                    topic=request.topic,
                    content=poll_data.get("content", ""),
                    sources=poll_data.get("sources", []),
                    provider=self.name,
                    latency_ms=latency_ms,
                )
            elif status == "failed":
                raise RuntimeError("Research failed")

        raise RuntimeError("Research timed out")
