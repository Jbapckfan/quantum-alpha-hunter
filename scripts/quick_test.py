"""
Quick test script - fetch and analyze a few symbols
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from qaht.equities_options.adapters.prices_yahoo import fetch_and_upsert
from qaht.equities_options.features.tech import upsert_factors_for_symbol
from qaht.backtest.labeler import label_explosions, get_explosion_stats
from qaht.scoring.ridge_model import train_and_score
from qaht.logging_conf import setup_logging
from qaht.db import init_db

logger = setup_logging()


def main():
    # Test symbols
    test_symbols = ['AAPL', 'GME', 'TSLA']

    logger.info("Initializing database...")
    init_db()

    logger.info(f"Testing with: {test_symbols}")

    # Fetch prices
    logger.info("Fetching prices...")
    fetch_and_upsert(test_symbols, period="1y")

    # Compute features
    logger.info("Computing features...")
    for symbol in test_symbols:
        upsert_factors_for_symbol(symbol)

    # Label explosions
    logger.info("Labeling explosions...")
    for symbol in test_symbols:
        label_explosions(symbol)

    # Get stats
    get_explosion_stats(test_symbols)

    # Train and score
    logger.info("Training and scoring...")
    scores = train_and_score(test_symbols, asset_type='stock')

    if scores is not None:
        logger.info("\nScores:")
        logger.info(scores[['symbol', 'quantum_score', 'conviction_level']])

    logger.info("\n✅ Test complete!")


if __name__ == "__main__":
    main()
