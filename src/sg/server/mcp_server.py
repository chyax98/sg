"""MCP Server - Expose gateway as MCP server."""

import logging
from typing import Any

from fastmcp import FastMCP

logger = logging.getLogger(__name__)


class MCPServer:
    """MCP Server wrapper for Search Gateway."""

    def __init__(self, gateway):
        self.gateway = gateway
        self.mcp = FastMCP(
            name="search-gateway",
            version="1.0.0",
        )
        self._setup_tools()

    def _setup_tools(self):
        @self.mcp.tool()
        async def search(
            query: str,
            provider: str | None = None,
            max_results: int = 10,
        ) -> str:
            """Search the web.

            Args:
                query: Search query
                provider: Optional provider (tavily, brave, exa, duckduckgo)
                max_results: Maximum results (default 10)

            Returns:
                Search results as formatted text
            """
            result = await self.gateway.search(
                query=query,
                provider=provider,
                max_results=max_results,
            )

            # Format results
            lines = [f"Search: {result.query} (via {result.provider})"]
            lines.append(f"Found {result.total} results in {result.latency_ms:.0f}ms\n")

            for i, r in enumerate(result.results, 1):
                lines.append(f"[{i}] {r.title}")
                lines.append(f"    {r.url}")
                if r.content:
                    lines.append(f"    {r.content[:200]}...")
                lines.append("")

            return "\n".join(lines)

        @self.mcp.tool()
        async def extract(
            urls: list[str],
            format: str = "markdown",
        ) -> str:
            """Extract content from URLs.

            Args:
                urls: List of URLs to extract
                format: Output format (markdown, text)

            Returns:
                Extracted content
            """
            result = await self.gateway.extract(urls=urls, format=format)

            lines = []
            for r in result.results:
                lines.append(f"=== {r.url} ===")
                if r.title:
                    lines.append(f"Title: {r.title}")
                if r.error:
                    lines.append(f"Error: {r.error}")
                else:
                    lines.append(r.content[:2000])
                lines.append("")

            return "\n".join(lines)

        @self.mcp.tool()
        async def research(
            topic: str,
            depth: str = "auto",
        ) -> str:
            """Deep research on a topic.

            Args:
                topic: Research topic/question
                depth: Research depth (mini, pro, auto)

            Returns:
                Research findings
            """
            result = await self.gateway.research(topic=topic, depth=depth)
            return result.content

        @self.mcp.tool()
        async def list_providers() -> str:
            """List available search providers."""
            providers = await self.gateway.list_providers()

            lines = ["Available Search Providers:"]
            for p in providers:
                status = "✓" if p.healthy else "✗"
                fallback = " (fallback)" if p.is_fallback else ""
                lines.append(f"  {status} {p.name}{fallback}")
                lines.append(f"    Capabilities: {', '.join(p.capabilities)}")
                lines.append(f"    Priority: {p.priority}")

            return "\n".join(lines)

    async def start(self):
        """Start MCP server (stdio mode)."""
        # MCP server runs in stdio mode when used as MCP tool
        # HTTP transport is handled separately
        logger.info("MCP server initialized")

    async def stop(self):
        """Stop MCP server."""
        logger.info("MCP server stopped")

    async def run_stdio(self):
        """Run MCP server in stdio mode."""
        await self.mcp.run_stdio_async()

    async def run_http(self, port: int = 8101):
        """Run MCP server in HTTP mode."""
        await self.mcp.run_http_async(host="0.0.0.0", port=port)
