"""MCP Server — expose gateway as MCP tools for LLMs."""

import logging
from typing import Any

import httpx

from .._utils import ensure_gateway_running

logger = logging.getLogger(__name__)


def _format_toon_preview(result: dict, max_preview: int = 5) -> str:
    """Format search result as TOON for LLM tool response."""
    query = result.get("query", "")
    result_file = result.get("result_file", "")
    results = result.get("results", [])
    total = result.get("total", len(results))

    lines = [
        f"q: {query}",
        f"file: {result_file}",
        "",
        f"results[{min(total, max_preview)}]{{title,url,score}}:",
    ]

    for i, r in enumerate(results[:max_preview], 1):
        score = r.get("score")
        score_str = f"{score:.2f}" if score else "-"
        title = (
            r.get("title", "")[:50] + "..." if len(r.get("title", "")) > 50 else r.get("title", "")
        )
        url = r.get("url", "")
        lines.append(f"  {i},{title},{url},{score_str}")

    if total > max_preview:
        lines.append(f"  ... ({total - max_preview} more)")

    lines.append("")
    lines.append("To read specific results, read file lines:")
    lines.append("  Line 1 = result [1], Line 2 = result [2], etc.")

    return "\n".join(lines)


class MCPServer:
    """MCP Server for Search Gateway.

    Run with `sg mcp` to start in stdio mode for Claude Desktop integration.

    This server connects to a running gateway daemon (starts one if needed)
    and exposes MCP tools for LLM integration.
    """

    def __init__(self, port: int = 8100, config: str | None = None):
        self.port = port
        self.config = config
        self.base_url = f"http://127.0.0.1:{port}"

        # Ensure daemon is running before setting up tools
        ensure_gateway_running(port, config)

        # Import FastMCP lazily to avoid import overhead
        from fastmcp import FastMCP

        self.mcp = FastMCP(name="search-gateway")
        self._setup_tools()

    async def _call_gateway(self, endpoint: str, data: dict | None = None) -> dict[str, Any]:
        """Make HTTP call to gateway daemon, ensuring it's running."""
        ensure_gateway_running(self.port, self.config)

        async with httpx.AsyncClient(timeout=300.0) as client:
            if data:
                resp = await client.post(f"{self.base_url}{endpoint}", json=data)
            else:
                resp = await client.get(f"{self.base_url}{endpoint}")
            resp.raise_for_status()
            return resp.json()

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
            extra: dict | None = None,
        ) -> str:
            """Search the web using multiple search engines with automatic failover.

            This tool performs web searches across multiple providers (Tavily, Exa, Brave, You.com,
            SearXNG, DuckDuckGo) with automatic failover if one provider fails. Results are saved
            to a file and the file path is returned with metadata.

            Use this when you need to:
            - Find current information on the web
            - Research topics with recent data
            - Gather multiple sources on a subject
            - Search with specific domain filters or time ranges

            Args:
                query: Search query string (e.g., "Python async programming 2026")
                provider: Optional provider name to prefer (tavily, brave, exa, youcom, searxng, duckduckgo, xcrawl)
                         If not specified, uses automatic provider selection with failover
                max_results: Maximum number of results to return (default 10, max varies by provider)
                include_domains: List of domains to restrict results to (e.g., ["python.org", "github.com"])
                                Only supported by some providers (Tavily, Exa)
                exclude_domains: List of domains to exclude from results
                                Only supported by some providers (Tavily, Exa)
                time_range: Filter by time period - "day", "week", "month", or "year"
                           Only supported by some providers
                search_depth: Search thoroughness - "basic" (faster) or "advanced" (more comprehensive)
                             Only supported by some providers (Tavily)
                extra: Extra parameters for specific providers (e.g., {"location": "CN", "language": "zh"})
                       Supported params vary by provider - unsupported params are ignored

            Returns:
                TOON format string containing:
                - Query and view file path
                - Preview of top results with title, URL, score

                Example output:
                q: Python async
                file: /Users/xxx/.sg/history/view/2026-03/1742752563408-e1.txt

                results[5]{title,url,score}:
                  1,Python Asyncio Docs,https://docs.python.org/3/library/asyncio.html,0.95
                  2,...

            Next steps:
            - Read the view file for full results
            - Each result has [N] marker for easy navigation
            """
            result = await self._call_gateway(
                "/search",
                {
                    "query": query,
                    "provider": provider,
                    "max_results": max_results,
                    "include_domains": include_domains or [],
                    "exclude_domains": exclude_domains or [],
                    "time_range": time_range,
                    "search_depth": search_depth,
                    "extra": extra or {},
                },
            )

            return _format_toon_preview(result)

        @self.mcp.tool()
        async def extract(
            urls: list[str],
            format: str = "markdown",
            extra: dict | None = None,
        ) -> str:
            """Extract clean, readable content from web pages.

            This tool fetches web pages and extracts the main content, removing ads, navigation,
            and other clutter. Supports multiple providers (Firecrawl, Jina, Tavily, Exa) with
            automatic failover.

            Use this when you need to:
            - Read article content from a URL
            - Extract documentation from web pages
            - Get clean text from blog posts or news articles
            - Process multiple URLs in batch

            Args:
                urls: List of URLs to extract content from (e.g., ["https://example.com/article"])
                     Can process multiple URLs in a single call
                format: Output format - "markdown" (default, preserves structure) or "text" (plain text)
                extra: Extra parameters for specific providers (e.g., {"device": "mobile", "js_render": false})
                       Supported params vary by provider - unsupported params are ignored

            Returns:
                Extracted content for each URL, formatted as:
                === <URL> ===
                Title: <page title>
                <content in markdown or text format>

                If extraction fails for a URL, an error message is included instead.

            Note: Content is returned directly (also saved to file for record keeping).
            For very long pages, content may be truncated to first 5000 characters per URL.
            """
            result = await self._call_gateway(
                "/extract",
                {
                    "urls": urls,
                    "format": format,
                    "extra": extra or {},
                },
            )

            # Format content for display
            lines = []
            for r in result.get("results", []):
                lines.append(f"=== {r.get('url', '')} ===")
                if r.get("title"):
                    lines.append(f"Title: {r['title']}")
                if r.get("error"):
                    lines.append(f"Error: {r['error']}")
                else:
                    lines.append(r.get("content", "")[:5000])
                lines.append("")
            return "\n".join(lines)

        @self.mcp.tool()
        async def research(
            topic: str,
            depth: str = "auto",
        ) -> str:
            """Conduct deep research on a topic using multiple sources and synthesis.

            This tool performs comprehensive research by searching multiple sources, extracting
            relevant content, and synthesizing information. Currently powered by Tavily's research
            API with automatic fallback to other providers.

            Use this when you need to:
            - Gather comprehensive information on a complex topic
            - Synthesize information from multiple authoritative sources
            - Get a well-rounded view with citations
            - Research current events or recent developments

            Args:
                topic: Research topic or question (e.g., "Impact of AI on software development in 2026")
                depth: Research thoroughness level:
                      - "mini": Quick research, fewer sources, faster (good for simple questions)
                      - "pro": Deep research, more sources, comprehensive (good for complex topics)
                      - "auto": Automatically choose based on query complexity (default)

            Returns:
                Research report containing:
                - Synthesized findings from multiple sources
                - Citations and source URLs
                - Key insights and conclusions

            Note: Research content is returned directly (also saved to file for record keeping).
            This operation may take longer than simple search (10-30 seconds depending on depth).
            """
            result = await self._call_gateway(
                "/research",
                {
                    "topic": topic,
                    "depth": depth,
                },
            )

            return result.get("content", "")

        @self.mcp.tool()
        async def list_providers() -> str:
            """List all available search providers and their current operational status.

            This tool shows which search providers are configured, their capabilities,
            and whether they are currently healthy or experiencing issues.

            Use this when you need to:
            - Check which providers are available for searching
            - Verify provider health before making a search request
            - Understand provider capabilities (search, extract, research)
            - Troubleshoot search failures

            Returns:
                A formatted list of providers showing:
                - Status: OK (healthy) or DOWN (circuit breaker open)
                - Provider name and type
                - Capabilities: which operations the provider supports
                - Priority: lower numbers are tried first
                - Fallback status: whether this provider is used as last resort

            Example output:
                Search Gateway Providers:
                  [OK] exa (exa)
                      Capabilities: search, extract
                      Priority: 1
                  [DOWN] tavily (tavily) (fallback: search)
                      Capabilities: search, extract, research
                      Priority: 2
            """
            providers = await self._call_gateway("/providers")

            lines = ["Search Gateway Providers:"]
            for p in providers:
                status = "OK" if p.get("healthy", True) else "DOWN"
                fallback_for = p.get("fallback_for", [])
                fallback = f" (fallback: {','.join(fallback_for)})" if fallback_for else ""
                lines.append(f"  [{status}] {p.get('name', '')} ({p.get('type', '')}){fallback}")
                lines.append(f"      Capabilities: {', '.join(p.get('capabilities', []))}")
                lines.append(f"      Priority: {p.get('priority', '')}")

            return "\n".join(lines)

    async def run_stdio(self):
        """Run MCP server in stdio mode (for Claude Desktop)."""
        await self.mcp.run_stdio_async()
