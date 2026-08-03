"""Firecrawl adapter — official firecrawl-py v2."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from ..models.search import ExtractRequest, ExtractResponse, SearchRequest, SearchResponse
from ._assemble import attr, make_hit, make_page, optional_list, text
from .base import ExtractProvider, ProviderInfo, SearchProvider, cap, extract_cap, search_cap

_TBS = {"day": "qdr:d", "week": "qdr:w", "month": "qdr:m", "year": "qdr:y"}


class FirecrawlProvider(SearchProvider, ExtractProvider):
    info = ProviderInfo(
        type="firecrawl",
        display_name="Firecrawl",
        capability=cap(
            search=search_cap(domains=True, exclude_domains=True, time_range=True, location=True),
            extract=extract_cap(
                formats=("markdown", "html", "text"), multi_url=True, only_main=True
            ),
        ),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._client = None

    async def initialize(self) -> bool:
        self.api_key = self.api_key or self.env_value("FIRECRAWL_API_KEY")
        if not self.api_key:
            return False
        from firecrawl import AsyncFirecrawl

        self._client = AsyncFirecrawl(api_key=self.api_key, timeout=max(5.0, self.timeout / 1000))
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
        kwargs: dict[str, Any] = {"query": request.query, "limit": request.limit}
        if include := optional_list(request.domains):
            kwargs["include_domains"] = include
        if exclude := optional_list(request.exclude_domains):
            kwargs["exclude_domains"] = exclude
        if request.time_range in _TBS:
            kwargs["tbs"] = _TBS[request.time_range]
        if request.location:
            kwargs["location"] = request.location

        data = await self._client.search(**kwargs)
        latency = (time.perf_counter() - start) * 1000
        items = self._items(data)[: request.limit]
        hits = [
            make_hit(
                title=attr(item, "title"),
                url=attr(item, "url", "link"),
                snippet=attr(item, "description", "markdown", "content", "text"),
                score=attr(item, "score", "position", default=0.0),
                source=self.name,
            )
            for item in items
        ]
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
        fmt = request.format if request.format in ("markdown", "html") else "markdown"
        scrape_kwargs: dict[str, Any] = {
            "formats": ["markdown"] if request.format == "text" else [fmt]
        }
        if request.only_main is not None:
            scrape_kwargs["only_main_content"] = bool(request.only_main)

        async def one(url: str):
            try:
                doc = await self._client.scrape(url, **scrape_kwargs)  # type: ignore[union-attr]
                body = text(attr(doc, "markdown", "html", "raw_html", "content", "text"))
                meta = attr(doc, "metadata")
                title = text(attr(meta, "title"), attr(doc, "title"))
                return make_page(url=url, content=body, title=title or None)
            except Exception as e:
                return make_page(url=url, error=str(e))

        pages = list(await asyncio.gather(*[one(u) for u in request.urls]))
        return ExtractResponse(
            results=pages,
            provider=self.name,
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    @staticmethod
    def _items(data: Any) -> list[Any]:
        if data is None:
            return []
        if isinstance(data, list):
            return data
        web = attr(data, "web")
        if web:
            return list(web)
        if isinstance(data, dict):
            for key in ("data", "results", "web"):
                val = data.get(key)
                if isinstance(val, list):
                    return val
        return []
