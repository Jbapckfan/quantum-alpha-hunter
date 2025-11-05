"""
Response caching utilities for API clients

Provides intelligent caching to reduce API calls and improve performance.
"""
import hashlib
import json
import time
import logging
from typing import Optional, Any, Callable
from pathlib import Path
from functools import wraps
from datetime import datetime

logger = logging.getLogger(__name__)


class ResponseCache:
    """
    Simple file-based cache for API responses.

    Features:
    - TTL (time-to-live) support
    - Automatic cleanup of expired entries
    - Thread-safe operations
    - Configurable cache directory
    """

    def __init__(self, cache_dir: str = "cache", default_ttl: int = 3600):
        """
        Initialize response cache.

        Args:
            cache_dir: Directory to store cache files
            default_ttl: Default time-to-live in seconds (default: 1 hour)
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.default_ttl = default_ttl

    def _generate_key(self, *args, **kwargs) -> str:
        """Generate cache key from function arguments."""
        # Create a unique key from arguments
        key_data = {
            'args': args,
            'kwargs': kwargs
        }
        key_string = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_string.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """
        Get cached value.

        Args:
            key: Cache key

        Returns:
            Cached value if valid, None otherwise
        """
        cache_file = self.cache_dir / f"{key}.json"

        if not cache_file.exists():
            return None

        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)

            # Check if expired
            expires_at = cache_data.get('expires_at', 0)
            if time.time() > expires_at:
                logger.debug(f"Cache expired for key: {key}")
                cache_file.unlink()  # Delete expired cache
                return None

            logger.debug(f"Cache hit for key: {key}")
            return cache_data.get('value')

        except Exception as e:
            logger.warning(f"Error reading cache: {e}")
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Set cached value.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (uses default if None)
        """
        cache_file = self.cache_dir / f"{key}.json"
        ttl = ttl or self.default_ttl

        cache_data = {
            'value': value,
            'cached_at': time.time(),
            'expires_at': time.time() + ttl
        }

        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f)
            logger.debug(f"Cached value for key: {key} (TTL: {ttl}s)")
        except Exception as e:
            logger.warning(f"Error writing cache: {e}")

    def clear(self) -> None:
        """Clear all cache entries."""
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                cache_file.unlink()
            except Exception as e:
                logger.warning(f"Error deleting cache file {cache_file}: {e}")
        logger.info("Cache cleared")

    def cleanup_expired(self) -> int:
        """
        Remove expired cache entries.

        Returns:
            Number of entries removed
        """
        removed = 0
        current_time = time.time()

        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)

                expires_at = cache_data.get('expires_at', 0)
                if current_time > expires_at:
                    cache_file.unlink()
                    removed += 1

            except Exception as e:
                logger.warning(f"Error checking cache file {cache_file}: {e}")

        if removed > 0:
            logger.info(f"Cleaned up {removed} expired cache entries")

        return removed


def cached(ttl: int = 3600, cache_dir: str = "cache"):
    """
    Decorator to cache function results.

    Args:
        ttl: Time-to-live in seconds (default: 1 hour)
        cache_dir: Directory to store cache files

    Usage:
        @cached(ttl=1800)  # Cache for 30 minutes
        def get_stock_data(symbol: str):
            return fetch_data(symbol)
    """
    cache = ResponseCache(cache_dir=cache_dir, default_ttl=ttl)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key from function name and arguments
            key_data = f"{func.__module__}.{func.__name__}"
            cache_key = cache._generate_key(key_data, *args, **kwargs)

            # Try to get from cache
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value

            # Call function and cache result
            result = func(*args, **kwargs)

            # Only cache non-None, non-empty results
            if result is not None:
                if isinstance(result, (dict, list)):
                    if result:  # Only cache if not empty
                        cache.set(cache_key, result, ttl)
                else:
                    cache.set(cache_key, result, ttl)

            return result

        # Add cache control methods to wrapper
        wrapper.cache = cache
        wrapper.clear_cache = cache.clear
        wrapper.cleanup_cache = cache.cleanup_expired

        return wrapper

    return decorator


# Example usage:
if __name__ == '__main__':
    print("="*80)
    print("🗄️  Response Cache Examples")
    print("="*80)
    print()

    # Example 1: Basic cache usage
    cache = ResponseCache(cache_dir="test_cache", default_ttl=60)

    # Set and get
    cache.set("test_key", {"data": "value"})
    result = cache.get("test_key")
    print(f"Cached value: {result}")

    # Example 2: Using decorator
    @cached(ttl=300)  # Cache for 5 minutes
    def expensive_operation(param: str):
        print(f"  [Executing expensive operation with param: {param}]")
        return {"result": f"processed_{param}"}

    print("\nFirst call (cache miss):")
    result1 = expensive_operation("test")
    print(f"Result: {result1}")

    print("\nSecond call (cache hit):")
    result2 = expensive_operation("test")
    print(f"Result: {result2}")

    print("\nDifferent parameter (cache miss):")
    result3 = expensive_operation("other")
    print(f"Result: {result3}")

    print()
    print("="*80)
