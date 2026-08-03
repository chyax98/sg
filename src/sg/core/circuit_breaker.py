"""Circuit breaker with exponential backoff recovery.

Three-state machine: CLOSED → OPEN → HALF_OPEN → CLOSED.

Recovery timeout increases with each consecutive trip:
  1st trip: base_timeout (e.g. 5 minutes)
  2nd trip: base_timeout * multiplier
  later trips: capped at max_timeout

Fatal errors (auth failure, quota exhaustion) bypass the threshold
and open the breaker immediately with a dedicated timeout.
"""

import logging
import time

logger = logging.getLogger(__name__)


class FailureType:
    """Classify failures to determine breaker behavior."""

    TRANSIENT = "transient"  # timeout, 500, empty result — normal backoff
    QUOTA = "quota"  # 429, quota exceeded
    AUTH = "auth"  # 401, 403
    UNKNOWN = "unknown"  # default — treat as transient


class CircuitBreaker:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        failure_threshold: int = 3,
        base_timeout: float = 300.0,  # 5 minutes
        multiplier: float = 2.0,
        max_timeout: float = 3600.0,  # 1 hour cap
        success_threshold: int = 2,
        quota_timeout: float = 3600.0,  # 1 hour for quota errors
        auth_timeout: float = 86400.0,  # 1 day for auth errors
    ):
        self.failure_threshold = failure_threshold
        self.base_timeout = base_timeout
        self.multiplier = multiplier
        self.max_timeout = max_timeout
        self.success_threshold = success_threshold
        self.quota_timeout = quota_timeout
        self.auth_timeout = auth_timeout

        self._state = self.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._trip_count = 0  # how many times breaker has opened
        self._last_failure_time = 0.0
        self._current_timeout = base_timeout
        self._last_failure_type = FailureType.TRANSIENT
        self._disabled_until: float | None = None  # absolute monotonic time

    @property
    def state(self) -> str:
        if self._state == self.OPEN:
            now = time.monotonic()
            # Check if disabled_until has passed
            if self._disabled_until and now >= self._disabled_until:
                logger.info("Circuit breaker entering HALF_OPEN state for probing")
                self._state = self.HALF_OPEN
                self._success_count = 0
            elif (
                not self._disabled_until and now - self._last_failure_time >= self._current_timeout
            ):
                logger.info("Circuit breaker entering HALF_OPEN state for probing")
                self._state = self.HALF_OPEN
                self._success_count = 0
        return self._state

    @property
    def remaining_disabled_seconds(self) -> float:
        """How many seconds until the breaker allows a probe. 0 if not open."""
        if self._state != self.OPEN:
            return 0
        now = time.monotonic()
        if self._disabled_until:
            return max(0, self._disabled_until - now)
        return max(0, self._current_timeout - (now - self._last_failure_time))

    @property
    def current_timeout_seconds(self) -> float:
        """Current OPEN duration in seconds."""
        return self._current_timeout

    def allow_request(self) -> bool:
        return self.state != self.OPEN

    def record_success(self) -> None:
        """Record success. In HALF_OPEN, enough successes close the breaker."""
        if self._state == self.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                logger.info(f"Circuit breaker CLOSED: recovered after {self._trip_count} trips")
                self._state = self.CLOSED
                self._failure_count = 0
                self._success_count = 0
                self._trip_count = 0  # reset escalation on full recovery
                self._disabled_until = None
        else:
            # Any success in CLOSED resets consecutive failure count
            self._failure_count = 0

    def record_failure(self, failure_type: str = FailureType.TRANSIENT) -> None:
        """Record failure. Opens breaker based on type and threshold."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        self._last_failure_type = failure_type

        if failure_type == FailureType.AUTH:
            # Auth failure → immediately open with long timeout
            self._open_breaker(self.auth_timeout, failure_type)
        elif failure_type == FailureType.QUOTA:
            # Quota exhausted → immediately open with quota timeout
            self._open_breaker(self.quota_timeout, failure_type)
        elif self._state == self.HALF_OPEN:
            # Any failure in HALF_OPEN → back to OPEN with escalated timeout
            self._open_breaker(self._next_timeout(), failure_type)
        elif self._failure_count >= self.failure_threshold:
            # Consecutive transient failures exceeded threshold
            self._open_breaker(self._next_timeout(), failure_type)

    def _open_breaker(self, timeout: float, failure_type: str) -> None:
        """Transition to OPEN with given timeout."""
        self._state = self.OPEN
        self._trip_count += 1
        self._current_timeout = timeout
        self._disabled_until = time.monotonic() + timeout

        logger.warning(
            "Circuit breaker OPENED: failure_type=%s, timeout=%.0fs, trip_count=%s",
            failure_type,
            timeout,
            self._trip_count,
        )

    def _next_timeout(self) -> float:
        """Calculate next timeout with exponential backoff."""
        timeout = self.base_timeout * (self.multiplier ** (self._trip_count))
        return min(timeout, self.max_timeout)

    def reset(self) -> None:
        """Manual reset to closed state."""
        logger.info("Circuit breaker manually reset to CLOSED state")
        self._state = self.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._trip_count = 0
        self._last_failure_time = 0.0
        self._current_timeout = self.base_timeout
        self._disabled_until = None
        self._last_failure_type = FailureType.TRANSIENT

    def status(self) -> dict:
        """Current breaker status for API responses."""
        return {
            "state": self.state,
            "failure_count": self._failure_count,
            "trip_count": self._trip_count,
            "last_failure_type": self._last_failure_type,
            "remaining_disabled_seconds": round(self.remaining_disabled_seconds),
        }
