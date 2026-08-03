"""Gateway — main service orchestrator."""

import asyncio
import logging
import signal
from typing import Any

from ..core.executor import Executor
from ..core.history import SearchHistory
from ..models.config import GatewayConfig
from ..models.search import (
    DocsContextRequest,
    DocsContextResponse,
    DocsLibrarySearchRequest,
    DocsLibrarySearchResponse,
    ExtractRequest,
    ExtractResponse,
    ExtractResult,
    ResearchDepth,
    ResearchRequest,
    ResearchResponse,
    SearchRequest,
    SearchResponse,
)
from ..protocol import merge_warnings, project_extract, project_research, project_search
from ..providers.base import ExtractProvider, ResearchProvider, SearchProvider
from ..providers.context7 import Context7Provider
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
        limit: int = 10,
        spread_index: int | None = None,
        **kwargs,
    ) -> SearchResponse:
        """Execute search with failover."""
        request = SearchRequest(query=query, provider=provider, limit=limit, **kwargs)
        warnings_acc: list[str] = []

        async def op(p):
            if not isinstance(p, SearchProvider):
                raise RuntimeError(f"{p.name} does not support search")
            projected = project_search(request, p.protocol_capability.search)
            warnings_acc.extend(projected.warnings)
            return await p.search(projected.request)

        response: SearchResponse = await self.executor.execute(
            "search",
            op,
            provider=provider,
            spread_index=spread_index,
        )
        response.warnings = merge_warnings(response.warnings, warnings_acc)
        result_file = await self.history.record(request, response)
        response.result_file = result_file
        return response

    async def search_batch(
        self,
        queries: list[str],
        provider: str | None = None,
        limit: int = 10,
        **kwargs,
    ) -> list[SearchResponse]:
        """Execute multiple searches in parallel, spread across providers."""
        logger.info(f"Executing batch search: {len(queries)} queries")
        tasks = [
            self.search(
                q,
                provider=provider,
                limit=limit,
                spread_index=i if provider is None else None,
                **kwargs,
            )
            for i, q in enumerate(queries)
        ]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        results: list[SearchResponse] = []
        for i, r in enumerate(raw_results):
            if isinstance(r, BaseException):
                logger.error(f"Batch search query '{queries[i]}' failed: {r}")
                results.append(
                    SearchResponse(
                        query=queries[i],
                        provider=provider or "",
                        results=[],
                        total=0,
                        latency_ms=0.0,
                        error=str(r),
                    )
                )
            else:
                results.append(r)

        success_count = sum(1 for result in results if not result.error)
        logger.info(f"Batch search completed: {success_count}/{len(queries)} succeeded")
        return results

    @staticmethod
    def _normalize_extract_results(
        urls: list[str], results: list[ExtractResult]
    ) -> list[ExtractResult]:
        """Align provider extract results to requested URLs.

        Some batch extract providers may reorder results or omit failed URLs entirely.
        Normalize the response so downstream history/result-file generation always has one
        entry per requested URL in request order.
        """
        aligned: list[ExtractResult | None] = [None] * len(urls)
        used = [False] * len(results)

        for idx, url in enumerate(urls):
            for result_idx, result in enumerate(results):
                if used[result_idx]:
                    continue
                if result.url == url:
                    aligned[idx] = result
                    used[result_idx] = True
                    break

        remaining_results = [
            result for result_idx, result in enumerate(results) if not used[result_idx]
        ]
        remaining_positions = [idx for idx, result in enumerate(aligned) if result is None]

        if remaining_results and len(remaining_results) == len(remaining_positions):
            for idx, result in zip(remaining_positions, remaining_results, strict=False):
                aligned[idx] = result.model_copy(update={"url": urls[idx]})

        return [
            result
            if result is not None
            else ExtractResult(
                url=urls[idx],
                content="",
                error="provider returned no extract result",
            )
            for idx, result in enumerate(aligned)
        ]

    async def extract(
        self, urls: list[str], provider: str | None = None, **kwargs
    ) -> ExtractResponse:
        """Extract content with failover. Multiple URLs spread across providers when beneficial."""
        # Only spread when there are multiple extract providers available
        # Otherwise use batch API (single provider can batch URLs more efficiently)
        should_spread = (
            len(urls) > 1
            and provider is None
            and self.executor.available_group_count("extract") >= 2
        )

        warnings_acc: list[str] = []
        if should_spread:
            # Spread: each URL independently selects a provider
            async def _extract_one(url: str, idx: int) -> ExtractResponse:
                request = ExtractRequest(urls=[url], **kwargs)

                async def op(p):
                    if not isinstance(p, ExtractProvider):
                        raise RuntimeError(f"{p.name} does not support extract")
                    projected = project_extract(request, p.protocol_capability.extract)
                    warnings_acc.extend(projected.warnings)
                    return await p.extract(projected.request)

                return await self.executor.execute(  # type: ignore[no-any-return]
                    "extract",
                    op,
                    spread_index=idx,
                )

            tasks = [_extract_one(url, i) for i, url in enumerate(urls)]
            responses = await asyncio.gather(*tasks, return_exceptions=True)

            # Merge results
            all_results = []
            providers_used: set[str] = set()
            max_latency = 0.0
            for i, resp in enumerate(responses):
                if isinstance(resp, BaseException):
                    logger.error(f"Extract URL '{urls[i]}' failed: {resp}")
                    all_results.append(ExtractResult(url=urls[i], content="", error=str(resp)))
                else:
                    all_results.extend(resp.results)
                    providers_used.add(resp.provider)
                    max_latency = max(max_latency, resp.latency_ms)
                    warnings_acc.extend(getattr(resp, "warnings", None) or [])

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
                projected = project_extract(request, p.protocol_capability.extract)
                warnings_acc.extend(projected.warnings)
                return await p.extract(projected.request)

            response = await self.executor.execute("extract", op, provider=provider)

        response.results = self._normalize_extract_results(urls, response.results)
        response.warnings = merge_warnings(response.warnings, warnings_acc)

        # Save each URL as a separate file with line wrapping
        file_manifest = await self.history.record_extract(
            urls=urls,
            results=response.results,
            provider=response.provider,
            latency_ms=response.latency_ms,
        )
        response.result_files = file_manifest
        return response

    async def research(
        self, topic: str, depth: ResearchDepth = "auto", provider: str | None = None
    ) -> ResearchResponse:
        """Deep research with failover."""
        request = ResearchRequest(topic=topic, depth=depth)
        warnings_acc: list[str] = []

        async def op(p):
            if not isinstance(p, ResearchProvider):
                raise RuntimeError(f"{p.name} does not support research")
            projected = project_research(request, p.protocol_capability.research)
            warnings_acc.extend(projected.warnings)
            return await p.research(projected.request)

        response: ResearchResponse = await self.executor.execute("research", op, provider=provider)
        response.warnings = merge_warnings(response.warnings, warnings_acc)

        # Save to history file
        result_file = await self.history.record_content(
            operation="research",
            query=topic,
            provider=response.provider,
            latency_ms=response.latency_ms,
            content=response.report,
        )
        response.result_file = result_file
        return response

    # === Context7 docs side-path (not web search) ===

    async def docs_search(
        self,
        library_name: str,
        query: str,
        *,
        fast: bool = False,
        provider: str | None = None,
    ) -> DocsLibrarySearchResponse:
        """Official resolve-library-id. POST /docs/search — multi-key LB only."""
        request = DocsLibrarySearchRequest(
            library_name=library_name,
            query=query,
            fast=fast,
        )

        async def op(p):
            if not isinstance(p, Context7Provider):
                raise RuntimeError(f"{p.name} does not support docs_search")
            return await p.docs_search(request)

        # Prefer group name "context7"; else any provider with the capability
        target = provider
        if not target and self.providers.has_group("context7"):
            target = "context7"
        return await self.executor.execute("docs_search", op, provider=target)  # type: ignore[no-any-return]

    async def docs_context(
        self,
        library_id: str,
        query: str,
        *,
        fast: bool = False,
        provider: str | None = None,
    ) -> DocsContextResponse:
        """Official query-docs. POST /docs/context — multi-key LB only."""
        request = DocsContextRequest(library_id=library_id, query=query, fast=fast)

        async def op(p):
            if not isinstance(p, Context7Provider):
                raise RuntimeError(f"{p.name} does not support docs_context")
            return await p.docs_context(request)

        target = provider
        if not target and self.providers.has_group("context7"):
            target = "context7"
        return await self.executor.execute("docs_context", op, provider=target)  # type: ignore[no-any-return]

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

        new_config = GatewayConfig.load(self.config_path)
        new_providers = ProviderRegistry(new_config.providers)
        new_executor = Executor(new_config.executor, new_providers)
        new_history = SearchHistory(new_config.history)

        try:
            await new_providers.initialize()
        except Exception:
            await new_providers.shutdown()
            raise

        old_providers = self.providers
        self.config = new_config
        self.providers = new_providers
        self.executor = new_executor
        self.history = new_history

        await old_providers.shutdown()
        logger.info("Configuration reloaded")
