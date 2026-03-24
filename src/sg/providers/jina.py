"""Jina Reader provider — raw httpx (no SDK, URL-prefix API)."""

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


class JinaReaderProvider(SearchProvider, ExtractProvider):
    """Jina Reader: free URL extraction, paid search.

    Extract (r.jina.ai) is free. Search (s.jina.ai) requires API key.
    """

    info = ProviderInfo(
        type="jina",
        display_name="Jina Reader",
        needs_api_key=False,
        free=True,
        capabilities=("extract",),
        search_features=(),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._extract_client: httpx.AsyncClient | None = None
        self._search_client: httpx.AsyncClient | None = None
        self._capabilities = ["extract"]

    async def initialize(self) -> bool:
        self._extract_client = httpx.AsyncClient(
            timeout=self.timeout / 1000,
            follow_redirects=True,
        )
        if self.api_key:
            self._search_client = httpx.AsyncClient(
                base_url="https://s.jina.ai",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout / 1000,
            )
            self._capabilities = ["search", "extract"]
        return True

    async def shutdown(self) -> None:
        if self._extract_client:
            await self._extract_client.aclose()
            self._extract_client = None
        if self._search_client:
            await self._search_client.aclose()
            self._search_client = None

    async def health_check(self) -> tuple[bool, str | None]:
        if not self._extract_client:
            return (False, "Not initialized")
        return (True, None)

    @property
    def capabilities(self) -> list[str]:
        return self._capabilities

    async def search(self, request: SearchRequest) -> SearchResponse:
        if not self._search_client:
            raise RuntimeError("Jina search requires API key")
        self.validate_search_request(request)

        start = time.perf_counter()

        resp = await self._search_client.get(
            f"/{request.query}",
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("data", []):
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    content=item.get("content", ""),
                    source=self.name,
                )
            )
            if len(results) >= request.max_results:
                break

        latency = (time.perf_counter() - start) * 1000
        return SearchResponse(
            query=request.query,
            provider=self.name,
            results=results,
            total=len(results),
            latency_ms=latency,
        )

    async def extract(self, request: ExtractRequest) -> ExtractResponse:
        if not self._extract_client:
            raise RuntimeError("Not initialized")

        start = time.perf_counter()
        results = []

        for url in request.urls:
            try:
                resp = await self._extract_client.get(
                    f"https://r.jina.ai/{url}",
                    headers={"Accept": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()

                results.append(
                    ExtractResult(
                        url=url,
                        content=data.get("data", {}).get("content", resp.text),
                        title=data.get("data", {}).get("title"),
                    )
                )
            except Exception as e:
                results.append(ExtractResult(url=url, content="", error=str(e)))

        latency = (time.perf_counter() - start) * 1000
        return ExtractResponse(results=results, provider=self.name, latency_ms=latency)
