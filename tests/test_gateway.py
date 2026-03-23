"""Tests for Gateway with v3.0 architecture (executor-based)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sg.server.gateway import Gateway
from sg.core.executor import Executor
from sg.providers.registry import ProviderRegistry
from sg.models.config import GatewayConfig, ExecutorConfig, Strategy
from sg.models.search import SearchResponse, SearchResult


class TestGatewayInit:

    def test_gateway_creates_executor(self, tmp_path):
        """Gateway creates an Executor (not router + load_balancer)."""
        config_file = tmp_path / "config.json"
        config_file.write_text('{"version": "3.0"}')

        gw = Gateway(config_path=str(config_file), port=19000)
        assert hasattr(gw, "executor")
        assert isinstance(gw.executor, Executor)
        assert not hasattr(gw, "router")
        assert not hasattr(gw, "load_balancer")

    def test_gateway_uses_executor_config(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text('{"version": "3.0", "executor": {"strategy": "random"}}')

        gw = Gateway(config_path=str(config_file), port=19001)
        assert gw.config.executor.strategy == Strategy.RANDOM

    def test_gateway_port_override(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text('{"version": "3.0", "server": {"port": 9000}}')

        gw = Gateway(config_path=str(config_file), port=19002)
        assert gw.port == 19002


class TestGatewaySearch:

    @pytest.mark.asyncio
    async def test_search_delegates_to_executor(self, tmp_path):
        """search() calls executor.execute() with 'search' capability."""
        config_file = tmp_path / "config.json"
        config_file.write_text('{"version": "3.0"}')

        gw = Gateway(config_path=str(config_file), port=19010)

        expected_response = SearchResponse(
            query="test", provider="mock", results=[], total=0, latency_ms=10.0,
        )
        gw.executor = MagicMock(spec=Executor)
        gw.executor.execute = AsyncMock(return_value=expected_response)
        gw.history = MagicMock()
        gw.history.record = AsyncMock()

        result = await gw.search("test", max_results=5)

        assert result.provider == "mock"
        gw.executor.execute.assert_called_once()
        call_args = gw.executor.execute.call_args
        assert call_args[0][0] == "search"  # capability
        assert call_args[1].get("provider") is None

    @pytest.mark.asyncio
    async def test_search_with_provider_override(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text('{"version": "3.0"}')

        gw = Gateway(config_path=str(config_file), port=19011)

        expected_response = SearchResponse(
            query="test", provider="tavily-main", results=[], total=0, latency_ms=10.0,
        )
        gw.executor = MagicMock(spec=Executor)
        gw.executor.execute = AsyncMock(return_value=expected_response)
        gw.history = MagicMock()
        gw.history.record = AsyncMock()

        result = await gw.search("test", provider="tavily-main")

        call_args = gw.executor.execute.call_args
        assert call_args[1].get("provider") == "tavily-main"

    @pytest.mark.asyncio
    async def test_search_records_history(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text('{"version": "3.0"}')

        gw = Gateway(config_path=str(config_file), port=19012)

        response = SearchResponse(
            query="test", provider="mock", results=[], total=0, latency_ms=10.0,
        )
        gw.executor = MagicMock(spec=Executor)
        gw.executor.execute = AsyncMock(return_value=response)
        gw.history = MagicMock()
        gw.history.record = AsyncMock()

        await gw.search("test")
        gw.history.record.assert_called_once()


class TestGatewayExtract:

    @pytest.mark.asyncio
    async def test_extract_delegates_to_executor(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text('{"version": "3.0"}')

        gw = Gateway(config_path=str(config_file), port=19020)
        gw.executor = MagicMock(spec=Executor)
        gw.executor.execute = AsyncMock(return_value="extract_result")

        result = await gw.extract(["https://example.com"])

        gw.executor.execute.assert_called_once()
        call_args = gw.executor.execute.call_args
        assert call_args[0][0] == "extract"


class TestGatewayResearch:

    @pytest.mark.asyncio
    async def test_research_delegates_to_executor(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text('{"version": "3.0"}')

        gw = Gateway(config_path=str(config_file), port=19030)
        gw.executor = MagicMock(spec=Executor)
        gw.executor.execute = AsyncMock(return_value="research_result")

        result = await gw.research("AI trends")

        gw.executor.execute.assert_called_once()
        call_args = gw.executor.execute.call_args
        assert call_args[0][0] == "research"


class TestGatewayStatus:

    @pytest.mark.asyncio
    async def test_get_status(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text('{"version": "3.0", "executor": {"strategy": "failover"}}')

        gw = Gateway(config_path=str(config_file), port=19040)
        gw._running = True
        gw.executor = MagicMock(spec=Executor)
        gw.executor.get_metrics.return_value = {}

        status = await gw.get_status()

        assert status["running"] is True
        assert status["port"] == 19040
        assert status["strategy"] == "failover"
        assert "providers" in status
        assert "metrics" in status

    @pytest.mark.asyncio
    async def test_health_check_delegates_to_executor(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text('{"version": "3.0"}')

        gw = Gateway(config_path=str(config_file), port=19041)
        gw.executor = MagicMock(spec=Executor)
        gw.executor.run_health_checks = AsyncMock(return_value={
            "healthy": ["duckduckgo"],
            "unhealthy": [],
        })

        result = await gw.health_check()

        assert "duckduckgo" in result["healthy"]
        gw.executor.run_health_checks.assert_called_once()


class TestGatewayConfig:

    @pytest.mark.asyncio
    async def test_reload_config(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text('{"version": "3.0"}')

        gw = Gateway(config_path=str(config_file), port=19050)

        # Mock provider lifecycle
        gw.providers = MagicMock(spec=ProviderRegistry)
        gw.providers.shutdown = AsyncMock()
        gw.providers.all.return_value = {}

        with patch.object(ProviderRegistry, "initialize", new_callable=AsyncMock):
            await gw.reload_config()

        # After reload, executor should be a fresh Executor instance
        assert isinstance(gw.executor, Executor)
