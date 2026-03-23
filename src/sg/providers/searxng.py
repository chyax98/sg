"""SearXNG provider — self-hosted meta-search, raw httpx."""

import time

import httpx

from ..models.search import SearchRequest, SearchResponse, SearchResult
from .base import ProviderInfo, SearchProvider


class SearXNGProvider(SearchProvider):
    """SearXNG: self-hosted meta-search engine. Free, no API key."""

    info = ProviderInfo(
        type="searxng",
        display_name="SearXNG",
        needs_api_key=False,
        needs_url=True,
        free=True,
        capabilities=("search",),
        search_features=("time_range",),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._client: httpx.AsyncClient | None = None

    async def initialize(self) -> bool:
        base_url = self.url or "http://localhost:8888"
        self._client = httpx.AsyncClient(
            base_url=base_url,
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
        try:
            resp = await self._client.get("/search", params={"q": "test", "format": "json"})
            return resp.status_code == 200, None
        except Exception as e:
            return (False, str(e))

    async def search(self, request: SearchRequest) -> SearchResponse:
        if not self._client:
            raise RuntimeError("Not initialized")
        self.validate_search_request(request)

        start = time.perf_counter()

        params: dict[str, str | int] = {"q": request.query, "format": "json", "pageno": 1}
        if request.time_range:
            params["time_range"] = request.time_range

        resp = await self._client.get("/search", params=params)
        resp.raise_for_status()
        data = resp.json()

        results = [
            SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                content=item.get("content", ""),
                score=float(item.get("score", 0)),
                source=self.name,
            )
            for item in data.get("results", [])[:request.max_results]
        ]

        latency = (time.perf_counter() - start) * 1000
        return SearchResponse(
            query=request.query, provider=self.name,
            results=results, total=len(results), latency_ms=latency,
        )
