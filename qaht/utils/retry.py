"""
Retry logic with exponential backoff and jitter
Handles transient API failures gracefully
"""
import random
import time
import logging
from functools import wraps
from typing import Callable, Tuple, Type

logger = logging.getLogger("qaht.retry")


def retry_with_backoff(
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 60.0,
    jitter: bool = True
):
    """
    Decorator that retries a function with exponential backoff

    Args:
        exceptions: Tuple of exception types to catch
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        backoff_factor: Multiplier for delay after each retry
        max_delay: Maximum delay between retries
        jitter: Add randomness to delay (±20%)

    Example:
        @retry_with_backoff(max_retries=3, initial_delay=2.0)
        def fetch_data():
            return requests.get("https://api.example.com/data").json()
    """

    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)

                except exceptions as e:
                    if attempt == max_retries:
                        logger.error(
                            f"Final attempt {attempt + 1} failed for {func.__name__}: {str(e)}"
                        )
                        raise

                    # Add jitter to prevent thundering herd (±20%)
                    actual_delay = delay
                    if jitter:
                        actual_delay = delay * (1 + 0.2 * (random.random() - 0.5))

                    # Handle HTTP rate limits with Retry-After header
                    if hasattr(e, 'response') and e.response is not None:
                        retry_after = e.response.headers.get('Retry-After')
                        if retry_after:
                            try:
                                actual_delay = float(retry_after)
                                logger.info(f"Respecting Retry-After: {actual_delay}s")
                            except (ValueError, TypeError):
                                pass

                    logger.warning(
                        f"Attempt {attempt + 1}/{max_retries} failed for {func.__name__}: "
                        f"{str(e)}. Retrying in {actual_delay:.1f}s..."
                    )

                    time.sleep(actual_delay)
                    delay = min(delay * backoff_factor, max_delay)

            return None

        return wrapper

    return decorator


def safe_execute(func: Callable, default=None, log_errors: bool = True):
    """
    Execute a function and return default value on error

    Args:
        func: Function to execute
        default: Default value to return on error
        log_errors: Whether to log errors

    Returns:
        Function result or default value
    """
    try:
        return func()
    except Exception as e:
        if log_errors:
            logger.error(f"Error in {func.__name__}: {str(e)}")
        return default
