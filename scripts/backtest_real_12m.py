#!/usr/bin/env python
"""
REAL BACKTEST - Last 12 Months
NO MOCK DATA - REAL SIGNALS ONLY

Fetches real data, computes real features, trains real model, shows real results
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    logger.info("="*70)
    logger.info("REAL BACKTEST - LAST 12 MONTHS")
    logger.info("NO MOCK DATA - REAL SIGNALS ONLY")
    logger.info("="*70)

    # Import after logging setup
    from qaht.db import session_scope, init_db
    from qaht.config import load_config
    from qaht.schemas import PriceOHLC, Factors, Labels, Predictions
    from qaht.universe import filter_by_market_cap, MEGA_CAP_BLOCKLIST
    from qaht.equities_options.adapters.prices_yahoo import fetch_prices, upsert_prices
    from qaht.equities_options.features.tech import compute_technical_features
    from qaht.backtest.labeler import label_explosions
    from qaht.scoring.ridge_model import train_model as train_ridge_model
    from qaht.backtest.simulator import simulate
    from qaht.backtest.metrics import calculate_performance
    from qaht.validation import DataValidator
    from sqlalchemy import select

    # Initialize
    config = load_config()
    init_db(config)

    # Date range: Last 12 months + buffer for technical indicators
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 + 60)  # 14 months for indicator calculation

    logger.info(f"Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

    # STEP 1: Build realistic small/mid-cap universe
    logger.info("\n" + "="*70)
    logger.info("STEP 1: BUILDING MULTI-BAGGER UNIVERSE")
    logger.info("="*70)

    # Small/mid-cap stocks with growth potential
    # NO mega-caps (AAPL, TSLA, NVDA blocked)
    small_mid_caps = [
        # Small-cap AI/Tech ($500M - $3B range)
        'SOUN', 'BBAI', 'PATH', 'FROG',

        # Small-cap Clean Energy
        'PLUG', 'FCEL', 'BE', 'CLSK',

        # Small-cap Biotech
        'SAVA', 'OCGN', 'VXRT',

        # Mid-cap Growth ($3B - $10B range)
        'PLTR', 'SOFI', 'HOOD',

        # Emerging sectors
        'COIN', 'MARA', 'RIOT',

        # Crypto (for volatility)
        'BTC-USD', 'ETH-USD', 'SOL-USD'
    ]

    # Verify no mega-caps
    mega_caps_found = [s for s in small_mid_caps if s in MEGA_CAP_BLOCKLIST]
    if mega_caps_found:
        logger.error(f"MEGA-CAPS DETECTED: {mega_caps_found} - REMOVING")
        small_mid_caps = [s for s in small_mid_caps if s not in MEGA_CAP_BLOCKLIST]

    logger.info(f"Universe: {len(small_mid_caps)} small/mid-cap symbols")
    logger.info(f"Symbols: {', '.join(small_mid_caps[:10])}...")

    # STEP 2: Fetch REAL data from Yahoo Finance
    logger.info("\n" + "="*70)
    logger.info("STEP 2: FETCHING REAL DATA (Yahoo Finance)")
    logger.info("="*70)

    try:
        logger.info("Downloading 14 months of price data...")
        df_prices = fetch_prices(small_mid_caps, period="500d")  # ~14 months

        if df_prices.empty:
            logger.error("Failed to fetch price data")
            return 1

        logger.info(f"✅ Fetched {len(df_prices):,} price records")

        # Validate data quality
        validator = DataValidator()
        is_valid, issues = validator.validate_price_data(df_prices)

        if not is_valid:
            logger.error("❌ Price data validation FAILED:")
            for issue in issues:
                logger.error(f"   {issue}")
            return 1
        elif issues:
            logger.warning("⚠️  Data quality warnings:")
            for issue in issues[:5]:  # Show first 5
                logger.warning(f"   {issue}")

        # Upsert to database
        upsert_prices(df_prices)
        logger.info("✅ Data saved to database")

    except Exception as e:
        logger.error(f"❌ Data fetch failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # STEP 3: Compute REAL features
    logger.info("\n" + "="*70)
    logger.info("STEP 3: COMPUTING REAL FEATURES")
    logger.info("="*70)

    symbols_with_features = []

    with session_scope() as session:
        for symbol in small_mid_caps:
            try:
                # Skip crypto for now (different feature set)
                if '-USD' in symbol:
                    continue

                compute_technical_features(symbol)
                symbols_with_features.append(symbol)
                logger.info(f"✅ {symbol}: Features computed")

            except Exception as e:
                logger.warning(f"⚠️  {symbol}: Feature computation failed - {e}")

    logger.info(f"✅ Computed features for {len(symbols_with_features)} symbols")

    # STEP 4: Label REAL explosions
    logger.info("\n" + "="*70)
    logger.info("STEP 4: LABELING REAL EXPLOSIVE MOVES")
    logger.info("="*70)

    total_explosions = 0

    with session_scope() as session:
        for symbol in symbols_with_features:
            try:
                label_explosions(symbol, horizon=10, threshold=0.50)  # 50% threshold for stocks

                # Count explosions
                explosions = session.execute(
                    select(Labels).where(
                        Labels.symbol == symbol,
                        Labels.explosive_10d == True
                    )
                ).scalars().all()

                total_explosions += len(explosions)

                if len(explosions) > 0:
                    logger.info(f"✅ {symbol}: {len(explosions)} explosions detected")

            except Exception as e:
                logger.warning(f"⚠️  {symbol}: Labeling failed - {e}")

    logger.info(f"✅ Found {total_explosions} real explosive events (50%+ moves)")

    if total_explosions == 0:
        logger.warning("⚠️  No explosions found - backtest may have limited signals")

    # STEP 5: Train REAL model
    logger.info("\n" + "="*70)
    logger.info("STEP 5: TRAINING MODEL ON REAL DATA")
    logger.info("="*70)

    try:
        model_dict = train_ridge_model(symbols=symbols_with_features, asset_type='stock')

        if model_dict is None:
            logger.error("❌ Model training failed")
            return 1

        logger.info(f"✅ Model trained on {model_dict['n_samples']} samples")
        logger.info(f"   Best alpha: {model_dict['best_alpha']}")

        # Show top features
        logger.info("   Top 5 features:")
        for feat, importance in list(model_dict['feature_importance'].items())[:5]:
            logger.info(f"      {feat}: {importance:+.4f}")

    except Exception as e:
        logger.error(f"❌ Model training failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # STEP 6: Generate REAL predictions
    logger.info("\n" + "="*70)
    logger.info("STEP 6: GENERATING REAL PREDICTIONS")
    logger.info("="*70)

    from qaht.scoring.ridge_model import score_symbols

    try:
        # Score all symbols with factors
        with session_scope() as session:
            # Get all dates with factors
            dates = session.execute(
                select(Factors.date).distinct().order_by(Factors.date)
            ).scalars().all()

            logger.info(f"Scoring {len(symbols_with_features)} symbols across {len(dates)} dates...")

            total_predictions = 0
            high_conviction_count = 0

            for date in dates:
                # Get factors for this date
                factors_for_date = session.execute(
                    select(Factors).where(Factors.date == date)
                ).scalars().all()

                symbols_to_score = [f.symbol for f in factors_for_date]

                if not symbols_to_score:
                    continue

                # Score
                scores_df = score_symbols(symbols_to_score, model_dict, asset_type='stock')

                # Save predictions
                for _, row in scores_df.iterrows():
                    pred = Predictions(
                        symbol=row['symbol'],
                        date=row['date'],
                        quantum_score=row['quantum_score'],
                        prob_hit_10d=row['prob_hit_10d'],
                        conviction_level=row['conviction_level'],
                        components=str(row['components'])
                    )
                    session.merge(pred)
                    total_predictions += 1

                    if row['conviction_level'] in ['MAX', 'HIGH']:
                        high_conviction_count += 1

            session.commit()

        logger.info(f"✅ Generated {total_predictions} real predictions")
        logger.info(f"   High conviction (80+): {high_conviction_count}")

    except Exception as e:
        logger.error(f"❌ Prediction generation failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # STEP 7: Run REAL backtest
    logger.info("\n" + "="*70)
    logger.info("STEP 7: BACKTESTING WITH REAL SIGNALS")
    logger.info("="*70)

    # Backtest period: Last 12 months only (not training period)
    backtest_start = (end_date - timedelta(days=365)).strftime("%Y-%m-%d")
    backtest_end = end_date.strftime("%Y-%m-%d")

    logger.info(f"Backtest period: {backtest_start} to {backtest_end}")
    logger.info("Parameters:")
    logger.info("  Initial capital: $100,000")
    logger.info("  Min score: 80 (HIGH/MAX conviction only)")
    logger.info("  Position size: 10% ($10,000 per trade)")
    logger.info("  Max positions: 5 concurrent")
    logger.info("  Profit target: 50%")
    logger.info("  Stop loss: -15%")
    logger.info("  Max hold: 14 days")
    logger.info("  Transaction costs: 0.3% round-trip")

    try:
        trades_df = simulate(
            start_date=backtest_start,
            end_date=backtest_end,
            initial_capital=100000,
            min_score=80,  # Only HIGH/MAX conviction
            max_positions=5,
            position_size_pct=0.10,
            profit_target=0.50,  # 50% target
            stop_loss=-0.15,      # -15% stop
            max_hold_days=14,
            symbols=symbols_with_features  # Only symbols we trained on
        )

        if trades_df.empty:
            logger.warning("⚠️  No trades executed during backtest period")
            logger.warning("Possible reasons:")
            logger.warning("  - No high conviction signals (score >= 80)")
            logger.warning("  - Insufficient price data in backtest period")
            logger.warning("  - Model too conservative")
            return 1

        logger.info(f"✅ Backtest complete: {len(trades_df)} trades executed")

    except Exception as e:
        logger.error(f"❌ Backtest failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # STEP 8: Analyze REAL results
    logger.info("\n" + "="*70)
    logger.info("STEP 8: REAL PERFORMANCE ANALYSIS")
    logger.info("="*70)

    try:
        metrics = calculate_performance(trades_df, initial_capital=100000)

        # Display results
        logger.info("\n" + "🎯 BACKTEST RESULTS (REAL DATA)")
        logger.info("="*70)
        logger.info(f"Period: {backtest_start} to {backtest_end}")
        logger.info(f"Strategy: Small/mid-cap multi-bagger detection")
        logger.info("")
        logger.info("TRADE STATISTICS:")
        logger.info(f"  Total Trades: {metrics['total_trades']}")
        logger.info(f"  Winning Trades: {metrics['winning_trades']} ({metrics['hit_rate']*100:.1f}%)")
        logger.info(f"  Losing Trades: {metrics['losing_trades']}")
        logger.info("")
        logger.info("RETURNS (After 0.3% Transaction Costs):")
        logger.info(f"  Average Return: {metrics['avg_return']*100:+.2f}%")
        logger.info(f"  Median Return: {metrics['median_return']*100:+.2f}%")
        logger.info(f"  Average Winner: {metrics['avg_winner']*100:+.2f}%")
        logger.info(f"  Average Loser: {metrics['avg_loser']*100:+.2f}%")
        logger.info("")
        logger.info("PORTFOLIO PERFORMANCE:")
        logger.info(f"  Starting Capital: ${100000:,.2f}")
        logger.info(f"  Final Capital: ${metrics['final_capital']:,.2f}")
        logger.info(f"  Total P&L: ${metrics['total_pnl']:+,.2f}")
        logger.info(f"  Total Return: {metrics['total_return_pct']*100:+.1f}%")
        logger.info("")
        logger.info("RISK METRICS:")
        logger.info(f"  Sharpe Ratio: {metrics['sharpe_ratio']:.2f} (>1.5 = good, >2.0 = excellent)")
        logger.info(f"  Sortino Ratio: {metrics['sortino_ratio']:.2f}")
        logger.info(f"  Max Drawdown: {metrics['max_drawdown']*100:.1f}%")
        logger.info(f"  Profit Factor: {metrics['profit_factor']:.2f} (profit/loss ratio)")
        logger.info("")
        logger.info("TRADING EFFICIENCY:")
        logger.info(f"  Win/Loss Ratio: {metrics['win_loss_ratio']:.2f}x")
        logger.info(f"  Average Hold Time: {metrics['avg_hold_days']:.1f} days")
        logger.info(f"  Expectancy: {metrics['expectancy']*100:+.2f}% per trade")
        logger.info("")

        if metrics['by_conviction']:
            logger.info("PERFORMANCE BY CONVICTION LEVEL:")
            for level in ['MAX', 'HIGH', 'MED']:
                if level in metrics['by_conviction']:
                    stats = metrics['by_conviction'][level]
                    logger.info(
                        f"  {level:4s}: {stats['count']:2d} trades | "
                        f"Hit Rate: {stats['hit_rate']*100:5.1f}% | "
                        f"Avg Return: {stats['avg_return']*100:+6.2f}% | "
                        f"P&L: ${stats['total_pnl']:+10,.2f}"
                    )

        logger.info("")
        logger.info("BEST/WORST TRADES:")
        if metrics['best_trade_symbol']:
            logger.info(f"  Best: {metrics['best_trade_symbol']} ({metrics['best_trade_return']*100:+.1f}%)")
        if metrics['worst_trade_symbol']:
            logger.info(f"  Worst: {metrics['worst_trade_symbol']} ({metrics['worst_trade_return']*100:+.1f}%)")

        logger.info("")
        logger.info("="*70)

        # Save detailed trades
        output_file = 'backtest_results_real.csv'
        trades_df.to_csv(output_file, index=False)
        logger.info(f"✅ Detailed trades saved to: {output_file}")

        # Annualized return
        days_in_period = (datetime.strptime(backtest_end, "%Y-%m-%d") -
                         datetime.strptime(backtest_start, "%Y-%m-%d")).days
        annualized_return = (1 + metrics['total_return_pct']) ** (365 / days_in_period) - 1

        logger.info("")
        logger.info(f"📊 ANNUALIZED RETURN: {annualized_return*100:+.1f}%")
        logger.info("")

        # Verdict
        if metrics['total_return_pct'] > 0.50:  # 50%+
            logger.info("✅ EXCELLENT - Beat target (50%+ return)")
        elif metrics['total_return_pct'] > 0.30:  # 30-50%
            logger.info("✅ GOOD - Strong performance (30-50% return)")
        elif metrics['total_return_pct'] > 0.15:  # 15-30%
            logger.info("⚠️  MODERATE - Decent but below target (15-30% return)")
        elif metrics['total_return_pct'] > 0:  # Positive
            logger.info("⚠️  WEAK - Positive but low return (<15%)")
        else:  # Negative
            logger.info("❌ LOSS - Strategy lost money")

        logger.info("="*70)

        return 0

    except Exception as e:
        logger.error(f"❌ Performance analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
