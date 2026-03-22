"""Gateway - Main search gateway service."""

import asyncio
import logging
import signal
from pathlib import Path
from typing import Any

from ..core.history import SearchHistory
from ..core.load_balancer import LoadBalancer
from ..core.router import Router
from ..models.config import GatewayConfig
from ..models.search import (
    ExtractRequest,
    ProviderStatus,
    ResearchRequest,
    SearchRequest,
    SearchResponse,
)
from ..providers.registry import BUILTIN_PROVIDERS, ProviderRegistry
from .http_server import HTTPServer
from .mcp_server import MCPServer

logger = logging.getLogger(__name__)


class Gateway:
    """Search Gateway - Unified search with load balancing."""

    def __init__(self, config_path: str = "config.json", port: int | None = None):
        self.config_path = config_path
        self.config = GatewayConfig.load(config_path)
        self.port = port or self.config.server.port

        # Components
        self.providers = ProviderRegistry(self.config.providers)
        self.router = Router(registry=self.providers)
        self.load_balancer = LoadBalancer(self.config.load_balancer, self.providers)
        self.history = SearchHistory(self.config.history)

        # Servers
        self.http_server: HTTPServer | None = None
        self.mcp_server: MCPServer | None = None

        self._running = False
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Start the gateway."""
        logger.info(f"Starting Search Gateway on port {self.port}")

        await self.providers.initialize()

        available = self.providers.available_search_providers
        logger.info(f"Available search providers: {available}")
        if not available:
            logger.warning("No search providers available!")

        # Start HTTP server
        self.http_server = HTTPServer(self, self.port)
        await self.http_server.start()

        # Conditionally start MCP server
        if self.config.mcp.enabled:
            self.mcp_server = MCPServer(self)
            await self.mcp_server.start()
            logger.info("MCP server enabled")

        self._running = True
        logger.info(f"Gateway ready: http://127.0.0.1:{self.port}")

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

    async def stop(self) -> None:
        """Stop the gateway."""
        if not self._running:
            return

        logger.info("Stopping Search Gateway")
        self._running = False

        if self.http_server:
            await self.http_server.stop()
        if self.mcp_server:
            await self.mcp_server.stop()

        await self.providers.shutdown()
        self._shutdown_event.set()

    async def wait_shutdown(self) -> None:
        await self._shutdown_event.wait()

    # === Core API ===

    async def search(
        self, query: str, provider: str | None = None, max_results: int = 10, **kwargs,
    ) -> SearchResponse:
        """Execute search."""
        request = SearchRequest(query=query, provider=provider, max_results=max_results, **kwargs)
        providers = self.router.route(provider=provider)

        async def execute(p, **kw):
            search_provider = self.providers.get_search_provider(p.name)
            if not search_provider:
                raise RuntimeError(f"Provider {p.name} does not support search")
            return await search_provider.search(request)

        response = await self.load_balancer.execute_with_failover(providers, execute)

        # Record history
        await self.history.record(request, response)

        return response

    async def extract(self, urls: list[str], provider: str | None = None, **kwargs) -> Any:
        """Extract content from URLs."""
        request = ExtractRequest(urls=urls, **kwargs)

        # Try specified provider, then any extract-capable provider
        provider_name = provider
        if provider_name:
            extract_provider = self.providers.get_extract_provider(provider_name)
        else:
            # Find first healthy extract provider by priority
            candidates = self.providers.get_healthy_providers("extract")
            extract_provider = candidates[0] if candidates else None

        if not extract_provider:
            raise RuntimeError("No extract provider available")

        from ..providers.base import ExtractProvider as EP
        if isinstance(extract_provider, EP):
            return await extract_provider.extract(request)
        raise RuntimeError("Provider does not support extract")

    async def research(self, topic: str, depth: str = "auto", provider: str | None = None) -> Any:
        """Execute deep research."""
        request = ResearchRequest(topic=topic, depth=depth)

        provider_name = provider
        if provider_name:
            research_provider = self.providers.get_research_provider(provider_name)
        else:
            candidates = self.providers.get_healthy_providers("research")
            research_provider = candidates[0] if candidates else None

        if not research_provider:
            raise RuntimeError("No research provider available")

        from ..providers.base import ResearchProvider as RP
        if isinstance(research_provider, RP):
            return await research_provider.research(request)
        raise RuntimeError("Provider does not support research")

    async def get_status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "port": self.port,
            "strategy": self.config.load_balancer.strategy.value,
            "mcp_enabled": self.config.mcp.enabled,
            "history_enabled": self.config.history.enabled,
            "providers": {
                "total": len(self.providers._providers),
                "healthy": len(self.providers._healthy_providers),
                "available": self.providers.available_search_providers,
            },
            "metrics": self.load_balancer.get_metrics(),
        }

    async def list_providers(self) -> list[ProviderStatus]:
        return self.providers.list_providers()

    async def health_check(self) -> dict[str, Any]:
        await self.providers.health_check_all()
        return {
            "healthy": list(self.providers._healthy_providers),
            "unhealthy": [
                name for name in self.providers._providers
                if name not in self.providers._healthy_providers
            ],
        }

    # === Config management ===

    def get_config_raw(self) -> dict:
        """Get raw config (without env var expansion)."""
        return GatewayConfig.load_raw(self.config_path)

    def save_config_raw(self, data: dict) -> None:
        """Save raw config to file."""
        GatewayConfig.save_raw(data, self.config_path)

    @staticmethod
    def get_provider_types() -> list[dict]:
        """List available provider types."""
        type_info = {
            "tavily": {"name": "Tavily", "needs_api_key": True, "needs_url": False, "free": False, "capabilities": ["search", "extract", "research"]},
            "brave": {"name": "Brave Search", "needs_api_key": True, "needs_url": False, "free": False, "capabilities": ["search"]},
            "exa": {"name": "Exa", "needs_api_key": True, "needs_url": False, "free": False, "capabilities": ["search", "extract"]},
            "serper": {"name": "Serper (Google)", "needs_api_key": True, "needs_url": False, "free": False, "capabilities": ["search"]},
            "youcom": {"name": "You.com", "needs_api_key": True, "needs_url": False, "free": False, "capabilities": ["search"]},
            "firecrawl": {"name": "Firecrawl", "needs_api_key": True, "needs_url": False, "free": False, "capabilities": ["search", "extract"]},
            "jina": {"name": "Jina Reader", "needs_api_key": False, "needs_url": False, "free": True, "capabilities": ["extract"]},  # search requires key
            "searxng": {"name": "SearXNG", "needs_api_key": False, "needs_url": True, "free": True, "capabilities": ["search"]},
            "duckduckgo": {"name": "DuckDuckGo", "needs_api_key": False, "needs_url": False, "free": True, "capabilities": ["search"]},
        }
        return [{"type": k, **v} for k, v in type_info.items()]

    async def reload_config(self) -> None:
        """Reload config and reinitialize providers."""
        logger.info("Reloading configuration...")
        await self.providers.shutdown()

        self.config = GatewayConfig.load(self.config_path)
        self.providers = ProviderRegistry(self.config.providers)
        self.router = Router(registry=self.providers)
        self.load_balancer = LoadBalancer(self.config.load_balancer, self.providers)
        self.history = SearchHistory(self.config.history)

        await self.providers.initialize()
        logger.info("Configuration reloaded")
