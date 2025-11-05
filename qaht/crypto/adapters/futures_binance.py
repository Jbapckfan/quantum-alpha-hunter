"""
Binance Futures API adapter for funding rates and open interest
Public endpoints, no API key required
"""
import requests
import pandas as pd
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import time
import logging

from ...db import session_scope
from ...schemas import FuturesMetrics
from ...utils.retry import retry_with_backoff
from ...config import get_config

logger = logging.getLogger("qaht.adapters.binance_futures")
config = get_config()

BINANCE_FUTURES_BASE = "https://fapi.binance.com/fapi/v1"

SYMBOL_MAP = {
    'BTC': 'BTCUSDT',
    'ETH': 'ETHUSDT',
    'SOL': 'SOLUSDT',
    'DOGE': 'DOGEUSDT',
    'SHIB': '1000SHIBUSDT',
    'ADA': 'ADAUSDT',
    'XRP': 'XRPUSDT',
    'DOT': 'DOTUSDT',
    'AVAX': 'AVAXUSDT',
    'LINK': 'LINKUSDT',
}


@retry_with_backoff(max_retries=3, initial_delay=1.0)
def fetch_funding_rate(symbol: str) -> Optional[float]:
    """
    Fetch current funding rate for a perpetual futures contract

    Args:
        symbol: Binance futures symbol (e.g., 'BTCUSDT')

    Returns:
        Current funding rate (as decimal, e.g., 0.0001 = 0.01%)
    """
    url = f"{BINANCE_FUTURES_BASE}/premiumIndex"
    params = {'symbol': symbol}

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    data = response.json()
    return float(data['lastFundingRate'])


@retry_with_backoff(max_retries=3, initial_delay=1.0)
def fetch_open_interest(symbol: str) -> Dict:
    """
    Fetch current open interest

    Args:
        symbol: Binance futures symbol

    Returns:
        Dict with open interest in contracts and USD value
    """
    url = f"{BINANCE_FUTURES_BASE}/openInterest"
    params = {'symbol': symbol}

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    data = response.json()

    # Get current price to calculate USD value
    price_url = f"{BINANCE_FUTURES_BASE}/ticker/price"
    price_response = requests.get(price_url, params=params, timeout=10)
    price_data = price_response.json()
    price = float(price_data['price'])

    oi_contracts = float(data['openInterest'])
    oi_usd = oi_contracts * price

    return {
        'oi': oi_contracts,
        'oi_usd': oi_usd,
        'price': price
    }


def fetch_futures_metrics(symbols: List[str]) -> pd.DataFrame:
    """
    Fetch funding rate and open interest for multiple symbols

    Args:
        symbols: List of symbols (e.g., ['BTC', 'ETH'])

    Returns:
        DataFrame with futures metrics
    """
    results = []
    today = datetime.now().strftime('%Y-%m-%d')

    for symbol in symbols:
        binance_symbol = SYMBOL_MAP.get(symbol.upper())

        if not binance_symbol:
            logger.warning(f"No Binance futures mapping for {symbol}")
            continue

        try:
            funding_rate = fetch_funding_rate(binance_symbol)
            oi_data = fetch_open_interest(binance_symbol)

            results.append({
                'symbol': symbol.upper(),
                'date': today,
                'funding_rate': funding_rate,
                'oi': oi_data['oi'],
                'oi_usd': oi_data['oi_usd'],
                'basis_pct': None  # Can calculate if we have spot price
            })

            time.sleep(config.api_rate_limit_delay * 0.5)  # Binance allows more requests

        except Exception as e:
            logger.error(f"Failed to fetch futures metrics for {symbol}: {e}")

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results)
    logger.info(f"Fetched futures metrics for {len(results)} symbols")

    return df


def upsert_futures_metrics(df: pd.DataFrame):
    """
    Insert or update futures metrics in database

    Args:
        df: DataFrame with futures metrics
    """
    if df.empty:
        logger.warning("Empty DataFrame passed to upsert_futures_metrics")
        return

    with session_scope() as session:
        inserted = 0
        updated = 0

        for _, row in df.iterrows():
            existing = session.get(FuturesMetrics, (row['symbol'], row['date']))

            if existing:
                existing.funding_rate = float(row['funding_rate'])
                existing.oi = float(row['oi'])
                existing.oi_usd = float(row['oi_usd'])
                if pd.notna(row['basis_pct']):
                    existing.basis_pct = float(row['basis_pct'])
                updated += 1
            else:
                metric = FuturesMetrics(
                    symbol=row['symbol'],
                    date=row['date'],
                    funding_rate=float(row['funding_rate']),
                    oi=float(row['oi']),
                    oi_usd=float(row['oi_usd']),
                    basis_pct=float(row['basis_pct']) if pd.notna(row['basis_pct']) else None
                )
                session.add(metric)
                inserted += 1

        logger.info(f"Upserted futures metrics: {inserted} inserted, {updated} updated")


def fetch_and_upsert_futures(symbols: List[str]):
    """
    Convenience function: fetch and upsert futures metrics

    Args:
        symbols: List of crypto symbols
    """
    df = fetch_futures_metrics(symbols)
    if not df.empty:
        upsert_futures_metrics(df)
        return len(df)
    return 0
