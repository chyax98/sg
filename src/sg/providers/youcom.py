"""You.com provider - High accuracy AI search."""

import logging
import os
import time

import httpx

from ..models.search import SearchRequest, SearchResponse, SearchResult
from .base import SearchProvider

logger = logging.getLogger(__name__)


class YouComProvider(SearchProvider):
    """You.com Search API - High accuracy web search.

    Industry-leading 93% accuracy on SimpleQA benchmark.
    API docs: https://docs.you.com/api-reference/search/v1-search
    Get key: https://you.com/platform/api-keys
    """

    name = "youcom"
    capabilities = ["search"]
    BASE_URL = "https://ydc-index.io"

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key or os.environ.get("YOUCOM_API_KEY", "")
        self.priority = kwargs.get("priority", 5)  # High priority due to accuracy

    async def initialize(self) -> bool:
        if not self.api_key:
            logger.warning("You.com: No API key provided")
            return False
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=self.timeout / 1000,
            headers={
                "X-API-Key": self.api_key,
                "Accept": "application/json",
            },
        )
        return True

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> tuple[bool, str | None]:
        if not self.api_key:
            return False, "No API key"
        try:
            resp = await self._client.get("/v1/search", params={"query": "test", "count": 1})
            if resp.status_code == 200:
                return True, None
            elif resp.status_code == 403:
                return False, "API key invalid or rate limited"
            return False, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)

    async def search(self, request: SearchRequest) -> SearchResponse:
        """Execute search via You.com API."""
        start = time.perf_counter()

        params = {
            "query": request.query,
            "count": request.max_results,
        }

        # Add language filter if specified
        if request.extra.get("language"):
            params["language"] = request.extra["language"]

        resp = await self._client.get("/v1/search", params=params)
        resp.raise_for_status()
        data = resp.json()

        results = []
        # You.com returns results in results.web array
        web_results = data.get("results", {}).get("web", [])
        for item in web_results:
            # Combine description and snippets for content
            content = item.get("description", "")
            snippets = item.get("snippets", [])
            if snippets:
                snippet_text = "\n".join(snippets[:2])
                content = f"{content}\n{snippet_text}" if content else snippet_text

            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                content=content.strip(),
                snippet=item.get("description", "")[:300] if item.get("description") else "",
                score=0.0,
                source=self.name,
                published_date=item.get("page_age"),
            ))

        latency = (time.perf_counter() - start) * 1000
        return SearchResponse(
            query=request.query,
            provider=self.name,
            results=results,
            total=len(results),
            latency_ms=latency,
        )
