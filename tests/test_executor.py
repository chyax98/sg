"""Tests for Executor."""

from collections import defaultdict
from unittest.mock import AsyncMock, MagicMock

import pytest

from sg.core.circuit_breaker import CircuitBreaker
from sg.core.executor import Executor, ProviderMetrics
from sg.models.config import (
    CircuitBreakerConfig,
    ExecutorConfig,
    FailoverConfig,
    HealthCheckConfig,
)
from sg.models.search import SearchRequest, SearchResponse
from sg.providers.base import ProviderInfo, SearchProvider
from sg.providers.registry import ProviderRegistry


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
            query=request.query,
            provider=self.name,
            results=[],
            total=0,
            latency_ms=10.0,
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


def _make_registry(group_map: dict[str, list[SearchProvider]], fallback_group: str | None = None):
    """Build a mock ProviderRegistry with provider groups and instances."""
    registry = MagicMock(spec=ProviderRegistry)
    by_name = {
        provider.name: provider
        for providers in group_map.values()
        for provider in providers
    }
    instance_to_group = {
        provider.name: group_name
        for group_name, providers in group_map.items()
        for provider in providers
    }

    registry.get.side_effect = lambda name: by_name.get(name)
    registry.all.return_value = by_name
    registry.group_for_instance.side_effect = lambda name: instance_to_group.get(name)
    registry.has_group.side_effect = lambda name: name in group_map
    registry.get_fallback_group.return_value = fallback_group

    def get_group_order(capability):
        groups = []
        for group_name, providers in group_map.items():
            if group_name == fallback_group:
                continue
            if any(capability in provider.capabilities for provider in providers):
                groups.append(group_name)
        return groups

    registry.get_group_order.side_effect = get_group_order

    def select_instance(group_name, capability, excluded_instances=None, allow_request=None):
        for provider in group_map.get(group_name, []):
            if capability not in provider.capabilities:
                continue
            if excluded_instances and provider.name in excluded_instances:
                continue
            if allow_request and not allow_request(provider.name):
                continue
            return provider
        return None

    registry.select_instance.side_effect = select_instance
    return registry


def _make_config(**overrides):
    defaults = {
        "health_check": HealthCheckConfig(failure_threshold=3, success_threshold=2),
        "circuit_breaker": CircuitBreakerConfig(base_timeout=60),
        "failover": FailoverConfig(max_attempts=3),
    }
    defaults.update(overrides)
    return ExecutorConfig(**defaults)


class TestExecuteBasic:
    @pytest.mark.asyncio
    async def test_execute_returns_result_from_first_group(self):
        registry = _make_registry(
            {
                "primary": [FakeProvider(name="primary-1", priority=1)],
                "secondary": [FakeProvider(name="secondary-1", priority=5)],
            }
        )
        executor = Executor(_make_config(), registry)

        async def op(provider):
            return await provider.search(SearchRequest(query="test"))

        result = await executor.execute("search", op)
        assert result.provider == "primary-1"

    @pytest.mark.asyncio
    async def test_execute_failover_on_error(self):
        registry = _make_registry(
            {
                "primary": [FakeProvider(name="primary-1", should_fail=True)],
                "secondary": [FakeProvider(name="secondary-1")],
            }
        )
        executor = Executor(_make_config(), registry)

        async def op(provider):
            return await provider.search(SearchRequest(query="test"))

        result = await executor.execute("search", op)
        assert result.provider == "secondary-1"

    @pytest.mark.asyncio
    async def test_execute_retries_other_instance_in_same_group(self):
        registry = _make_registry(
            {
                "exa": [
                    FakeProvider(name="exa-1", should_fail=True),
                    FakeProvider(name="exa-2"),
                ],
                "brave": [FakeProvider(name="brave-1")],
            }
        )
        executor = Executor(_make_config(), registry)

        async def op(provider):
            return await provider.search(SearchRequest(query="test"))

        result = await executor.execute("search", op, provider="exa")
        assert result.provider == "exa-2"

    @pytest.mark.asyncio
    async def test_execute_with_explicit_group(self):
        registry = _make_registry(
            {
                "primary": [FakeProvider(name="primary-1")],
                "secondary": [FakeProvider(name="secondary-1")],
            }
        )
        executor = Executor(_make_config(), registry)

        async def op(provider):
            return await provider.search(SearchRequest(query="test"))

        result = await executor.execute("search", op, provider="secondary")
        assert result.provider == "secondary-1"

    @pytest.mark.asyncio
    async def test_execute_with_explicit_instance(self):
        registry = _make_registry(
            {
                "primary": [FakeProvider(name="primary-1")],
                "secondary": [
                    FakeProvider(name="secondary-1"),
                    FakeProvider(name="secondary-2"),
                ],
            }
        )
        executor = Executor(_make_config(), registry)

        async def op(provider):
            return await provider.search(SearchRequest(query="test"))

        result = await executor.execute("search", op, provider="secondary-2")
        assert result.provider == "secondary-2"

    @pytest.mark.asyncio
    async def test_execute_raises_when_all_fail(self):
        registry = _make_registry(
            {
                "primary": [FakeProvider(name="primary-1", should_fail=True)],
                "secondary": [FakeProvider(name="secondary-1", should_fail=True)],
            }
        )
        executor = Executor(_make_config(), registry)

        async def op(provider):
            return await provider.search(SearchRequest(query="test"))

        with pytest.raises(RuntimeError, match="All providers failed"):
            await executor.execute("search", op)

    @pytest.mark.asyncio
    async def test_execute_raises_when_no_candidates(self):
        registry = _make_registry({})
        executor = Executor(_make_config(), registry)

        async def op(provider):
            return "unused"

        with pytest.raises(RuntimeError, match="No providers available"):
            await executor.execute("search", op)


class TestExecuteFallback:
    @pytest.mark.asyncio
    async def test_fallback_used_when_main_groups_fail(self):
        registry = _make_registry(
            {
                "main": [FakeProvider(name="main-1", should_fail=True)],
                "duckduckgo": [FakeProvider(name="duckduckgo")],
            },
            fallback_group="duckduckgo",
        )
        executor = Executor(_make_config(failover=FailoverConfig(max_attempts=1)), registry)

        async def op(provider):
            return await provider.search(SearchRequest(query="test"))

        result = await executor.execute("search", op)
        assert result.provider == "duckduckgo"

    def test_fallback_not_duplicated_in_candidate_groups(self):
        registry = _make_registry(
            {"duckduckgo": [FakeProvider(name="duckduckgo")]},
            fallback_group="duckduckgo",
        )
        executor = Executor(_make_config(), registry)

        candidates = executor._candidate_groups("search")
        assert candidates == ["duckduckgo"]


class TestExecuteStrategy:
    def test_groups_always_ordered_by_priority(self):
        """Group selection is always by priority, strategy only affects instance selection."""
        registry = _make_registry(
            {
                "p1": [FakeProvider(name="p1-1")],
                "p2": [FakeProvider(name="p2-1")],
                "p3": [FakeProvider(name="p3-1")],
            }
        )
        # Groups are always ordered by priority
        executor = Executor(_make_config(), registry)

        # Groups are always returned in priority order (from get_group_order mock)
        assert executor._candidate_groups("search") == ["p1", "p2", "p3"]
        assert executor._candidate_groups("search") == ["p1", "p2", "p3"]
        assert executor._candidate_groups("search") == ["p1", "p2", "p3"]

    def test_random_strategy_does_not_shuffle_groups(self):
        """Strategy no longer affects group ordering, only instance selection."""
        registry = _make_registry(
            {
                "p1": [FakeProvider(name="p1-1")],
                "p2": [FakeProvider(name="p2-1")],
                "p3": [FakeProvider(name="p3-1")],
                "p4": [FakeProvider(name="p4-1")],
            }
        )
        executor = Executor(_make_config(), registry)

        # Groups are always returned in priority order, regardless of strategy
        orderings = {tuple(executor._candidate_groups("search")) for _ in range(20)}
        assert len(orderings) == 1
        assert list(orderings)[0] == ("p1", "p2", "p3", "p4")


class TestExecuteCircuitBreaker:
    @pytest.mark.asyncio
    async def test_circuit_breaker_skips_open_instances(self):
        registry = _make_registry(
            {
                "exa": [
                    FakeProvider(name="exa-1"),
                    FakeProvider(name="exa-2"),
                ],
                "brave": [FakeProvider(name="brave-1")],
            }
        )
        executor = Executor(_make_config(), registry)

        breaker = executor._breaker("exa-1")
        for _ in range(3):
            breaker.record_failure()
        assert breaker.state == CircuitBreaker.OPEN

        async def op(provider):
            return await provider.search(SearchRequest(query="test"))

        result = await executor.execute("search", op, provider="exa")
        assert result.provider == "exa-2"

    @pytest.mark.asyncio
    async def test_failure_records_on_breaker(self):
        registry = _make_registry(
            {
                "exa": [FakeProvider(name="exa-1", should_fail=True)],
                "brave": [FakeProvider(name="brave-1")],
            }
        )
        executor = Executor(_make_config(), registry)

        async def op(provider):
            return await provider.search(SearchRequest(query="test"))

        await executor.execute("search", op)
        assert executor._breaker("exa-1")._failure_count == 1

    @pytest.mark.asyncio
    async def test_success_records_on_breaker(self):
        registry = _make_registry({"exa": [FakeProvider(name="exa-1")]})
        executor = Executor(_make_config(), registry)

        async def op(provider):
            return await provider.search(SearchRequest(query="test"))

        await executor.execute("search", op)
        assert executor._breaker("exa-1")._failure_count == 0

    @pytest.mark.asyncio
    async def test_fallback_attempt_updates_metrics_when_outside_max_attempts(self):
        registry = _make_registry(
            {
                "exa": [FakeProvider(name="exa-1", should_fail=True)],
                "brave": [FakeProvider(name="brave-1", should_fail=True)],
                "duckduckgo": [FakeProvider(name="duckduckgo", should_fail=True)],
            },
            fallback_group="duckduckgo",
        )
        executor = Executor(_make_config(failover=FailoverConfig(max_attempts=2)), registry)

        async def op(provider):
            return await provider.search(SearchRequest(query="test"))

        with pytest.raises(RuntimeError, match="All providers failed"):
            await executor.execute("search", op)

        metrics = executor.get_metrics()
        assert metrics["duckduckgo"]["failures"] == 1

    @pytest.mark.asyncio
    async def test_unsupported_search_params_fail_over_to_supported_provider(self):
        registry = _make_registry(
            {
                "plain": [FakeProvider(name="plain-1")],
                "domain": [DomainAwareProvider(name="domain-1")],
            }
        )
        executor = Executor(_make_config(), registry)
        request = SearchRequest(query="test", include_domains=["example.com"])

        async def op(provider):
            return await provider.search(request)

        result = await executor.execute("search", op)
        assert result.provider == "domain-1"

    @pytest.mark.asyncio
    async def test_explicit_provider_raises_on_unsupported_search_params(self):
        registry = _make_registry({"plain": [FakeProvider(name="plain-1")]})
        executor = Executor(_make_config(), registry)
        request = SearchRequest(query="test", include_domains=["example.com"])

        async def op(provider):
            return await provider.search(request)

        with pytest.raises(RuntimeError, match="All providers failed"):
            await executor.execute("search", op, provider="plain")

    @pytest.mark.asyncio
    async def test_capability_mismatch_does_not_trip_breaker(self):
        registry = _make_registry(
            {
                "plain": [FakeProvider(name="plain-1")],
                "domain": [DomainAwareProvider(name="domain-1")],
            }
        )
        executor = Executor(_make_config(), registry)
        request = SearchRequest(query="test", include_domains=["example.com"])

        async def op(provider):
            return await provider.search(request)

        await executor.execute("search", op)
        assert executor._breaker("plain-1").state == CircuitBreaker.CLOSED
        assert executor.get_metrics()["plain-1"]["requests"] == 0
        assert executor.get_metrics()["plain-1"]["failures"] == 0


class TestExecuteMetrics:
    @pytest.mark.asyncio
    async def test_metrics_recorded_on_success(self):
        registry = _make_registry({"exa": [FakeProvider(name="exa-1")]})
        executor = Executor(_make_config(), registry)

        async def op(provider):
            return await provider.search(SearchRequest(query="test"))

        await executor.execute("search", op)

        metrics = executor.get_metrics()
        assert "exa-1" in metrics
        assert metrics["exa-1"]["requests"] == 1
        assert metrics["exa-1"]["successes"] == 1
        assert metrics["exa-1"]["failures"] == 0
        assert metrics["exa-1"]["circuit_breaker"] == "closed"

    @pytest.mark.asyncio
    async def test_metrics_recorded_on_failure(self):
        registry = _make_registry(
            {
                "exa": [FakeProvider(name="exa-1", should_fail=True)],
                "brave": [FakeProvider(name="brave-1")],
            }
        )
        executor = Executor(_make_config(), registry)

        async def op(provider):
            return await provider.search(SearchRequest(query="test"))

        await executor.execute("search", op)

        metrics = executor.get_metrics()
        assert metrics["exa-1"]["failures"] == 1
        assert metrics["brave-1"]["successes"] == 1

    def test_provider_metrics_avg_latency(self):
        metrics = ProviderMetrics(requests=2, successes=2, total_latency_ms=300.0)
        assert metrics.avg_latency_ms == 150.0

    def test_provider_metrics_success_rate(self):
        metrics = ProviderMetrics(requests=3, successes=2, failures=1)
        assert metrics.success_rate == pytest.approx(66.67, rel=0.01)

    def test_provider_metrics_zero_requests(self):
        metrics = ProviderMetrics()
        assert metrics.avg_latency_ms == 0
        assert metrics.success_rate == 100


class TestHealthChecks:
    @pytest.mark.asyncio
    async def test_run_health_checks(self):
        healthy_provider = FakeProvider(name="healthy-1")
        unhealthy_provider = FakeProvider(name="unhealthy-1")
        unhealthy_provider.health_check = AsyncMock(return_value=(False, "down"))

        registry = _make_registry(
            {
                "healthy": [healthy_provider],
                "unhealthy": [unhealthy_provider],
            }
        )
        executor = Executor(_make_config(), registry)

        for _ in range(3):
            executor._breaker("healthy-1").record_failure()
        assert executor._breaker("healthy-1").state == CircuitBreaker.OPEN

        result = await executor.run_health_checks()

        assert "healthy-1" in result["healthy"]
        assert any(item["name"] == "unhealthy-1" for item in result["unhealthy"])
        assert executor._breaker("healthy-1").state == CircuitBreaker.CLOSED

    def test_get_breaker_state(self):
        registry = _make_registry({})
        executor = Executor(_make_config(), registry)
        assert executor.get_breaker_state("new-provider") == CircuitBreaker.CLOSED
