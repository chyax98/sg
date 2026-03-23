"""Provider registry — manages lifecycle and discovery."""

import asyncio
import logging
from typing import Type

from ..models.config import ProviderConfig
from ..models.search import ProviderStatus
from .base import BaseProvider, ExtractProvider, ResearchProvider, SearchProvider

logger = logging.getLogger(__name__)

# Lazy imports to avoid circular deps — populated at module level
BUILTIN_PROVIDERS: dict[str, Type[BaseProvider]] = {}


def _register_builtins():
    """Register all built-in provider classes."""
    from .brave import BraveProvider
    from .duckduckgo import DuckDuckGoProvider
    from .exa import ExaProvider
    from .firecrawl import FirecrawlProvider
    from .jina import JinaReaderProvider
    from .searxng import SearXNGProvider
    from .tavily import TavilyProvider
    from .youcom import YouComProvider

    for cls in (DuckDuckGoProvider, TavilyProvider, BraveProvider, ExaProvider,
                SearXNGProvider, JinaReaderProvider,
                FirecrawlProvider, YouComProvider):
        BUILTIN_PROVIDERS[cls.info.type] = cls


class ProviderRegistry:
    """Registry for managing provider instances."""

    def __init__(self, config: dict[str, ProviderConfig] | None = None):
        self._providers: dict[str, BaseProvider] = {}
        self._config = config or {}
        self._fallback: str | None = None

        if not BUILTIN_PROVIDERS:
            _register_builtins()

    async def initialize(self) -> None:
        """Initialize all configured providers + DuckDuckGo fallback."""
        # Ensure DuckDuckGo fallback exists
        has_ddg = any(
            (cfg.type or iid) == "duckduckgo"
            for iid, cfg in self._config.items()
        )

        if not has_ddg:
            ddg_cls = BUILTIN_PROVIDERS["duckduckgo"]
            ddg = ddg_cls(name="duckduckgo", priority=100)
            if await ddg.initialize():
                self._providers["duckduckgo"] = ddg
                self._fallback = "duckduckgo"
                logger.info("Auto-added DuckDuckGo as fallback")

        for instance_id, cfg in self._config.items():
            if not cfg.enabled:
                continue

            provider_type = cfg.type or instance_id
            provider_class = BUILTIN_PROVIDERS.get(provider_type)
            if not provider_class:
                logger.warning(f"Unknown provider type: {provider_type} (instance: {instance_id})")
                continue

            try:
                provider = provider_class(
                    name=instance_id,
                    api_key=cfg.api_key,
                    url=cfg.url,
                    priority=cfg.priority,
                    timeout=cfg.timeout,
                )

                if await provider.initialize():
                    self._providers[instance_id] = provider
                    if cfg.is_fallback or provider_type == "duckduckgo":
                        self._fallback = instance_id
                    logger.info(f"Initialized: {instance_id} ({provider_type})")
                else:
                    logger.warning(f"Failed to initialize: {instance_id}")
            except Exception as e:
                logger.error(f"Error initializing {instance_id}: {e}")

    async def shutdown(self) -> None:
        """Shutdown all providers."""
        tasks = []
        for name, provider in self._providers.items():
            tasks.append(self._safe_shutdown(name, provider))
        await asyncio.gather(*tasks)
        self._providers.clear()

    @staticmethod
    async def _safe_shutdown(name: str, provider: BaseProvider):
        try:
            await provider.shutdown()
        except Exception as e:
            logger.error(f"Error shutting down {name}: {e}")

    def get(self, name: str) -> BaseProvider | None:
        return self._providers.get(name)

    def all(self) -> dict[str, BaseProvider]:
        return self._providers

    def get_by_capability(self, capability: str) -> list[BaseProvider]:
        """Get providers with given capability, sorted by priority."""
        result = [
            p for p in self._providers.values()
            if capability in p.capabilities and p.name != self._fallback
        ]
        result.sort(key=lambda p: p.priority)
        return result

    def get_fallback(self) -> BaseProvider | None:
        if self._fallback:
            return self._providers.get(self._fallback)
        return None

    def get_search_provider(self, name: str) -> SearchProvider | None:
        p = self._providers.get(name)
        return p if isinstance(p, SearchProvider) else None

    def get_extract_provider(self, name: str) -> ExtractProvider | None:
        p = self._providers.get(name)
        return p if isinstance(p, ExtractProvider) else None

    def get_research_provider(self, name: str) -> ResearchProvider | None:
        p = self._providers.get(name)
        return p if isinstance(p, ResearchProvider) else None

    def list_providers(self) -> list[ProviderStatus]:
        """List all providers with status info."""
        result = []
        for name, provider in self._providers.items():
            provider_type = ""
            if name in self._config:
                provider_type = self._config[name].type or name
            else:
                for type_name, cls in BUILTIN_PROVIDERS.items():
                    if isinstance(provider, cls):
                        provider_type = type_name
                        break

            result.append(ProviderStatus(
                name=name,
                type=provider_type,
                enabled=True,
                healthy=True,  # actual health tracked by circuit breaker
                capabilities=provider.capabilities,
                search_features=getattr(provider, "search_features", []),
                priority=provider.priority,
                is_fallback=(name == self._fallback),
            ))
        return result

    @staticmethod
    def get_provider_types() -> list[dict]:
        """Derive provider type info from class metadata."""
        if not BUILTIN_PROVIDERS:
            _register_builtins()
        return [
            {
                "type": cls.info.type,
                "name": cls.info.display_name,
                "needs_api_key": cls.info.needs_api_key,
                "needs_url": cls.info.needs_url,
                "free": cls.info.free,
                "capabilities": list(cls.info.capabilities),
                "search_features": list(cls.info.search_features),
            }
            for cls in BUILTIN_PROVIDERS.values()
        ]
