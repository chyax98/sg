"""Tests for LoadBalancer."""

import pytest
from unittest.mock import MagicMock

from sg.core.load_balancer import LoadBalancer
from sg.models.config import LoadBalancerConfig, FailoverConfig, HealthCheckConfig, LSStrategy
from sg.providers.base import SearchProvider
from sg.models.search import SearchRequest, SearchResponse


class MockProvider(SearchProvider):

    def __init__(self, name: str, healthy: bool = True, priority: int = 10):
        super().__init__()
        self._name = name
        self.healthy = healthy
        self.priority = priority

    @property
    def name(self):
        return self._name

    async def initialize(self):
        return True

    async def shutdown(self):
        pass

    async def health_check(self):
        return (self.healthy, None)

    async def search(self, request: SearchRequest) -> SearchResponse:
        if not self.healthy:
            raise Exception(f"Provider {self.name} is unhealthy")
        return SearchResponse(
            query=request.query, provider=self.name,
            results=[], total=0, latency_ms=100.0,
        )


class TestLoadBalancer:

    @pytest.fixture
    def registry(self):
        registry = MagicMock()
        registry._healthy_providers = {"provider1", "provider2", "duckduckgo"}
        registry.get_fallback_provider = MagicMock(return_value=MockProvider("duckduckgo"))

        def mock_get(name):
            providers = {
                "provider1": MockProvider("provider1", priority=1),
                "provider2": MockProvider("provider2", priority=2),
                "duckduckgo": MockProvider("duckduckgo", priority=100),
            }
            return providers.get(name)

        registry.get = MagicMock(side_effect=mock_get)
        return registry

    @pytest.fixture
    def config(self):
        return LoadBalancerConfig(
            strategy=LSStrategy.FAILOVER,
            health_check=HealthCheckConfig(failure_threshold=3),
            failover=FailoverConfig(retry_count=2, retry_delay=100),
        )

    @pytest.mark.asyncio
    async def test_select_failover(self, registry, config):
        """Failover selects first provider (highest priority)."""
        lb = LoadBalancer(config, registry)
        provider = await lb.select(["provider1", "provider2"])
        assert provider.name == "provider1"

    @pytest.mark.asyncio
    async def test_select_random(self, registry, config):
        """Random selects from available providers."""
        config.strategy = LSStrategy.RANDOM
        lb = LoadBalancer(config, registry)
        provider = await lb.select(["provider1", "provider2"])
        assert provider.name in ["provider1", "provider2"]

    @pytest.mark.asyncio
    async def test_select_fallback_on_empty(self, registry, config):
        """Falls back to DuckDuckGo when no providers available."""
        lb = LoadBalancer(config, registry)
        provider = await lb.select([])
        assert provider.name == "duckduckgo"

    @pytest.mark.asyncio
    async def test_execute_with_failover_success(self, registry, config):
        """Successful execution without failover."""
        lb = LoadBalancer(config, registry)

        async def operation(provider):
            return await provider.search(SearchRequest(query="test"))

        result = await lb.execute_with_failover(["provider1", "provider2"], operation)
        assert result.provider == "provider1"

    @pytest.mark.asyncio
    async def test_execute_with_failover_retry(self, registry, config):
        """Failed provider triggers failover to next."""
        # Make provider1 fail
        def mock_get(name):
            if name == "provider1":
                p = MockProvider("provider1", healthy=False)
                return p
            elif name == "provider2":
                return MockProvider("provider2")
            elif name == "duckduckgo":
                return MockProvider("duckduckgo")
            return None
        registry.get = MagicMock(side_effect=mock_get)

        lb = LoadBalancer(config, registry)

        async def operation(provider):
            return await provider.search(SearchRequest(query="test"))

        result = await lb.execute_with_failover(["provider1", "provider2"], operation)
        # Should succeed with provider2 or duckduckgo
        assert result.provider in ["provider2", "duckduckgo"]

    def test_record_success(self, registry, config):
        lb = LoadBalancer(config, registry)
        lb.record_success("provider1", 100.0)
        lb.record_success("provider1", 200.0)

        metrics = lb.get_metrics()
        assert metrics["provider1"]["requests"] == 2
        assert metrics["provider1"]["successes"] == 2
        assert metrics["provider1"]["failures"] == 0

    def test_record_failure(self, registry, config):
        lb = LoadBalancer(config, registry)
        lb.record_failure("provider1")

        metrics = lb.get_metrics()
        assert metrics["provider1"]["failures"] == 1

    def test_get_metrics(self, registry, config):
        lb = LoadBalancer(config, registry)
        lb.record_success("provider1", 100.0)
        lb.record_success("provider1", 200.0)
        lb.record_failure("provider1")

        metrics = lb.get_metrics()
        assert metrics["provider1"]["avg_latency_ms"] == 150.0
        assert metrics["provider1"]["success_rate"] == pytest.approx(66.67, rel=0.01)
