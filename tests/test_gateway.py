"""Tests for Gateway."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sg.core.executor import Executor

from sg.models.search import (
    ExtractResponse,
    ExtractResult,
    ResearchResponse,
    SearchResponse,
)
from sg.providers.registry import ProviderRegistry
from sg.server.gateway import Gateway


class TestGatewayInit:
    def test_gateway_creates_executor(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("{}")

        gateway = Gateway(config_path=str(config_file), port=19000)
        assert isinstance(gateway.executor, Executor)
        assert not hasattr(gateway, "router")
        assert not hasattr(gateway, "load_balancer")

    def test_gateway_uses_executor_config(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("{}")

        gateway = Gateway(config_path=str(config_file), port=19001)
        assert gateway.config.executor.failover.max_attempts == 3

    def test_gateway_port_override(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text('{"server": {"port": 9000}}')

        gateway = Gateway(config_path=str(config_file), port=19002)
        assert gateway.port == 19002


class TestGatewaySearch:
    @pytest.mark.asyncio
    async def test_search_delegates_to_executor(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("{}")

        gateway = Gateway(config_path=str(config_file), port=19010)
        expected_response = SearchResponse(
            query="test",
            provider="mock",
            results=[],
            total=0,
            latency_ms=10.0,
        )
        gateway.executor = MagicMock(spec=Executor)
        gateway.executor.execute = AsyncMock(return_value=expected_response)
        gateway.history = MagicMock()
        gateway.history.record = AsyncMock()

        result = await gateway.search("test", max_results=5)

        assert result.provider == "mock"
        gateway.executor.execute.assert_called_once()
        call_args = gateway.executor.execute.call_args
        assert call_args[0][0] == "search"
        assert call_args[1].get("provider") is None

    @pytest.mark.asyncio
    async def test_search_with_provider_override(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("{}")

        gateway = Gateway(config_path=str(config_file), port=19011)
        gateway.executor = MagicMock(spec=Executor)
        gateway.executor.execute = AsyncMock(
            return_value=SearchResponse(
                query="test",
                provider="exa-1",
                results=[],
                total=0,
                latency_ms=10.0,
            )
        )
        gateway.history = MagicMock()
        gateway.history.record = AsyncMock()

        await gateway.search("test", provider="exa")

        call_args = gateway.executor.execute.call_args
        assert call_args[1].get("provider") == "exa"

    @pytest.mark.asyncio
    async def test_search_records_history(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("{}")

        gateway = Gateway(config_path=str(config_file), port=19012)
        gateway.executor = MagicMock(spec=Executor)
        gateway.executor.execute = AsyncMock(
            return_value=SearchResponse(
                query="test",
                provider="mock",
                results=[],
                total=0,
                latency_ms=10.0,
            )
        )
        gateway.history = MagicMock()
        gateway.history.record = AsyncMock()

        await gateway.search("test")
        gateway.history.record.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_batch_keeps_failed_queries(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("{}")

        gateway = Gateway(config_path=str(config_file), port=19013)

        async def fake_search(query, **kwargs):
            if query == "bad":
                raise RuntimeError("boom")
            return SearchResponse(
                query=query,
                provider="mock",
                results=[],
                total=0,
                latency_ms=10.0,
            )

        gateway.search = AsyncMock(side_effect=fake_search)

        results = await gateway.search_batch(["ok1", "bad", "ok2"])

        assert [result.query for result in results] == ["ok1", "bad", "ok2"]
        assert results[1].error == "boom"
        assert results[1].total == 0


class TestGatewayExtract:
    @pytest.mark.asyncio
    async def test_extract_delegates_to_executor(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("{}")

        gateway = Gateway(config_path=str(config_file), port=19020)
        mock_response = ExtractResponse(
            results=[
                ExtractResult(url="https://example.com", content="extracted", title="Example"),
            ],
            provider="exa",
            latency_ms=100.0,
        )
        gateway.executor = MagicMock(spec=Executor)
        gateway.executor.execute = AsyncMock(return_value=mock_response)
        gateway.executor.available_group_count = MagicMock(return_value=1)
        gateway.history = MagicMock()
        gateway.history.record_extract = AsyncMock(
            return_value=[
                {
                    "url": "https://example.com",
                    "title": "Example",
                    "file": "/tmp/x.txt",
                    "chars": 9,
                    "lines": 1,
                },
            ]
        )

        result = await gateway.extract(["https://example.com"])

        gateway.executor.execute.assert_called_once()
        assert gateway.executor.execute.call_args[0][0] == "extract"
        gateway.history.record_extract.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_stores_result_files_on_response(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("{}")

        gateway = Gateway(config_path=str(config_file), port=19021)
        mock_response = ExtractResponse(
            results=[
                ExtractResult(url="https://a.com", content="A content", title="A"),
            ],
            provider="jina",
            latency_ms=50.0,
        )
        expected_manifest = [
            {"url": "https://a.com", "title": "A", "file": "/tmp/a.txt", "chars": 9, "lines": 1},
        ]
        gateway.executor = MagicMock(spec=Executor)
        gateway.executor.execute = AsyncMock(return_value=mock_response)
        gateway.executor.available_group_count = MagicMock(return_value=1)
        gateway.history = MagicMock()
        gateway.history.record_extract = AsyncMock(return_value=expected_manifest)

        result = await gateway.extract(["https://a.com"])

        assert result.result_files == expected_manifest
        assert result.result_files[0]["url"] == "https://a.com"

    @pytest.mark.asyncio
    async def test_extract_normalizes_missing_results_to_requested_urls(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("{}")

        gateway = Gateway(config_path=str(config_file), port=19022)
        mock_response = ExtractResponse(
            results=[
                ExtractResult(url="https://b.com", content="B content", title="B"),
            ],
            provider="exa",
            latency_ms=100.0,
        )
        gateway.executor = MagicMock(spec=Executor)
        gateway.executor.execute = AsyncMock(return_value=mock_response)
        gateway.executor.available_group_count = MagicMock(return_value=1)
        gateway.history = MagicMock()
        gateway.history.record_extract = AsyncMock(return_value=[])

        result = await gateway.extract(["https://a.com", "https://b.com"])

        assert [item.url for item in result.results] == ["https://a.com", "https://b.com"]
        assert result.results[0].error == "provider returned no extract result"
        assert result.results[1].content == "B content"

    @pytest.mark.asyncio
    async def test_extract_normalizes_reordered_results(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("{}")

        gateway = Gateway(config_path=str(config_file), port=19023)
        mock_response = ExtractResponse(
            results=[
                ExtractResult(url="https://b.com", content="B content", title="B"),
                ExtractResult(url="https://a.com", content="A content", title="A"),
            ],
            provider="exa",
            latency_ms=100.0,
        )
        gateway.executor = MagicMock(spec=Executor)
        gateway.executor.execute = AsyncMock(return_value=mock_response)
        gateway.executor.available_group_count = MagicMock(return_value=1)
        gateway.history = MagicMock()
        gateway.history.record_extract = AsyncMock(return_value=[])

        result = await gateway.extract(["https://a.com", "https://b.com"])

        assert [item.url for item in result.results] == ["https://a.com", "https://b.com"]
        assert [item.content for item in result.results] == ["A content", "B content"]


class TestGatewayResearch:
    @pytest.mark.asyncio
    async def test_research_delegates_to_executor(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("{}")

        gateway = Gateway(config_path=str(config_file), port=19030)
        mock_response = ResearchResponse(
            topic="AI trends",
            content="Research content here",
            sources=["https://src.com"],
            provider="tavily",
            latency_ms=2000.0,
        )
        gateway.executor = MagicMock(spec=Executor)
        gateway.executor.execute = AsyncMock(return_value=mock_response)
        gateway.history = MagicMock()
        gateway.history.record_content = AsyncMock(return_value="/tmp/research.txt")

        result = await gateway.research("AI trends")

        gateway.executor.execute.assert_called_once()
        assert gateway.executor.execute.call_args[0][0] == "research"
        assert result.topic == "AI trends"


class TestGatewayStatus:
    @pytest.mark.asyncio
    async def test_get_status(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("{}")

        gateway = Gateway(config_path=str(config_file), port=19040)
        gateway._running = True
        gateway.executor = MagicMock(spec=Executor)
        gateway.executor.get_metrics.return_value = {}

        status = await gateway.get_status()

        assert status["running"] is True
        assert status["port"] == 19040
        assert status["strategy"] == "priority"
        assert "providers" in status
        assert "metrics" in status

    @pytest.mark.asyncio
    async def test_health_check_delegates_to_executor(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("{}")

        gateway = Gateway(config_path=str(config_file), port=19041)
        gateway.executor = MagicMock(spec=Executor)
        gateway.executor.run_health_checks = AsyncMock(
            return_value={"healthy": ["duckduckgo"], "unhealthy": []}
        )

        result = await gateway.health_check()

        assert "duckduckgo" in result["healthy"]
        gateway.executor.run_health_checks.assert_called_once()


class TestGatewayConfig:
    @pytest.mark.asyncio
    async def test_reload_config(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("{}")

        gateway = Gateway(config_path=str(config_file), port=19050)
        old_providers = MagicMock(spec=ProviderRegistry)
        old_providers.shutdown = AsyncMock()
        old_providers.all.return_value = {}
        gateway.providers = old_providers

        with patch.object(ProviderRegistry, "initialize", new_callable=AsyncMock):
            await gateway.reload_config()

        assert isinstance(gateway.executor, Executor)
        old_providers.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_reload_config_keeps_existing_state_when_new_config_invalid(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("{}")

        gateway = Gateway(config_path=str(config_file), port=19051)
        old_providers = MagicMock(spec=ProviderRegistry)
        old_providers.shutdown = AsyncMock()
        old_providers.all.return_value = {}
        gateway.providers = old_providers
        old_executor = gateway.executor
        old_history = gateway.history

        config_file.write_text('{"providers": {"bad": {"type": "tavily", "api_key": "x"}}}')

        with pytest.raises(Exception):
            await gateway.reload_config()

        assert gateway.providers is old_providers
        assert gateway.executor is old_executor
        assert gateway.history is old_history
        old_providers.shutdown.assert_not_called()

    @pytest.mark.asyncio
    async def test_reload_config_keeps_existing_state_when_new_init_fails(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("{}")

        gateway = Gateway(config_path=str(config_file), port=19052)
        old_providers = MagicMock(spec=ProviderRegistry)
        old_providers.shutdown = AsyncMock()
        old_providers.all.return_value = {}
        gateway.providers = old_providers
        old_executor = gateway.executor
        old_history = gateway.history

        new_providers = MagicMock(spec=ProviderRegistry)
        new_providers.initialize = AsyncMock(side_effect=RuntimeError("init failed"))
        new_providers.shutdown = AsyncMock()

        with patch("sg.server.gateway.ProviderRegistry", return_value=new_providers):
            with pytest.raises(RuntimeError, match="init failed"):
                await gateway.reload_config()

        assert gateway.providers is old_providers
        assert gateway.executor is old_executor
        assert gateway.history is old_history
        old_providers.shutdown.assert_not_called()
        new_providers.shutdown.assert_called_once()
