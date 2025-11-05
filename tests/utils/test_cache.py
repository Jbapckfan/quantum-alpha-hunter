"""
Unit tests for caching utilities
"""
import pytest
import time
import json
from pathlib import Path
from qaht.utils.cache import ResponseCache, cached


class TestResponseCache:
    """Tests for ResponseCache class"""

    def setup_method(self):
        """Setup test cache"""
        self.cache = ResponseCache(cache_dir="test_cache", default_ttl=60)

    def teardown_method(self):
        """Cleanup test cache"""
        self.cache.clear()

    def test_initialization(self):
        """Test cache initialization"""
        assert self.cache.cache_dir.exists()
        assert self.cache.default_ttl == 60

    def test_set_and_get(self):
        """Test setting and getting cache values"""
        key = "test_key"
        value = {"data": "test_value"}

        self.cache.set(key, value)
        result = self.cache.get(key)

        assert result == value

    def test_get_missing_key(self):
        """Test getting non-existent key returns None"""
        result = self.cache.get("nonexistent_key")
        assert result is None

    def test_cache_expiration(self):
        """Test cache entries expire after TTL"""
        key = "expire_test"
        value = {"data": "expires"}

        # Set with 1 second TTL
        self.cache.set(key, value, ttl=1)

        # Should exist immediately
        result = self.cache.get(key)
        assert result == value

        # Wait for expiration
        time.sleep(1.1)

        # Should be expired now
        result = self.cache.get(key)
        assert result is None

    def test_cache_key_generation(self):
        """Test cache key generation from arguments"""
        key1 = self.cache._generate_key("arg1", "arg2", kwarg1="value1")
        key2 = self.cache._generate_key("arg1", "arg2", kwarg1="value1")
        key3 = self.cache._generate_key("arg1", "arg3", kwarg1="value1")

        # Same arguments should generate same key
        assert key1 == key2

        # Different arguments should generate different key
        assert key1 != key3

    def test_clear_cache(self):
        """Test clearing all cache entries"""
        self.cache.set("key1", "value1")
        self.cache.set("key2", "value2")
        self.cache.set("key3", "value3")

        self.cache.clear()

        assert self.cache.get("key1") is None
        assert self.cache.get("key2") is None
        assert self.cache.get("key3") is None

    def test_cleanup_expired(self):
        """Test cleanup of expired entries"""
        # Add some entries with different TTLs
        self.cache.set("key1", "value1", ttl=1)  # Expires soon
        self.cache.set("key2", "value2", ttl=3600)  # Long TTL
        self.cache.set("key3", "value3", ttl=1)  # Expires soon

        # Wait for short TTL entries to expire
        time.sleep(1.1)

        # Cleanup expired
        removed = self.cache.cleanup_expired()

        assert removed == 2
        assert self.cache.get("key1") is None
        assert self.cache.get("key2") is not None  # Should still exist
        assert self.cache.get("key3") is None

    def test_cache_different_types(self):
        """Test caching different data types"""
        # Dictionary
        self.cache.set("dict", {"key": "value"})
        assert self.cache.get("dict") == {"key": "value"}

        # List
        self.cache.set("list", [1, 2, 3])
        assert self.cache.get("list") == [1, 2, 3]

        # String
        self.cache.set("string", "test")
        assert self.cache.get("string") == "test"

        # Number
        self.cache.set("number", 42)
        assert self.cache.get("number") == 42

        # Boolean
        self.cache.set("bool", True)
        assert self.cache.get("bool") is True

    def test_cache_overwrites_existing(self):
        """Test that setting a key overwrites existing value"""
        key = "overwrite_test"

        self.cache.set(key, "original")
        assert self.cache.get(key) == "original"

        self.cache.set(key, "updated")
        assert self.cache.get(key) == "updated"


class TestCachedDecorator:
    """Tests for @cached decorator"""

    def setup_method(self):
        """Setup for decorator tests"""
        self.call_count = 0

    def teardown_method(self):
        """Cleanup test cache"""
        cache_dir = Path("cache")
        if cache_dir.exists():
            for f in cache_dir.glob("*.json"):
                f.unlink()

    def test_decorator_caches_result(self):
        """Test decorator caches function results"""
        @cached(ttl=60)
        def test_func(x):
            self.call_count += 1
            return x * 2

        # First call should execute function
        result1 = test_func(5)
        assert result1 == 10
        assert self.call_count == 1

        # Second call should use cache
        result2 = test_func(5)
        assert result2 == 10
        assert self.call_count == 1  # Not called again

    def test_decorator_different_args(self):
        """Test decorator handles different arguments"""
        @cached(ttl=60)
        def test_func(x, y):
            self.call_count += 1
            return x + y

        result1 = test_func(1, 2)
        assert result1 == 3
        assert self.call_count == 1

        # Same args should use cache
        result2 = test_func(1, 2)
        assert result2 == 3
        assert self.call_count == 1

        # Different args should execute function
        result3 = test_func(2, 3)
        assert result3 == 5
        assert self.call_count == 2

    def test_decorator_with_kwargs(self):
        """Test decorator with keyword arguments"""
        @cached(ttl=60)
        def test_func(x, y=10):
            self.call_count += 1
            return x + y

        result1 = test_func(5, y=10)
        assert result1 == 15
        assert self.call_count == 1

        # Same kwargs should use cache
        result2 = test_func(5, y=10)
        assert result2 == 15
        assert self.call_count == 1

    def test_decorator_expiration(self):
        """Test decorator respects TTL"""
        @cached(ttl=1)  # 1 second TTL
        def test_func(x):
            self.call_count += 1
            return x * 2

        # First call
        result1 = test_func(5)
        assert result1 == 10
        assert self.call_count == 1

        # Wait for expiration
        time.sleep(1.1)

        # Should execute again after expiration
        result2 = test_func(5)
        assert result2 == 10
        assert self.call_count == 2

    def test_decorator_skip_none_results(self):
        """Test decorator doesn't cache None results"""
        @cached(ttl=60)
        def test_func(x):
            self.call_count += 1
            return None if x < 0 else x * 2

        # None result should not be cached
        result1 = test_func(-1)
        assert result1 is None
        assert self.call_count == 1

        result2 = test_func(-1)
        assert result2 is None
        assert self.call_count == 2  # Called again (not cached)

    def test_decorator_skip_empty_results(self):
        """Test decorator doesn't cache empty collections"""
        @cached(ttl=60)
        def test_func(x):
            self.call_count += 1
            return [] if x < 0 else [x, x*2]

        # Empty list should not be cached
        result1 = test_func(-1)
        assert result1 == []
        assert self.call_count == 1

        result2 = test_func(-1)
        assert result2 == []
        assert self.call_count == 2  # Called again

        # Non-empty list should be cached
        result3 = test_func(5)
        assert result3 == [5, 10]
        assert self.call_count == 3

        result4 = test_func(5)
        assert result4 == [5, 10]
        assert self.call_count == 3  # Cached

    def test_cache_control_methods(self):
        """Test cache control methods on decorated function"""
        @cached(ttl=60)
        def test_func(x):
            self.call_count += 1
            return x * 2

        # Call function
        test_func(5)
        assert self.call_count == 1

        # Should use cache
        test_func(5)
        assert self.call_count == 1

        # Clear cache
        test_func.clear_cache()

        # Should execute again after cache clear
        test_func(5)
        assert self.call_count == 2


@pytest.mark.integration
class TestCacheIntegration:
    """Integration tests for cache usage"""

    def teardown_method(self):
        """Cleanup"""
        cache_dir = Path("test_cache")
        if cache_dir.exists():
            for f in cache_dir.glob("*.json"):
                f.unlink()

    def test_cache_api_response_pattern(self):
        """Test caching API response pattern"""
        call_count = 0

        @cached(ttl=60, cache_dir="test_cache")
        def fetch_api_data(symbol: str):
            nonlocal call_count
            call_count += 1
            # Simulate API call
            return {
                'symbol': symbol,
                'price': 100.00,
                'timestamp': time.time()
            }

        # First call - cache miss
        data1 = fetch_api_data('AAPL')
        assert data1['symbol'] == 'AAPL'
        assert call_count == 1

        # Second call - cache hit
        data2 = fetch_api_data('AAPL')
        assert data2['symbol'] == 'AAPL'
        assert call_count == 1  # Not called again
        assert data1 == data2  # Same cached data

        # Different symbol - cache miss
        data3 = fetch_api_data('GOOGL')
        assert data3['symbol'] == 'GOOGL'
        assert call_count == 2
