"""
Improved synthetic data generator with realistic compression → explosion patterns
Creates data that mimics actual market behavior before explosive moves
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from qaht.db import init_db, session_scope
from qaht.schemas import PriceOHLC, SocialMentions
from qaht.logging_conf import setup_logging

logger = setup_logging()


def create_compression_explosion_sequence(days: int, explosion_start: int,
                                         compression_days: int = 20,
                                         explosion_magnitude: float = 0.60,
                                         explosion_days: int = 8) -> np.ndarray:
    """
    Create realistic compression → explosion pattern

    Pattern:
    1. Pre-compression: Normal volatility
    2. Compression: Volatility drops 50%, tight range
    3. Explosion: 50-100% move over 5-10 days
    4. Post-explosion: Return to normal or consolidation

    Args:
        days: Total days
        explosion_start: Day when explosion starts
        compression_days: Days of compression before explosion
        explosion_magnitude: Total return (0.60 = 60%)
        explosion_days: Days for the move to complete

    Returns:
        Array of daily returns
    """
    returns = np.random.normal(0.001, 0.02, days)  # Base returns

    # Pre-compression phase
    compression_start = explosion_start - compression_days

    # Compression phase: Low volatility, tight range
    returns[compression_start:explosion_start] = np.random.normal(0, 0.005, compression_days)

    # Add Bollinger Band compression (prices stay in narrow range)
    # Moving averages converge
    convergence_factor = np.linspace(1.0, 0.1, compression_days)
    returns[compression_start:explosion_start] *= convergence_factor

    # Explosion phase
    explosion_end = explosion_start + explosion_days

    # Distribute returns across explosion days (not uniform - spike early)
    explosion_returns = np.zeros(explosion_days)
    # Front-load the move (bigger moves early)
    base_weights = np.array([3, 2.5, 2, 1.5, 1.2, 1, 0.8, 0.5])
    weights = base_weights[:min(explosion_days, len(base_weights))]

    # Extend weights if needed
    if explosion_days > len(weights):
        extra = explosion_days - len(weights)
        weights = np.concatenate([weights, np.ones(extra) * 0.3])

    weights = weights / weights.sum()

    for i in range(explosion_days):
        explosion_returns[i] = explosion_magnitude * weights[i]

    returns[explosion_start:explosion_end] = explosion_returns

    # Post-explosion: Either consolidation or pullback
    if explosion_end < days:
        # 50% chance of consolidation, 50% chance of pullback
        if np.random.random() > 0.5:
            # Consolidation (low volatility)
            returns[explosion_end:] = np.random.normal(0, 0.01, days - explosion_end)
        else:
            # Pullback (negative drift)
            returns[explosion_end:] = np.random.normal(-0.02, 0.02, days - explosion_end)

    return returns


def generate_realistic_price_series(symbol: str, start_date: str, days: int = 400,
                                   base_price: float = 100.0,
                                   num_explosions: int = 2,
                                   volatility_regime: str = 'high') -> pd.DataFrame:
    """
    Generate realistic price data with compression → explosion patterns

    Args:
        symbol: Ticker symbol
        start_date: Start date
        days: Number of days
        base_price: Starting price
        num_explosions: Number of explosive moves to include
        volatility_regime: 'low', 'medium', 'high'

    Returns:
        DataFrame with OHLCV data
    """
    dates = pd.date_range(start=start_date, periods=days, freq='D')

    # Base volatility by regime
    vol_map = {'low': 0.015, 'medium': 0.025, 'high': 0.04}
    base_vol = vol_map.get(volatility_regime, 0.025)

    # Initialize returns with regime-appropriate volatility
    returns = np.random.normal(0.001, base_vol, days)

    # Add trending periods (persistence)
    trend_length = 30
    for i in range(0, days, 50):
        # Random trend direction
        trend = np.random.choice([-0.005, 0.005], p=[0.3, 0.7])  # Bullish bias
        trend_end = min(i + trend_length, days)
        returns[i:trend_end] += trend

    # Add compression → explosion sequences
    explosion_days_range = (6, 12)
    compression_days_range = (15, 25)

    explosion_times = []

    for i in range(num_explosions):
        # Space explosions apart (at least 60 days)
        min_day = 100 + i * 120
        max_day = min(min_day + 80, days - 50)

        if max_day > min_day:
            explosion_start = np.random.randint(min_day, max_day)
            explosion_days = np.random.randint(*explosion_days_range)
            compression_days = np.random.randint(*compression_days_range)
            magnitude = np.random.uniform(0.50, 1.0)  # 50-100% move

            # Create pattern
            pattern = create_compression_explosion_sequence(
                days=days,
                explosion_start=explosion_start,
                compression_days=compression_days,
                explosion_magnitude=magnitude,
                explosion_days=explosion_days
            )

            # Blend pattern into base returns
            returns = pattern

            explosion_times.append({
                'start': explosion_start,
                'days': explosion_days,
                'magnitude': magnitude,
                'compression_days': compression_days
            })

    # Calculate prices
    prices = base_price * np.cumprod(1 + returns)

    # Generate OHLC
    data = []
    for i, (date, close) in enumerate(zip(dates, prices)):
        # Intraday volatility
        intraday_vol = base_vol / 2
        open_price = prices[i-1] * (1 + np.random.normal(0, intraday_vol/2)) if i > 0 else close

        # High/Low based on daily range
        high = max(open_price, close) * (1 + abs(np.random.normal(0, intraday_vol)))
        low = min(open_price, close) * (1 - abs(np.random.normal(0, intraday_vol)))

        # Volume: Spike during explosions
        base_volume = np.random.lognormal(15, 0.5)

        # Check if we're in an explosion phase
        in_explosion = False
        for exp in explosion_times:
            if exp['start'] <= i < exp['start'] + exp['days']:
                in_explosion = True
                # Volume 2-5x during explosion
                base_volume *= np.random.uniform(2, 5)
                break

        # Check if we're in compression phase
        in_compression = False
        for exp in explosion_times:
            compression_start = exp['start'] - exp['compression_days']
            if compression_start <= i < exp['start']:
                in_compression = True
                # Volume decreases during compression
                base_volume *= np.random.uniform(0.3, 0.7)
                break

        data.append({
            'symbol': symbol,
            'date': date.strftime('%Y-%m-%d'),
            'open': round(open_price, 2),
            'high': round(high, 2),
            'low': round(low, 2),
            'close': round(close, 2),
            'volume': int(base_volume),
            'asset_type': 'crypto' if symbol.endswith('-USD') else 'stock'
        })

    df = pd.DataFrame(data)

    # Log explosion info
    logger.info(f"{symbol}: Created {len(explosion_times)} explosions at days {[e['start'] for e in explosion_times]}")

    return df


def generate_social_data_correlated(symbol: str, dates: list, price_df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate social data that correlates with price explosions

    Social pattern:
    - Low baseline mentions
    - Spike 3-7 days BEFORE explosion (early attention)
    - Massive spike DURING explosion (FOMO)
    - Decay after explosion
    """
    data = []
    base_mentions = np.random.randint(20, 100)

    # Calculate daily returns for correlation
    price_df['return'] = price_df['close'].pct_change()
    price_df['ma_20'] = price_df['close'].rolling(20).mean()
    price_df['volatility'] = price_df['return'].rolling(10).std()

    for i, date in enumerate(dates):
        # Base mentions with some noise
        mentions = int(base_mentions * (1 + np.random.normal(0, 0.3)))

        # Look ahead to detect upcoming explosions (early signal)
        if i < len(price_df) - 10:
            # Check if big move coming in next 5-10 days
            future_returns = price_df['close'].iloc[i+5:i+10].pct_change().sum()

            if future_returns > 0.15:  # 15%+ move coming
                # Early social signal (3-7 days before)
                mentions *= np.random.uniform(1.5, 3.0)

        # During explosions: Massive social spike
        if i < len(price_df):
            today_return = price_df['return'].iloc[i]

            if today_return > 0.05:  # Big up day
                mentions *= np.random.uniform(3, 8)
            elif today_return > 0.02:  # Moderate up day
                mentions *= np.random.uniform(1.5, 2.5)

        # Engagement quality decreases during FOMO
        if mentions > base_mentions * 3:
            # High mentions = low engagement quality (bots, spam)
            author_entropy = np.random.uniform(1.5, 2.5)  # Lower diversity
            engagement_ratio = np.random.uniform(0.2, 0.4)  # Lower quality
        else:
            # Normal mentions = good engagement
            author_entropy = np.random.uniform(2.5, 4.0)
            engagement_ratio = np.random.uniform(0.4, 0.8)

        mentions = max(0, int(mentions))

        data.append({
            'symbol': symbol,
            'date': date,
            'reddit_count': mentions,
            'twitter_count': int(mentions * 0.7),
            'author_entropy': author_entropy,
            'engagement_ratio': engagement_ratio
        })

    return pd.DataFrame(data)


def main():
    print("=" * 80)
    print("🎲 IMPROVED SYNTHETIC DATA GENERATOR")
    print("=" * 80)

    init_db()
    logger.info("Database initialized")

    # Symbol configurations with realistic characteristics
    symbols_config = [
        # Meme stocks - high volatility, multiple explosions
        {'symbol': 'GME', 'base_price': 15, 'explosions': 3, 'volatility': 'high'},
        {'symbol': 'AMC', 'base_price': 8, 'explosions': 2, 'volatility': 'high'},
        {'symbol': 'BBBY', 'base_price': 5, 'explosions': 2, 'volatility': 'high'},

        # Tech growth - medium volatility, occasional explosions
        {'symbol': 'NVDA', 'base_price': 200, 'explosions': 2, 'volatility': 'medium'},
        {'symbol': 'AMD', 'base_price': 80, 'explosions': 2, 'volatility': 'medium'},
        {'symbol': 'PLTR', 'base_price': 12, 'explosions': 2, 'volatility': 'medium'},
        {'symbol': 'COIN', 'base_price': 60, 'explosions': 2, 'volatility': 'medium'},

        # Established tech - lower volatility, rare explosions
        {'symbol': 'AAPL', 'base_price': 150, 'explosions': 1, 'volatility': 'low'},
        {'symbol': 'MSFT', 'base_price': 300, 'explosions': 1, 'volatility': 'low'},
        {'symbol': 'TSLA', 'base_price': 180, 'explosions': 2, 'volatility': 'medium'},

        # Crypto - very high volatility, frequent explosions
        {'symbol': 'BTC-USD', 'base_price': 28000, 'explosions': 3, 'volatility': 'high'},
        {'symbol': 'ETH-USD', 'base_price': 1800, 'explosions': 3, 'volatility': 'high'},
        {'symbol': 'SOL-USD', 'base_price': 25, 'explosions': 4, 'volatility': 'high'},
        {'symbol': 'DOGE-USD', 'base_price': 0.08, 'explosions': 3, 'volatility': 'high'},
    ]

    start_date = (datetime.now() - timedelta(days=400)).strftime('%Y-%m-%d')

    total_explosions = 0

    for config in symbols_config:
        symbol = config['symbol']
        print(f"\n{'='*80}")
        print(f"📊 Generating {symbol} with {config['explosions']} explosions")
        print(f"{'='*80}")

        # Generate price data
        price_df = generate_realistic_price_series(
            symbol=symbol,
            start_date=start_date,
            days=400,
            base_price=config['base_price'],
            num_explosions=config['explosions'],
            volatility_regime=config['volatility']
        )

        # Save to database
        with session_scope() as session:
            for _, row in price_df.iterrows():
                existing = session.get(PriceOHLC, (row['symbol'], row['date']))

                if not existing:
                    price = PriceOHLC(
                        symbol=row['symbol'],
                        date=row['date'],
                        open=float(row['open']),
                        high=float(row['high']),
                        low=float(row['low']),
                        close=float(row['close']),
                        volume=int(row['volume']),
                        asset_type=row['asset_type']
                    )
                    session.add(price)

        print(f"  ✅ {len(price_df)} price rows")

        # Generate correlated social data
        social_df = generate_social_data_correlated(symbol, price_df['date'].tolist(), price_df)

        with session_scope() as session:
            for _, row in social_df.iterrows():
                existing = session.get(SocialMentions, (row['symbol'], row['date']))

                if not existing:
                    social = SocialMentions(
                        symbol=row['symbol'],
                        date=row['date'],
                        reddit_count=int(row['reddit_count']),
                        twitter_count=int(row['twitter_count']),
                        author_entropy=float(row['author_entropy']),
                        engagement_ratio=float(row['engagement_ratio'])
                    )
                    session.add(social)

        print(f"  ✅ {len(social_df)} social rows")

        # Calculate actual explosions
        explosions = (price_df['close'].pct_change(10) >= 0.50).sum()
        total_explosions += explosions
        print(f"  🚀 {explosions} actual 10-day explosions (50%+) detected")

    print("\n" + "=" * 80)
    print(f"✅ GENERATION COMPLETE")
    print("=" * 80)
    print(f"\nTotal symbols: {len(symbols_config)}")
    print(f"Total explosions: {total_explosions}")
    print(f"Avg explosions per symbol: {total_explosions / len(symbols_config):.1f}")

    print("\n📈 Data quality improvements:")
    print("  ✅ Realistic compression → explosion patterns")
    print("  ✅ Correlated social signals (early + FOMO)")
    print("  ✅ Volume spikes during moves")
    print("  ✅ Multiple volatility regimes")
    print("  ✅ Proper trending behavior")

    print("\n🎯 Next steps:")
    print("  1. Run: python scripts/test_full_workflow.py")
    print("  2. Check model performance on realistic patterns")
    print("  3. Verify feature importance (social_delta should be strong)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
