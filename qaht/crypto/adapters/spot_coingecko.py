"""
CoinGecko API adapter for crypto spot prices
Free tier: 10-30 calls/minute (no API key needed)
"""
import requests
import pandas as pd
from typing import List, Optional, Dict
from datetime import datetime
import time
import logging

from ...db import session_scope
from ...schemas import PriceOHLC
from ...utils.retry import retry_with_backoff
from ...config import get_config

logger = logging.getLogger("qaht.adapters.coingecko")
config = get_config()

COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"

# Symbol mapping (CoinGecko ID -> common symbol)
SYMBOL_MAP = {
    'bitcoin': 'BTC',
    'ethereum': 'ETH',
    'solana': 'SOL',
    'dogecoin': 'DOGE',
    'shiba-inu': 'SHIB',
    'cardano': 'ADA',
    'ripple': 'XRP',
    'polkadot': 'DOT',
    'avalanche-2': 'AVAX',
    'chainlink': 'LINK',
}

# Reverse mapping
ID_MAP = {v: k for k, v in SYMBOL_MAP.items()}


@retry_with_backoff(max_retries=3, initial_delay=2.0)
def fetch_coingecko_ohlc(coin_id: str, days: int = 90) -> pd.DataFrame:
    """
    Fetch OHLC data from CoinGecko

    Args:
        coin_id: CoinGecko coin ID (e.g., 'bitcoin', 'ethereum')
        days: Number of days of historical data (max 90 for free tier)

    Returns:
        DataFrame with OHLC data
    """
    url = f"{COINGECKO_BASE_URL}/coins/{coin_id}/ohlc"
    params = {
        'vs_currency': 'usd',
        'days': min(days, 90)  # Free tier limit
    }

    logger.debug(f"Fetching CoinGecko OHLC for {coin_id}")

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    data = response.json()

    if not data:
        logger.warning(f"No OHLC data for {coin_id}")
        return pd.DataFrame()

    # Data format: [[timestamp_ms, open, high, low, close], ...]
    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df['date'] = df['timestamp'].dt.strftime('%Y-%m-%d')
    df['symbol'] = SYMBOL_MAP.get(coin_id, coin_id.upper())

    # CoinGecko doesn't provide volume in OHLC endpoint, fetch separately
    df['volume'] = 0.0  # Placeholder

    df = df[['symbol', 'date', 'open', 'high', 'low', 'close', 'volume']]

    # Rate limiting
    time.sleep(config.api_rate_limit_delay)

    return df


@retry_with_backoff(max_retries=3, initial_delay=2.0)
def fetch_coingecko_market_data(coin_ids: List[str]) -> pd.DataFrame:
    """
    Fetch current market data including volume from CoinGecko

    Args:
        coin_ids: List of CoinGecko coin IDs

    Returns:
        DataFrame with current price and volume data
    """
    url = f"{COINGECKO_BASE_URL}/coins/markets"
    params = {
        'vs_currency': 'usd',
        'ids': ','.join(coin_ids),
        'order': 'market_cap_desc',
        'per_page': len(coin_ids),
        'page': 1,
        'sparkline': False
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    data = response.json()

    if not data:
        return pd.DataFrame()

    results = []
    for coin in data:
        results.append({
            'symbol': SYMBOL_MAP.get(coin['id'], coin['symbol'].upper()),
            'date': datetime.now().strftime('%Y-%m-%d'),
            'open': coin['current_price'],  # Approximation
            'high': coin['high_24h'] or coin['current_price'],
            'low': coin['low_24h'] or coin['current_price'],
            'close': coin['current_price'],
            'volume': coin['total_volume'] or 0.0
        })

    time.sleep(config.api_rate_limit_delay)

    return pd.DataFrame(results)


def fetch_crypto_prices(symbols: List[str], days: int = 90) -> pd.DataFrame:
    """
    Fetch historical prices for crypto symbols

    Args:
        symbols: List of symbols (e.g., ['BTC', 'ETH', 'SOL'])
        days: Number of days of history

    Returns:
        Combined DataFrame with OHLC data
    """
    results = []

    for symbol in symbols:
        # Map symbol to CoinGecko ID
        coin_id = ID_MAP.get(symbol.upper())

        if not coin_id:
            logger.warning(f"No CoinGecko mapping for {symbol}")
            continue

        try:
            df = fetch_coingecko_ohlc(coin_id, days)
            if not df.empty:
                results.append(df)
        except Exception as e:
            logger.error(f"Failed to fetch {symbol}: {e}")

    if not results:
        return pd.DataFrame()

    combined = pd.concat(results, ignore_index=True)
    logger.info(f"Fetched {len(combined)} rows for {len(results)} crypto symbols")

    return combined


def upsert_crypto_prices(df: pd.DataFrame):
    """
    Insert or update crypto price data in database

    Args:
        df: DataFrame with OHLC data
    """
    if df.empty:
        logger.warning("Empty DataFrame passed to upsert_crypto_prices")
        return

    with session_scope() as session:
        inserted = 0
        updated = 0

        for _, row in df.iterrows():
            existing = session.get(PriceOHLC, (row['symbol'], row['date']))

            if existing:
                existing.open = float(row['open'])
                existing.high = float(row['high'])
                existing.low = float(row['low'])
                existing.close = float(row['close'])
                existing.volume = float(row['volume'])
                updated += 1
            else:
                price = PriceOHLC(
                    symbol=row['symbol'],
                    date=row['date'],
                    open=float(row['open']),
                    high=float(row['high']),
                    low=float(row['low']),
                    close=float(row['close']),
                    volume=float(row['volume']),
                    asset_type='crypto'
                )
                session.add(price)
                inserted += 1

        logger.info(f"Upserted crypto prices: {inserted} inserted, {updated} updated")


def fetch_and_upsert_crypto(symbols: List[str], days: int = 90):
    """
    Convenience function: fetch and upsert crypto prices

    Args:
        symbols: List of crypto symbols
        days: Number of days of history
    """
    df = fetch_crypto_prices(symbols, days)
    if not df.empty:
        upsert_crypto_prices(df)
        return len(df)
    return 0
