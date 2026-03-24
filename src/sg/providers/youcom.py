"""You.com provider — raw httpx (SDK is beta/auto-generated)."""

import os
import time

import httpx

from ..models.search import (
    ExtractRequest,
    ExtractResponse,
    ExtractResult,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from .base import ExtractProvider, ProviderInfo, SearchProvider


class YouComProvider(SearchProvider, ExtractProvider):
    """You.com: high accuracy AI search (93% SimpleQA).

    API: https://docs.you.com
    Supports: Search, Contents (extract)
    """

    info = ProviderInfo(
        type="youcom",
        display_name="You.com",
        capabilities=("search", "extract"),
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
        params: dict[str, str | int] = {"query": query, "count": request.max_results}
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
            lang = request.extra["language"]
            if isinstance(lang, str):
                params["language"] = lang

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

            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    content=content.strip(),
                    source=self.name,
                    published_date=item.get("page_age"),
                )
            )

        latency = (time.perf_counter() - start) * 1000
        return SearchResponse(
            query=request.query,
            provider=self.name,
            results=results,
            total=len(results),
            latency_ms=latency,
        )

    async def extract(self, request: ExtractRequest) -> ExtractResponse:
        """Extract content from URLs using You.com Contents API."""
        if not self._client:
            raise RuntimeError("Not initialized")

        start = time.perf_counter()

        # You.com Contents API expects POST with urls array
        resp = await self._client.post(
            "/v1/contents",
            json={"urls": request.urls},
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data:  # Response is a list
            results.append(
                ExtractResult(
                    url=item.get("url", ""),
                    content=item.get("html", ""),
                    title=None,  # You.com doesn't return title in contents
                )
            )

        latency = (time.perf_counter() - start) * 1000
        return ExtractResponse(results=results, provider=self.name, latency_ms=latency)
