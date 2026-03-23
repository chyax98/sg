"""Executor — provider failover + per-instance selection + circuit breaker."""

import asyncio
import logging
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from ..models.config import ExecutorConfig, Strategy
from ..providers.base import BaseProvider, ProviderCapabilityError
from ..providers.registry import ProviderRegistry
from .circuit_breaker import CircuitBreaker, FailureType

logger = logging.getLogger(__name__)


@dataclass
class ProviderMetrics:
    requests: int = 0
    successes: int = 0
    failures: int = 0
    total_latency_ms: float = 0

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / self.successes if self.successes else 0

    @property
    def success_rate(self) -> float:
        return (self.successes / self.requests * 100) if self.requests else 100


def _classify_error(e: Exception) -> str:
    """Classify an exception into a failure type for the circuit breaker."""
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code in (401, 403):
            return FailureType.AUTH
        if code == 429:
            return FailureType.QUOTA
        if code >= 500:
            return FailureType.TRANSIENT
    # Check error message for common patterns
    msg = str(e).lower()
    if "unauthorized" in msg or "forbidden" in msg or "invalid api key" in msg:
        return FailureType.AUTH
    if "rate limit" in msg or "quota" in msg or "exceeded" in msg:
        return FailureType.QUOTA
    return FailureType.TRANSIENT


class Executor:
    """Provider selection + failover + circuit breaker + metrics.

    Architecture:
      - Provider groups are ALWAYS selected in strict priority order (lowest number = highest priority)
      - Only failover to next priority group on failure
      - Load balancing happens at the instance level within each group via provider.selection:
        * priority: always select highest priority instance
        * round_robin: rotate among instances in priority order
        * random: random selection among available instances
    """

    def __init__(self, config: ExecutorConfig, registry: ProviderRegistry):
        self.config = config
        self.registry = registry
        self._breakers: dict[str, CircuitBreaker] = {}
        self._metrics: dict[str, ProviderMetrics] = {}
        self._rr_index = 0
        self._rr_lock = threading.Lock()

    def _breaker(self, name: str) -> CircuitBreaker:
        if name not in self._breakers:
            cb = self.config.circuit_breaker
            hc = self.config.health_check
            self._breakers[name] = CircuitBreaker(
                failure_threshold=hc.failure_threshold,
                base_timeout=cb.base_timeout,
                multiplier=cb.multiplier,
                max_timeout=cb.max_timeout,
                success_threshold=hc.success_threshold,
                quota_timeout=cb.quota_timeout,
                auth_timeout=cb.auth_timeout,
            )
        return self._breakers[name]

    def _metrics_for(self, name: str) -> ProviderMetrics:
        if name not in self._metrics:
            self._metrics[name] = ProviderMetrics()
        return self._metrics[name]

    async def _try_provider(
        self,
        name: str,
        provider: BaseProvider,
        operation: Callable[[BaseProvider], Any],
    ) -> tuple[bool, Any, Exception | None]:
        """Run one provider attempt and update breaker/metrics."""
        breaker = self._breaker(name)
        metrics = self._metrics_for(name)

        try:
            timeout_s = provider.timeout / 1000
            start = time.perf_counter()
            async with asyncio.timeout(timeout_s):
                result = await operation(provider)
            latency = (time.perf_counter() - start) * 1000

            breaker.record_success()
            metrics.requests += 1
            metrics.successes += 1
            metrics.total_latency_ms += latency
            logger.info(f"Provider {name} succeeded in {latency:.1f}ms")
            return True, result, None
        except ProviderCapabilityError as e:
            logger.info(f"Provider {name} skipped: {e}")
            return False, None, e
        except Exception as e:
            failure_type = _classify_error(e)
            breaker.record_failure(failure_type)
            metrics.requests += 1
            metrics.failures += 1

            disabled_hours = breaker.current_timeout_seconds / 3600
            if failure_type == FailureType.AUTH:
                logger.error(
                    f"Provider {name}: auth failure, disabled for {disabled_hours:.0f}h"
                )
            elif failure_type == FailureType.QUOTA:
                logger.warning(
                    f"Provider {name}: quota exceeded, disabled for {disabled_hours:.0f}h"
                )
            else:
                logger.warning(f"Provider {name} failed: {e}")
            return False, None, e

    def _candidate_groups(self, capability: str, provider: str | None = None) -> list[str]:
        """Build ordered provider-group list to try.

        Provider groups are ALWAYS ordered by priority (lowest number = highest priority).
        The executor.strategy setting is deprecated and no longer affects group selection.
        Load balancing happens at the instance level within each group via provider.selection.
        """
        if provider:
            if self.registry.get(provider):
                group_name = self.registry.group_for_instance(provider)
                return [group_name] if group_name else []
            if self.registry.has_group(provider):
                return [provider]
            return []

        # Get groups ordered by priority (strictly enforced)
        groups = list(self.registry.get_group_order(capability))

        # Add fallback group at the end
        fallback_group = self.registry.get_fallback_group(capability)
        if fallback_group and fallback_group not in groups:
            groups.append(fallback_group)
        return groups

    async def execute(
        self,
        capability: str,
        operation: Callable[[BaseProvider], Any],
        provider: str | None = None,
    ) -> Any:
        """Execute operation with failover across providers."""
        logger.info(f"Executing {capability} request, provider={provider or 'auto'}")

        groups = self._candidate_groups(capability, provider)
        if not groups:
            raise RuntimeError(f"No providers available for '{capability}'")

        max_attempts = min(len(groups), self.config.failover.max_attempts)
        last_error: Exception | None = None

        tried_groups = groups[:max_attempts]
        logger.debug(f"Candidate groups: {tried_groups}")

        for group_name in tried_groups:
            logger.debug(f"Trying group: {group_name}")
            attempted_instances: set[str] = set()

            while True:
                if provider and self.registry.get(provider):
                    if provider in attempted_instances:
                        break
                    provider_instance = self.registry.get(provider)
                    if not provider_instance:
                        break
                    attempted_instances.add(provider)
                else:
                    provider_instance = self.registry.select_instance(
                        group_name,
                        capability,
                        excluded_instances=attempted_instances,
                        allow_request=lambda instance_id: self._breaker(instance_id).allow_request(),
                    )
                    if not provider_instance:
                        break
                    attempted_instances.add(provider_instance.name)

                ok, result, error = await self._try_provider(
                    provider_instance.name,
                    provider_instance,
                    operation,
                )
                if ok:
                    logger.info(f"Request completed: provider={provider_instance.name}")
                    return result
                last_error = error

                if isinstance(error, ProviderCapabilityError):
                    break

        fallback_group = self.registry.get_fallback_group(capability)
        if fallback_group and fallback_group not in tried_groups:
            logger.debug(f"All normal providers failed, trying fallback group: {fallback_group}")
            attempted_instances = set()
            while True:
                provider_instance = self.registry.select_instance(
                    fallback_group,
                    capability,
                    excluded_instances=attempted_instances,
                    allow_request=lambda instance_id: self._breaker(instance_id).allow_request(),
                )
                if not provider_instance:
                    break
                attempted_instances.add(provider_instance.name)

                ok, result, error = await self._try_provider(
                    provider_instance.name,
                    provider_instance,
                    operation,
                )
                if ok:
                    logger.info(f"Fallback to {provider_instance.name} succeeded")
                    return result
                last_error = error

        raise RuntimeError(f"All providers failed. Last error: {last_error}")

    def get_metrics(self) -> dict[str, dict[str, Any]]:
        result = {}
        for name, m in self._metrics.items():
            breaker = self._breaker(name)
            bs = breaker.status()
            result[name] = {
                "requests": m.requests,
                "successes": m.successes,
                "failures": m.failures,
                "avg_latency_ms": round(m.avg_latency_ms, 1),
                "success_rate": round(m.success_rate, 1),
                "circuit_breaker": bs["state"],
                "disabled_seconds_remaining": bs["remaining_disabled_seconds"],
                "trip_count": bs["trip_count"],
                "last_failure_type": bs["last_failure_type"],
            }
        return result

    def get_breaker_state(self, name: str) -> str:
        return self._breaker(name).state

    def get_breaker_status(self, name: str) -> dict:
        return self._breaker(name).status()

    async def run_health_checks(self) -> dict[str, Any]:
        """Explicit health check. Resets breakers for healthy providers."""
        healthy = []
        unhealthy = []

        for name, provider in self.registry.all().items():
            try:
                is_healthy, error = await provider.health_check()
                if is_healthy:
                    self._breaker(name).reset()
                    healthy.append(name)
                else:
                    unhealthy.append({"name": name, "error": error})
            except Exception as e:
                unhealthy.append({"name": name, "error": str(e)})

        return {"healthy": healthy, "unhealthy": unhealthy}
