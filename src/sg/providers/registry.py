"""Provider registry - Manages all search providers."""

import asyncio
import logging
import time
from typing import Type

from ..models.config import ProviderConfig
from ..models.search import ProviderStatus
from .base import BaseProvider, ExtractProvider, ResearchProvider, SearchProvider
from .brave import BraveProvider
from .duckduckgo import DuckDuckGoProvider
from .exa import ExaProvider
from .firecrawl import FirecrawlProvider
from .jina import JinaReaderProvider
from .youcom import YouComProvider
from .searxng import SearXNGProvider
from .serper import SerperProvider
from .tavily import TavilyProvider

logger = logging.getLogger(__name__)

# Built-in providers: type name -> class
BUILTIN_PROVIDERS: dict[str, Type[BaseProvider]] = {
    "duckduckgo": DuckDuckGoProvider,
    "tavily": TavilyProvider,
    "brave": BraveProvider,
    "exa": ExaProvider,
    "serper": SerperProvider,
    "searxng": SearXNGProvider,
    "jina": JinaReaderProvider,
    "firecrawl": FirecrawlProvider,
    "youcom": YouComProvider,
}


class ProviderRegistry:
    """Registry for managing search providers."""

    def __init__(self, config: dict[str, ProviderConfig] | None = None):
        self._providers: dict[str, BaseProvider] = {}
        self._config = config or {}
        self._healthy_providers: set[str] = set()
        self._fallback_providers: list[str] = []

    async def initialize(self) -> None:
        """Initialize all configured providers."""
        # Always add DuckDuckGo as fallback
        has_ddg = False
        for instance_id, cfg in self._config.items():
            provider_type = cfg.type or instance_id
            if provider_type == "duckduckgo":
                has_ddg = True
                break

        if not has_ddg and "duckduckgo" not in self._providers:
            ddg = DuckDuckGoProvider()
            await ddg.initialize()
            ddg.name = "duckduckgo"
            self._providers["duckduckgo"] = ddg
            self._fallback_providers.append("duckduckgo")
            logger.info("Initialized DuckDuckGo as fallback provider")

        # Initialize configured providers
        for instance_id, provider_config in self._config.items():
            if not provider_config.enabled:
                continue

            # Determine type: explicit type field, or fall back to instance_id
            provider_type = provider_config.type or instance_id
            provider_class = BUILTIN_PROVIDERS.get(provider_type)
            if not provider_class:
                logger.warning(f"Unknown provider type: {provider_type} (instance: {instance_id})")
                continue

            try:
                kwargs = {
                    "api_key": provider_config.api_key,
                    "url": provider_config.url,
                    "priority": provider_config.priority,
                    "timeout": provider_config.timeout,
                }
                # Pass extra env vars for google (cx)
                if provider_type == "google" and provider_config.env:
                    kwargs["cx"] = provider_config.env.get("cx", "")

                provider = provider_class(**kwargs)
                provider.name = instance_id  # Use instance ID as name
                provider.is_fallback = provider_config.is_fallback

                success = await provider.initialize()
                if success:
                    self._providers[instance_id] = provider
                    if provider_config.is_fallback or provider_type == "duckduckgo":
                        self._fallback_providers.append(instance_id)
                    logger.info(f"Initialized provider: {instance_id} (type: {provider_type})")
                else:
                    logger.warning(f"Failed to initialize provider: {instance_id}")

            except Exception as e:
                logger.error(f"Error initializing provider {instance_id}: {e}")

        await self.health_check_all()

    async def shutdown(self) -> None:
        """Shutdown all providers."""
        for name, provider in self._providers.items():
            try:
                await provider.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down provider {name}: {e}")

        self._providers.clear()
        self._healthy_providers.clear()

    async def health_check_all(self) -> None:
        """Check health of all providers."""
        async def check(name: str, provider: BaseProvider):
            healthy, error = await provider.health_check()
            provider.healthy = healthy
            if healthy:
                self._healthy_providers.add(name)
            else:
                self._healthy_providers.discard(name)
            return name, healthy, error

        results = await asyncio.gather(
            *[check(n, p) for n, p in self._providers.items()],
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Health check error: {result}")
            else:
                name, healthy, error = result
                if not healthy:
                    logger.warning(f"Provider {name} unhealthy: {error}")

    def get(self, name: str) -> BaseProvider | None:
        return self._providers.get(name)

    def get_search_provider(self, name: str) -> SearchProvider | None:
        provider = self._providers.get(name)
        if provider and isinstance(provider, SearchProvider):
            return provider
        return None

    def get_extract_provider(self, name: str) -> ExtractProvider | None:
        provider = self._providers.get(name)
        if provider and isinstance(provider, ExtractProvider):
            return provider
        return None

    def get_research_provider(self, name: str) -> ResearchProvider | None:
        provider = self._providers.get(name)
        if provider and isinstance(provider, ResearchProvider):
            return provider
        return None

    def get_healthy_providers(self, capability: str = "search") -> list[BaseProvider]:
        """Get all healthy providers with specified capability, sorted by priority."""
        result = []
        for name in self._healthy_providers:
            provider = self._providers.get(name)
            if provider and capability in provider.capabilities:
                result.append(provider)
        result.sort(key=lambda p: p.priority)
        return result

    def get_fallback_provider(self) -> SearchProvider | None:
        for name in self._fallback_providers:
            provider = self._providers.get(name)
            if provider and isinstance(provider, SearchProvider):
                return provider
        return None

    def list_providers(self) -> list[ProviderStatus]:
        """List all providers with status."""
        result = []
        for name, provider in self._providers.items():
            # Determine the provider type from config or class
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
                enabled=provider.enabled,
                healthy=provider.healthy,
                capabilities=provider.capabilities,
                priority=provider.priority,
                is_fallback=provider.is_fallback,
                last_check=time.time(),
            ))
        return result

    @property
    def available_search_providers(self) -> list[str]:
        return [
            name for name, provider in self._providers.items()
            if provider.healthy and "search" in provider.capabilities
        ]
