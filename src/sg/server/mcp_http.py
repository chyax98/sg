"""Mount Streamable HTTP MCP on the gateway FastAPI app."""

import logging

from starlette.applications import Starlette

from .mcp_server import MCPServer

logger = logging.getLogger(__name__)

MCP_HTTP_PATH = "/mcp"


def create_mcp_http_app(
    *,
    port: int,
    config_path: str | None = None,
) -> Starlette:
    """FastMCP streamable-http sub-app (needs ``lifespan`` on parent FastAPI)."""
    server = MCPServer(port=port, config=config_path, require_daemon=False)
    mcp_app: Starlette = server.mcp.http_app(transport="streamable-http", path="/")
    logger.info("MCP streamable-http app ready at %s", MCP_HTTP_PATH)
    return mcp_app


def mount_mcp_http(
    app,
    mcp_app: Starlette,
) -> None:
    app.mount(MCP_HTTP_PATH, mcp_app)
