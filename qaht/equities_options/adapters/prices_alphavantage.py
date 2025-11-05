"""
Alpha Vantage price data adapter
Free tier: 500 calls/day, 5 calls/minute
Get your free API key: https://www.alphavantage.co/support/#api-key
"""
import pandas as pd
import numpy as np
from typing import List, Optional
import time
import logging
import os
from datetime import datetime, timedelta

from ...db import session_scope
from ...schemas import PriceOHLC
from ...config import get_config
from ...utils.retry import retry_with_backoff

logger = logging.getLogger("qaht.adapters.alphavantage")
config = get_config()


class RateLimiter:
    """Simple rate limiter for API calls"""
    def __init__(self, calls_per_minute: int = 5):
        self.calls_per_minute = calls_per_minute
        self.call_times = []

    def wait_if_needed(self):
        """Wait if we've hit the rate limit"""
        now = time.time()
        # Remove calls older than 1 minute
        self.call_times = [t for t in self.call_times if now - t < 60]

        if len(self.call_times) >= self.calls_per_minute:
            # Wait until oldest call is > 60 seconds old
            sleep_time = 60 - (now - self.call_times[0]) + 1
            if sleep_time > 0:
                logger.info(f"Rate limit reached, waiting {sleep_time:.1f}s")
                time.sleep(sleep_time)

        self.call_times.append(time.time())


# Global rate limiter
rate_limiter = RateLimiter(calls_per_minute=5)


@retry_with_backoff(max_retries=3, initial_delay=2)
def fetch_daily_prices(symbol: str, api_key: str, outputsize: str = 'full') -> pd.DataFrame:
    """
    Fetch daily price data from Alpha Vantage

    Args:
        symbol: Ticker symbol
        api_key: Alpha Vantage API key
        outputsize: 'compact' (100 days) or 'full' (20+ years)

    Returns:
        DataFrame with OHLCV data
    """
    import requests

    # Rate limiting
    rate_limiter.wait_if_needed()

    url = 'https://www.alphavantage.co/query'
    params = {
        'function': 'TIME_SERIES_DAILY',
        'symbol': symbol,
        'outputsize': outputsize,
        'apikey': api_key
    }

    logger.debug(f"Fetching {symbol} from Alpha Vantage")

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()

    data = response.json()

    # Check for errors
    if 'Error Message' in data:
        raise ValueError(f"Alpha Vantage error: {data['Error Message']}")

    if 'Note' in data:
        # Rate limit message
        raise ValueError(f"Rate limit exceeded: {data['Note']}")

    if 'Time Series (Daily)' not in data:
        # Check if it's a crypto symbol
        if symbol.endswith('-USD'):
            logger.warning(f"{symbol} looks like crypto, use crypto adapter instead")
        raise ValueError(f"No time series data for {symbol}")

    # Parse time series
    time_series = data['Time Series (Daily)']

    rows = []
    for date_str, values in time_series.items():
        rows.append({
            'date': date_str,
            'open': float(values['1. open']),
            'high': float(values['2. high']),
            'low': float(values['3. low']),
            'close': float(values['4. close']),
            'volume': int(values['5. volume'])
        })

    df = pd.DataFrame(rows)
    df['symbol'] = symbol
    df['asset_type'] = 'stock'

    # Sort by date
    df = df.sort_values('date').reset_index(drop=True)

    logger.info(f"Fetched {len(df)} days for {symbol}")

    return df


def fetch_and_upsert(symbols: List[str],
                     lookback_days: Optional[int] = None,
                     api_key: Optional[str] = None) -> int:
    """
    Fetch price data for symbols and upsert to database

    Args:
        symbols: List of ticker symbols
        lookback_days: Number of days to fetch (None = all available)
        api_key: Alpha Vantage API key (or set ALPHAVANTAGE_API_KEY env var)

    Returns:
        Number of rows inserted/updated
    """
    if api_key is None:
        api_key = os.getenv('ALPHAVANTAGE_API_KEY')

    if not api_key:
        raise ValueError(
            "Alpha Vantage API key required. Get free key at: "
            "https://www.alphavantage.co/support/#api-key\n"
            "Set via: export ALPHAVANTAGE_API_KEY=your_key"
        )

    if lookback_days is None:
        lookback_days = config.pipeline.lookback_days

    # Determine output size
    outputsize = 'full' if lookback_days > 100 else 'compact'

    logger.info(f"Fetching {len(symbols)} symbols from Alpha Vantage (lookback={lookback_days}d)")

    total_rows = 0

    for symbol in symbols:
        try:
            # Fetch data
            df = fetch_daily_prices(symbol, api_key, outputsize)

            # Filter by lookback
            if lookback_days:
                cutoff_date = (datetime.now() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')
                df = df[df['date'] >= cutoff_date]

            # Upsert to database
            with session_scope() as session:
                for _, row in df.iterrows():
                    existing = session.get(PriceOHLC, (symbol, row['date']))

                    if existing:
                        # Update
                        existing.open = row['open']
                        existing.high = row['high']
                        existing.low = row['low']
                        existing.close = row['close']
                        existing.volume = row['volume']
                    else:
                        # Insert
                        price = PriceOHLC(
                            symbol=symbol,
                            date=row['date'],
                            open=row['open'],
                            high=row['high'],
                            low=row['low'],
                            close=row['close'],
                            volume=row['volume'],
                            asset_type='stock'
                        )
                        session.add(price)

            total_rows += len(df)
            logger.info(f"Upserted {len(df)} rows for {symbol}")

        except Exception as e:
            logger.error(f"Failed to fetch {symbol}: {e}")
            continue

    logger.info(f"Total rows upserted: {total_rows}")
    return total_rows


def get_api_key_instructions():
    """Print instructions for getting Alpha Vantage API key"""
    return """
    🔑 Alpha Vantage API Key Required

    1. Visit: https://www.alphavantage.co/support/#api-key
    2. Enter your email to get a free API key instantly
    3. Set environment variable:
       export ALPHAVANTAGE_API_KEY=your_key_here

    Or add to your .env file:
       ALPHAVANTAGE_API_KEY=your_key_here

    Free tier limits:
    - 500 API calls per day
    - 5 calls per minute
    - Perfect for daily pipeline runs!
    """


if __name__ == "__main__":
    # Test the adapter
    print("Testing Alpha Vantage adapter...")

    api_key = os.getenv('ALPHAVANTAGE_API_KEY')
    if not api_key:
        print(get_api_key_instructions())
        exit(1)

    # Test with a single symbol
    try:
        df = fetch_daily_prices('AAPL', api_key, outputsize='compact')
        print(f"\n✅ Successfully fetched {len(df)} rows for AAPL")
        print(f"\nLatest data:")
        print(df.tail())
    except Exception as e:
        print(f"\n❌ Error: {e}")
