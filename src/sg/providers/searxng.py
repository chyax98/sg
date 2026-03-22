"""SearXNG provider - self-hosted meta-search engine."""

import logging
import time

import httpx

from ..models.search import SearchRequest, SearchResponse, SearchResult
from .base import SearchProvider

logger = logging.getLogger(__name__)


class SearXNGProvider(SearchProvider):
    """SearXNG search provider (self-hosted, no API key needed)."""

    name = "searxng"
    capabilities = ["search"]

    def __init__(self, url: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.url = url or "http://localhost:8888"
        self.priority = kwargs.get("priority", 20)

    async def initialize(self) -> bool:
        self._client = httpx.AsyncClient(
            base_url=self.url,
            timeout=self.timeout / 1000,
        )
        return True

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> tuple[bool, str | None]:
        try:
            resp = await self._client.get("/search", params={"q": "test", "format": "json"})
            return resp.status_code == 200, None
        except Exception as e:
            return False, str(e)

    async def search(self, request: SearchRequest) -> SearchResponse:
        start = time.perf_counter()

        params = {
            "q": request.query,
            "format": "json",
            "pageno": 1,
        }

        if request.time_range:
            time_map = {"day": "day", "week": "week", "month": "month", "year": "year"}
            if request.time_range in time_map:
                params["time_range"] = time_map[request.time_range]

        resp = await self._client.get("/search", params=params)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("results", [])[:request.max_results]:
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                content=item.get("content", ""),
                score=float(item.get("score", 0)),
                source=self.name,
            ))

        latency = (time.perf_counter() - start) * 1000
        return SearchResponse(
            query=request.query,
            provider=self.name,
            results=results,
            total=len(results),
            latency_ms=latency,
        )
