"""MCP Server — expose gateway as MCP tools for LLMs."""

import logging

from fastmcp import FastMCP

logger = logging.getLogger(__name__)


class MCPServer:
    """MCP Server for Search Gateway.

    Run with `sg mcp` to start in stdio mode for Claude Desktop integration.
    """

    def __init__(self, gateway):
        self.gateway = gateway
        self.mcp = FastMCP(name="search-gateway")
        self._setup_tools()

    def _setup_tools(self):
        @self.mcp.tool()
        async def search(
            query: str,
            provider: str | None = None,
            max_results: int = 10,
            include_domains: list[str] | None = None,
            exclude_domains: list[str] | None = None,
            time_range: str | None = None,
            search_depth: str = "basic",
        ) -> str:
            """Search the web using multiple search engines with automatic failover.

            Args:
                query: Search query
                provider: Optional provider name (tavily, brave, exa, etc.)
                max_results: Maximum results (default 10)
                include_domains: Restrict results to these domains when supported
                exclude_domains: Exclude these domains when supported
                time_range: day, week, month, year when supported
                search_depth: basic or advanced when supported
            """
            result = await self.gateway.search(
                query=query,
                provider=provider,
                max_results=max_results,
                include_domains=include_domains or [],
                exclude_domains=exclude_domains or [],
                time_range=time_range,
                search_depth=search_depth,
            )

            lines = [f"Search: {result.query} (via {result.provider}, {result.latency_ms:.0f}ms)"]
            lines.append(f"{result.total} results\n")

            for i, r in enumerate(result.results, 1):
                lines.append(f"[{i}] {r.title}")
                lines.append(f"    {r.url}")
                if r.content:
                    lines.append(f"    {r.content[:300]}")
                lines.append("")

            return "\n".join(lines)

        @self.mcp.tool()
        async def extract(
            urls: list[str],
            format: str = "markdown",
        ) -> str:
            """Extract content from web pages as clean markdown.

            Args:
                urls: URLs to extract content from
                format: Output format (markdown or text)
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
                    lines.append(r.content[:5000])
                lines.append("")

            return "\n".join(lines)

        @self.mcp.tool()
        async def research(
            topic: str,
            depth: str = "auto",
        ) -> str:
            """Deep research on a topic with multiple sources.

            Args:
                topic: Research topic or question
                depth: Research depth (mini, pro, auto)
            """
            result = await self.gateway.research(topic=topic, depth=depth)
            return result.content

        @self.mcp.tool()
        async def list_providers() -> str:
            """List available search providers and their status."""
            providers = await self.gateway.list_providers()

            lines = ["Search Gateway Providers:"]
            for p in providers:
                status = "OK" if p.healthy else "DOWN"
                fallback = " (fallback)" if p.is_fallback else ""
                lines.append(f"  [{status}] {p.name} ({p.type}){fallback}")
                lines.append(f"      Capabilities: {', '.join(p.capabilities)}")
                lines.append(f"      Priority: {p.priority}")

            return "\n".join(lines)

    async def run_stdio(self):
        """Run MCP server in stdio mode (for Claude Desktop)."""
        await self.mcp.run_stdio_async()

    async def run_http(self, host: str = "0.0.0.0", port: int = 8101):
        """Run MCP server in HTTP/SSE mode."""
        await self.mcp.run_sse_async(host=host, port=port)
