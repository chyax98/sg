"""SDK - Python client for search gateway."""

import httpx
from typing import Any

from ..models.search import SearchResponse


class SearchClient:
    """Search Gateway SDK client.

    Usage:
        from sg.sdk import SearchClient

        client = SearchClient()
        results = client.search("MCP protocol 2025")
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
        **kwargs,
    ) -> SearchResponse:
        """Execute search.

        Args:
            query: Search query
            provider: Optional provider name (tavily, brave, exa, duckduckgo)
            max_results: Maximum results to return
            include_domains: Only include these domains
            exclude_domains: Exclude these domains
            time_range: Time filter (day, week, month, year)
            **kwargs: Additional parameters

        Returns:
            SearchResponse with results
        """
        resp = self._client.post(
            f"{self.base_url}/search",
            json={
                "query": query,
                "provider": provider,
                "max_results": max_results,
                "include_domains": include_domains or [],
                "exclude_domains": exclude_domains or [],
                "time_range": time_range,
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
    ) -> dict[str, Any]:
        """Extract content from URLs.

        Args:
            urls: List of URLs to extract
            provider: Optional provider (default: tavily)
            format: Output format (markdown, text)
            extract_depth: Extraction depth (basic, advanced)

        Returns:
            Extracted content
        """
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
        return resp.json()

    def research(
        self,
        topic: str,
        depth: str = "auto",
        provider: str | None = None,
    ) -> dict[str, Any]:
        """Execute deep research.

        Args:
            topic: Research topic
            depth: Research depth (mini, pro, auto)
            provider: Optional provider (default: tavily)

        Returns:
            Research results
        """
        resp = self._client.post(
            f"{self.base_url}/research",
            json={
                "topic": topic,
                "depth": depth,
                "provider": provider,
            },
            timeout=300.0,
        )
        resp.raise_for_status()
        return resp.json()

    def list_providers(self) -> list[dict[str, Any]]:
        """List all providers."""
        resp = self._client.get(f"{self.base_url}/providers")
        resp.raise_for_status()
        return resp.json()

    def get_status(self) -> dict[str, Any]:
        """Get gateway status."""
        resp = self._client.get(f"{self.base_url}/status")
        resp.raise_for_status()
        return resp.json()

    def health_check(self) -> dict[str, Any]:
        """Run health check."""
        resp = self._client.post(f"{self.base_url}/health-check")
        resp.raise_for_status()
        return resp.json()

    def close(self):
        """Close client connection."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class AsyncSearchClient:
    """Async Search Gateway SDK client."""

    def __init__(self, base_url: str = "http://127.0.0.1:8100"):
        self.base_url = base_url
        self._client = httpx.AsyncClient(timeout=30.0)

    async def search(
        self,
        query: str,
        provider: str | None = None,
        max_results: int = 10,
        **kwargs,
    ) -> SearchResponse:
        """Execute search."""
        resp = await self._client.post(
            f"{self.base_url}/search",
            json={
                "query": query,
                "provider": provider,
                "max_results": max_results,
                "extra": kwargs,
            },
        )
        resp.raise_for_status()
        return SearchResponse.model_validate(resp.json())

    async def extract(
        self,
        urls: list[str],
        provider: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Extract content from URLs."""
        resp = await self._client.post(
            f"{self.base_url}/extract",
            json={"urls": urls, "provider": provider, **kwargs},
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.json()

    async def research(
        self,
        topic: str,
        depth: str = "auto",
        provider: str | None = None,
    ) -> dict[str, Any]:
        """Execute deep research."""
        resp = await self._client.post(
            f"{self.base_url}/research",
            json={"topic": topic, "depth": depth, "provider": provider},
            timeout=300.0,
        )
        resp.raise_for_status()
        return resp.json()

    async def list_providers(self) -> list[dict[str, Any]]:
        """List all providers."""
        resp = await self._client.get(f"{self.base_url}/providers")
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        """Close client connection."""
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
