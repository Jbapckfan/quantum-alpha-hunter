"""
Daily pipeline for equities/options vertical
Orchestrates: data fetch → features → labels → scoring
"""
import logging
from typing import List, Optional
import time
from datetime import datetime

from ...config import get_config
from ...db import init_db
from ...utils.parallel import process_concurrently
from ...logging_conf import setup_logging

from ..adapters.prices_yahoo import fetch_and_upsert
from ..adapters.reddit_praw import fetch_and_upsert_reddit
from ..features.tech import upsert_factors_for_symbol
from ..features.social import compute_social_delta
from ...backtest.labeler import label_explosions
from ...scoring.ridge_model import train_and_score

logger = setup_logging()
config = get_config()


class PipelineMonitor:
    """Track pipeline execution time"""

    def __init__(self):
        self.start_time = time.time()
        self.steps = {}

    def start_step(self, name: str):
        self.steps[name] = {'start': time.time()}

    def end_step(self, name: str):
        if name in self.steps:
            self.steps[name]['end'] = time.time()
            self.steps[name]['duration'] = self.steps[name]['end'] - self.steps[name]['start']

    def get_summary(self) -> dict:
        total_duration = time.time() - self.start_time
        return {
            'total_duration': total_duration,
            'steps': self.steps,
            'timestamp': datetime.utcnow().isoformat()
        }


def run(universe_csv: Optional[str] = None) -> dict:
    """
    Run complete equities/options pipeline

    Args:
        universe_csv: Path to symbol universe file

    Returns:
        Pipeline execution summary
    """
    monitor = PipelineMonitor()

    # Initialize database
    init_db()

    # Load symbols
    if universe_csv:
        with open(universe_csv) as f:
            symbols = [line.strip().upper() for line in f if line.strip() and not line.startswith("#")]
    else:
        symbols = config.get_universe_symbols()
        # Filter to stocks only (remove crypto symbols)
        symbols = [s for s in symbols if not s.endswith('-USD')]

    logger.info(f"Starting equities pipeline with {len(symbols)} symbols")

    # Step 1: Fetch price data
    monitor.start_step("price_ingestion")
    logger.info("Fetching prices from Yahoo Finance...")

    try:
        row_count = fetch_and_upsert(
            symbols,
            period=f"{config.pipeline.lookback_days}d"
        )
        logger.info(f"Fetched {row_count} price rows")
    except Exception as e:
        logger.error(f"Price ingestion failed: {e}")

    monitor.end_step("price_ingestion")

    # Step 2: Fetch social data
    monitor.start_step("social_ingestion")
    logger.info("Fetching Reddit mentions...")

    try:
        social_count = fetch_and_upsert_reddit(symbols, asset_type='stock')
        logger.info(f"Fetched social data for {social_count} symbols")
    except Exception as e:
        logger.error(f"Social ingestion failed: {e}")

    monitor.end_step("social_ingestion")

    # Step 3: Compute technical features
    monitor.start_step("technical_features")
    logger.info("Computing technical features...")

    def compute_tech_features(symbol):
        try:
            upsert_factors_for_symbol(symbol)
        except Exception as e:
            logger.error(f"Failed to compute features for {symbol}: {e}")

    process_concurrently(
        symbols,
        compute_tech_features,
        max_workers=config.pipeline.max_concurrent,
        description="Computing technical features",
        show_progress=False
    )

    monitor.end_step("technical_features")

    # Step 4: Compute social features
    monitor.start_step("social_features")
    logger.info("Computing social deltas...")

    def compute_social_features(symbol):
        try:
            compute_social_delta(symbol, window=7)
        except Exception as e:
            logger.error(f"Failed to compute social features for {symbol}: {e}")

    process_concurrently(
        symbols,
        compute_social_features,
        max_workers=config.pipeline.max_concurrent,
        description="Computing social features",
        show_progress=False
    )

    monitor.end_step("social_features")

    # Step 5: Label explosions
    monitor.start_step("labeling")
    logger.info("Labeling explosive moves...")

    def label_symbol(symbol):
        try:
            label_explosions(symbol, horizon=10)
        except Exception as e:
            logger.error(f"Failed to label {symbol}: {e}")

    process_concurrently(
        symbols,
        label_symbol,
        max_workers=config.pipeline.max_concurrent,
        description="Labeling explosions",
        show_progress=False
    )

    monitor.end_step("labeling")

    # Step 6: Train model and score
    monitor.start_step("scoring")
    logger.info("Training model and generating scores...")

    try:
        scores = train_and_score(symbols, asset_type='stock')
        if scores is not None:
            logger.info(f"Scored {len(scores)} symbols")
    except Exception as e:
        logger.error(f"Scoring failed: {e}")

    monitor.end_step("scoring")

    # Generate summary
    summary = monitor.get_summary()
    logger.info(f"Equities pipeline completed in {summary['total_duration']:.2f}s")

    return summary
