"""MCP Server — expose gateway as MCP tools for LLMs."""

import asyncio
import logging
import sys
from typing import Any

import httpx

from .._agent_output import (
    MCP_SERVER_INSTRUCTIONS,
    format_extract_output,
    format_research_output,
    format_search_output,
)
from .._utils import ensure_gateway_running

logger = logging.getLogger(__name__)


async def _exit_when_stdin_closed() -> None:
    """Exit when the MCP host closes stdio (e.g. OpenCode client.close or parent exit)."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, sys.stdin.buffer.read)
    logger.info("MCP stdio client disconnected (stdin EOF)")


class MCPServer:
    """MCP Server for Search Gateway.

    Run with `search-gateway mcp` to start in stdio mode.
    Connects to a running gateway daemon (starts one if needed).
    """

    def __init__(self, port: int = 8100, config: str | None = None, *, require_daemon: bool = True):
        self.port = port
        self.config = config
        self.base_url = f"http://127.0.0.1:{port}"

        if require_daemon:
            ensure_gateway_running(port, config)

        from fastmcp import FastMCP

        self.mcp = FastMCP(name="search-gateway", instructions=MCP_SERVER_INSTRUCTIONS)
        self._setup_tools()

    @property
    def http_client(self) -> httpx.AsyncClient:
        if not hasattr(self, "_http_client"):
            self._http_client = httpx.AsyncClient(timeout=300.0)
        return self._http_client

    async def _call_gateway(self, endpoint: str, data: dict | None = None) -> dict[str, Any]:
        if data:
            resp = await self.http_client.post(f"{self.base_url}{endpoint}", json=data)
        else:
            resp = await self.http_client.get(f"{self.base_url}{endpoint}")
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    def _setup_tools(self):
        @self.mcp.tool()
        async def search(
            query: str,
            limit: int = 10,
            domains: list[str] | None = None,
            exclude_domains: list[str] | None = None,
            time_range: str | None = None,
            depth: str = "basic",
        ) -> str:
            """Search the public web; returns title, URL, and snippet per hit.

            Use for current events, changelogs, issues, and discovering pages on the open internet.
            Snippets only — not full page bodies. Be specific in the query; optional domains/time_range help.
            """
            result = await self._call_gateway(
                "/search",
                {
                    "query": query,
                    "limit": limit,
                    "domains": domains or [],
                    "exclude_domains": exclude_domains or [],
                    "time_range": time_range,
                    "depth": depth,
                },
            )
            return format_search_output(result)

        @self.mcp.tool()
        async def extract(
            urls: list[str],
            format: str = "markdown",
        ) -> str:
            """Fetch URLs and extract main readable page text (markdown or plain).

            Use when you already have concrete page URLs and need the article/docs body.
            Weak on login walls and heavy SPAs. Prefer a small batch of URLs per call.
            """
            result = await self._call_gateway(
                "/extract",
                {
                    "urls": urls,
                    "format": format,
                },
            )
            return format_extract_output(result)

        @self.mcp.tool()
        async def research(
            topic: str,
            depth: str = "auto",
        ) -> str:
            """Multi-source web research; returns one synthesized brief (often 10–30s+).

            Use for broad/comparative questions that need a writeup, not a raw hit list.
            depth: auto (default), mini (faster), or pro (deeper).
            """
            result = await self._call_gateway(
                "/research",
                {
                    "topic": topic,
                    "depth": depth,
                },
            )
            return format_research_output(result)

    async def run_stdio(self):
        """Run MCP server in stdio mode."""
        mcp_task = asyncio.create_task(self.mcp.run_stdio_async(show_banner=False))
        stdin_task = asyncio.create_task(_exit_when_stdin_closed())
        try:
            await asyncio.wait({mcp_task, stdin_task}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in (mcp_task, stdin_task):
                if not task.done():
                    task.cancel()
            for task in (mcp_task, stdin_task):
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            if hasattr(self, "_http_client"):
                await self._http_client.aclose()
