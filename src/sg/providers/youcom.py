"""You.com provider — raw httpx (SDK is beta/auto-generated)."""

import os
import time

import httpx

from ..models.search import SearchRequest, SearchResponse, SearchResult
from .base import ProviderInfo, SearchProvider


class YouComProvider(SearchProvider):
    """You.com: high accuracy AI search (93% SimpleQA).

    API: https://docs.you.com
    """

    info = ProviderInfo(
        type="youcom",
        display_name="You.com",
        capabilities=("search",),
        search_features=("include_domains", "exclude_domains", "time_range"),
    )

    BASE_URL = "https://ydc-index.io"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._client: httpx.AsyncClient | None = None

    async def initialize(self) -> bool:
        api_key = self.api_key or os.environ.get("YOUCOM_API_KEY")
        if not api_key:
            return False
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={"X-API-Key": api_key, "Accept": "application/json"},
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
            request.include_domains,
            request.exclude_domains,
        )
        params = {"query": query, "count": request.max_results}
        if request.time_range:
            freshness_map = {
                "day": "day",
                "week": "week",
                "month": "month",
                "year": "year",
            }
            if request.time_range in freshness_map:
                params["freshness"] = freshness_map[request.time_range]
        if request.extra.get("language"):
            params["language"] = request.extra["language"]

        resp = await self._client.get("/v1/search", params=params)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("results", {}).get("web", []):
            content = item.get("description", "")
            snippets = item.get("snippets", [])
            if snippets:
                snippet_text = "\n".join(snippets[:2])
                content = f"{content}\n{snippet_text}" if content else snippet_text

            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                content=content.strip(),
                source=self.name,
                published_date=item.get("page_age"),
            ))

        latency = (time.perf_counter() - start) * 1000
        return SearchResponse(
            query=request.query, provider=self.name,
            results=results, total=len(results), latency_ms=latency,
        )
