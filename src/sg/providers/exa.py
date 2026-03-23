"""Exa provider — uses official exa-py SDK."""

import os
import time
from datetime import datetime, timedelta, timezone

from ..models.search import (
    ExtractRequest, ExtractResponse, ExtractResult,
    SearchRequest, SearchResponse, SearchResult,
)
from .base import ExtractProvider, ProviderInfo, SearchProvider


class ExaProvider(SearchProvider, ExtractProvider):
    """Exa: AI semantic search + content extraction.

    Free 1,000/month, Pro from $10/month.
    """

    info = ProviderInfo(
        type="exa",
        display_name="Exa",
        capabilities=("search", "extract"),
        search_features=("include_domains", "exclude_domains", "time_range", "search_depth"),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._client = None

    async def initialize(self) -> bool:
        api_key = self.api_key or os.environ.get("EXA_API_KEY") or os.environ.get("EXA_POOL_API_KEY")
        if not api_key:
            return False
        api_base = self.url or os.environ.get("EXA_POOL_BASE_URL")
        from exa_py import AsyncExa
        if api_base:
            self._client = AsyncExa(api_key=api_key, api_base=api_base)
        else:
            self._client = AsyncExa(api_key=api_key)
        return True

    async def shutdown(self) -> None:
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

        kwargs = {
            "query": request.query,
            "num_results": request.max_results,
            "contents": {"highlights": True},
        }
        if request.search_depth != "basic" and not request.extra.get("type"):
            type_map = {
                "basic": "auto",
                "advanced": "deep",
                "fast": "fast",
                "ultra-fast": "instant",
            }
            if request.search_depth in type_map:
                kwargs["type"] = type_map[request.search_depth]
        if request.extra.get("type"):
            kwargs["type"] = request.extra["type"]
        if request.extra.get("category"):
            kwargs["category"] = request.extra["category"]
        if request.include_domains:
            kwargs["include_domains"] = request.include_domains
        if request.exclude_domains:
            kwargs["exclude_domains"] = request.exclude_domains
        if request.time_range:
            days_map = {"day": 1, "week": 7, "month": 30, "year": 365}
            if request.time_range in days_map:
                start_date = datetime.now(timezone.utc) - timedelta(days=days_map[request.time_range])
                kwargs["start_published_date"] = start_date.isoformat()

        result = await self._client.search(**kwargs)
        latency = (time.perf_counter() - start) * 1000

        results = []
        for r in result.results:
            highlights = getattr(r, "highlights", []) or []
            content = "\n".join(highlights) if highlights else getattr(r, "text", "") or ""

            results.append(SearchResult(
                title=getattr(r, "title", "") or "",
                url=getattr(r, "url", "") or "",
                content=content,
                score=getattr(r, "score", 0.0) or 0.0,
                source=self.name,
                published_date=getattr(r, "published_date", None),
                author=getattr(r, "author", None),
            ))

        return SearchResponse(
            query=request.query, provider=self.name,
            results=results, total=len(results), latency_ms=latency,
        )

    async def extract(self, request: ExtractRequest) -> ExtractResponse:
        if not self._client:
            raise RuntimeError("Not initialized")

        start = time.perf_counter()

        result = await self._client.get_contents(
            urls=request.urls,
            text=True,
        )
        latency = (time.perf_counter() - start) * 1000

        results = [
            ExtractResult(
                url=getattr(r, "url", "") or "",
                content=getattr(r, "text", "") or "",
                title=getattr(r, "title", None),
            )
            for r in result.results
        ]

        return ExtractResponse(results=results, provider=self.name, latency_ms=latency)
