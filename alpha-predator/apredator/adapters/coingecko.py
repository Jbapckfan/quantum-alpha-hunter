"""
CoinGecko adapter.
Fetches OHLC price data and market metrics for crypto assets.
Sourced from QAHT spot_coingecko.py.
"""
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Union

import pandas as pd
import requests

from ..config import get_config
from ..db import session_scope
from ..schemas import PriceOHLC
from ..universe.crypto import SYMBOL_MAP
from ..utils.retry import retry_with_backoff

logger = logging.getLogger("apredator.adapters.coingecko")

_BASE_URL = "https://api.coingecko.com/api/v3"


# ---------------------------------------------------------------------------
# OHLC data
# ---------------------------------------------------------------------------

@retry_with_backoff(max_retries=3, initial_delay=2.0)
def fetch_coingecko_ohlc(coin_id: str, days: int = 90) -> pd.DataFrame:
    """Fetch OHLC candlestick data from CoinGecko.

    Parameters
    ----------
    coin_id : str
        CoinGecko coin identifier (e.g. ``"bitcoin"``, ``"ethereum"``).
    days : int
        Number of days of history. CoinGecko supports 1, 7, 14, 30, 90,
        180, 365, ``"max"``.

    Returns
    -------
    pd.DataFrame
        Columns: ``date, open, high, low, close``.
    """
    config = get_config()
    url = f"{_BASE_URL}/coins/{coin_id}/ohlc"
    params = {"vs_currency": "usd", "days": days}

    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # Rate limiting
    time.sleep(config.api_rate_limit_delay)

    if not data:
        logger.warning(f"No OHLC data returned for {coin_id}")
        return pd.DataFrame()

    # CoinGecko returns [[timestamp, open, high, low, close], ...]
    df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close"])
    df["date"] = pd.to_datetime(df["timestamp"], unit="ms").dt.strftime("%Y-%m-%d")
    df = df.drop(columns=["timestamp"])

    # Deduplicate by date (CoinGecko may return multiple candles per day)
    df = df.drop_duplicates(subset=["date"], keep="last")
    df = df.sort_values("date").reset_index(drop=True)

    logger.debug(f"Fetched {len(df)} OHLC rows for {coin_id}")
    return df


# ---------------------------------------------------------------------------
# Market data (volume, market cap)
# ---------------------------------------------------------------------------

@retry_with_backoff(max_retries=3, initial_delay=2.0)
def fetch_market_data(coin_ids: Union[str, List[str]]) -> pd.DataFrame:
    """Fetch current market data from CoinGecko for one or more coins.

    Parameters
    ----------
    coin_ids : str or list[str]
        CoinGecko coin ID(s).

    Returns
    -------
    pd.DataFrame
        Columns: ``coin_id, symbol, price, volume_24h, market_cap,
        price_change_24h_pct``.
    """
    config = get_config()

    if isinstance(coin_ids, str):
        coin_ids = [coin_ids]

    url = f"{_BASE_URL}/coins/markets"
    params = {
        "vs_currency": "usd",
        "ids": ",".join(coin_ids),
        "order": "market_cap_desc",
        "per_page": 250,
        "page": 1,
        "sparkline": "false",
    }

    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    time.sleep(config.api_rate_limit_delay)

    if not data:
        logger.warning(f"No market data returned for {coin_ids}")
        return pd.DataFrame()

    rows = []
    for coin in data:
        rows.append({
            "coin_id": coin.get("id", ""),
            "symbol": (coin.get("symbol") or "").upper(),
            "price": coin.get("current_price"),
            "volume_24h": coin.get("total_volume"),
            "market_cap": coin.get("market_cap"),
            "price_change_24h_pct": coin.get("price_change_percentage_24h"),
        })

    df = pd.DataFrame(rows)
    logger.info(f"Fetched market data for {len(df)} coins")
    return df


# ---------------------------------------------------------------------------
# Upsert to DB
# ---------------------------------------------------------------------------

@retry_with_backoff(max_retries=3, initial_delay=2.0)
def fetch_and_upsert_crypto(
    coin_ids: Union[str, List[str]],
    days: int = 90,
) -> int:
    """Fetch OHLC data from CoinGecko and upsert into PriceOHLC table.

    CoinGecko coin IDs are mapped to ticker symbols via ``SYMBOL_MAP``.
    Coins not in the map use the CoinGecko ID as the symbol (upper-cased).

    Parameters
    ----------
    coin_ids : str or list[str]
        CoinGecko coin ID(s).
    days : int
        Number of days of history.

    Returns
    -------
    int
        Number of rows upserted.
    """
    if isinstance(coin_ids, str):
        coin_ids = [coin_ids]

    total_count = 0

    for coin_id in coin_ids:
        try:
            df = fetch_coingecko_ohlc(coin_id, days=days)
            if df.empty:
                continue

            # Map CoinGecko ID to ticker symbol
            ticker = SYMBOL_MAP.get(coin_id, coin_id.upper())

            with session_scope() as session:
                for _, row in df.iterrows():
                    obj = PriceOHLC(
                        symbol=ticker,
                        date=row["date"],
                        open=float(row["open"]) if pd.notna(row["open"]) else 0.0,
                        high=float(row["high"]) if pd.notna(row["high"]) else 0.0,
                        low=float(row["low"]) if pd.notna(row["low"]) else 0.0,
                        close=float(row["close"]) if pd.notna(row["close"]) else 0.0,
                        volume=0.0,  # CoinGecko OHLC endpoint does not include volume
                        asset_type="crypto",
                    )
                    session.merge(obj)
                    total_count += 1

            logger.debug(f"Upserted {len(df)} rows for {ticker} ({coin_id})")

        except Exception as exc:
            logger.error(f"Failed to fetch/upsert {coin_id}: {exc}")

    logger.info(f"Upserted {total_count} crypto price rows for {len(coin_ids)} coins")
    return total_count
