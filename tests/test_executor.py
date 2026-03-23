"""Tests for Executor."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sg.core.executor import Executor, ProviderMetrics
from sg.core.circuit_breaker import CircuitBreaker
from sg.models.config import (
    ExecutorConfig, Strategy, HealthCheckConfig,
    CircuitBreakerConfig, FailoverConfig,
)
from sg.providers.base import BaseProvider, ProviderInfo, SearchProvider
from sg.providers.registry import ProviderRegistry
from sg.models.search import SearchRequest, SearchResponse


class FakeProvider(SearchProvider):
    """Minimal test provider."""

    info = ProviderInfo(
        type="fake",
        display_name="Fake",
        needs_api_key=False,
        free=True,
        capabilities=("search",),
    )

    def __init__(self, name="fake", *, should_fail=False, priority=10, **kwargs):
        super().__init__(name=name, priority=priority, **kwargs)
        self.should_fail = should_fail

    async def initialize(self) -> bool:
        return True

    async def shutdown(self) -> None:
        pass

    async def search(self, request):
        self.validate_search_request(request)
        if self.should_fail:
            raise RuntimeError(f"{self.name} failed")
        return SearchResponse(
            query=request.query, provider=self.name,
            results=[], total=0, latency_ms=10.0,
        )


class DomainAwareProvider(FakeProvider):
    info = ProviderInfo(
        type="domain-aware",
        display_name="DomainAware",
        needs_api_key=False,
        free=True,
        capabilities=("search",),
        search_features=("include_domains",),
    )


def _make_registry(*providers, fallback_name=None):
    """Build a mock ProviderRegistry with given providers."""
    registry = MagicMock(spec=ProviderRegistry)
    by_name = {p.name: p for p in providers}
    registry.get.side_effect = lambda n: by_name.get(n)
    registry.all.return_value = by_name

    # get_by_capability returns all non-fallback providers sorted by priority
    def get_by_cap(cap):
        return sorted(
            [p for p in providers if cap in p.capabilities and p.name != fallback_name],
            key=lambda p: p.priority,
        )
    registry.get_by_capability.side_effect = get_by_cap

    if fallback_name and fallback_name in by_name:
        registry.get_fallback.return_value = by_name[fallback_name]
    else:
        registry.get_fallback.return_value = None

    return registry


def _make_config(**overrides):
    defaults = {
        "strategy": Strategy.ROUND_ROBIN,
        "health_check": HealthCheckConfig(failure_threshold=3, success_threshold=2),
        "circuit_breaker": CircuitBreakerConfig(base_timeout=60),
        "failover": FailoverConfig(max_attempts=3),
    }
    defaults.update(overrides)
    return ExecutorConfig(**defaults)


class TestExecuteBasic:

    @pytest.mark.asyncio
    async def test_execute_returns_result_from_first_provider(self):
        p1 = FakeProvider(name="primary", priority=1)
        p2 = FakeProvider(name="secondary", priority=5)
        registry = _make_registry(p1, p2)
        executor = Executor(_make_config(), registry)

        async def op(p):
            return await p.search(SearchRequest(query="test"))

        result = await executor.execute("search", op)
        assert result.provider == "primary"

    @pytest.mark.asyncio
    async def test_execute_failover_on_error(self):
        p1 = FakeProvider(name="bad", priority=1, should_fail=True)
        p2 = FakeProvider(name="good", priority=5)
        registry = _make_registry(p1, p2)
        executor = Executor(_make_config(), registry)

        async def op(p):
            return await p.search(SearchRequest(query="test"))

        result = await executor.execute("search", op)
        assert result.provider == "good"

    @pytest.mark.asyncio
    async def test_execute_with_explicit_provider(self):
        p1 = FakeProvider(name="primary", priority=1)
        p2 = FakeProvider(name="secondary", priority=5)
        registry = _make_registry(p1, p2)
        executor = Executor(_make_config(), registry)

        async def op(p):
            return await p.search(SearchRequest(query="test"))

        result = await executor.execute("search", op, provider="secondary")
        assert result.provider == "secondary"

    @pytest.mark.asyncio
    async def test_execute_raises_when_all_fail(self):
        p1 = FakeProvider(name="bad1", priority=1, should_fail=True)
        p2 = FakeProvider(name="bad2", priority=5, should_fail=True)
        registry = _make_registry(p1, p2)
        executor = Executor(_make_config(), registry)

        async def op(p):
            return await p.search(SearchRequest(query="test"))

        with pytest.raises(RuntimeError, match="All providers failed"):
            await executor.execute("search", op)

    @pytest.mark.asyncio
    async def test_execute_raises_when_no_candidates(self):
        registry = _make_registry()  # no providers
        executor = Executor(_make_config(), registry)

        async def op(p):
            return "unused"

        with pytest.raises(RuntimeError, match="No providers available"):
            await executor.execute("search", op)


class TestExecuteFallback:

    @pytest.mark.asyncio
    async def test_fallback_used_when_main_providers_fail(self):
        main = FakeProvider(name="main", priority=1, should_fail=True)
        fb = FakeProvider(name="duckduckgo", priority=100)
        registry = _make_registry(main, fb, fallback_name="duckduckgo")
        executor = Executor(_make_config(failover=FailoverConfig(max_attempts=1)), registry)

        async def op(p):
            return await p.search(SearchRequest(query="test"))

        result = await executor.execute("search", op)
        assert result.provider == "duckduckgo"

    @pytest.mark.asyncio
    async def test_fallback_not_duplicated_in_candidates(self):
        """If fallback is already in the candidate list, it should not be appended again."""
        fb = FakeProvider(name="duckduckgo", priority=100)
        registry = _make_registry(fb, fallback_name="duckduckgo")

        # get_by_capability returns empty (fallback excluded), but fallback appended
        executor = Executor(_make_config(), registry)
        candidates = executor._candidates("search")
        assert candidates.count("duckduckgo") == 1


class TestExecuteStrategy:

    def test_round_robin_rotates_start_provider(self):
        providers = [
            FakeProvider(name="p1", priority=1),
            FakeProvider(name="p2", priority=2),
            FakeProvider(name="p3", priority=3),
        ]
        registry = _make_registry(*providers)
        executor = Executor(_make_config(strategy=Strategy.ROUND_ROBIN), registry)

        assert executor._candidates("search") == ["p1", "p2", "p3"]
        assert executor._candidates("search") == ["p2", "p3", "p1"]
        assert executor._candidates("search") == ["p3", "p1", "p2"]

    @pytest.mark.asyncio
    async def test_random_strategy_shuffles(self):
        providers = [FakeProvider(name=f"p{i}", priority=10) for i in range(5)]
        registry = _make_registry(*providers)
        config = _make_config(strategy=Strategy.RANDOM)
        executor = Executor(config, registry)

        # Run multiple times and check we get different orderings
        orderings = set()
        for _ in range(20):
            candidates = executor._candidates("search")
            orderings.add(tuple(candidates))

        # With 5 providers and 20 attempts, we should see more than 1 ordering
        assert len(orderings) > 1


class TestExecuteCircuitBreaker:

    @pytest.mark.asyncio
    async def test_circuit_breaker_skips_open_providers(self):
        p1 = FakeProvider(name="broken", priority=1)
        p2 = FakeProvider(name="working", priority=5)
        registry = _make_registry(p1, p2)
        executor = Executor(_make_config(), registry)

        # Manually open the breaker for p1
        breaker = executor._breaker("broken")
        for _ in range(3):
            breaker.record_failure()
        assert breaker.state == CircuitBreaker.OPEN

        async def op(p):
            return await p.search(SearchRequest(query="test"))

        result = await executor.execute("search", op)
        assert result.provider == "working"

    @pytest.mark.asyncio
    async def test_failure_records_on_breaker(self):
        p1 = FakeProvider(name="flaky", priority=1, should_fail=True)
        p2 = FakeProvider(name="stable", priority=5)
        registry = _make_registry(p1, p2)
        executor = Executor(_make_config(), registry)

        async def op(p):
            return await p.search(SearchRequest(query="test"))

        await executor.execute("search", op)
        assert executor._breaker("flaky")._failure_count == 1

    @pytest.mark.asyncio
    async def test_success_records_on_breaker(self):
        p1 = FakeProvider(name="ok", priority=1)
        registry = _make_registry(p1)
        executor = Executor(_make_config(), registry)

        async def op(p):
            return await p.search(SearchRequest(query="test"))

        await executor.execute("search", op)
        # Success resets failure count to 0
        assert executor._breaker("ok")._failure_count == 0

    @pytest.mark.asyncio
    async def test_fallback_attempt_updates_metrics_when_outside_max_attempts(self):
        p1 = FakeProvider(name="bad1", priority=1, should_fail=True)
        p2 = FakeProvider(name="bad2", priority=2, should_fail=True)
        fb = FakeProvider(name="duckduckgo", priority=100, should_fail=True)
        registry = _make_registry(p1, p2, fb, fallback_name="duckduckgo")
        executor = Executor(_make_config(failover=FailoverConfig(max_attempts=2)), registry)

        async def op(p):
            return await p.search(SearchRequest(query="test"))

        with pytest.raises(RuntimeError, match="All providers failed"):
            await executor.execute("search", op)

        metrics = executor.get_metrics()
        assert metrics["duckduckgo"]["failures"] == 1

    @pytest.mark.asyncio
    async def test_unsupported_search_params_fail_over_to_supported_provider(self):
        p1 = FakeProvider(name="plain", priority=1)
        p2 = DomainAwareProvider(name="domain", priority=5)
        registry = _make_registry(p1, p2)
        executor = Executor(_make_config(strategy=Strategy.FAILOVER), registry)
        request = SearchRequest(query="test", include_domains=["example.com"])

        async def op(p):
            return await p.search(request)

        result = await executor.execute("search", op)
        assert result.provider == "domain"

    @pytest.mark.asyncio
    async def test_explicit_provider_raises_on_unsupported_search_params(self):
        p1 = FakeProvider(name="plain", priority=1)
        registry = _make_registry(p1)
        executor = Executor(_make_config(), registry)
        request = SearchRequest(query="test", include_domains=["example.com"])

        async def op(p):
            return await p.search(request)

        with pytest.raises(RuntimeError, match="All providers failed"):
            await executor.execute("search", op, provider="plain")

    @pytest.mark.asyncio
    async def test_capability_mismatch_does_not_trip_breaker(self):
        p1 = FakeProvider(name="plain", priority=1)
        p2 = DomainAwareProvider(name="domain", priority=5)
        registry = _make_registry(p1, p2)
        executor = Executor(_make_config(strategy=Strategy.FAILOVER), registry)
        request = SearchRequest(query="test", include_domains=["example.com"])

        async def op(p):
            return await p.search(request)

        await executor.execute("search", op)
        assert executor._breaker("plain").state == CircuitBreaker.CLOSED
        assert executor.get_metrics()["plain"]["requests"] == 0
        assert executor.get_metrics()["plain"]["failures"] == 0


class TestExecuteMetrics:

    @pytest.mark.asyncio
    async def test_metrics_recorded_on_success(self):
        p = FakeProvider(name="prov")
        registry = _make_registry(p)
        executor = Executor(_make_config(), registry)

        async def op(p):
            return await p.search(SearchRequest(query="test"))

        await executor.execute("search", op)

        metrics = executor.get_metrics()
        assert "prov" in metrics
        assert metrics["prov"]["requests"] == 1
        assert metrics["prov"]["successes"] == 1
        assert metrics["prov"]["failures"] == 0
        assert metrics["prov"]["circuit_breaker"] == "closed"

    @pytest.mark.asyncio
    async def test_metrics_recorded_on_failure(self):
        p1 = FakeProvider(name="fail", priority=1, should_fail=True)
        p2 = FakeProvider(name="ok", priority=5)
        registry = _make_registry(p1, p2)
        executor = Executor(_make_config(), registry)

        async def op(p):
            return await p.search(SearchRequest(query="test"))

        await executor.execute("search", op)

        metrics = executor.get_metrics()
        assert metrics["fail"]["failures"] == 1
        assert metrics["ok"]["successes"] == 1

    def test_provider_metrics_avg_latency(self):
        m = ProviderMetrics(requests=2, successes=2, total_latency_ms=300.0)
        assert m.avg_latency_ms == 150.0

    def test_provider_metrics_success_rate(self):
        m = ProviderMetrics(requests=3, successes=2, failures=1)
        assert m.success_rate == pytest.approx(66.67, rel=0.01)

    def test_provider_metrics_zero_requests(self):
        m = ProviderMetrics()
        assert m.avg_latency_ms == 0
        assert m.success_rate == 100


class TestHealthChecks:

    @pytest.mark.asyncio
    async def test_run_health_checks(self):
        healthy_p = FakeProvider(name="healthy")
        unhealthy_p = FakeProvider(name="unhealthy")
        unhealthy_p.health_check = AsyncMock(return_value=(False, "down"))

        registry = _make_registry(healthy_p, unhealthy_p)
        executor = Executor(_make_config(), registry)

        # Open the breaker for healthy provider so we can verify reset
        executor._breaker("healthy").record_failure()
        executor._breaker("healthy").record_failure()
        executor._breaker("healthy").record_failure()
        assert executor._breaker("healthy").state == CircuitBreaker.OPEN

        result = await executor.run_health_checks()

        assert "healthy" in result["healthy"]
        assert any(u["name"] == "unhealthy" for u in result["unhealthy"])
        # Breaker should be reset for the healthy provider
        assert executor._breaker("healthy").state == CircuitBreaker.CLOSED

    def test_get_breaker_state(self):
        registry = _make_registry()
        executor = Executor(_make_config(), registry)
        assert executor.get_breaker_state("new-provider") == CircuitBreaker.CLOSED
