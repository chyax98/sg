"""Gateway — main service orchestrator."""

import asyncio
import logging
import signal
from typing import Any

from ..core.executor import Executor
from ..core.history import SearchHistory
from ..models.config import GatewayConfig
from ..models.search import (
    ExtractRequest,
    ExtractResponse,
    ExtractResult,
    ResearchRequest,
    ResearchResponse,
    SearchRequest,
    SearchResponse,
)
from ..providers.base import ExtractProvider, ResearchProvider, SearchProvider
from ..providers.registry import ProviderRegistry
from .http_server import HTTPServer

logger = logging.getLogger(__name__)


class Gateway:
    """Search Gateway — unified search with failover."""

    def __init__(self, config_path: str | None = None, port: int | None = None):
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
            name for name, p in self.providers.all().items() if isinstance(p, SearchProvider)
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
        self,
        query: str,
        provider: str | None = None,
        max_results: int = 10,
        spread_index: int | None = None,
        **kwargs,
    ) -> SearchResponse:
        """Execute search with failover."""
        request = SearchRequest(query=query, provider=provider, max_results=max_results, **kwargs)

        async def op(p):
            if not isinstance(p, SearchProvider):
                raise RuntimeError(f"{p.name} does not support search")
            return await p.search(request)

        response: SearchResponse = await self.executor.execute(
            "search", op, provider=provider, spread_index=spread_index,
        )
        result_file = await self.history.record(request, response)
        response.result_file = result_file
        return response

    async def search_batch(
        self,
        queries: list[str],
        provider: str | None = None,
        max_results: int = 10,
        **kwargs,
    ) -> list[SearchResponse]:
        """Execute multiple searches in parallel, spread across providers."""
        logger.info(f"Executing batch search: {len(queries)} queries")
        tasks = [
            self.search(q, provider=provider, max_results=max_results,
                        spread_index=i if provider is None else None, **kwargs)
            for i, q in enumerate(queries)
        ]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        results: list[SearchResponse] = []
        for i, r in enumerate(raw_results):
            if isinstance(r, Exception):
                logger.error(f"Batch search query '{queries[i]}' failed: {r}")
            else:
                results.append(r)

        logger.info(f"Batch search completed: {len(results)}/{len(queries)} succeeded")
        return results

    async def extract(self, urls: list[str], provider: str | None = None, **kwargs) -> ExtractResponse:
        """Extract content with failover. Multiple URLs spread across providers when beneficial."""
        # Only spread when there are multiple extract providers available
        # Otherwise use batch API (single provider can batch URLs more efficiently)
        should_spread = (
            len(urls) > 1
            and provider is None
            and self.executor.available_group_count("extract") >= 2
        )

        if should_spread:
            # Spread: each URL independently selects a provider
            async def _extract_one(url: str, idx: int) -> ExtractResponse:
                request = ExtractRequest(urls=[url], **kwargs)

                async def op(p):
                    if not isinstance(p, ExtractProvider):
                        raise RuntimeError(f"{p.name} does not support extract")
                    return await p.extract(request)

                return await self.executor.execute(
                    "extract", op, spread_index=idx,
                )

            tasks = [_extract_one(url, i) for i, url in enumerate(urls)]
            responses = await asyncio.gather(*tasks, return_exceptions=True)

            # Merge results
            all_results = []
            providers_used: set[str] = set()
            max_latency = 0.0
            for i, resp in enumerate(responses):
                if isinstance(resp, Exception):
                    logger.error(f"Extract URL '{urls[i]}' failed: {resp}")
                    all_results.append(ExtractResult(url=urls[i], content="", error=str(resp)))
                else:
                    all_results.extend(resp.results)
                    providers_used.add(resp.provider)
                    max_latency = max(max_latency, resp.latency_ms)

            response = ExtractResponse(
                results=all_results,
                provider=",".join(sorted(providers_used)),
                latency_ms=max_latency,
            )
        else:
            # Single URL, explicit provider, or only 1 extract provider — use batch API
            request = ExtractRequest(urls=urls, **kwargs)

            async def op(p):
                if not isinstance(p, ExtractProvider):
                    raise RuntimeError(f"{p.name} does not support extract")
                return await p.extract(request)

            response = await self.executor.execute("extract", op, provider=provider)

        # Save each URL as a separate file with line wrapping
        file_manifest = await self.history.record_extract(
            urls=urls,
            results=response.results,
            provider=response.provider,
            latency_ms=response.latency_ms,
        )
        response.result_files = file_manifest
        return response

    async def research(self, topic: str, depth: str = "auto", provider: str | None = None) -> ResearchResponse:
        """Deep research with failover."""
        request = ResearchRequest(topic=topic, depth=depth)

        async def op(p):
            if not isinstance(p, ResearchProvider):
                raise RuntimeError(f"{p.name} does not support research")
            return await p.research(request)

        response: ResearchResponse = await self.executor.execute("research", op, provider=provider)
        
        # Save to history file
        result_file = await self.history.record_content(
            operation="research",
            query=topic,
            provider=response.provider,
            latency_ms=response.latency_ms,
            content=response.content
        )
        response.result_file = result_file
        return response

    # === Status ===

    async def get_status(self) -> dict[str, Any]:
        providers = self.providers.all()
        search_providers = [name for name, p in providers.items() if isinstance(p, SearchProvider)]
        return {
            "running": self._running,
            "port": self.port,
            "strategy": "priority",  # always priority-based failover
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
