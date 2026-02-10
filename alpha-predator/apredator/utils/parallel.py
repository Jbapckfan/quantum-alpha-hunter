"""Concurrent data processing utilities."""
import concurrent.futures
from typing import List, Callable, Any, Optional
import logging
from tqdm import tqdm

logger = logging.getLogger("apredator.parallel")


def process_concurrently(
    items: List[Any],
    process_func: Callable,
    max_workers: int = 5,
    description: str = "Processing",
    show_progress: bool = True,
) -> List[Any]:
    """Process items concurrently with progress tracking."""
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_item = {executor.submit(process_func, item): item for item in items}
        iterator = concurrent.futures.as_completed(future_to_item)
        if show_progress:
            iterator = tqdm(iterator, total=len(items), desc=description)
        for future in iterator:
            item = future_to_item[future]
            try:
                results.append(future.result())
            except Exception as e:
                logger.error(f"Failed processing {item}: {e}")
                results.append(None)
    return results


def batch_process(
    items: List[Any],
    process_func: Callable[[List[Any]], Any],
    batch_size: int = 100,
    max_workers: int = 5,
    description: str = "Batch processing",
) -> List[Any]:
    """Process items in batches concurrently."""
    batches = [items[i : i + batch_size] for i in range(0, len(items), batch_size)]
    logger.info(f"Processing {len(items)} items in {len(batches)} batches")
    return process_concurrently(batches, process_func, max_workers=max_workers, description=description)


def parallel_map(func: Callable, items: List[Any], max_workers: Optional[int] = None) -> List[Any]:
    """Simple parallel map implementation."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        return list(executor.map(func, items))
