"""
Daily pipeline for crypto vertical
"""
import logging
from typing import List, Optional
import time
from datetime import datetime

from ...config import get_config
from ...db import init_db
from ...utils.parallel import process_concurrently
from ...logging_conf import setup_logging

from ..adapters.spot_coingecko import fetch_and_upsert_crypto
from ..adapters.futures_binance import fetch_and_upsert_futures
from ...equities_options.adapters.reddit_praw import fetch_and_upsert_reddit
from ...equities_options.features.tech import upsert_factors_for_symbol
from ...equities_options.features.social import compute_social_delta
from ...backtest.labeler import label_explosions
from ...scoring.ridge_model import train_and_score

logger = setup_logging()
config = get_config()


def run(universe_csv: Optional[str] = None) -> dict:
    """
    Run complete crypto pipeline

    Args:
        universe_csv: Path to symbol universe file

    Returns:
        Pipeline execution summary
    """
    start_time = time.time()
    steps = {}

    # Initialize database
    init_db()

    # Load crypto symbols
    if universe_csv:
        with open(universe_csv) as f:
            symbols = [line.strip().upper() for line in f if line.strip() and not line.startswith("#")]
    else:
        all_symbols = config.get_universe_symbols()
        # Filter to crypto only (symbols ending in -USD or known crypto)
        symbols = [s.replace('-USD', '') for s in all_symbols if '-USD' in s or s in ['BTC', 'ETH', 'SOL', 'DOGE', 'SHIB']]

    logger.info(f"Starting crypto pipeline with {len(symbols)} symbols")

    # Step 1: Fetch spot prices
    step_start = time.time()
    logger.info("Fetching crypto prices from CoinGecko...")

    try:
        price_count = fetch_and_upsert_crypto(symbols, days=90)
        logger.info(f"Fetched {price_count} price rows")
    except Exception as e:
        logger.error(f"Price ingestion failed: {e}")

    steps['price_ingestion'] = time.time() - step_start

    # Step 2: Fetch futures data (funding rates, OI)
    step_start = time.time()
    logger.info("Fetching futures metrics from Binance...")

    try:
        futures_count = fetch_and_upsert_futures(symbols)
        logger.info(f"Fetched futures data for {futures_count} symbols")
    except Exception as e:
        logger.error(f"Futures ingestion failed: {e}")

    steps['futures_ingestion'] = time.time() - step_start

    # Step 3: Fetch social data
    step_start = time.time()
    logger.info("Fetching Reddit mentions...")

    try:
        social_count = fetch_and_upsert_reddit(symbols, asset_type='crypto')
        logger.info(f"Fetched social data for {social_count} symbols")
    except Exception as e:
        logger.error(f"Social ingestion failed: {e}")

    steps['social_ingestion'] = time.time() - step_start

    # Step 4: Compute technical features
    step_start = time.time()
    logger.info("Computing technical features...")

    def compute_features(symbol):
        try:
            upsert_factors_for_symbol(symbol)
            compute_social_delta(symbol, window=7)
        except Exception as e:
            logger.error(f"Failed to compute features for {symbol}: {e}")

    process_concurrently(
        symbols,
        compute_features,
        max_workers=config.pipeline.max_concurrent,
        description="Computing features",
        show_progress=False
    )

    steps['feature_computation'] = time.time() - step_start

    # Step 5: Label explosions
    step_start = time.time()
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
        description="Labeling",
        show_progress=False
    )

    steps['labeling'] = time.time() - step_start

    # Step 6: Train and score
    step_start = time.time()
    logger.info("Training model and generating scores...")

    try:
        scores = train_and_score(symbols, asset_type='crypto')
        if scores is not None:
            logger.info(f"Scored {len(scores)} symbols")
    except Exception as e:
        logger.error(f"Scoring failed: {e}")

    steps['scoring'] = time.time() - step_start

    # Generate summary
    total_duration = time.time() - start_time
    summary = {
        'total_duration': total_duration,
        'steps': steps,
        'timestamp': datetime.utcnow().isoformat()
    }

    logger.info(f"Crypto pipeline completed in {total_duration:.2f}s")

    return summary
