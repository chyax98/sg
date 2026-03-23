"""Tests for ProviderRegistry."""

import pytest

from sg.models.config import ProviderConfig, ProviderInstanceConfig
from sg.providers.base import ProviderInfo, SearchProvider
from sg.providers.registry import ProviderRegistry, BUILTIN_PROVIDERS


class FakeRegistryProvider(SearchProvider):
    info = ProviderInfo(
        type="fake-registry",
        display_name="Fake Registry",
        needs_api_key=False,
        needs_url=False,
        free=True,
        capabilities=("search",),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def initialize(self) -> bool:
        return True

    async def shutdown(self) -> None:
        pass

    async def search(self, request):
        raise NotImplementedError


class TestProviderRegistry:
    @pytest.mark.asyncio
    async def test_explicit_fallback_group_prevents_auto_duckduckgo(self):
        original_builtins = dict(BUILTIN_PROVIDERS)
        BUILTIN_PROVIDERS["fake-registry"] = FakeRegistryProvider

        registry = ProviderRegistry(
            {
                "primary": ProviderConfig(
                    type="fake-registry",
                    instances=[ProviderInstanceConfig(id="primary-1")],
                ),
                "backup": ProviderConfig(
                    type="fake-registry",
                    is_fallback=True,
                    instances=[ProviderInstanceConfig(id="backup-1")],
                ),
            }
        )

        try:
            await registry.initialize()
            assert registry.get_fallback_group() == "backup"
            assert "duckduckgo" not in registry.all()
        finally:
            await registry.shutdown()
            BUILTIN_PROVIDERS.clear()
            BUILTIN_PROVIDERS.update(original_builtins)

    @pytest.mark.asyncio
    async def test_instance_url_is_used_directly(self):
        original_builtins = dict(BUILTIN_PROVIDERS)
        BUILTIN_PROVIDERS["fake-registry"] = FakeRegistryProvider

        registry = ProviderRegistry(
            {
                "primary": ProviderConfig(
                    type="fake-registry",
                    defaults={"timeout": 15000},
                    instances=[
                        ProviderInstanceConfig(
                            id="primary-1",
                            url="https://custom.example.com",
                        )
                    ],
                )
            }
        )

        try:
            await registry.initialize()
            provider = registry.get("primary-1")
            assert provider is not None
            assert provider.url == "https://custom.example.com"
            assert provider.timeout == 15000
        finally:
            await registry.shutdown()
            BUILTIN_PROVIDERS.clear()
            BUILTIN_PROVIDERS.update(original_builtins)
