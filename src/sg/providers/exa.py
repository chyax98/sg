"""Exa adapter — official exa-py SDK."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any

from ..models.search import ExtractRequest, ExtractResponse, SearchRequest, SearchResponse
from ._assemble import attr, make_hit, make_page, optional_list, text
from .base import ExtractProvider, ProviderInfo, SearchProvider, cap, extract_cap, search_cap

_DEPTH_TO_TYPE = {
    "basic": "auto",
    "advanced": "deep",
    "fast": "fast",
    "ultra-fast": "instant",
}


class ExaProvider(SearchProvider, ExtractProvider):
    info = ProviderInfo(
        type="exa",
        display_name="Exa",
        capability=cap(
            search=search_cap(
                domains=True,
                exclude_domains=True,
                time_range=True,
                depth=True,
                location=True,
                raw_content=True,
            ),
            extract=extract_cap(formats=("markdown", "text"), multi_url=True),
        ),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._client = None

    async def initialize(self) -> bool:
        api_key = (
            self.api_key or self.env_value("EXA_API_KEY") or self.env_value("EXA_POOL_API_KEY")
        )
        if not api_key:
            return False
        api_base = self.url or self.env_value("EXA_POOL_BASE_URL")
        from exa_py import AsyncExa

        self._client = (
            AsyncExa(api_key=api_key, api_base=api_base) if api_base else AsyncExa(api_key=api_key)
        )
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
        kwargs: dict[str, Any] = {
            "query": request.query,
            "num_results": request.limit,
            "contents": (
                {"highlights": True, "text": True}
                if request.want_raw
                else {"highlights": True, "text": {"max_characters": 2000}}
            ),
            "type": _DEPTH_TO_TYPE.get(request.depth, "auto"),
        }
        if include := optional_list(request.domains):
            kwargs["include_domains"] = include
        if exclude := optional_list(request.exclude_domains):
            kwargs["exclude_domains"] = exclude
        if request.time_range:
            days = {"day": 1, "week": 7, "month": 30, "year": 365}.get(request.time_range)
            if days:
                kwargs["start_published_date"] = (
                    datetime.now(UTC) - timedelta(days=days)
                ).isoformat()
        if request.location:
            kwargs["user_location"] = request.location

        result = await self._client.search(**kwargs)
        latency = (time.perf_counter() - start) * 1000
        hits = []
        for r in getattr(result, "results", None) or []:
            highlights = attr(r, "highlights", default=[]) or []
            body = text(highlights, attr(r, "text"), attr(r, "summary"))
            hits.append(
                make_hit(
                    title=attr(r, "title"),
                    url=attr(r, "url"),
                    snippet=body,
                    score=attr(r, "score", default=0.0),
                    source=self.name,
                    published_at=attr(r, "published_date"),
                    author=attr(r, "author"),
                    raw=attr(r, "text") if request.want_raw else None,
                )
            )
        return SearchResponse(
            query=request.query,
            provider=self.name,
            results=hits,
            total=len(hits),
            latency_ms=latency,
        )

    async def extract(self, request: ExtractRequest) -> ExtractResponse:
        if not self._client:
            raise RuntimeError("Not initialized")
        start = time.perf_counter()
        result = await self._client.get_contents(urls=request.urls, text=True)
        pages = [
            make_page(
                url=attr(r, "url"), content=attr(r, "text", "content"), title=attr(r, "title")
            )
            for r in (getattr(result, "results", None) or [])
        ]
        return ExtractResponse(
            results=pages,
            provider=self.name,
            latency_ms=(time.perf_counter() - start) * 1000,
        )
