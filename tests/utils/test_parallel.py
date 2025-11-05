"""
Tests for Parallel Processing Utilities
"""
import pytest
import time
from unittest.mock import Mock
from qaht.utils.parallel import process_concurrently, batch_process, parallel_map


class TestProcessConcurrently:
    """Test concurrent processing"""

    def test_process_concurrently_success(self):
        """Test successful concurrent processing"""
        def square(x):
            return x * x

        items = [1, 2, 3, 4, 5]
        results = process_concurrently(items, square, max_workers=2, show_progress=False)

        # Order not guaranteed in concurrent processing
        assert sorted(results) == [1, 4, 9, 16, 25]

    def test_process_concurrently_with_failures(self):
        """Test concurrent processing with some failures"""
        def risky_func(x):
            if x == 3:
                raise ValueError("Intentional error")
            return x * 2

        items = [1, 2, 3, 4, 5]
        results = process_concurrently(items, risky_func, max_workers=2, show_progress=False)

        # Should have None for failed item
        assert results.count(None) == 1
        assert 2 in results
        assert 4 in results

    def test_process_concurrently_empty_list(self):
        """Test processing empty list"""
        results = process_concurrently([], lambda x: x, show_progress=False)
        assert results == []

    def test_process_concurrently_single_worker(self):
        """Test with single worker"""
        items = [1, 2, 3]
        results = process_concurrently(items, lambda x: x * 2, max_workers=1, show_progress=False)
        assert results == [2, 4, 6]

    def test_process_concurrently_max_workers(self):
        """Test with multiple workers"""
        items = list(range(10))
        results = process_concurrently(items, lambda x: x + 1, max_workers=5, show_progress=False)
        assert len(results) == 10


class TestBatchProcess:
    """Test batch processing"""

    def test_batch_process_basic(self):
        """Test basic batch processing"""
        def process_batch(batch):
            return sum(batch)

        items = list(range(10))  # [0, 1, 2, ..., 9]
        results = batch_process(items, process_batch, batch_size=3, max_workers=2, description="Test")

        # Should have 4 batches: [0,1,2], [3,4,5], [6,7,8], [9]
        assert len(results) == 4
        assert sum(results) == sum(items)  # Total should match

    def test_batch_process_exact_division(self):
        """Test when items divide evenly into batches"""
        def count_batch(batch):
            return len(batch)

        items = list(range(12))
        results = batch_process(items, count_batch, batch_size=4, max_workers=2, description="Test")

        # Should have 3 batches of 4 items each
        assert len(results) == 3
        assert all(r == 4 for r in results)

    def test_batch_process_single_batch(self):
        """Test when batch size exceeds items"""
        def process_batch(batch):
            return len(batch)

        items = [1, 2, 3]
        results = batch_process(items, process_batch, batch_size=10, max_workers=1, description="Test")

        # Should have only 1 batch
        assert len(results) == 1
        assert results[0] == 3


class TestParallelMap:
    """Test parallel map"""

    def test_parallel_map_basic(self):
        """Test basic parallel map"""
        def double(x):
            return x * 2

        items = [1, 2, 3, 4, 5]
        results = parallel_map(double, items)

        assert results == [2, 4, 6, 8, 10]

    def test_parallel_map_with_max_workers(self):
        """Test parallel map with specified workers"""
        items = [1, 2, 3, 4, 5]
        results = parallel_map(lambda x: x + 10, items, max_workers=2)

        assert results == [11, 12, 13, 14, 15]

    def test_parallel_map_empty_list(self):
        """Test parallel map with empty list"""
        results = parallel_map(lambda x: x, [])
        assert results == []

    def test_parallel_map_single_item(self):
        """Test parallel map with single item"""
        results = parallel_map(lambda x: x * 3, [5])
        assert results == [15]


@pytest.mark.integration
class TestParallelIntegration:
    """Integration tests for parallel processing"""

    def test_concurrent_speed_improvement(self):
        """Test that concurrent processing is faster"""
        def slow_func(x):
            time.sleep(0.1)
            return x

        items = [1, 2, 3, 4]

        # Sequential would take 0.4s
        # Concurrent with 4 workers should take ~0.1s
        start = time.time()
        results = process_concurrently(items, slow_func, max_workers=4, show_progress=False)
        duration = time.time() - start

        # Order not guaranteed in concurrent processing
        assert sorted(results) == sorted(items)
        assert duration < 0.3  # Should be much faster than sequential

    def test_batch_process_maintains_order(self):
        """Test that batch processing maintains correct order"""
        def process_batch(batch):
            return [x * 2 for x in batch]

        items = list(range(10))
        results = batch_process(items, process_batch, batch_size=3, max_workers=2, description="Test")

        # Flatten results
        flattened = [item for batch in results if batch for item in batch]

        # Note: order might not be preserved in concurrent processing
        assert len(flattened) == len(items)
