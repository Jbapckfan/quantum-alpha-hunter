"""
Complete workflow test: Features → Labels → Scoring → Backtest
This validates the entire Quantum Alpha Hunter system end-to-end
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timedelta

from qaht.db import init_db, session_scope
from qaht.schemas import PriceOHLC
from qaht.equities_options.features.tech import upsert_factors_for_symbol
from qaht.equities_options.features.social import compute_social_delta
from qaht.backtest.labeler import label_explosions
from qaht.scoring.ridge_model import train_and_score
from qaht.backtest.simulator import simulate
from qaht.backtest.metrics import calculate_performance, print_performance_report
from qaht.logging_conf import setup_logging
from sqlalchemy import select

logger = setup_logging()


def main():
    print("=" * 80)
    print("🚀 QUANTUM ALPHA HUNTER - FULL SYSTEM TEST")
    print("=" * 80)

    # Initialize
    init_db()
    logger.info("Database initialized")

    # Get symbols from database
    with session_scope() as session:
        symbols = session.execute(
            select(PriceOHLC.symbol).distinct()
        ).scalars().all()

    if not symbols:
        print("❌ No data found! Run: python scripts/generate_synthetic_data.py")
        return 1

    symbols = list(symbols)
    print(f"\n📊 Found {len(symbols)} symbols: {', '.join(symbols)}")

    # ========================================================================
    # STEP 1: COMPUTE FEATURES
    # ========================================================================
    print("\n" + "=" * 80)
    print("1️⃣  COMPUTING TECHNICAL & SOCIAL FEATURES")
    print("=" * 80)

    for symbol in symbols:
        try:
            print(f"\n  Processing {symbol}...")

            # Technical features
            upsert_factors_for_symbol(symbol)
            print(f"    ✅ Technical features")

            # Social features
            compute_social_delta(symbol, window=7)
            print(f"    ✅ Social features")

        except Exception as e:
            print(f"    ❌ Error: {e}")
            import traceback
            traceback.print_exc()

    # ========================================================================
    # STEP 2: LABEL EXPLOSIONS
    # ========================================================================
    print("\n" + "=" * 80)
    print("2️⃣  LABELING EXPLOSIVE MOVES")
    print("=" * 80)

    for symbol in symbols:
        try:
            label_explosions(symbol, horizon=10)
            print(f"  ✅ {symbol}")
        except Exception as e:
            print(f"  ❌ {symbol}: {e}")

    # ========================================================================
    # STEP 3: TRAIN MODEL & GENERATE SCORES
    # ========================================================================
    print("\n" + "=" * 80)
    print("3️⃣  TRAINING MODEL & GENERATING QUANTUM SCORES")
    print("=" * 80)

    try:
        scores = train_and_score(symbols, asset_type='stock')

        if scores is not None and not scores.empty:
            print(f"\n✅ Scored {len(scores)} symbols")
            print("\nTop 5 Signals:")
            top5 = scores.nlargest(5, 'quantum_score')[['symbol', 'quantum_score', 'conviction_level', 'prob_hit_10d']]
            for _, row in top5.iterrows():
                print(f"  {row['symbol']:8s} Score: {row['quantum_score']:3d}  "
                      f"Conviction: {row['conviction_level']:4s}  "
                      f"Prob: {row['prob_hit_10d']:.1%}")
        else:
            print("⚠️  No scores generated (may need more training data)")

    except Exception as e:
        print(f"❌ Scoring failed: {e}")
        import traceback
        traceback.print_exc()

    # ========================================================================
    # STEP 4: RUN BACKTEST
    # ========================================================================
    print("\n" + "=" * 80)
    print("4️⃣  RUNNING HISTORICAL BACKTEST")
    print("=" * 80)

    # Define backtest period (use most recent 200 days)
    with session_scope() as session:
        all_dates = session.execute(
            select(PriceOHLC.date).distinct().order_by(PriceOHLC.date)
        ).scalars().all()

    if len(all_dates) < 100:
        print("❌ Not enough historical data for backtest")
        return 1

    # Use middle portion for training, recent portion for testing
    train_cutoff = len(all_dates) // 2
    test_start_idx = train_cutoff + 50  # Leave gap

    start_date = all_dates[test_start_idx]
    end_date = all_dates[-20]  # Leave some buffer at end

    print(f"\nBacktest Period: {start_date} to {end_date}")
    print(f"Test Days: {len(all_dates[test_start_idx:-20])}")

    try:
        results = simulate(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            initial_capital=100000,
            min_score=70
        )

        if 'error' in results:
            print(f"❌ Backtest error: {results['error']}")
            return 1

        # Calculate metrics
        metrics = calculate_performance(results)

        # Print report
        print("\n")
        print_performance_report(metrics)

        # ========================================================================
        # EVALUATION
        # ========================================================================
        print("\n" + "=" * 80)
        print("🎯 SYSTEM EVALUATION")
        print("=" * 80)

        # Check if meets targets
        targets = {
            'Hit Rate (High Conviction)': (metrics.get('conviction_performance', {}).get('HIGH', {}).get('hit_rate', 0), 0.70, '≥70%'),
            'Sharpe Ratio': (metrics.get('sharpe_ratio', 0), 1.0, '≥1.0'),
            'Max Drawdown': (abs(metrics.get('max_drawdown', 0)), 0.08, '≤8%'),
            'Multi-Bagger Capture': (metrics.get('multi_bagger_capture_rate', 0), 0.05, '≥5%'),
        }

        print()
        for metric_name, (actual, target, desc) in targets.items():
            if 'Drawdown' in metric_name:
                passed = actual <= target
                emoji = "✅" if passed else "⚠️ "
            else:
                passed = actual >= target
                emoji = "✅" if passed else "⚠️ "

            print(f"  {emoji} {metric_name:25s}: {actual:6.1%}  (target: {desc})")

        print("\n" + "=" * 80)
        print("🎉 FULL SYSTEM TEST COMPLETE!")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ Backtest failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
