"""DuckDuckGo provider - Free fallback without API key."""

import logging
import time
from typing import Any

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS  # fallback

from ..models.search import SearchRequest, SearchResponse, SearchResult
from .base import SearchProvider


class DuckDuckGoProvider(SearchProvider):
    """DuckDuckGo search provider - Free, no API key required.

    Best for: Fallback when other providers fail, privacy-focused searches.
    """

    name = "duckduckgo"
    capabilities = ["search"]
    is_fallback = True  # Mark as fallback provider

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._ddgs = None
        self.priority = 100  # Lowest priority, used as fallback
        self.weight = 1

    async def initialize(self) -> bool:
        """Initialize DuckDuckGo client."""
        try:
            self._ddgs = DDGS()
            self.healthy = True
            return True
        except Exception as e:
            self.healthy = False
            return False

    async def shutdown(self) -> None:
        """No cleanup needed."""
        self._ddgs = None

    async def health_check(self) -> tuple[bool, str | None]:
        """DuckDuckGo is always available."""
        return (True, None)

    async def search(self, request: SearchRequest) -> SearchResponse:
        """Execute search using DuckDuckGo."""
        start_time = time.time()

        try:
            # Build search params (query is positional, rest are kwargs)
            kwargs: dict[str, Any] = {
                "max_results": request.max_results,
            }

            # Time range
            if request.time_range:
                time_map = {
                    "day": "d",
                    "week": "w",
                    "month": "m",
                    "year": "y",
                }
                kwargs["timelimit"] = time_map.get(request.time_range)

            # Region/language
            if request.extra.get("region"):
                kwargs["region"] = request.extra["region"]

            # Run search (query is positional argument)
            results = []
            if self._ddgs:
                raw_results = self._ddgs.text(request.query, **kwargs)

                for r in raw_results:
                    results.append(SearchResult(
                        title=r.get("title", ""),
                        url=r.get("href", ""),
                        content=r.get("body", ""),
                        snippet=r.get("body", ""),
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

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            # Return empty results on error (as fallback)
            return SearchResponse(
                query=request.query,
                provider=self.name,
                results=[],
                total=0,
                latency_ms=latency_ms,
            )

    async def search_images(self, query: str, max_results: int = 10) -> list[dict]:
        """Search for images."""
        if not self._ddgs:
            return []

        try:
            results = self._ddgs.images(query, max_results=max_results)
            return results
        except Exception as e:
            logging.getLogger(__name__).warning(f"Image search failed: {e}")
            return []

    async def search_news(self, query: str, max_results: int = 10) -> list[dict]:
        """Search for news."""
        if not self._ddgs:
            return []

        try:
            results = self._ddgs.news(query, max_results=max_results)
            return results
        except Exception as e:
            logging.getLogger(__name__).warning(f"News search failed: {e}")
            return []
