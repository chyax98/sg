"""You.com provider — raw httpx (SDK is beta/auto-generated)."""

import re
import time
from html.parser import HTMLParser

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


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        elif tag in ("p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"):
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        elif tag in ("p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"):
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip and data:
            self._parts.append(data)

    def text(self) -> str:
        raw = "".join(self._parts)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def _html_to_text(html: str) -> str:
    parser = _HTMLTextExtractor()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:
        return re.sub(r"<[^>]+>", " ", html or "").strip()
    return parser.text()


class YouComProvider(SearchProvider, ExtractProvider):
    """You.com: high accuracy AI search (93% SimpleQA).

    API: https://docs.you.com
    Supports: Search, Contents (extract)
    """

    info = ProviderInfo(
        type="youcom",
        display_name="You.com",
        capabilities=("search", "extract"),
        search_features=("domains", "exclude_domains", "time_range", "language"),
    )

    BASE_URL = "https://ydc-index.io"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._client: httpx.AsyncClient | None = None

    async def initialize(self) -> bool:
        api_key = self.api_key or self.env_value("YOUCOM_API_KEY")
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
            request.domains,
            request.exclude_domains,
        )
        params: dict[str, str | int] = {"query": query, "count": request.limit}
        if request.time_range:
            freshness_map = {
                "day": "day",
                "week": "week",
                "month": "month",
                "year": "year",
            }
            if request.time_range in freshness_map:
                params["freshness"] = freshness_map[request.time_range]
        if request.language:
            params["language"] = request.language

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
                    snippet=content.strip(),
                    source=self.name,
                    published_at=item.get("page_age"),
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
        items = (
            data
            if isinstance(data, list)
            else data.get("results", []) or data.get("data", []) or []
        )
        for item in items:
            if not isinstance(item, dict):
                continue
            url = item.get("url", "")
            err = item.get("error") or item.get("message")
            if err and not (item.get("html") or item.get("text") or item.get("markdown")):
                results.append(ExtractResult(url=url, content="", error=str(err)))
                continue

            if request.format == "html":
                content = item.get("html") or item.get("text") or ""
            else:
                content = (
                    item.get("markdown")
                    or item.get("text")
                    or _html_to_text(item.get("html") or "")
                )
            if not str(content).strip():
                results.append(ExtractResult(url=url, content="", error="empty extract"))
                continue
            results.append(
                ExtractResult(
                    url=url,
                    content=content,
                    title=item.get("title"),
                )
            )

        latency = (time.perf_counter() - start) * 1000
        return ExtractResponse(results=results, provider=self.name, latency_ms=latency)
