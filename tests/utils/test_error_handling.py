"""
Unit tests for error handling utilities
"""
import pytest
import requests
from datetime import datetime
from qaht.utils.error_handling import (
    APIError,
    RateLimitError,
    AuthenticationError,
    NotFoundError,
    handle_api_errors,
    safe_get,
    parse_timestamp,
    RetryableRequest
)


class TestExceptions:
    """Tests for custom exception classes"""

    def test_api_error(self):
        """Test APIError base exception"""
        error = APIError("Test error")
        assert str(error) == "Test error"
        assert isinstance(error, Exception)

    def test_rate_limit_error(self):
        """Test RateLimitError"""
        error = RateLimitError("Rate limit exceeded")
        assert isinstance(error, APIError)
        assert isinstance(error, Exception)

    def test_authentication_error(self):
        """Test AuthenticationError"""
        error = AuthenticationError("Auth failed")
        assert isinstance(error, APIError)

    def test_not_found_error(self):
        """Test NotFoundError"""
        error = NotFoundError("Resource not found")
        assert isinstance(error, APIError)


class TestHandleApiErrors:
    """Tests for @handle_api_errors decorator"""

    def test_successful_function_call(self):
        """Test decorator with successful function"""
        @handle_api_errors("TestAPI", default_return={})
        def success_func():
            return {"status": "ok"}

        result = success_func()
        assert result == {"status": "ok"}

    def test_http_404_error(self):
        """Test 404 HTTP error handling"""
        @handle_api_errors("TestAPI", default_return={}, log_level="warning")
        def not_found_func():
            response = requests.Response()
            response.status_code = 404
            error = requests.exceptions.HTTPError(response=response)
            raise error

        result = not_found_func()
        assert result == {}

    def test_http_429_rate_limit(self, mocker):
        """Test 429 rate limit error"""
        @handle_api_errors("TestAPI", default_return={})
        def rate_limit_func():
            response = mocker.Mock()
            response.status_code = 429
            error = requests.exceptions.HTTPError(response=response)
            raise error

        with pytest.raises(RateLimitError):
            rate_limit_func()

    def test_http_401_authentication(self, mocker):
        """Test 401 authentication error"""
        @handle_api_errors("TestAPI", default_return={}, raise_on_auth_error=True)
        def auth_func():
            response = mocker.Mock()
            response.status_code = 401
            error = requests.exceptions.HTTPError(response=response)
            raise error

        with pytest.raises(AuthenticationError):
            auth_func()

    def test_timeout_error(self):
        """Test timeout error handling"""
        @handle_api_errors("TestAPI", default_return=[])
        def timeout_func():
            raise requests.exceptions.Timeout("Connection timeout")

        result = timeout_func()
        assert result == []

    def test_connection_error(self):
        """Test connection error handling"""
        @handle_api_errors("TestAPI", default_return=None)
        def connection_func():
            raise requests.exceptions.ConnectionError("Connection failed")

        result = connection_func()
        assert result is None

    def test_value_error(self):
        """Test ValueError handling (JSON parsing)"""
        @handle_api_errors("TestAPI", default_return={})
        def parse_func():
            raise ValueError("Invalid JSON")

        result = parse_func()
        assert result == {}

    def test_unexpected_exception(self):
        """Test unexpected exception handling"""
        @handle_api_errors("TestAPI", default_return="error")
        def unexpected_func():
            raise RuntimeError("Unexpected error")

        result = unexpected_func()
        assert result == "error"

    def test_auth_error_no_raise(self):
        """Test auth error without re-raising"""
        @handle_api_errors("TestAPI", default_return={}, raise_on_auth_error=False)
        def auth_func():
            response = requests.Response()
            response.status_code = 401
            error = requests.exceptions.HTTPError(response=response)
            raise error

        result = auth_func()
        assert result == {}

    def test_custom_log_level(self):
        """Test custom log level setting"""
        @handle_api_errors("TestAPI", default_return=None, log_level="debug")
        def debug_func():
            raise ValueError("Debug error")

        result = debug_func()
        assert result is None


class TestSafeGet:
    """Tests for safe_get utility"""

    def test_single_level_access(self):
        """Test single level dictionary access"""
        data = {'name': 'John', 'age': 30}
        assert safe_get(data, 'name') == 'John'
        assert safe_get(data, 'age') == 30

    def test_nested_access(self):
        """Test nested dictionary access"""
        data = {
            'user': {
                'profile': {
                    'name': 'John',
                    'age': 30
                }
            }
        }
        assert safe_get(data, 'user', 'profile', 'name') == 'John'
        assert safe_get(data, 'user', 'profile', 'age') == 30

    def test_missing_key_default(self):
        """Test missing key with default value"""
        data = {'name': 'John'}
        assert safe_get(data, 'age', default=0) == 0
        assert safe_get(data, 'missing', default='N/A') == 'N/A'

    def test_missing_nested_key(self):
        """Test missing nested key"""
        data = {'user': {'name': 'John'}}
        assert safe_get(data, 'user', 'email', default='') == ''
        assert safe_get(data, 'user', 'profile', 'age', default=0) == 0

    def test_none_value(self):
        """Test None value handling"""
        data = {'key': None}
        assert safe_get(data, 'key', default='default') == 'default'

    def test_empty_dict(self):
        """Test empty dictionary"""
        data = {}
        assert safe_get(data, 'key', default=None) is None

    def test_non_dict_intermediate(self):
        """Test non-dict intermediate value"""
        data = {'user': 'John'}
        assert safe_get(data, 'user', 'name', default='') == ''

    def test_list_access(self):
        """Test accessing list (should return default)"""
        data = {'items': [1, 2, 3]}
        assert safe_get(data, 'items', 0, default='N/A') == 'N/A'


class TestParseTimestamp:
    """Tests for parse_timestamp utility"""

    def test_iso_format(self):
        """Test ISO format parsing"""
        ts = parse_timestamp("2024-01-15T12:30:00Z")
        assert ts.year == 2024
        assert ts.month == 1
        assert ts.day == 15
        assert ts.hour == 12
        assert ts.minute == 30

    def test_iso_format_with_microseconds(self):
        """Test ISO format with microseconds"""
        ts = parse_timestamp("2024-01-15T12:30:00.123456Z")
        assert ts.year == 2024
        assert ts.microsecond > 0

    def test_custom_formats(self):
        """Test custom format strings"""
        formats = [
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]

        ts1 = parse_timestamp("2024-01-15T12:30:00Z", formats=formats)
        assert ts1.year == 2024

        ts2 = parse_timestamp("2024-01-15 12:30:00", formats=formats)
        assert ts2.year == 2024

        ts3 = parse_timestamp("2024-01-15", formats=formats)
        assert ts3.year == 2024

    def test_invalid_timestamp_default_now(self):
        """Test invalid timestamp with default=now"""
        ts = parse_timestamp("invalid")
        assert isinstance(ts, datetime)
        # Should be close to now
        assert (datetime.now() - ts).seconds < 1

    def test_invalid_timestamp_custom_default(self):
        """Test invalid timestamp with custom default"""
        default = datetime(2020, 1, 1)
        ts = parse_timestamp("invalid", default=default)
        assert ts == default

    def test_empty_timestamp(self):
        """Test empty timestamp"""
        default = datetime(2020, 1, 1)
        ts = parse_timestamp("", default=default)
        assert ts == default

    def test_none_timestamp(self):
        """Test None timestamp"""
        default = datetime(2020, 1, 1)
        ts = parse_timestamp(None, default=default)
        assert ts == default

    def test_non_string_timestamp(self):
        """Test non-string timestamp"""
        default = datetime(2020, 1, 1)
        ts = parse_timestamp(12345, default=default)
        assert ts == default


class TestRetryableRequest:
    """Tests for RetryableRequest class"""

    def test_successful_request(self, mocker):
        """Test successful request on first try"""
        mock_response = mocker.Mock()
        mock_response.status_code = 200
        mock_request = mocker.patch('requests.request', return_value=mock_response)

        requester = RetryableRequest(max_retries=3)
        response = requester.get("https://api.example.com/data")

        assert response == mock_response
        assert mock_request.call_count == 1

    def test_retry_on_failure(self, mocker):
        """Test retry behavior on failures"""
        # First 2 calls fail, 3rd succeeds
        mock_response_fail = mocker.Mock()
        mock_response_fail.raise_for_status.side_effect = requests.exceptions.HTTPError()

        mock_response_success = mocker.Mock()

        mock_request = mocker.patch('requests.request', side_effect=[
            mock_response_fail,
            mock_response_fail,
            mock_response_success
        ])

        mock_time = mocker.patch('time.sleep')  # Don't actually sleep

        requester = RetryableRequest(max_retries=3, backoff_factor=1.0)
        response = requester.get("https://api.example.com/data")

        assert response == mock_response_success
        assert mock_request.call_count == 3
        assert mock_time.call_count == 2  # Slept twice (after 1st and 2nd failures)

    def test_exhausted_retries(self, mocker):
        """Test when all retries are exhausted"""
        mock_response = mocker.Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError()

        mock_request = mocker.patch('requests.request', return_value=mock_response)
        mock_time = mocker.patch('time.sleep')

        requester = RetryableRequest(max_retries=3, backoff_factor=1.0)

        with pytest.raises(requests.exceptions.HTTPError):
            requester.get("https://api.example.com/data")

        assert mock_request.call_count == 3

    def test_no_retry_on_4xx_errors(self, mocker):
        """Test that 4xx errors don't trigger retries"""
        response = mocker.Mock()
        response.status_code = 404
        error = requests.exceptions.HTTPError(response=response)
        response.raise_for_status.side_effect = error

        mock_request = mocker.patch('requests.request', return_value=response)

        requester = RetryableRequest(max_retries=3)

        with pytest.raises(requests.exceptions.HTTPError):
            requester.get("https://api.example.com/data")

        # Should not retry on 4xx
        assert mock_request.call_count == 1

    def test_exponential_backoff(self, mocker):
        """Test exponential backoff timing"""
        mock_response = mocker.Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError()

        mocker.patch('requests.request', return_value=mock_response)
        mock_sleep = mocker.patch('time.sleep')

        requester = RetryableRequest(max_retries=4, backoff_factor=2.0)

        try:
            requester.get("https://api.example.com/data")
        except requests.exceptions.HTTPError:
            pass

        # Should sleep: 2.0, 4.0, 8.0 (exponential)
        sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
        assert len(sleep_calls) == 3
        assert sleep_calls[0] == 2.0  # 2.0 * 2^0
        assert sleep_calls[1] == 4.0  # 2.0 * 2^1
        assert sleep_calls[2] == 8.0  # 2.0 * 2^2

    def test_post_request(self, mocker):
        """Test POST request"""
        mock_response = mocker.Mock()
        mock_request = mocker.patch('requests.request', return_value=mock_response)

        requester = RetryableRequest()
        response = requester.post("https://api.example.com/data", json={'test': 'data'})

        assert response == mock_response
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[0][0] == 'POST'  # Method
        assert call_args[1]['json'] == {'test': 'data'}  # Data

    def test_custom_timeout(self, mocker):
        """Test custom timeout setting"""
        mock_response = mocker.Mock()
        mock_request = mocker.patch('requests.request', return_value=mock_response)

        requester = RetryableRequest(timeout=30)
        requester.get("https://api.example.com/data")

        call_args = mock_request.call_args
        assert call_args[1]['timeout'] == 30


# Integration tests
class TestErrorHandlingIntegration:
    """Integration tests for error handling"""

    def test_decorated_function_with_retries(self, mocker):
        """Test decorator with retry logic"""
        call_count = 0

        @handle_api_errors("TestAPI", default_return={})
        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise requests.exceptions.Timeout()
            return {"status": "ok"}

        # Even though function fails twice, decorator catches errors
        # (Note: decorator doesn't retry, it just returns default on error)
        result = flaky_function()
        assert result == {}  # First call fails, returns default

    def test_safe_api_data_extraction(self):
        """Test safe data extraction from API response"""
        # Simulated API response
        api_response = {
            'data': {
                'user': {
                    'profile': {
                        'name': 'John',
                        'email': 'john@example.com'
                    }
                }
            },
            'meta': {
                'timestamp': '2024-01-15T12:30:00Z'
            }
        }

        # Safe extraction
        name = safe_get(api_response, 'data', 'user', 'profile', 'name', default='Unknown')
        email = safe_get(api_response, 'data', 'user', 'profile', 'email', default='')
        phone = safe_get(api_response, 'data', 'user', 'profile', 'phone', default='N/A')

        assert name == 'John'
        assert email == 'john@example.com'
        assert phone == 'N/A'  # Missing key, uses default

        # Parse timestamp
        ts_str = safe_get(api_response, 'meta', 'timestamp', default='')
        ts = parse_timestamp(ts_str)
        assert ts.year == 2024
