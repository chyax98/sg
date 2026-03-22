"""Load balancer - Distribute requests across providers."""

import asyncio
import logging
import random
import time
from typing import Any

from ..models.config import LoadBalancerConfig, LSStrategy
from ..providers.base import BaseProvider
from ..providers.registry import ProviderRegistry

logger = logging.getLogger(__name__)


class LoadBalancer:
    """Load balancer for search providers. Supports failover and random strategies."""

    def __init__(self, config: LoadBalancerConfig, registry: ProviderRegistry):
        self.config = config
        self.registry = registry
        self._metrics: dict[str, dict[str, Any]] = {}

    async def select(self, providers: list[str]) -> BaseProvider | None:
        """Select a provider based on strategy."""
        if not providers:
            return self.registry.get_fallback_provider()

        available = []
        for name in providers:
            provider = self.registry.get(name)
            if provider and provider.healthy:
                available.append(provider)

        if not available:
            return self.registry.get_fallback_provider()

        if self.config.strategy == LSStrategy.RANDOM:
            return random.choice(available)

        # Default: failover — use first (highest priority, already sorted)
        return available[0]

    def record_success(self, provider_name: str, latency_ms: float = 0):
        """Record successful request."""
        if provider_name not in self._metrics:
            self._metrics[provider_name] = {
                "requests": 0, "successes": 0, "failures": 0, "total_latency_ms": 0,
            }
        self._metrics[provider_name]["requests"] += 1
        self._metrics[provider_name]["successes"] += 1
        self._metrics[provider_name]["total_latency_ms"] += latency_ms

    def record_failure(self, provider_name: str):
        """Record failed request."""
        if provider_name not in self._metrics:
            self._metrics[provider_name] = {
                "requests": 0, "successes": 0, "failures": 0, "total_latency_ms": 0,
            }
        self._metrics[provider_name]["requests"] += 1
        self._metrics[provider_name]["failures"] += 1

    def get_metrics(self) -> dict[str, dict[str, Any]]:
        """Get metrics for all providers."""
        result = {}
        for name, metrics in self._metrics.items():
            avg_latency = (
                metrics["total_latency_ms"] / metrics["successes"]
                if metrics["successes"] > 0 else 0
            )
            success_rate = (
                metrics["successes"] / metrics["requests"] * 100
                if metrics["requests"] > 0 else 100
            )
            result[name] = {**metrics, "avg_latency_ms": avg_latency, "success_rate": success_rate}
        return result

    async def execute_with_failover(
        self, providers: list[str], operation: callable, **kwargs,
    ) -> Any:
        """Execute operation with automatic failover."""
        last_error = None
        attempted = set()

        for attempt in range(self.config.failover.retry_count + 1):
            available = [p for p in providers if p not in attempted]
            if not available:
                break

            provider = await self.select(available)
            if not provider:
                break

            attempted.add(provider.name)

            try:
                start = time.perf_counter()
                result = await operation(provider, **kwargs)
                latency = (time.perf_counter() - start) * 1000
                self.record_success(provider.name, latency)
                return result
            except Exception as e:
                logger.warning(f"Provider {provider.name} failed: {e}")
                self.record_failure(provider.name)
                last_error = e

                metrics = self._metrics.get(provider.name, {})
                if metrics.get("failures", 0) >= self.config.health_check.failure_threshold:
                    provider.healthy = False
                    self.registry._healthy_providers.discard(provider.name)

                if attempt < self.config.failover.retry_count:
                    await asyncio.sleep(self.config.failover.retry_delay / 1000)

        # All providers failed, use fallback
        fallback = self.registry.get_fallback_provider()
        if fallback and fallback.name not in attempted:
            logger.info("Using fallback provider")
            try:
                return await operation(fallback, **kwargs)
            except Exception as e:
                logger.error(f"Fallback provider also failed: {e}")

        raise RuntimeError(f"All providers failed. Last error: {last_error}")
