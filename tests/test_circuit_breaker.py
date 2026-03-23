"""Tests for CircuitBreaker."""

from unittest.mock import patch

from sg.core.circuit_breaker import CircuitBreaker, FailureType


class TestCircuitBreakerStates:

    def test_initial_state_is_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitBreaker.CLOSED

    def test_allows_requests_when_closed(self):
        cb = CircuitBreaker()
        assert cb.allow_request() is True

    def test_stays_closed_on_success(self):
        cb = CircuitBreaker()
        cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED

    def test_opens_after_failure_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.CLOSED
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

    def test_blocks_requests_when_open(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.allow_request() is False

    @patch("sg.core.circuit_breaker.time.monotonic")
    def test_transitions_to_half_open_after_base_timeout(self, mock_monotonic):
        cb = CircuitBreaker(failure_threshold=1, base_timeout=10.0)

        mock_monotonic.return_value = 100.0
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

        # After base timeout elapses, transitions to HALF_OPEN
        mock_monotonic.return_value = 110.0
        assert cb.state == CircuitBreaker.HALF_OPEN

    def test_half_open_allows_requests(self):
        cb = CircuitBreaker(failure_threshold=1, base_timeout=0.0)
        cb.record_failure()
        # Force half-open by reading state (base_timeout=0.0)
        _ = cb.state
        assert cb.allow_request() is True

    def test_half_open_closes_after_success_threshold(self):
        cb = CircuitBreaker(failure_threshold=1, base_timeout=0.0, success_threshold=2)
        cb.record_failure()
        _ = cb.state  # transition to HALF_OPEN

        cb.record_success()
        assert cb.state == CircuitBreaker.HALF_OPEN  # not yet
        cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED  # now closed

    def test_half_open_reopens_on_failure(self):
        cb = CircuitBreaker(
            failure_threshold=1,
            base_timeout=0.0,
            multiplier=2.0,
            max_timeout=100.0,
        )
        cb.record_failure()
        _ = cb.state  # transition to HALF_OPEN

        cb.record_failure()
        assert cb._state == CircuitBreaker.OPEN
        assert cb.current_timeout_seconds == 0.0

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        # Failure count reset, need 3 more to open
        cb.record_failure()
        assert cb.state == CircuitBreaker.CLOSED

    def test_quota_failure_opens_immediately(self):
        cb = CircuitBreaker(failure_threshold=3, quota_timeout=123.0)
        cb.record_failure(FailureType.QUOTA)
        assert cb.state == CircuitBreaker.OPEN
        assert cb.current_timeout_seconds == 123.0

    def test_auth_failure_opens_immediately(self):
        cb = CircuitBreaker(failure_threshold=3, auth_timeout=456.0)
        cb.record_failure(FailureType.AUTH)
        assert cb.state == CircuitBreaker.OPEN
        assert cb.current_timeout_seconds == 456.0

    @patch("sg.core.circuit_breaker.time.monotonic")
    def test_timeout_escalates_on_repeated_trips(self, mock_monotonic):
        cb = CircuitBreaker(
            failure_threshold=1,
            base_timeout=10.0,
            multiplier=6.0,
            max_timeout=100.0,
        )

        mock_monotonic.return_value = 100.0
        cb.record_failure()
        assert cb.current_timeout_seconds == 10.0

        mock_monotonic.return_value = 110.0
        assert cb.state == CircuitBreaker.HALF_OPEN

        mock_monotonic.return_value = 111.0
        cb.record_failure()
        assert cb.current_timeout_seconds == 60.0

        mock_monotonic.return_value = 171.0
        assert cb.state == CircuitBreaker.HALF_OPEN

        mock_monotonic.return_value = 172.0
        cb.record_failure()
        assert cb.current_timeout_seconds == 100.0


class TestCircuitBreakerReset:

    def test_reset_clears_all_state(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

        cb.reset()
        assert cb.state == CircuitBreaker.CLOSED
        assert cb._failure_count == 0
        assert cb._success_count == 0
        assert cb._last_failure_time == 0.0
        assert cb.allow_request() is True


class TestCircuitBreakerRecoveryTimeout:

    def test_stays_open_before_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, base_timeout=60.0)
        cb.record_failure()
        # Should still be OPEN -- nowhere near 60 seconds
        assert cb.state == CircuitBreaker.OPEN

    @patch("sg.core.circuit_breaker.time.monotonic")
    def test_transitions_after_timeout(self, mock_monotonic):
        cb = CircuitBreaker(failure_threshold=1, base_timeout=30.0)

        mock_monotonic.return_value = 100.0
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

        # 30 seconds later
        mock_monotonic.return_value = 130.0
        assert cb.state == CircuitBreaker.HALF_OPEN
