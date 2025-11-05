"""
Tests for Retry Utilities
"""
import pytest
import time
from unittest.mock import Mock, patch
from qaht.utils.retry import retry_with_backoff, safe_execute


class TestRetryWithBackoff:
    """Test retry decorator with exponential backoff"""

    def test_success_on_first_attempt(self):
        """Test function succeeds on first attempt"""
        call_count = 0

        @retry_with_backoff(max_retries=3)
        def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = successful_func()

        assert result == "success"
        assert call_count == 1

    def test_success_after_retries(self, mocker):
        """Test function succeeds after initial failures"""
        call_count = 0
        mock_sleep = mocker.patch('time.sleep')

        @retry_with_backoff(max_retries=3, jitter=False)
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary error")
            return "success"

        result = flaky_func()

        assert result == "success"
        assert call_count == 3
        assert mock_sleep.call_count == 2  # 2 retries before success

    def test_all_retries_exhausted(self, mocker):
        """Test function fails after all retries"""
        call_count = 0
        mock_sleep = mocker.patch('time.sleep')

        @retry_with_backoff(max_retries=3, jitter=False)
        def failing_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Persistent error")

        with pytest.raises(ValueError, match="Persistent error"):
            failing_func()

        assert call_count == 4  # Initial + 3 retries
        assert mock_sleep.call_count == 3

    def test_exponential_backoff_timing(self, mocker):
        """Test exponential backoff delays"""
        mock_sleep = mocker.patch('time.sleep')

        @retry_with_backoff(max_retries=3, initial_delay=1.0, backoff_factor=2.0, jitter=False)
        def failing_func():
            raise ValueError("Error")

        with pytest.raises(ValueError):
            failing_func()

        # Should sleep: 1s, 2s, 4s
        calls = [call[0][0] for call in mock_sleep.call_args_list]
        assert calls == [1.0, 2.0, 4.0]

    def test_max_delay_cap(self, mocker):
        """Test delay is capped at max_delay"""
        mock_sleep = mocker.patch('time.sleep')

        @retry_with_backoff(
            max_retries=5,
            initial_delay=10.0,
            backoff_factor=2.0,
            max_delay=30.0,
            jitter=False
        )
        def failing_func():
            raise ValueError("Error")

        with pytest.raises(ValueError):
            failing_func()

        # Should sleep: 10s, 20s, 30s, 30s, 30s (capped)
        calls = [call[0][0] for call in mock_sleep.call_args_list]
        assert calls == [10.0, 20.0, 30.0, 30.0, 30.0]

    def test_jitter_adds_randomness(self, mocker):
        """Test jitter adds randomness to delays"""
        mock_sleep = mocker.patch('time.sleep')
        mocker.patch('random.random', return_value=0.5)  # Predictable randomness

        @retry_with_backoff(max_retries=2, initial_delay=1.0, jitter=True)
        def failing_func():
            raise ValueError("Error")

        with pytest.raises(ValueError):
            failing_func()

        # With jitter and random=0.5, delays will be modified
        # actual_delay = delay * (1 + 0.2 * (0.5 - 0.5)) = delay * 1.0
        # So same as without jitter in this case
        assert mock_sleep.call_count == 2

    def test_specific_exceptions_only(self, mocker):
        """Test only specified exceptions are retried"""
        call_count = 0
        mock_sleep = mocker.patch('time.sleep')

        @retry_with_backoff(exceptions=(ValueError,), max_retries=3)
        def func_with_different_errors():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Retryable")
            else:
                raise TypeError("Not retryable")

        with pytest.raises(TypeError, match="Not retryable"):
            func_with_different_errors()

        # Should retry once (ValueError), then fail on TypeError
        assert call_count == 2
        assert mock_sleep.call_count == 1

    def test_retry_after_header(self, mocker):
        """Test respects Retry-After header"""
        mock_sleep = mocker.patch('time.sleep')

        @retry_with_backoff(max_retries=2, initial_delay=1.0, jitter=False)
        def func_with_retry_after():
            # Create exception with response and Retry-After header
            error = ValueError("Rate limited")
            error.response = Mock()
            error.response.headers = {'Retry-After': '5.0'}
            raise error

        with pytest.raises(ValueError):
            func_with_retry_after()

        # Should respect Retry-After value
        calls = [call[0][0] for call in mock_sleep.call_args_list]
        assert calls[0] == 5.0

    def test_invalid_retry_after_header(self, mocker):
        """Test handles invalid Retry-After header"""
        mock_sleep = mocker.patch('time.sleep')

        @retry_with_backoff(max_retries=2, initial_delay=1.0, jitter=False)
        def func_with_invalid_retry_after():
            error = ValueError("Error")
            error.response = Mock()
            error.response.headers = {'Retry-After': 'invalid'}
            raise error

        with pytest.raises(ValueError):
            func_with_invalid_retry_after()

        # Should fall back to normal delay
        calls = [call[0][0] for call in mock_sleep.call_args_list]
        assert calls[0] == 1.0

    def test_function_with_arguments(self, mocker):
        """Test decorated function with arguments"""
        call_count = 0
        mock_sleep = mocker.patch('time.sleep')

        @retry_with_backoff(max_retries=2, jitter=False)
        def func_with_args(x, y, z=10):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Error")
            return x + y + z

        result = func_with_args(1, 2, z=3)

        assert result == 6
        assert call_count == 2

    def test_preserves_function_metadata(self):
        """Test decorator preserves function metadata"""
        @retry_with_backoff()
        def documented_func():
            """This is a docstring"""
            pass

        assert documented_func.__name__ == 'documented_func'
        assert documented_func.__doc__ == 'This is a docstring'


class TestSafeExecute:
    """Test safe_execute utility"""

    def test_safe_execute_success(self):
        """Test successful execution"""
        def successful_func():
            return "result"

        result = safe_execute(successful_func)

        assert result == "result"

    def test_safe_execute_with_exception(self):
        """Test execution with exception returns default"""
        def failing_func():
            raise ValueError("Error")

        result = safe_execute(failing_func, default="default")

        assert result == "default"

    def test_safe_execute_default_none(self):
        """Test default value is None by default"""
        def failing_func():
            raise ValueError("Error")

        result = safe_execute(failing_func)

        assert result is None

    def test_safe_execute_logs_errors(self, caplog):
        """Test errors are logged"""
        import logging
        caplog.set_level(logging.ERROR)

        def failing_func():
            raise ValueError("Test error")

        safe_execute(failing_func, log_errors=True)

        assert "Test error" in caplog.text

    def test_safe_execute_no_logging(self, caplog):
        """Test errors are not logged when disabled"""
        import logging
        caplog.set_level(logging.ERROR)

        def failing_func():
            raise ValueError("Test error")

        safe_execute(failing_func, log_errors=False)

        assert len(caplog.records) == 0

    def test_safe_execute_with_lambda(self):
        """Test with lambda function"""
        result = safe_execute(lambda: 5 * 5, default=0)

        assert result == 25

    def test_safe_execute_different_exceptions(self):
        """Test handles different exception types"""
        def func_with_type_error():
            raise TypeError("Type error")

        result = safe_execute(func_with_type_error, default="fallback")

        assert result == "fallback"


@pytest.mark.integration
class TestRetryIntegration:
    """Integration tests for retry utilities"""

    def test_real_world_api_retry_pattern(self, mocker):
        """Test realistic API retry scenario"""
        call_count = 0
        mock_sleep = mocker.patch('time.sleep')

        @retry_with_backoff(
            exceptions=(ConnectionError, TimeoutError),
            max_retries=3,
            initial_delay=1.0,
            jitter=False
        )
        def api_call():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Network error")
            elif call_count == 2:
                raise TimeoutError("Timeout")
            else:
                return {"data": "success"}

        result = api_call()

        assert result == {"data": "success"}
        assert call_count == 3
        assert mock_sleep.call_count == 2

    def test_combined_retry_and_safe_execute(self, mocker):
        """Test combining retry and safe_execute"""
        call_count = 0
        mock_sleep = mocker.patch('time.sleep')

        @retry_with_backoff(max_retries=2, jitter=False)
        def risky_operation():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")

        # Use safe_execute to catch the final failure
        result = safe_execute(risky_operation, default="fallback")

        assert result == "fallback"
        assert call_count == 3  # Initial + 2 retries

    def test_retry_with_multiple_exception_types(self, mocker):
        """Test retry with multiple exception types"""
        call_count = 0
        mock_sleep = mocker.patch('time.sleep')

        @retry_with_backoff(
            exceptions=(ValueError, TypeError, KeyError),
            max_retries=3,
            jitter=False
        )
        def multi_error_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Value error")
            elif call_count == 2:
                raise TypeError("Type error")
            elif call_count == 3:
                raise KeyError("Key error")
            else:
                return "success"

        result = multi_error_func()

        assert result == "success"
        assert call_count == 4
