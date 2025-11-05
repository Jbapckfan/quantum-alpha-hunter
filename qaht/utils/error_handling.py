"""
Standardized error handling utilities for data sources

Provides consistent error handling patterns across all API integrations.
"""
import logging
import functools
import time
from datetime import datetime
from typing import Callable, Any, Optional, List
import requests

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Base exception for API errors"""
    pass


class RateLimitError(APIError):
    """Raised when API rate limit is exceeded"""
    pass


class AuthenticationError(APIError):
    """Raised when API authentication fails"""
    pass


class NotFoundError(APIError):
    """Raised when requested resource is not found"""
    pass


def handle_api_errors(
    source_name: str,
    default_return: Any = None,
    log_level: str = "error",
    raise_on_auth_error: bool = True
):
    """
    Decorator for consistent API error handling

    Args:
        source_name: Name of the data source (e.g., "StockTwits", "YouTube")
        default_return: Value to return on error (default: None)
        log_level: Logging level for errors ("error", "warning", "debug")
        raise_on_auth_error: Whether to re-raise authentication errors

    Usage:
        @handle_api_errors("StockTwits", default_return={})
        def get_data(self, symbol: str):
            # API call code here
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)

            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response else None

                # Handle specific HTTP status codes
                if status_code == 401 or status_code == 403:
                    error_msg = f"{source_name} authentication failed (HTTP {status_code})"
                    logger.error(error_msg)
                    if raise_on_auth_error:
                        raise AuthenticationError(error_msg) from e

                elif status_code == 404:
                    error_msg = f"{source_name} resource not found (HTTP 404)"
                    logger.warning(error_msg)
                    return default_return

                elif status_code == 429:
                    error_msg = f"{source_name} rate limit exceeded (HTTP 429)"
                    logger.warning(error_msg)
                    raise RateLimitError(error_msg) from e

                else:
                    error_msg = f"{source_name} HTTP error: {e}"
                    _log_message(log_level, error_msg)
                    return default_return

            except requests.exceptions.Timeout as e:
                error_msg = f"{source_name} request timeout: {e}"
                _log_message(log_level, error_msg)
                return default_return

            except requests.exceptions.ConnectionError as e:
                error_msg = f"{source_name} connection error: {e}"
                _log_message(log_level, error_msg)
                return default_return

            except requests.exceptions.RequestException as e:
                error_msg = f"{source_name} request failed: {e}"
                _log_message(log_level, error_msg)
                return default_return

            except ValueError as e:
                error_msg = f"{source_name} data parsing error: {e}"
                _log_message(log_level, error_msg)
                return default_return

            except Exception as e:
                error_msg = f"{source_name} unexpected error ({type(e).__name__}): {e}"
                logger.error(error_msg, exc_info=True)
                return default_return

        return wrapper
    return decorator


def _log_message(level: str, message: str):
    """Helper to log at specified level"""
    if level == "error":
        logger.error(message)
    elif level == "warning":
        logger.warning(message)
    elif level == "debug":
        logger.debug(message)
    else:
        logger.info(message)


def safe_get(data: dict, *keys, default=None):
    """
    Safely get nested dictionary values

    Args:
        data: Dictionary to search
        *keys: Sequence of keys to traverse
        default: Default value if key not found

    Returns:
        Value at nested key path, or default if not found

    Examples:
        >>> data = {'a': {'b': {'c': 123}}}
        >>> safe_get(data, 'a', 'b', 'c')
        123
        >>> safe_get(data, 'a', 'x', 'y', default=0)
        0
    """
    result = data
    for key in keys:
        if isinstance(result, dict):
            result = result.get(key)
            if result is None:
                return default
        else:
            return default
    return result if result is not None else default


def parse_timestamp(
    timestamp_str: str,
    formats: Optional[List[str]] = None,
    default: Optional[datetime] = None
) -> Optional[datetime]:
    """
    Parse timestamp string with multiple format attempts

    Args:
        timestamp_str: Timestamp string to parse
        formats: List of format strings to try (default: common formats)
        default: Default datetime if parsing fails (default: now)

    Returns:
        Parsed datetime object

    Examples:
        >>> parse_timestamp("2024-01-15T12:30:00Z")
        datetime(2024, 1, 15, 12, 30, 0)
        >>> parse_timestamp("invalid", default=None)
        None
    """
    if default is None:
        default = datetime.now()

    if not timestamp_str or not isinstance(timestamp_str, str):
        return default

    # Default formats to try
    if formats is None:
        formats = [
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]

    # Try ISO format first
    try:
        return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        pass

    # Try each format
    for fmt in formats:
        try:
            return datetime.strptime(timestamp_str, fmt)
        except (ValueError, TypeError):
            continue

    logger.debug(f"Failed to parse timestamp: {timestamp_str}")
    return default


class RetryableRequest:
    """
    Retryable HTTP request with exponential backoff

    Usage:
        request = RetryableRequest(max_retries=3, backoff_factor=2.0)
        response = request.get("https://api.example.com/data")
    """

    def __init__(self, max_retries: int = 3, backoff_factor: float = 1.0, timeout: int = 10):
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.timeout = timeout

    def get(self, url: str, **kwargs) -> requests.Response:
        """GET request with retries"""
        return self._request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        """POST request with retries"""
        return self._request("POST", url, **kwargs)

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Execute request with retries and exponential backoff"""
        kwargs.setdefault('timeout', self.timeout)

        last_exception = None
        for attempt in range(self.max_retries):
            try:
                response = requests.request(method, url, **kwargs)
                response.raise_for_status()
                return response

            except requests.exceptions.RequestException as e:
                last_exception = e

                # Don't retry on client errors (4xx)
                if isinstance(e, requests.exceptions.HTTPError):
                    if e.response and 400 <= e.response.status_code < 500:
                        raise

                # Exponential backoff for retries
                if attempt < self.max_retries - 1:
                    sleep_time = self.backoff_factor * (2 ** attempt)
                    logger.warning(
                        f"Request failed (attempt {attempt + 1}/{self.max_retries}), "
                        f"retrying in {sleep_time}s: {e}"
                    )
                    time.sleep(sleep_time)

        # All retries exhausted
        raise last_exception


if __name__ == '__main__':
    # Test error handling
    print("Testing error handling utilities...")

    # Test safe_get
    data = {'user': {'name': 'John', 'age': 30}, 'status': 'active'}
    assert safe_get(data, 'user', 'name') == 'John'
    assert safe_get(data, 'user', 'email', default='N/A') == 'N/A'
    assert safe_get(data, 'missing', 'key', default=0) == 0
    print("✓ safe_get tests passed")

    # Test parse_timestamp
    ts1 = parse_timestamp("2024-01-15T12:30:00Z")
    assert ts1.year == 2024
    ts2 = parse_timestamp("invalid", default=None)
    assert ts2 is None
    print("✓ parse_timestamp tests passed")

    # Test decorator
    @handle_api_errors("TestAPI", default_return=[])
    def test_func():
        raise ValueError("Test error")

    result = test_func()
    assert result == []
    print("✓ handle_api_errors decorator test passed")

    print("\n✅ All error handling tests passed!")
