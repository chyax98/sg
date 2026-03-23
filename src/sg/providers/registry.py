"""Provider registry — manages lifecycle, provider groups, and instance selection."""

import asyncio
import logging
import random
from typing import Callable, Type

from ..models.config import ProviderConfig, ProviderInstanceConfig
from ..models.search import ProviderStatus
from .base import BaseProvider, ExtractProvider, ResearchProvider, SearchProvider

logger = logging.getLogger(__name__)

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

    for cls in (
        DuckDuckGoProvider,
        TavilyProvider,
        BraveProvider,
        ExaProvider,
        SearXNGProvider,
        JinaReaderProvider,
        FirecrawlProvider,
        YouComProvider,
    ):
        BUILTIN_PROVIDERS[cls.info.type] = cls


class ProviderRegistry:
    """Registry for managing provider groups and instances."""

    def __init__(self, config: dict[str, ProviderConfig] | None = None):
        self._providers: dict[str, BaseProvider] = {}
        self._config = config or {}
        self._groups: dict[str, list[str]] = {}
        self._instance_to_group: dict[str, str] = {}
        self._rr_index: dict[str, int] = {}

        if not BUILTIN_PROVIDERS:
            _register_builtins()

    async def initialize(self) -> None:
        """Initialize configured provider groups and fallback."""
        groups = dict(self._config)
        has_explicit_fallback = any(
            cfg.enabled and cfg.fallback_for for cfg in groups.values()
        )

        if not has_explicit_fallback and "duckduckgo" not in groups:
            groups["duckduckgo"] = ProviderConfig(
                type="duckduckgo",
                priority=100,
                fallback_for=["search"],
                instances=[ProviderInstanceConfig(id="duckduckgo")],
            )

        for group_name, group_cfg in groups.items():
            if not group_cfg.enabled:
                continue

            provider_type = group_cfg.type or group_name
            provider_class = BUILTIN_PROVIDERS.get(provider_type)
            if not provider_class:
                logger.warning(f"Unknown provider type: {provider_type} (group: {group_name})")
                continue

            instance_ids: list[str] = []
            for instance_cfg in group_cfg.instances:
                if not instance_cfg.enabled:
                    continue
                try:
                    provider = provider_class(
                        name=instance_cfg.id,
                        api_key=instance_cfg.api_key,
                        url=instance_cfg.url,
                        priority=instance_cfg.priority,
                        timeout=instance_cfg.timeout or group_cfg.defaults.timeout,
                    )
                    if await provider.initialize():
                        self._providers[instance_cfg.id] = provider
                        self._instance_to_group[instance_cfg.id] = group_name
                        instance_ids.append(instance_cfg.id)
                        logger.info(f"Initialized: {instance_cfg.id} ({provider_type})")
                    else:
                        logger.warning(f"Failed to initialize: {instance_cfg.id}")
                except Exception as e:
                    logger.error(f"Error initializing {instance_cfg.id}: {e}")

            if instance_ids:
                self._groups[group_name] = instance_ids

    async def shutdown(self) -> None:
        """Shutdown all provider instances."""
        tasks = []
        for name, provider in self._providers.items():
            tasks.append(self._safe_shutdown(name, provider))
        await asyncio.gather(*tasks)
        self._providers.clear()
        self._groups.clear()
        self._instance_to_group.clear()

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

    def has_group(self, group_name: str) -> bool:
        return group_name in self._groups

    def group_for_instance(self, instance_id: str) -> str | None:
        return self._instance_to_group.get(instance_id)

    def get_group_order(self, capability: str) -> list[str]:
        """Get provider groups for a capability, sorted by group priority."""
        candidates: list[tuple[int, str]] = []
        for group_name, instance_ids in self._groups.items():
            cfg = self._config.get(group_name)
            if not cfg or not cfg.enabled:
                continue
            # Skip fallback groups from normal ordering
            if capability in cfg.fallback_for:
                continue
            if any(capability in self._providers[i].capabilities for i in instance_ids):
                candidates.append((cfg.priority, group_name))
        candidates.sort(key=lambda item: item[0])
        return [group_name for _, group_name in candidates]

    def get_fallback_group(self, capability: str) -> str | None:
        """Get fallback group for specific capability."""
        for group_name, cfg in self._config.items():
            if cfg.enabled and capability in cfg.fallback_for:
                if group_name in self._groups:
                    return group_name
        return None

    def select_instance(
        self,
        group_name: str,
        capability: str,
        excluded_instances: set[str] | None = None,
        allow_request: Callable[[str], bool] | None = None,
    ) -> BaseProvider | None:
        """Select one available instance from a provider group."""
        cfg = self._config.get(group_name)
        if not cfg:
            return None

        available = []
        for instance_id in self._groups.get(group_name, []):
            provider = self._providers.get(instance_id)
            if not provider or capability not in provider.capabilities:
                continue
            if excluded_instances and instance_id in excluded_instances:
                continue
            if allow_request and not allow_request(instance_id):
                continue
            available.append(provider)

        if not available:
            return None

        if cfg.selection == "priority":
            return min(available, key=lambda provider: provider.priority)
        if cfg.selection == "round_robin":
            available = sorted(available, key=lambda provider: provider.priority)
            idx = self._rr_index.get(group_name, 0) % len(available)
            self._rr_index[group_name] = self._rr_index.get(group_name, 0) + 1
            return available[idx]
        return random.choice(available)

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
        """List provider instances with group-level metadata."""
        result = []
        for instance_id, provider in self._providers.items():
            group_name = self._instance_to_group.get(instance_id, "")
            provider_type = ""
            if group_name in self._config:
                provider_type = self._config[group_name].type or group_name
            else:
                for type_name, cls in BUILTIN_PROVIDERS.items():
                    if isinstance(provider, cls):
                        provider_type = type_name
                        break

            result.append(
                ProviderStatus(
                    name=instance_id,
                    group=group_name,
                    type=provider_type,
                    enabled=True,
                    healthy=True,
                    capabilities=provider.capabilities,
                    search_features=getattr(provider, "search_features", []),
                    priority=provider.priority,
                    is_fallback=bool(
                        self._config.get(group_name)
                        and self._config[group_name].fallback_for
                    ),
                )
            )
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
