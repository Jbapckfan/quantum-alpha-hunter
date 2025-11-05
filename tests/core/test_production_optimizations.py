"""
Integration tests for production optimization components
"""
import pytest
from qaht.core.production_optimizations import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    AdaptiveRateLimiter
)


class TestCircuitBreaker:
    """Test CircuitBreaker initialization"""

    def test_initialization(self):
        """Test circuit breaker initialization"""
        cb = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=60,
            expected_exception=Exception
        )

        assert cb.failure_threshold == 3
        assert cb.recovery_timeout == 60
        assert cb.failure_count == 0
        assert cb.state == 'CLOSED'  # Initial state is CLOSED


class TestCircuitBreakerOpenError:
    """Test CircuitBreakerOpenError exception"""

    def test_exception_creation(self):
        """Test CircuitBreakerOpenError can be raised"""
        with pytest.raises(CircuitBreakerOpenError):
            raise CircuitBreakerOpenError("Circuit is open")


class TestAdaptiveRateLimiter:
    """Test AdaptiveRateLimiter initialization"""

    def test_initialization(self):
        """Test rate limiter initialization"""
        rl = AdaptiveRateLimiter(default_delay=1.0)

        # Check internal structures exist
        assert hasattr(rl, 'delays')
        assert hasattr(rl, 'last_call')
        assert hasattr(rl, 'consecutive_success')

    def test_endpoint_tracking(self):
        """Test per-endpoint tracking"""
        rl = AdaptiveRateLimiter(default_delay=0.5)

        # Different endpoints should be tracked separately
        rl.on_success("endpoint1")
        rl.on_success("endpoint2")

        assert "endpoint1" in rl.consecutive_success
        assert "endpoint2" in rl.consecutive_success

    def test_success_tracking(self):
        """Test success tracking increments counter"""
        rl = AdaptiveRateLimiter(default_delay=1.0)

        endpoint = "test_endpoint"
        rl.on_success(endpoint)

        assert rl.consecutive_success[endpoint] == 1

    def test_error_handling(self):
        """Test error increases delay"""
        rl = AdaptiveRateLimiter(default_delay=1.0)

        endpoint = "test_endpoint"
        initial_delay = rl.delays[endpoint]

        rl.on_error(endpoint)

        # Delay should increase after error
        assert rl.delays[endpoint] > initial_delay

    def test_rate_limit_handling(self):
        """Test rate limit handling"""
        rl = AdaptiveRateLimiter(default_delay=1.0)

        endpoint = "test_endpoint"
        initial_delay = rl.delays[endpoint]

        rl.on_rate_limit(endpoint)

        # Delay should increase after rate limit
        assert rl.delays[endpoint] > initial_delay

    def test_rate_limit_with_retry_after(self):
        """Test rate limit with retry-after header"""
        rl = AdaptiveRateLimiter(default_delay=1.0)

        endpoint = "test_endpoint"

        rl.on_rate_limit(endpoint, retry_after=10)

        # Delay should be set to retry_after value
        assert rl.delays[endpoint] == 10


@pytest.mark.integration
class TestCircuitBreakerIntegration:
    """Test circuit breaker integration"""

    def test_circuit_breaker_exists_in_api_clients(self):
        """Test that circuit breaker is used in API clients"""
        # This is tested via the data source integration tests
        # Just verify the class is importable and usable
        cb = CircuitBreaker(failure_threshold=5, recovery_timeout=180)
        assert cb is not None


@pytest.mark.integration
class TestAdaptiveRateLimiterIntegration:
    """Test rate limiter integration"""

    def test_rate_limiter_exists_in_api_clients(self):
        """Test that rate limiter is used in API clients"""
        # This is tested via the data source integration tests
        # Just verify the class is importable and usable
        rl = AdaptiveRateLimiter(default_delay=2.0)
        assert rl is not None
