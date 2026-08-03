"""Tavily adapter — official tavily-python SDK."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from ..models.search import (
    ExtractRequest,
    ExtractResponse,
    ResearchRequest,
    ResearchResponse,
    SearchRequest,
    SearchResponse,
)
from ._assemble import attr, make_hit, make_page, optional_list, text, urls_from_sources
from .base import (
    ExtractProvider,
    ProviderInfo,
    ResearchProvider,
    SearchProvider,
    cap,
    extract_cap,
    research_cap,
    search_cap,
)

_DONE = frozenset({"completed", "complete", "success", "done", "finished"})
_FAILED = frozenset({"failed", "error", "cancelled", "canceled"})


class TavilyProvider(SearchProvider, ExtractProvider, ResearchProvider):
    info = ProviderInfo(
        type="tavily",
        display_name="Tavily",
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
            research=research_cap(depths=("auto", "mini", "pro")),
        ),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._client = None

    async def initialize(self) -> bool:
        api_key = self.api_key or self.env_value("TAVILY_API_KEY")
        if not api_key:
            return False
        from tavily import AsyncTavilyClient

        self._client = AsyncTavilyClient(api_key=api_key)
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
            "max_results": request.limit,
            "search_depth": request.depth,
            "timeout": max(5.0, self.timeout / 1000),
        }
        if include := optional_list(request.domains):
            kwargs["include_domains"] = include
        if exclude := optional_list(request.exclude_domains):
            kwargs["exclude_domains"] = exclude
        if request.time_range:
            kwargs["time_range"] = request.time_range
        if request.location:
            kwargs["country"] = request.location
        if request.want_raw:
            kwargs["include_raw_content"] = "markdown"

        data = await self._client.search(**kwargs)
        latency = (time.perf_counter() - start) * 1000
        hits = [
            make_hit(
                title=r.get("title"),
                url=r.get("url"),
                snippet=r.get("content"),
                score=r.get("score", 0.0),
                source=self.name,
                published_at=r.get("published_date"),
                raw=r.get("raw_content") if request.want_raw else None,
            )
            for r in (data.get("results") or [])
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
        fmt = request.format if request.format in ("markdown", "text") else "markdown"
        data = await self._client.extract(
            urls=request.urls,
            format=fmt,
            timeout=max(5.0, self.timeout / 1000),
        )
        latency = (time.perf_counter() - start) * 1000

        pages = [
            make_page(
                url=r.get("url"),
                content=r.get("raw_content") or r.get("content"),
                title=r.get("title"),
            )
            for r in (data.get("results") or [])
        ]
        for r in data.get("failed_results") or data.get("errors") or []:
            if isinstance(r, dict):
                pages.append(make_page(url=r.get("url"), error=r.get("error") or "extract_failed"))
            else:
                pages.append(make_page(url="", error=str(r)))

        return ExtractResponse(results=pages, provider=self.name, latency_ms=latency)

    async def research(self, request: ResearchRequest) -> ResearchResponse:
        if not self._client:
            raise RuntimeError("Not initialized")

        start = time.perf_counter()
        model = request.depth if request.depth in ("mini", "pro", "auto") else "auto"
        timeout_s = max(120.0, self.timeout / 1000)
        data = await self._client.research(input=request.topic, model=model, timeout=timeout_s)
        data = await self._resolve_research(data, timeout_s=timeout_s)
        latency = (time.perf_counter() - start) * 1000

        report = text(attr(data, "content", "output", "report", "answer"))
        if not report:
            raise RuntimeError("Tavily research returned empty report")
        sources = urls_from_sources(attr(data, "sources", "results", default=[]))
        return ResearchResponse(
            topic=request.topic,
            report=report,
            sources=sources,
            provider=self.name,
            latency_ms=latency,
        )

    async def _resolve_research(self, data: Any, *, timeout_s: float) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise RuntimeError(f"Unexpected Tavily research response type: {type(data)!r}")
        if text(attr(data, "content", "output", "report", "answer")):
            return data
        status = text(attr(data, "status")).lower()
        if status in _FAILED:
            raise RuntimeError(
                f"Tavily research failed: {attr(data, 'error', 'message') or status}"
            )
        request_id = text(attr(data, "request_id", "id"))
        if not request_id:
            return data

        deadline = time.perf_counter() + timeout_s
        last = data
        while time.perf_counter() < deadline:
            await asyncio.sleep(2.0)
            last = await self._client.get_research(request_id)  # type: ignore[union-attr]
            if not isinstance(last, dict):
                continue
            st = text(attr(last, "status")).lower()
            if text(attr(last, "content", "output", "report", "answer")) or st in _DONE:
                return last
            if st in _FAILED:
                raise RuntimeError(
                    f"Tavily research failed: {attr(last, 'error', 'message') or st}"
                )
        raise TimeoutError(f"Tavily research timed out after {timeout_s:.0f}s (id={request_id})")
