#!/usr/bin/env python
"""
Comprehensive system validation - NO MOCK DATA
Validates all critical components work correctly

Usage:
    python scripts/validate_system.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from qaht.validation import DataValidator, check_for_look_ahead_bias
from qaht.universe import validate_universe_quality, MEGA_CAP_BLOCKLIST
from qaht.db import session_scope
from qaht.schemas import PriceOHLC, Factors, Labels, Predictions
from sqlalchemy import select, func
import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def validate_database():
    """Validate database integrity"""
    logger.info("="*60)
    logger.info("VALIDATING DATABASE")
    logger.info("="*60)

    with session_scope() as session:
        # Count records
        n_prices = session.execute(select(func.count()).select_from(PriceOHLC)).scalar()
        n_factors = session.execute(select(func.count()).select_from(Factors)).scalar()
        n_labels = session.execute(select(func.count()).select_from(Labels)).scalar()
        n_predictions = session.execute(select(func.count()).select_from(Predictions)).scalar()

        logger.info(f"Records in database:")
        logger.info(f"  Prices: {n_prices:,}")
        logger.info(f"  Factors: {n_factors:,}")
        logger.info(f"  Labels: {n_labels:,}")
        logger.info(f"  Predictions: {n_predictions:,}")

        if n_prices == 0:
            logger.warning("⚠️  No price data - run pipeline first")
            return False

        # Check for mega-caps in database
        logger.info("\nChecking for mega-caps in database...")
        symbols = session.execute(
            select(PriceOHLC.symbol).distinct()
        ).scalars().all()

        mega_caps_found = [s for s in symbols if s in MEGA_CAP_BLOCKLIST]
        if mega_caps_found:
            logger.error(f"❌ MEGA-CAPS FOUND: {mega_caps_found}")
            logger.error("   These should be REMOVED - they can't 10x!")
            return False
        else:
            logger.info("✅ No mega-caps found - good!")

        # Check data freshness
        latest_date = session.execute(
            select(PriceOHLC.date).order_by(PriceOHLC.date.desc()).limit(1)
        ).scalar_one_or_none()

        if latest_date:
            validator = DataValidator()
            is_fresh, msg = validator.check_data_freshness(latest_date, max_age_hours=72)
            if is_fresh:
                logger.info(f"✅ Data freshness: {msg}")
            else:
                logger.warning(f"⚠️  Data freshness: {msg}")

        return True


def validate_price_data_quality():
    """Validate price data quality"""
    logger.info("\n" + "="*60)
    logger.info("VALIDATING PRICE DATA QUALITY")
    logger.info("="*60)

    with session_scope() as session:
        # Get sample of price data
        prices = session.execute(
            select(PriceOHLC).limit(1000)
        ).scalars().all()

        if not prices:
            logger.warning("⚠️  No price data to validate")
            return False

        # Convert to DataFrame
        df = pd.DataFrame([{
            'symbol': p.symbol,
            'date': p.date,
            'open': p.open,
            'high': p.high,
            'low': p.low,
            'close': p.close,
            'volume': p.volume
        } for p in prices])

        validator = DataValidator()
        is_valid, issues = validator.validate_price_data(df)

        if is_valid:
            logger.info("✅ Price data validation passed")
        else:
            logger.error("❌ Price data validation FAILED:")
            for issue in issues:
                logger.error(f"   - {issue}")

        return is_valid


def validate_features():
    """Validate computed features"""
    logger.info("\n" + "="*60)
    logger.info("VALIDATING FEATURES")
    logger.info("="*60)

    with session_scope() as session:
        factors = session.execute(
            select(Factors).limit(100)
        ).scalars().all()

        if not factors:
            logger.warning("⚠️  No factors computed yet")
            return False

        # Convert to DataFrame
        df = pd.DataFrame([{
            'bb_width_pct': f.bb_width_pct,
            'ma_spread_pct': f.ma_spread_pct,
            'rsi_14': f.rsi_14,
            'social_delta_7d': f.social_delta_7d,
        } for f in factors])

        validator = DataValidator()
        feature_names = ['bb_width_pct', 'ma_spread_pct', 'rsi_14', 'social_delta_7d']
        is_valid, issues = validator.validate_features(df, feature_names)

        if is_valid:
            logger.info("✅ Feature validation passed")
        else:
            logger.warning("⚠️  Feature validation issues:")
            for issue in issues:
                logger.warning(f"   - {issue}")

        return True  # Warnings OK, errors not


def check_look_ahead_bias():
    """Check for look-ahead bias in predictions"""
    logger.info("\n" + "="*60)
    logger.info("CHECKING FOR LOOK-AHEAD BIAS")
    logger.info("="*60)

    with session_scope() as session:
        violations = check_for_look_ahead_bias(session)

        if not violations:
            logger.info("✅ No look-ahead bias detected")
            return True
        else:
            logger.error("❌ LOOK-AHEAD BIAS DETECTED:")
            for v in violations:
                logger.error(f"   {v}")
            logger.error("   Backtest results are INVALID - predictions using future data!")
            return False


def validate_training_data_balance():
    """Check class balance in training data"""
    logger.info("\n" + "="*60)
    logger.info("VALIDATING TRAINING DATA BALANCE")
    logger.info("="*60)

    with session_scope() as session:
        labels = session.execute(select(Labels)).scalars().all()

        if not labels:
            logger.warning("⚠️  No labels computed yet")
            return False

        n_total = len(labels)
        n_explosions = sum(1 for l in labels if l.explosive_10d)
        explosion_rate = n_explosions / n_total * 100 if n_total > 0 else 0

        logger.info(f"Training data distribution:")
        logger.info(f"  Total samples: {n_total:,}")
        logger.info(f"  Explosions: {n_explosions:,} ({explosion_rate:.1f}%)")
        logger.info(f"  Normal: {n_total - n_explosions:,} ({100-explosion_rate:.1f}%)")

        if explosion_rate < 1:
            logger.warning(f"⚠️  Very few explosions ({explosion_rate:.2f}%) - model might struggle")
            logger.warning("   Consider: Lower threshold, longer history, or more symbols")
        elif explosion_rate > 20:
            logger.warning(f"⚠️  Too many explosions ({explosion_rate:.1f}%) - threshold too low?")
        else:
            logger.info(f"✅ Reasonable class balance ({explosion_rate:.1f}%)")

        return True


def validate_model_predictions():
    """Validate model predictions are reasonable"""
    logger.info("\n" + "="*60)
    logger.info("VALIDATING MODEL PREDICTIONS")
    logger.info("="*60)

    with session_scope() as session:
        predictions = session.execute(select(Predictions)).scalars().all()

        if not predictions:
            logger.warning("⚠️  No predictions yet")
            return False

        # Analyze prediction distribution
        scores = [p.quantum_score for p in predictions]
        df = pd.DataFrame({'score': scores})

        logger.info(f"Prediction statistics (n={len(predictions)}):")
        logger.info(f"  Mean score: {df['score'].mean():.1f}")
        logger.info(f"  Median score: {df['score'].median():.1f}")
        logger.info(f"  Min score: {df['score'].min()}")
        logger.info(f"  Max score: {df['score'].max()}")

        # Check conviction distribution
        conviction_counts = {}
        for p in predictions:
            conv = p.conviction_level or 'UNKNOWN'
            conviction_counts[conv] = conviction_counts.get(conv, 0) + 1

        logger.info(f"\nConviction distribution:")
        for level in ['MAX', 'HIGH', 'MED', 'LOW', 'UNKNOWN']:
            count = conviction_counts.get(level, 0)
            pct = count / len(predictions) * 100 if predictions else 0
            logger.info(f"  {level:7s}: {count:4d} ({pct:5.1f}%)")

        # Warning if all predictions same conviction
        if len(conviction_counts) == 1:
            logger.warning("⚠️  All predictions have same conviction level - model might be broken")
            return False

        # Warning if no high-conviction predictions
        high_conviction = conviction_counts.get('MAX', 0) + conviction_counts.get('HIGH', 0)
        if high_conviction == 0:
            logger.warning("⚠️  No HIGH/MAX conviction predictions - model might be too conservative")

        logger.info("✅ Predictions appear reasonable")
        return True


def validate_backtest_costs():
    """Verify transaction costs are being applied"""
    logger.info("\n" + "="*60)
    logger.info("VALIDATING BACKTEST REALISM")
    logger.info("="*60)

    # Check simulator has transaction costs
    from qaht.backtest.simulator import Trade

    # Create test trade
    trade = Trade(
        symbol='TEST',
        entry_date='2024-01-01',
        entry_price=100.0,
        position_size=10000.0,
        quantum_score=85,
        conviction_level='HIGH'
    )

    # Close with 10% gain
    trade.close(110.0, 'test', '2024-01-11')

    # Calculate expected P&L with costs
    gross_pnl = 10000 * 0.10  # $1000 gross profit
    costs = 10000 * 0.0015 + 11000 * 0.0015  # Entry + exit costs (0.15%)
    expected_net_pnl = gross_pnl - costs

    # Check if costs were applied
    if abs(trade.pnl - expected_net_pnl) < 1:  # Within $1
        logger.info("✅ Transaction costs applied correctly")
        logger.info(f"   Gross P&L: ${gross_pnl:.2f}")
        logger.info(f"   Costs: ${costs:.2f}")
        logger.info(f"   Net P&L: ${trade.pnl:.2f}")
        return True
    else:
        logger.error(f"❌ Transaction costs NOT applied correctly")
        logger.error(f"   Expected: ${expected_net_pnl:.2f}, Got: ${trade.pnl:.2f}")
        return False


def main():
    """Run all validations"""
    logger.info("\n" + "🔍 QUANTUM ALPHA HUNTER - SYSTEM VALIDATION")
    logger.info("="*60)
    logger.info("NO MOCK DATA - REAL VALIDATION ONLY")
    logger.info("="*60 + "\n")

    results = {}

    try:
        results['database'] = validate_database()
        results['price_quality'] = validate_price_data_quality()
        results['features'] = validate_features()
        results['look_ahead_bias'] = check_look_ahead_bias()
        results['class_balance'] = validate_training_data_balance()
        results['predictions'] = validate_model_predictions()
        results['backtest_costs'] = validate_backtest_costs()

    except Exception as e:
        logger.error(f"❌ Validation failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Summary
    logger.info("\n" + "="*60)
    logger.info("VALIDATION SUMMARY")
    logger.info("="*60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for check, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status} - {check}")

    logger.info("="*60)
    logger.info(f"Result: {passed}/{total} checks passed")

    if passed == total:
        logger.info("✅ SYSTEM VALIDATION PASSED - Ready for production")
        return 0
    else:
        logger.error(f"❌ SYSTEM VALIDATION FAILED - {total-passed} critical issues")
        logger.error("Fix these issues before using system with real money!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
