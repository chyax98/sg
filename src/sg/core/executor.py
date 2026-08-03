"""Executor — provider failover + per-instance selection + circuit breaker."""

import asyncio
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from ..models.config import ExecutorConfig
from ..providers.base import BaseProvider, ProviderCapabilityError
from ..providers.registry import ProviderRegistry
from .circuit_breaker import CircuitBreaker, FailureType

logger = logging.getLogger(__name__)


class EmptyResultError(RuntimeError):
    """Provider returned 200-shaped payload with nothing usable — try next key/group."""


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


def _status_code(e: Exception) -> int | None:
    if isinstance(e, httpx.HTTPStatusError):
        return e.response.status_code
    response = getattr(e, "response", None)
    code = getattr(response, "status_code", None)
    if isinstance(code, int):
        return code
    text = f"{type(e).__name__}: {e}"
    m = re.search(r"\b([45]\d{2})\b", text)
    return int(m.group(1)) if m else None


def _classify_error(e: Exception) -> str:
    """Classify an exception into a failure type for the circuit breaker."""
    if isinstance(e, EmptyResultError):
        return FailureType.TRANSIENT

    code = _status_code(e)
    if code in (401, 403):
        return FailureType.AUTH
    if code == 429:
        return FailureType.QUOTA
    if code is not None and code >= 500:
        return FailureType.TRANSIENT

    msg = f"{type(e).__name__}: {e}".lower()
    if any(
        k in msg
        for k in (
            "unauthorized",
            "forbidden",
            "invalid api key",
            "invalid_api_key",
            "authentication",
            "api key",
        )
    ):
        return FailureType.AUTH
    if any(
        k in msg
        for k in (
            "rate limit",
            "rate_limit",
            "too many requests",
            "quota exceeded",
            "quota_exceeded",
            "insufficient credits",
        )
    ):
        return FailureType.QUOTA
    return FailureType.TRANSIENT


def _result_is_unusable(result: Any) -> bool:
    """True when the call 'succeeded' but has nothing the caller can use."""
    if result is None:
        return True

    # ResearchResponse: topic + report (+ sources)
    if hasattr(result, "report") and hasattr(result, "topic"):
        return not str(getattr(result, "report", "") or "").strip()

    # Context7 docs context (query-docs)
    if (
        hasattr(result, "library_id")
        and hasattr(result, "content")
        and not hasattr(result, "results")
    ):
        return not str(getattr(result, "content", "") or "").strip()

    # Context7 library resolve: empty list is a valid "no match" answer — do not failover
    if hasattr(result, "library_name") and hasattr(result, "results"):
        return False

    results = getattr(result, "results", None)
    if not isinstance(results, list):
        return False
    if not results:
        return True

    sample = results[0]
    has_content = hasattr(sample, "content") or (isinstance(sample, dict) and "content" in sample)
    if not has_content:
        return False

    def _page_bad(page: Any) -> bool:
        if isinstance(page, dict):
            err = page.get("error")
            content = page.get("content", "")
        else:
            err = getattr(page, "error", None)
            content = getattr(page, "content", "")
        return bool(err) or not str(content or "").strip()

    return all(_page_bad(page) for page in results)


def _err_text(e: Exception | None) -> str:
    if e is None:
        return ""
    text = str(e).strip()
    if text:
        return text
    return repr(e)


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

            if _result_is_unusable(result):
                raise EmptyResultError(f"{name} returned empty result")

            breaker.record_success()
            metrics.requests += 1
            metrics.successes += 1
            metrics.total_latency_ms += latency
            logger.info("Provider %s succeeded in %.1fms", name, latency)
            return True, result, None
        except ProviderCapabilityError as e:
            logger.info("Provider %s skipped: %s", name, e)
            return False, None, e
        except Exception as e:
            failure_type = _classify_error(e)
            breaker.record_failure(failure_type)
            metrics.requests += 1
            metrics.failures += 1

            disabled_s = breaker.current_timeout_seconds
            err = _err_text(e)
            if failure_type == FailureType.AUTH:
                logger.error(
                    "Provider %s: auth failure (%s), disabled for %.0fs",
                    name,
                    err,
                    disabled_s,
                )
            elif failure_type == FailureType.QUOTA:
                logger.warning(
                    "Provider %s: quota (%s), disabled for %.0fs",
                    name,
                    err,
                    disabled_s,
                )
            else:
                logger.warning("Provider %s failed (%s): %s", name, type(e).__name__, err)
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

    def available_group_count(self, capability: str) -> int:
        """Return number of candidate provider groups for a capability."""
        return len(self._candidate_groups(capability))

    async def execute(
        self,
        capability: str,
        operation: Callable[[BaseProvider], Any],
        provider: str | None = None,
        spread_index: int | None = None,
    ) -> Any:
        """Execute operation with failover across providers.

        Args:
            spread_index: If set, rotate candidate groups to distribute load.
                          e.g. with groups [tavily, exa, brave]:
                            spread_index=0 → try [tavily, exa, brave]
                            spread_index=1 → try [exa, brave, tavily]
                            spread_index=2 → try [brave, tavily, exa]
                          Each request still has full failover chain.
        """
        logger.info(f"Executing {capability} request, provider={provider or 'auto'}")

        groups = self._candidate_groups(capability, provider)
        if not groups:
            raise RuntimeError(f"No providers available for '{capability}'")

        # Spread: rotate starting point to distribute load across providers
        if spread_index is not None and provider is None and len(groups) > 1:
            offset = spread_index % len(groups)
            groups = groups[offset:] + groups[:offset]

        # max_attempts <= 0 → try every candidate group (local free-key pools)
        configured = self.config.failover.max_attempts
        max_attempts = len(groups) if configured <= 0 else min(len(groups), configured)
        last_error: Exception | None = None
        attempt_errors: list[str] = []

        tried_groups = groups[:max_attempts]
        logger.debug("Candidate groups (%s/%s): %s", max_attempts, len(groups), tried_groups)

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
                        allow_request=lambda instance_id: self._breaker(
                            instance_id
                        ).allow_request(),
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
                if error is not None and not isinstance(error, ProviderCapabilityError):
                    attempt_errors.append(f"{provider_instance.name}: {_err_text(error)}")

                if isinstance(error, ProviderCapabilityError):
                    break

        fallback_group = self.registry.get_fallback_group(capability)
        if fallback_group and fallback_group not in tried_groups:
            logger.debug("All normal providers failed, trying fallback group: %s", fallback_group)
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
                    logger.info("Fallback to %s succeeded", provider_instance.name)
                    return result
                last_error = error
                if error is not None and not isinstance(error, ProviderCapabilityError):
                    attempt_errors.append(f"{provider_instance.name}: {_err_text(error)}")

        detail = "; ".join(attempt_errors) if attempt_errors else _err_text(last_error)
        raise RuntimeError(f"All providers failed for '{capability}'. {detail}")

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
        """Probe providers. Does not reset OPEN breakers (many probes are no-ops)."""
        healthy = []
        unhealthy = []

        for name, provider in self.registry.all().items():
            try:
                is_healthy, error = await provider.health_check()
                if is_healthy:
                    healthy.append(name)
                else:
                    unhealthy.append({"name": name, "error": error})
            except Exception as e:
                unhealthy.append({"name": name, "error": _err_text(e)})

        return {"healthy": healthy, "unhealthy": unhealthy}
