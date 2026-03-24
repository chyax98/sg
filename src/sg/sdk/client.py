"""SDK — Python client for Search Gateway."""

from typing import Any

import httpx

from ..models.search import ExtractResponse, ResearchResponse, SearchResponse


class SearchClient:
    """Synchronous Search Gateway client.

    Usage:
        from sg.sdk import SearchClient

        with SearchClient() as client:
            results = client.search("MCP protocol")
            for r in results.results:
                print(f"- {r.title}: {r.url}")
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8100"):
        self.base_url = base_url
        self._client = httpx.Client(timeout=30.0)

    def search(
        self,
        query: str,
        provider: str | None = None,
        max_results: int = 10,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        time_range: str | None = None,
        search_depth: str = "basic",
        **kwargs,
    ) -> SearchResponse:
        """Execute search."""
        resp = self._client.post(
            f"{self.base_url}/search",
            json={
                "query": query,
                "provider": provider,
                "max_results": max_results,
                "include_domains": include_domains or [],
                "exclude_domains": exclude_domains or [],
                "time_range": time_range,
                "search_depth": search_depth,
                "extra": kwargs,
            },
        )
        resp.raise_for_status()
        return SearchResponse.model_validate(resp.json())

    def extract(
        self,
        urls: list[str],
        provider: str | None = None,
        format: str = "markdown",
        extract_depth: str = "basic",
    ) -> ExtractResponse:
        """Extract content from URLs."""
        resp = self._client.post(
            f"{self.base_url}/extract",
            json={
                "urls": urls,
                "provider": provider,
                "format": format,
                "extract_depth": extract_depth,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        return ExtractResponse.model_validate(resp.json())

    def research(
        self,
        topic: str,
        depth: str = "auto",
        provider: str | None = None,
    ) -> ResearchResponse:
        """Execute deep research."""
        resp = self._client.post(
            f"{self.base_url}/research",
            json={"topic": topic, "depth": depth, "provider": provider},
            timeout=300.0,
        )
        resp.raise_for_status()
        return ResearchResponse.model_validate(resp.json())

    def list_providers(self) -> list[dict[str, Any]]:
        resp = self._client.get(f"{self.base_url}/providers")
        resp.raise_for_status()
        data: list[dict[str, Any]] = resp.json()
        return data

    def get_status(self) -> dict[str, Any]:
        resp = self._client.get(f"{self.base_url}/status")
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data

    def health_check(self) -> dict[str, Any]:
        resp = self._client.post(f"{self.base_url}/health-check")
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class AsyncSearchClient:
    """Async Search Gateway client."""

    def __init__(self, base_url: str = "http://127.0.0.1:8100"):
        self.base_url = base_url
        self._client = httpx.AsyncClient(timeout=30.0)

    async def search(
        self,
        query: str,
        provider: str | None = None,
        max_results: int = 10,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        time_range: str | None = None,
        search_depth: str = "basic",
        **kwargs,
    ) -> SearchResponse:
        """Execute search."""
        resp = await self._client.post(
            f"{self.base_url}/search",
            json={
                "query": query,
                "provider": provider,
                "max_results": max_results,
                "include_domains": include_domains or [],
                "exclude_domains": exclude_domains or [],
                "time_range": time_range,
                "search_depth": search_depth,
                "extra": kwargs,
            },
        )
        resp.raise_for_status()
        return SearchResponse.model_validate(resp.json())

    async def extract(
        self,
        urls: list[str],
        provider: str | None = None,
        format: str = "markdown",
        extract_depth: str = "basic",
    ) -> ExtractResponse:
        """Extract content from URLs."""
        resp = await self._client.post(
            f"{self.base_url}/extract",
            json={
                "urls": urls,
                "provider": provider,
                "format": format,
                "extract_depth": extract_depth,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        return ExtractResponse.model_validate(resp.json())

    async def research(
        self,
        topic: str,
        depth: str = "auto",
        provider: str | None = None,
    ) -> ResearchResponse:
        """Execute deep research."""
        resp = await self._client.post(
            f"{self.base_url}/research",
            json={"topic": topic, "depth": depth, "provider": provider},
            timeout=300.0,
        )
        resp.raise_for_status()
        return ResearchResponse.model_validate(resp.json())

    async def list_providers(self) -> list[dict[str, Any]]:
        resp = await self._client.get(f"{self.base_url}/providers")
        resp.raise_for_status()
        data: list[dict[str, Any]] = resp.json()
        return data

    async def get_status(self) -> dict[str, Any]:
        resp = await self._client.get(f"{self.base_url}/status")
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data

    async def health_check(self) -> dict[str, Any]:
        resp = await self._client.post(f"{self.base_url}/health-check")
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data

    async def close(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
