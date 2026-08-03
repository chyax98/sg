"""TinyFish provider — raw httpx integration for Search and Fetch APIs."""

import json
import time
from typing import Any

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


class TinyFishProvider(SearchProvider, ExtractProvider):
    """TinyFish: search + fetch content extraction.

    API docs: https://docs.tinyfish.ai
    Search API: GET https://api.search.tinyfish.ai
    Fetch API: POST https://api.fetch.tinyfish.ai
    """

    info = ProviderInfo(
        type="tinyfish",
        display_name="TinyFish",
        capabilities=("search", "extract"),
        search_features=("domains", "exclude_domains", "language", "location"),
    )

    DEFAULT_SEARCH_URL = "https://api.search.tinyfish.ai"
    DEFAULT_FETCH_URL = "https://api.fetch.tinyfish.ai"
    FETCH_BATCH_SIZE = 10

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._search_client: httpx.AsyncClient | None = None
        self._fetch_client: httpx.AsyncClient | None = None

    async def initialize(self) -> bool:
        api_key = self.api_key or self.env_value("TINYFISH_API_KEY")
        if not api_key:
            return False

        self.api_key = api_key
        headers = {"X-API-Key": api_key, "Accept": "application/json"}
        timeout = self.timeout / 1000
        self._search_client = httpx.AsyncClient(
            base_url=self.url or self.env_value("TINYFISH_SEARCH_URL") or self.DEFAULT_SEARCH_URL,
            headers=headers,
            timeout=timeout,
        )
        self._fetch_client = httpx.AsyncClient(
            base_url=self.env_value("TINYFISH_FETCH_URL") or self.DEFAULT_FETCH_URL,
            headers={**headers, "Content-Type": "application/json"},
            timeout=timeout,
        )
        return True

    async def shutdown(self) -> None:
        if self._search_client:
            await self._search_client.aclose()
            self._search_client = None
        if self._fetch_client:
            await self._fetch_client.aclose()
            self._fetch_client = None

    async def health_check(self) -> tuple[bool, str | None]:
        if not self._search_client or not self._fetch_client:
            return (False, "Not initialized")
        return (True, None)

    async def search(self, request: SearchRequest) -> SearchResponse:
        if not self._search_client:
            raise RuntimeError("Not initialized")
        self.validate_search_request(request)

        start = time.perf_counter()
        query = self.apply_domain_operators(
            request.query,
            request.domains,
            request.exclude_domains,
        )
        params: dict[str, str] = {"query": query}
        language = request.language
        location = request.location
        if isinstance(language, str) and language:
            params["language"] = language
        if isinstance(location, str) and location:
            params["location"] = location

        resp = await self._search_client.get("/", params=params)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("results", [])[: request.limit]:
            results.append(
                SearchResult(
                    title=item.get("title") or "",
                    url=item.get("url") or "",
                    snippet=item.get("snippet") or "",
                    source=self.name,
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
        if not self._fetch_client:
            raise RuntimeError("Not initialized")

        start = time.perf_counter()
        results: list[ExtractResult] = []

        for idx in range(0, len(request.urls), self.FETCH_BATCH_SIZE):
            batch = request.urls[idx : idx + self.FETCH_BATCH_SIZE]
            resp = await self._fetch_client.post(
                "/",
                json={
                    "urls": batch,
                    "format": self._normalize_fetch_format(request.format),
                    "links": False,
                    "image_links": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            results.extend(self._parse_fetch_results(data))

        latency = (time.perf_counter() - start) * 1000
        return ExtractResponse(results=results, provider=self.name, latency_ms=latency)

    @staticmethod
    def _normalize_fetch_format(fmt: str) -> str:
        return fmt if fmt in {"html", "markdown", "json"} else "markdown"

    @staticmethod
    def _text_to_string(value: Any) -> str:
        if isinstance(value, str):
            return value
        if value is None:
            return ""
        return json.dumps(value, ensure_ascii=False)

    @classmethod
    def _parse_fetch_results(cls, data: dict[str, Any]) -> list[ExtractResult]:
        results: list[ExtractResult] = []
        for item in data.get("results", []):
            results.append(
                ExtractResult(
                    url=item.get("url") or item.get("final_url") or "",
                    content=cls._text_to_string(item.get("text")),
                    title=item.get("title"),
                )
            )

        for item in data.get("errors", []):
            results.append(
                ExtractResult(
                    url=item.get("url") or "",
                    content="",
                    error=item.get("error") or "fetch_error",
                )
            )
        return results
