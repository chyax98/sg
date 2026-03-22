"""Serper provider - Google SERP API via serper.dev."""

import logging
import os
import time

import httpx

from ..models.search import SearchRequest, SearchResponse, SearchResult
from .base import SearchProvider

logger = logging.getLogger(__name__)


class SerperProvider(SearchProvider):
    """Serper search provider (Google SERP API)."""

    name = "serper"
    capabilities = ["search", "news", "images"]
    BASE_URL = "https://google.serper.dev"

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key or os.environ.get("SERPER_API_KEY", "")
        self.priority = kwargs.get("priority", 8)

    async def initialize(self) -> bool:
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=self.timeout / 1000,
            headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
        )
        return True

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> tuple[bool, str | None]:
        if not self.api_key:
            return False, "No API key"
        try:
            resp = await self._client.post("/search", json={"q": "test", "num": 1})
            return resp.status_code == 200, None
        except Exception as e:
            return False, str(e)

    async def search(self, request: SearchRequest) -> SearchResponse:
        start = time.perf_counter()

        payload = {"q": request.query, "num": request.max_results}

        if request.time_range:
            tbs_map = {"day": "qdr:d", "week": "qdr:w", "month": "qdr:m", "year": "qdr:y"}
            if request.time_range in tbs_map:
                payload["tbs"] = tbs_map[request.time_range]

        resp = await self._client.post("/search", json=payload)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("organic", []):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("link", ""),
                content=item.get("snippet", ""),
                score=float(item.get("position", 0)),
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
