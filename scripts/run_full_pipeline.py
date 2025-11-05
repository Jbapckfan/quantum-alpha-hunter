"""
Run complete Quantum Alpha Hunter pipeline
Both equities and crypto
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from qaht.equities_options.pipeline.daily_job import run as run_equities
from qaht.crypto.pipeline.daily_job import run as run_crypto
from qaht.logging_conf import setup_logging

logger = setup_logging()


def main():
    logger.info("=" * 60)
    logger.info("Quantum Alpha Hunter - Full Pipeline")
    logger.info("=" * 60)

    # Run equities
    logger.info("\n📊 Running equities/options pipeline...")
    equities_summary = run_equities()

    # Run crypto
    logger.info("\n₿  Running crypto pipeline...")
    crypto_summary = run_crypto()

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Pipeline Complete!")
    logger.info(f"Equities: {equities_summary['total_duration']:.2f}s")
    logger.info(f"Crypto: {crypto_summary['total_duration']:.2f}s")
    logger.info(f"Total: {equities_summary['total_duration'] + crypto_summary['total_duration']:.2f}s")
    logger.info("=" * 60)

    logger.info("\nNext steps:")
    logger.info("  1. View results: qaht dashboard")
    logger.info("  2. Analyze symbol: qaht analyze <SYMBOL>")
    logger.info("  3. Check performance: qaht validate")


if __name__ == "__main__":
    main()
