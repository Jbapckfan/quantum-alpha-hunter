"""
Concurrent data processing utilities
"""
import concurrent.futures
from typing import List, Callable, Any, Optional
import logging
from tqdm import tqdm

logger = logging.getLogger("qaht.parallel")


def process_concurrently(
    items: List[Any],
    process_func: Callable,
    max_workers: int = 5,
    description: str = "Processing",
    show_progress: bool = True
) -> List[Any]:
    """
    Process items concurrently with progress tracking

    Args:
        items: List of items to process
        process_func: Function to apply to each item
        max_workers: Maximum number of concurrent workers
        description: Description for progress bar
        show_progress: Whether to show progress bar

    Returns:
        List of results (None for failed items)

    Example:
        def fetch_price(symbol):
            return yfinance.download(symbol)

        results = process_concurrently(
            ['AAPL', 'TSLA', 'NVDA'],
            fetch_price,
            max_workers=3,
            description="Fetching prices"
        )
    """
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_item = {executor.submit(process_func, item): item for item in items}

        # Process as they complete
        iterator = concurrent.futures.as_completed(future_to_item)

        if show_progress:
            iterator = tqdm(iterator, total=len(items), desc=description)

        for future in iterator:
            item = future_to_item[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                logger.error(f"Failed processing {item}: {str(e)}")
                results.append(None)

    return results


def batch_process(
    items: List[Any],
    process_func: Callable[[List[Any]], Any],
    batch_size: int = 100,
    max_workers: int = 5,
    description: str = "Batch processing"
) -> List[Any]:
    """
    Process items in batches concurrently

    Useful when the processing function is more efficient with batches
    (e.g., bulk database inserts, batch API calls)

    Args:
        items: List of items to process
        process_func: Function that processes a batch of items
        batch_size: Number of items per batch
        max_workers: Maximum concurrent batches
        description: Description for progress bar

    Returns:
        List of batch results
    """
    # Split items into batches
    batches = [items[i:i + batch_size] for i in range(0, len(items), batch_size)]

    logger.info(f"Processing {len(items)} items in {len(batches)} batches")

    return process_concurrently(
        batches,
        process_func,
        max_workers=max_workers,
        description=description
    )


def parallel_map(
    func: Callable,
    items: List[Any],
    max_workers: Optional[int] = None
) -> List[Any]:
    """
    Simple parallel map implementation

    Args:
        func: Function to map
        items: Items to map over
        max_workers: Maximum workers (defaults to CPU count)

    Returns:
        List of results
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        return list(executor.map(func, items))
