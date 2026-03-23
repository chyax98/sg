"""MCP Server — expose gateway as MCP tools for LLMs."""

import logging
from pathlib import Path

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
                A string containing:
                - Query, provider used, and result count
                - File path where full results are saved
                - File metadata: size (KB), line count, word count

                Example output:
                query="Python async" provider=exa results=10
                file=/Users/xxx/.sg/history/2026-03/20260323-103045-abc123.json (12.4KB, 287 lines, 1823 words)

            Next steps after receiving results:
            - For small files (<5KB): Read the entire file with the Read tool
            - For medium files (5-50KB): Use jq to extract specific fields like titles and URLs
            - For large files (>50KB): Use jq with array slicing to read first few results

            Example follow-up commands:
            - Read full results: Read the file path returned
            - Extract titles/URLs: Use Bash with jq '.results[] | {title, url}' <file>
            - Get first 5 results: Use Bash with jq '.results[0:5]' <file>
            """
            result = await self.gateway.search(
                query=query,
                provider=provider,
                max_results=max_results,
                include_domains=include_domains or [],
                exclude_domains=exclude_domains or [],
                time_range=time_range,
                search_depth=search_depth,
                extra=extra or {},
            )

            path = Path(result.result_file)
            text = path.read_text(encoding="utf-8")
            size_kb = path.stat().st_size / 1024
            lines = text.count("\n")
            words = len(text.split())

            return (
                f'query="{result.query}" provider={result.provider} results={result.total}\n'
                f"file={result.result_file} ({size_kb:.1f}KB, {lines} lines, {words} words)"
            )

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

            Note: Content is returned directly (not saved to file like search results).
            For very long pages, content may be truncated to first 5000 characters per URL.
            """
            result = await self.gateway.extract(urls=urls, format=format, extra=extra or {})

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

            Note: Research content is returned directly (not saved to file).
            This operation may take longer than simple search (10-30 seconds depending on depth).
            """
            result = await self.gateway.research(topic=topic, depth=depth)
            content: str = result.content
            return content

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
            providers = await self.gateway.list_providers()

            lines = ["Search Gateway Providers:"]
            for p in providers:
                status = "OK" if p.healthy else "DOWN"
                fallback = f" (fallback: {','.join(p.fallback_for)})" if p.fallback_for else ""
                lines.append(f"  [{status}] {p.name} ({p.type}){fallback}")
                lines.append(f"      Capabilities: {', '.join(p.capabilities)}")
                lines.append(f"      Priority: {p.priority}")

            return "\n".join(lines)

    async def run_stdio(self):
        """Run MCP server in stdio mode (for Claude Desktop)."""
        await self.mcp.run_stdio_async()

    async def run_http(self, host: str = "0.0.0.0", port: int = 8101):
        """Run MCP server in HTTP/SSE mode."""
        await self.mcp.run_sse_async(host=host, port=port)  # type: ignore[attr-defined]
