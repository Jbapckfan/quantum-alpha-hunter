"""
Generate synthetic price data for testing pipeline and backtest
Creates realistic price movements including some "explosive" moves
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

def generate_price_series(symbol: str, start_date: str, days: int = 400,
                         base_price: float = 100.0, volatility: float = 0.02,
                         with_explosion: bool = False) -> pd.DataFrame:
    """
    Generate synthetic price data with realistic characteristics

    Args:
        symbol: Ticker symbol
        start_date: Starting date
        days: Number of trading days
        base_price: Starting price
        volatility: Daily volatility (0.02 = 2%)
        with_explosion: Whether to include an explosive move

    Returns:
        DataFrame with OHLCV data
    """
    dates = pd.date_range(start=start_date, periods=days, freq='D')

    # Generate returns with some autocorrelation (trending)
    returns = np.random.normal(0.001, volatility, days)  # Slight upward drift

    # Add trending periods
    for i in range(0, days, 50):
        trend = np.random.choice([-0.01, 0.01], p=[0.4, 0.6])  # More up than down
        returns[i:i+30] += trend

    # Add explosive move if requested
    if with_explosion:
        explosion_day = np.random.randint(100, days - 50)
        # Pre-explosion compression (low volatility)
        returns[explosion_day-20:explosion_day] *= 0.5
        # Explosion! 50-100% move over 5-10 days
        explosion_days = np.random.randint(5, 11)
        explosion_return = np.random.uniform(0.5, 1.0)  # 50-100% total
        for day in range(explosion_days):
            returns[explosion_day + day] = explosion_return / explosion_days

    # Calculate prices
    prices = base_price * np.cumprod(1 + returns)

    # Generate OHLC data
    data = []
    for i, (date, close) in enumerate(zip(dates, prices)):
        # Open slightly different from previous close
        open_price = prices[i-1] * (1 + np.random.normal(0, volatility/2)) if i > 0 else close
        # High/Low based on intraday volatility
        high = max(open_price, close) * (1 + abs(np.random.normal(0, volatility/2)))
        low = min(open_price, close) * (1 - abs(np.random.normal(0, volatility/2)))
        # Volume with some randomness
        volume = int(np.random.lognormal(15, 0.5))  # Realistic volume distribution

        data.append({
            'symbol': symbol,
            'date': date.strftime('%Y-%m-%d'),
            'open': round(open_price, 2),
            'high': round(high, 2),
            'low': round(low, 2),
            'close': round(close, 2),
            'volume': volume,
            'asset_type': 'crypto' if symbol.endswith('-USD') else 'stock'
        })

    return pd.DataFrame(data)


def generate_social_data(symbol: str, dates: list) -> pd.DataFrame:
    """Generate synthetic social mention data"""
    data = []
    base_mentions = np.random.randint(10, 100)

    for date in dates:
        # Add some variability and trending
        mentions = int(base_mentions * (1 + np.random.normal(0, 0.5)))
        mentions = max(0, mentions)  # No negative mentions

        # Occasional spikes
        if np.random.random() < 0.05:  # 5% chance of spike
            mentions *= np.random.randint(3, 10)

        data.append({
            'symbol': symbol,
            'date': date,
            'reddit_count': mentions,
            'twitter_count': int(mentions * 0.7),  # Twitter usually less
            'author_entropy': np.random.uniform(2.0, 4.0),
            'engagement_ratio': np.random.uniform(0.3, 0.8)
        })

    return pd.DataFrame(data)


def main():
    print("🎲 Generating synthetic test data...")

    init_db()
    logger.info("Database initialized")

    # Test symbols with different characteristics
    symbols_config = [
        {'symbol': 'GME', 'base_price': 20, 'volatility': 0.05, 'with_explosion': True},
        {'symbol': 'AAPL', 'base_price': 150, 'volatility': 0.02, 'with_explosion': False},
        {'symbol': 'TSLA', 'base_price': 200, 'volatility': 0.04, 'with_explosion': True},
        {'symbol': 'NVDA', 'base_price': 300, 'volatility': 0.03, 'with_explosion': False},
        {'symbol': 'BTC-USD', 'base_price': 30000, 'volatility': 0.03, 'with_explosion': True},
        {'symbol': 'ETH-USD', 'base_price': 2000, 'volatility': 0.035, 'with_explosion': False},
    ]

    start_date = (datetime.now() - timedelta(days=400)).strftime('%Y-%m-%d')

    for config in symbols_config:
        symbol = config['symbol']
        print(f"\n📊 Generating data for {symbol}...")

        # Generate price data
        price_df = generate_price_series(
            symbol=symbol,
            start_date=start_date,
            days=400,
            base_price=config['base_price'],
            volatility=config['volatility'],
            with_explosion=config['with_explosion']
        )

        # Save to database
        with session_scope() as session:
            for _, row in price_df.iterrows():
                # Check if exists
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

        print(f"   ✅ {len(price_df)} price rows")

        # Generate social data
        social_df = generate_social_data(symbol, price_df['date'].tolist())

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

        print(f"   ✅ {len(social_df)} social rows")

    print("\n✅ Synthetic data generation complete!")
    print("\nNext steps:")
    print("  1. Run: python scripts/test_full_pipeline.py")
    print("  2. Or test features: python scripts/test_features.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
