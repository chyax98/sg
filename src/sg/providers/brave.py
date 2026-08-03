"""Brave Search provider — raw httpx (no official SDK)."""

import time
from typing import Any

import httpx

from ..models.search import SearchRequest, SearchResponse, SearchResult
from .base import ProviderInfo, SearchProvider


class BraveProvider(SearchProvider):
    """Brave Search: privacy-focused with search operators.

    Free 2,000/month, Pro from $5/month.
    """

    info = ProviderInfo(
        type="brave",
        display_name="Brave Search",
        capabilities=("search",),
        search_features=("domains", "exclude_domains", "time_range", "language", "location"),
    )

    BASE_URL = "https://api.search.brave.com/res/v1"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._client: httpx.AsyncClient | None = None

    async def initialize(self) -> bool:
        api_key = self.api_key or self.env_value("BRAVE_API_KEY")
        if not api_key:
            return False
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={"Accept": "application/json", "X-Subscription-Token": api_key},
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
        if not self._client:
            raise RuntimeError("Not initialized")
        self.validate_search_request(request)

        start = time.perf_counter()

        query = self.apply_domain_operators(
            request.query,
            request.domains,
            request.exclude_domains,
        )

        params: dict[str, Any] = {"q": query, "count": request.limit}
        if request.time_range:
            freshness_map = {
                "day": "pd",
                "week": "pw",
                "month": "pm",
                "year": "py",
            }
            if request.time_range in freshness_map:
                params["freshness"] = freshness_map[request.time_range]
        if request.location:
            params["country"] = request.location
        if request.language:
            params["search_lang"] = request.language

        resp = await self._client.get("/web/search", params=params)
        resp.raise_for_status()
        data = resp.json()

        results = [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("description", ""),
                source=self.name,
            )
            for r in data.get("web", {}).get("results", [])
        ]

        latency = (time.perf_counter() - start) * 1000
        return SearchResponse(
            query=request.query,
            provider=self.name,
            results=results,
            total=len(results),
            latency_ms=latency,
        )
