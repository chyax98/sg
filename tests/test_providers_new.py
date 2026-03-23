"""Tests for providers (Jina, Firecrawl, You.com) with v3.0 base class."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from sg.providers.jina import JinaReaderProvider
from sg.providers.firecrawl import FirecrawlProvider
from sg.providers.youcom import YouComProvider
from sg.providers.base import ProviderInfo


class TestJinaReaderProvider:

    def test_provider_info(self):
        assert JinaReaderProvider.info.type == "jina"
        assert JinaReaderProvider.info.needs_api_key is False
        assert JinaReaderProvider.info.free is True
        assert "extract" in JinaReaderProvider.info.capabilities

    def test_init_with_new_signature(self):
        provider = JinaReaderProvider(name="jina-1", priority=20, timeout=15000)
        assert provider.name == "jina-1"
        assert provider.priority == 20
        assert provider.timeout == 15000

    def test_default_no_api_key(self):
        provider = JinaReaderProvider(name="jina")
        assert provider.api_key is None

    def test_capabilities_extract_only_without_key(self):
        provider = JinaReaderProvider(name="jina")
        # Before initialize, capabilities come from info
        assert "extract" in provider.capabilities

    @pytest.mark.asyncio
    async def test_initialize_creates_client(self):
        provider = JinaReaderProvider(name="jina")
        result = await provider.initialize()
        assert result is True
        assert provider._extract_client is not None
        await provider.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_cleans_up(self):
        provider = JinaReaderProvider(name="jina")
        await provider.initialize()
        await provider.shutdown()
        assert provider._extract_client is None

    @pytest.mark.asyncio
    async def test_initialize_with_api_key_enables_search(self):
        provider = JinaReaderProvider(name="jina", api_key="test-key")
        await provider.initialize()
        assert provider._search_client is not None
        assert "search" in provider.capabilities
        assert "extract" in provider.capabilities
        await provider.shutdown()

    @pytest.mark.asyncio
    async def test_health_check_not_initialized(self):
        provider = JinaReaderProvider(name="jina")
        healthy, error = await provider.health_check()
        assert healthy is False

    @pytest.mark.asyncio
    async def test_health_check_initialized(self):
        provider = JinaReaderProvider(name="jina")
        await provider.initialize()
        healthy, error = await provider.health_check()
        assert healthy is True
        await provider.shutdown()


class TestFirecrawlProvider:

    def test_provider_info(self):
        assert FirecrawlProvider.info.type == "firecrawl"
        assert FirecrawlProvider.info.needs_api_key is True
        assert "search" in FirecrawlProvider.info.capabilities
        assert "extract" in FirecrawlProvider.info.capabilities
        assert "time_range" in FirecrawlProvider.info.search_features

    def test_init_with_new_signature(self):
        provider = FirecrawlProvider(name="firecrawl-1", api_key="test-key", priority=3)
        assert provider.name == "firecrawl-1"
        assert provider.api_key == "test-key"
        assert provider.priority == 3

    @pytest.mark.asyncio
    async def test_initialize_without_key_fails(self):
        provider = FirecrawlProvider(name="firecrawl")
        result = await provider.initialize()
        assert result is False

    @pytest.mark.asyncio
    async def test_initialize_with_empty_key_fails(self):
        provider = FirecrawlProvider(name="firecrawl", api_key="")
        result = await provider.initialize()
        assert result is False

    @pytest.mark.asyncio
    async def test_initialize_with_key(self):
        provider = FirecrawlProvider(name="firecrawl", api_key="test-key")
        result = await provider.initialize()
        assert result is True
        await provider.shutdown()

    @pytest.mark.asyncio
    async def test_health_check_not_initialized(self):
        provider = FirecrawlProvider(name="firecrawl")
        healthy, error = await provider.health_check()
        assert healthy is False
        assert "Not initialized" in error


class TestYouComProvider:

    def test_provider_info(self):
        assert YouComProvider.info.type == "youcom"
        assert YouComProvider.info.needs_api_key is True
        assert "search" in YouComProvider.info.capabilities
        assert "include_domains" in YouComProvider.info.search_features

    def test_init_with_new_signature(self):
        provider = YouComProvider(name="youcom-1", api_key="test-key", priority=5)
        assert provider.name == "youcom-1"
        assert provider.api_key == "test-key"
        assert provider.priority == 5

    @pytest.mark.asyncio
    async def test_initialize_without_key_fails(self):
        provider = YouComProvider(name="youcom")
        result = await provider.initialize()
        assert result is False

    @pytest.mark.asyncio
    async def test_initialize_with_empty_key_fails(self):
        provider = YouComProvider(name="youcom", api_key="")
        result = await provider.initialize()
        assert result is False

    @pytest.mark.asyncio
    async def test_initialize_with_key(self):
        provider = YouComProvider(name="youcom", api_key="test-key")
        result = await provider.initialize()
        assert result is True
        await provider.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_cleans_up(self):
        provider = YouComProvider(name="youcom", api_key="test-key")
        await provider.initialize()
        await provider.shutdown()
        assert provider._client is None

    @pytest.mark.asyncio
    async def test_health_check_not_initialized(self):
        provider = YouComProvider(name="youcom")
        healthy, error = await provider.health_check()
        assert healthy is False
        assert "Not initialized" in error
