"""DuckDuckGo provider — free fallback, no API key needed."""

import asyncio
import time
from typing import Any

from ..models.search import SearchRequest, SearchResponse, SearchResult
from .base import ProviderInfo, SearchProvider


class DuckDuckGoProvider(SearchProvider):
    """DuckDuckGo: free search, no API key. Used as fallback."""

    info = ProviderInfo(
        type="duckduckgo",
        display_name="DuckDuckGo",
        needs_api_key=False,
        free=True,
        capabilities=("search",),
        search_features=("time_range",),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._ddgs = None

    async def initialize(self) -> bool:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS  # type: ignore[assignment]
        self._ddgs = DDGS()
        return True

    async def shutdown(self) -> None:
        self._ddgs = None

    async def health_check(self) -> tuple[bool, str | None]:
        return (True, None)

    async def search(self, request: SearchRequest) -> SearchResponse:
        self.validate_search_request(request)
        start = time.perf_counter()

        kwargs: dict[str, Any] = {"max_results": request.max_results}
        if request.time_range:
            time_map = {"day": "d", "week": "w", "month": "m", "year": "y"}
            kwargs["timelimit"] = time_map.get(request.time_range)
        if request.extra.get("region"):
            kwargs["region"] = request.extra["region"]

        # DDGS.text() is synchronous — run in thread to avoid blocking
        raw = await asyncio.to_thread(self._ddgs.text, request.query, **kwargs)  # type: ignore[union-attr]

        results = [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("href", ""),
                content=r.get("body", ""),
                source=self.name,
            )
            for r in raw
        ]

        latency = (time.perf_counter() - start) * 1000
        return SearchResponse(
            query=request.query,
            provider=self.name,
            results=results,
            total=len(results),
            latency_ms=latency,
        )
