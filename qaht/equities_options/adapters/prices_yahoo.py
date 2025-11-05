"""
Yahoo Finance price data adapter
Fetches OHLCV data for stocks using yfinance
"""
import yfinance as yf
import pandas as pd
from typing import List, Optional
from datetime import datetime, timedelta
import logging

from ...db import session_scope
from ...schemas import PriceOHLC
from ...utils.retry import retry_with_backoff
from ...config import get_config

logger = logging.getLogger("qaht.adapters.yahoo")
config = get_config()


@retry_with_backoff(max_retries=3, initial_delay=2.0)
def fetch_prices(
    symbols: List[str],
    period: str = "1y",
    interval: str = "1d"
) -> pd.DataFrame:
    """
    Fetch price data for multiple symbols from Yahoo Finance

    Args:
        symbols: List of ticker symbols
        period: Time period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
        interval: Data interval (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)

    Returns:
        DataFrame with OHLCV data
    """
    if not symbols:
        logger.warning("No symbols provided to fetch_prices")
        return pd.DataFrame()

    logger.info(f"Fetching {len(symbols)} symbols from Yahoo Finance: period={period}, interval={interval}")

    try:
        # Download data for all symbols at once (more efficient)
        data = yf.download(
            symbols,
            period=period,
            interval=interval,
            group_by='ticker',
            auto_adjust=True,  # Adjust for splits and dividends
            progress=False,
            threads=True
        )

        if data.empty:
            logger.warning("No data returned from Yahoo Finance")
            return pd.DataFrame()

        # Reshape data for single vs multiple symbols
        if len(symbols) == 1:
            data.columns = pd.MultiIndex.from_product([[symbols[0]], data.columns])

        results = []
        for symbol in symbols:
            if symbol not in data.columns.get_level_values(0):
                logger.warning(f"No data for {symbol}")
                continue

            symbol_data = data[symbol].copy()
            symbol_data = symbol_data.dropna(subset=['Close'])

            if symbol_data.empty:
                continue

            symbol_data['symbol'] = symbol
            symbol_data['date'] = symbol_data.index.strftime('%Y-%m-%d')
            symbol_data = symbol_data.reset_index(drop=True)

            # Rename columns to lowercase
            symbol_data = symbol_data.rename(columns={
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume'
            })

            results.append(symbol_data[['symbol', 'date', 'open', 'high', 'low', 'close', 'volume']])

        if not results:
            return pd.DataFrame()

        combined = pd.concat(results, ignore_index=True)
        logger.info(f"Fetched {len(combined)} rows for {len(results)} symbols")

        return combined

    except Exception as e:
        logger.error(f"Error fetching prices: {e}")
        raise


def upsert_prices(df: pd.DataFrame):
    """
    Insert or update price data in database

    Args:
        df: DataFrame with columns: symbol, date, open, high, low, close, volume
    """
    if df.empty:
        logger.warning("Empty DataFrame passed to upsert_prices")
        return

    with session_scope() as session:
        inserted = 0
        updated = 0

        for _, row in df.iterrows():
            # Check if exists
            existing = session.get(PriceOHLC, (row['symbol'], row['date']))

            if existing:
                # Update existing record
                existing.open = float(row['open'])
                existing.high = float(row['high'])
                existing.low = float(row['low'])
                existing.close = float(row['close'])
                existing.volume = float(row['volume'])
                updated += 1
            else:
                # Insert new record
                price = PriceOHLC(
                    symbol=row['symbol'],
                    date=row['date'],
                    open=float(row['open']),
                    high=float(row['high']),
                    low=float(row['low']),
                    close=float(row['close']),
                    volume=float(row['volume']),
                    asset_type='stock'
                )
                session.add(price)
                inserted += 1

        logger.info(f"Upserted prices: {inserted} inserted, {updated} updated")


def fetch_and_upsert(symbols: List[str], period: str = "1y"):
    """
    Convenience function: fetch and immediately upsert

    Args:
        symbols: List of ticker symbols
        period: Time period to fetch
    """
    df = fetch_prices(symbols, period=period)
    if not df.empty:
        upsert_prices(df)
        return len(df)
    return 0


def get_latest_price(symbol: str) -> Optional[float]:
    """
    Get most recent closing price for a symbol

    Args:
        symbol: Ticker symbol

    Returns:
        Latest close price or None
    """
    with session_scope() as session:
        from sqlalchemy import select
        result = session.execute(
            select(PriceOHLC)
            .where(PriceOHLC.symbol == symbol)
            .order_by(PriceOHLC.date.desc())
            .limit(1)
        ).scalar_one_or_none()

        return result.close if result else None
