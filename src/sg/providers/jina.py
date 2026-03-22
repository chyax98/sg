"""Jina Reader provider - Free URL content extraction, paid search."""

import logging
import time

import httpx

from ..models.search import ExtractRequest, ExtractResult, ExtractResponse, SearchRequest, SearchResponse, SearchResult
from .base import ExtractProvider, SearchProvider

logger = logging.getLogger(__name__)


class JinaReaderProvider(SearchProvider, ExtractProvider):
    """Jina Reader - Free URL content extraction.

    - r.jina.ai/{url} - Extract URL content as markdown (FREE, no key needed)
    - s.jina.ai/{query} - Search (requires API key)

    Use this as the default extract fallback since it's free.
    """

    name = "jina"
    capabilities = ["extract"]  # search requires key, extract is free
    BASE_URL = "https://r.jina.ai"

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key  # Optional, enables search
        self.priority = kwargs.get("priority", 90)  # Low priority for search, high for extract
        self._extract_client = None
        self._search_client = None

    async def initialize(self) -> bool:
        # Extract client - always works (free)
        self._extract_client = httpx.AsyncClient(
            timeout=self.timeout / 1000,
            follow_redirects=True,
        )

        # Search client - requires API key
        if self.api_key:
            self._search_client = httpx.AsyncClient(
                base_url="https://s.jina.ai",
                timeout=self.timeout / 1000,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            self.capabilities = ["search", "extract"]

        return True

    async def shutdown(self) -> None:
        if self._extract_client:
            await self._extract_client.aclose()
            self._extract_client = None
        if self._search_client:
            await self._search_client.aclose()
            self._search_client = None

    async def health_check(self) -> tuple[bool, str | None]:
        try:
            resp = await self._extract_client.get("https://r.jina.ai/https://example.com")
            return resp.status_code == 200, None
        except Exception as e:
            return False, str(e)

    async def search(self, request: SearchRequest) -> SearchResponse:
        """Search using s.jina.ai (requires API key)."""
        if not self._search_client:
            raise RuntimeError("Jina search requires API key")

        start = time.perf_counter()

        # Use JSON format for structured response
        resp = await self._search_client.get(
            f"/{request.query}",
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("data", []):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                content=item.get("content", ""),
                snippet=item.get("content", "")[:300] if item.get("content") else "",
                source=self.name,
            ))
            if len(results) >= request.max_results:
                break

        latency = (time.perf_counter() - start) * 1000
        return SearchResponse(
            query=request.query,
            provider=self.name,
            results=results,
            total=len(results),
            latency_ms=latency,
        )

    async def extract(self, request: ExtractRequest) -> ExtractResponse:
        """Extract content from URLs as markdown (FREE)."""
        start = time.perf_counter()
        results = []

        for url in request.urls:
            try:
                resp = await self._extract_client.get(f"https://r.jina.ai/{url}")
                resp.raise_for_status()
                content = resp.text

                # Parse title from response
                title = ""
                lines = content.split("\n")
                for line in lines[:5]:
                    if line.startswith("Title:"):
                        title = line[6:].strip()
                        break

                results.append(ExtractResult(
                    url=url,
                    content=content,
                    title=title,
                ))
            except Exception as e:
                results.append(ExtractResult(url=url, content="", error=str(e)))

        latency = (time.perf_counter() - start) * 1000
        return ExtractResponse(results=results, provider=self.name, latency_ms=latency)
