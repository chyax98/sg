"""Gateway — main service orchestrator."""

import asyncio
import logging
import signal
from typing import Any

from ..core.executor import Executor
from ..core.history import SearchHistory
from ..models.config import GatewayConfig
from ..models.search import (
    ExtractRequest, ResearchRequest, SearchRequest, SearchResponse,
)
from ..providers.base import ExtractProvider, ResearchProvider, SearchProvider
from ..providers.registry import ProviderRegistry
from .http_server import HTTPServer

logger = logging.getLogger(__name__)


class Gateway:
    """Search Gateway — unified search with failover."""

    def __init__(self, config_path: str = "config.json", port: int | None = None):
        self.config_path = config_path
        self.config = GatewayConfig.load(config_path)
        self.port = port or self.config.server.port

        self.providers = ProviderRegistry(self.config.providers)
        self.executor = Executor(self.config.executor, self.providers)
        self.history = SearchHistory(self.config.history)

        self.http_server: HTTPServer | None = None
        self._running = False
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Start the gateway."""
        logger.info(f"Starting Search Gateway on port {self.port}")

        await self.providers.initialize()

        available = [
            name for name, p in self.providers.all().items()
            if isinstance(p, SearchProvider)
        ]
        logger.info(f"Available search providers: {available}")
        if not available:
            logger.warning("No search providers available!")

        self.http_server = HTTPServer(self, self.port, self.config.server.host)
        await self.http_server.start()

        self._running = True
        logger.info(f"Gateway ready: http://{self.config.server.host}:{self.port}")

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
        await self.providers.shutdown()
        self._shutdown_event.set()

    async def wait_shutdown(self) -> None:
        await self._shutdown_event.wait()

    # === Core API — all go through executor.execute() ===

    async def search(
        self, query: str, provider: str | None = None, max_results: int = 10, **kwargs,
    ) -> SearchResponse:
        """Execute search with failover."""
        request = SearchRequest(query=query, provider=provider, max_results=max_results, **kwargs)

        async def op(p):
            if not isinstance(p, SearchProvider):
                raise RuntimeError(f"{p.name} does not support search")
            return await p.search(request)

        response = await self.executor.execute("search", op, provider=provider)
        result_file = await self.history.record(request, response)
        response.result_file = result_file
        return response

    async def search_batch(
        self, queries: list[str], provider: str | None = None, max_results: int = 10, **kwargs,
    ) -> list[SearchResponse]:
        """Execute multiple searches in parallel."""
        tasks = [
            self.search(q, provider=provider, max_results=max_results, **kwargs)
            for q in queries
        ]
        return await asyncio.gather(*tasks, return_exceptions=False)

    async def extract(self, urls: list[str], provider: str | None = None, **kwargs) -> Any:
        """Extract content with failover."""
        request = ExtractRequest(urls=urls, **kwargs)

        async def op(p):
            if not isinstance(p, ExtractProvider):
                raise RuntimeError(f"{p.name} does not support extract")
            return await p.extract(request)

        return await self.executor.execute("extract", op, provider=provider)

    async def research(self, topic: str, depth: str = "auto", provider: str | None = None) -> Any:
        """Deep research with failover."""
        request = ResearchRequest(topic=topic, depth=depth)

        async def op(p):
            if not isinstance(p, ResearchProvider):
                raise RuntimeError(f"{p.name} does not support research")
            return await p.research(request)

        return await self.executor.execute("research", op, provider=provider)

    # === Status ===

    async def get_status(self) -> dict[str, Any]:
        providers = self.providers.all()
        search_providers = [
            name for name, p in providers.items()
            if isinstance(p, SearchProvider)
        ]
        return {
            "running": self._running,
            "port": self.port,
            "strategy": self.config.executor.strategy.value,
            "providers": {
                "total": len(providers),
                "available": search_providers,
            },
            "metrics": self.executor.get_metrics(),
        }

    async def list_providers(self):
        return self.providers.list_providers()

    async def health_check(self):
        return await self.executor.run_health_checks()

    # === Config management ===

    def get_config_raw(self) -> dict:
        return GatewayConfig.load_raw(self.config_path)

    def save_config_raw(self, data: dict) -> None:
        GatewayConfig.save_raw(data, self.config_path)

    async def reload_config(self) -> None:
        """Reload config and reinitialize everything."""
        logger.info("Reloading configuration...")
        await self.providers.shutdown()

        self.config = GatewayConfig.load(self.config_path)
        self.providers = ProviderRegistry(self.config.providers)
        self.executor = Executor(self.config.executor, self.providers)
        self.history = SearchHistory(self.config.history)

        await self.providers.initialize()
        logger.info("Configuration reloaded")
