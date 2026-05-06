"""Tests for providers (Jina, Firecrawl, You.com)."""

import pytest

from sg.models.search import ExtractRequest, SearchRequest
from sg.providers.firecrawl import FirecrawlProvider
from sg.providers.jina import JinaReaderProvider
from sg.providers.tinyfish import TinyFishProvider
from sg.providers.youcom import YouComProvider


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


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


class TestTinyFishProvider:
    def test_provider_info(self):
        assert TinyFishProvider.info.type == "tinyfish"
        assert TinyFishProvider.info.needs_api_key is True
        assert "search" in TinyFishProvider.info.capabilities
        assert "extract" in TinyFishProvider.info.capabilities
        assert "include_domains" in TinyFishProvider.info.search_features

    def test_init_with_new_signature(self):
        provider = TinyFishProvider(name="tinyfish-1", api_key="test-key", priority=5)
        assert provider.name == "tinyfish-1"
        assert provider.api_key == "test-key"
        assert provider.priority == 5

    @pytest.mark.asyncio
    async def test_initialize_without_key_fails(self):
        provider = TinyFishProvider(name="tinyfish")
        result = await provider.initialize()
        assert result is False

    @pytest.mark.asyncio
    async def test_initialize_with_key(self):
        provider = TinyFishProvider(name="tinyfish", api_key="test-key")
        result = await provider.initialize()
        assert result is True
        await provider.shutdown()

    @pytest.mark.asyncio
    async def test_health_check_not_initialized(self):
        provider = TinyFishProvider(name="tinyfish")
        healthy, error = await provider.health_check()
        assert healthy is False
        assert "Not initialized" in error

    @pytest.mark.asyncio
    async def test_search_maps_tinyfish_response(self):
        class FakeSearchClient:
            async def get(self, path, params):
                assert path == "/"
                assert params == {
                    "query": "python tutorial site:docs.python.org -site:youtube.com",
                    "language": "en",
                }
                return FakeResponse(
                    {
                        "query": "python tutorial",
                        "results": [
                            {
                                "position": 1,
                                "site_name": "docs.python.org",
                                "title": "Python Tutorial",
                                "snippet": "Start here",
                                "url": "https://docs.python.org/3/tutorial/",
                            }
                        ],
                        "total_results": 1,
                    }
                )

        provider = TinyFishProvider(name="tinyfish", api_key="test-key")
        provider._search_client = FakeSearchClient()
        response = await provider.search(
            SearchRequest(
                query="python tutorial",
                include_domains=["docs.python.org"],
                exclude_domains=["youtube.com"],
                extra={"language": "en"},
            )
        )

        assert response.provider == "tinyfish"
        assert response.total == 1
        assert response.results[0].title == "Python Tutorial"
        assert response.results[0].extra["site_name"] == "docs.python.org"

    @pytest.mark.asyncio
    async def test_extract_maps_results_and_errors(self):
        class FakeFetchClient:
            async def post(self, path, json):
                assert path == "/"
                assert json == {
                    "urls": ["https://example.com"],
                    "format": "markdown",
                    "links": True,
                    "image_links": False,
                }
                return FakeResponse(
                    {
                        "results": [
                            {
                                "url": "https://example.com",
                                "title": "Example",
                                "text": "# Example",
                            }
                        ],
                        "errors": [{"url": "https://bad.example", "error": "timeout"}],
                    }
                )

        provider = TinyFishProvider(name="tinyfish", api_key="test-key")
        provider._fetch_client = FakeFetchClient()
        response = await provider.extract(
            ExtractRequest(urls=["https://example.com"], extra={"links": True})
        )

        assert response.provider == "tinyfish"
        assert response.results[0].content == "# Example"
        assert response.results[1].url == "https://bad.example"
        assert response.results[1].error == "timeout"
