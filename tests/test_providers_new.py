"""Tests for new providers (Jina, Firecrawl, You.com)."""

import pytest

from sg.providers.jina import JinaReaderProvider
from sg.providers.firecrawl import FirecrawlProvider
from sg.providers.youcom import YouComProvider
from sg.models.search import SearchRequest, ExtractRequest


class TestJinaReaderProvider:

    def test_attributes(self):
        provider = JinaReaderProvider()
        assert provider.name == "jina"
        assert "extract" in provider.capabilities  # Free tier
        assert provider.priority == 90  # Low priority fallback

    def test_free_no_key_needed(self):
        provider = JinaReaderProvider()
        assert provider.api_key is None

    @pytest.mark.asyncio
    async def test_initialize_and_shutdown(self):
        provider = JinaReaderProvider()
        result = await provider.initialize()
        assert result is True
        assert provider._extract_client is not None
        await provider.shutdown()
        assert provider._extract_client is None

    @pytest.mark.asyncio
    async def test_health_check(self):
        provider = JinaReaderProvider()
        await provider.initialize()
        healthy, error = await provider.health_check()
        # Should succeed - r.jina.ai is free
        assert healthy is True
        await provider.shutdown()

    @pytest.mark.asyncio
    async def test_extract_works(self):
        provider = JinaReaderProvider()
        await provider.initialize()
        result = await provider.extract(ExtractRequest(urls=["https://example.com"]))
        assert len(result.results) == 1
        assert result.results[0].url == "https://example.com"
        assert "Example Domain" in result.results[0].content
        await provider.shutdown()


class TestFirecrawlProvider:

    def test_attributes(self):
        provider = FirecrawlProvider(api_key="test-key")
        assert provider.name == "firecrawl"
        assert "search" in provider.capabilities
        assert "extract" in provider.capabilities

    @pytest.mark.asyncio
    async def test_initialize_without_key_fails(self):
        provider = FirecrawlProvider(api_key="")
        result = await provider.initialize()
        assert result is False

    @pytest.mark.asyncio
    async def test_initialize_with_key(self):
        provider = FirecrawlProvider(api_key="test-key")
        result = await provider.initialize()
        assert result is True
        await provider.shutdown()

    @pytest.mark.asyncio
    async def test_health_check_no_key(self):
        provider = FirecrawlProvider(api_key="")
        await provider.initialize()
        healthy, error = await provider.health_check()
        assert healthy is False
        assert "No API key" in error


class TestYouComProvider:

    def test_attributes(self):
        provider = YouComProvider(api_key="test-key")
        assert provider.name == "youcom"
        assert "search" in provider.capabilities
        assert provider.priority == 5  # High priority due to accuracy

    def test_priority_high(self):
        """You.com has high priority due to accuracy."""
        provider = YouComProvider(api_key="test")
        assert provider.priority < 10  # Lower number = higher priority

    @pytest.mark.asyncio
    async def test_initialize_without_key_fails(self):
        provider = YouComProvider(api_key="")
        result = await provider.initialize()
        assert result is False

    @pytest.mark.asyncio
    async def test_initialize_with_key(self):
        provider = YouComProvider(api_key="test-key")
        result = await provider.initialize()
        assert result is True
        await provider.shutdown()

    @pytest.mark.asyncio
    async def test_health_check_no_key(self):
        provider = YouComProvider(api_key="")
        await provider.initialize()
        healthy, error = await provider.health_check()
        assert healthy is False
        assert "No API key" in error
