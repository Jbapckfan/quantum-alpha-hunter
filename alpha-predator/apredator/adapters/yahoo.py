"""
Yahoo Finance adapter.
Downloads OHLCV price data, fundamentals, and options chains via yfinance.
Sourced from QAHT prices_yahoo.py.
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Union

import pandas as pd
import yfinance as yf

from ..db import session_scope
from ..schemas import PriceOHLC
from ..utils.retry import retry_with_backoff

logger = logging.getLogger("apredator.adapters.yahoo")


# ---------------------------------------------------------------------------
# Price data
# ---------------------------------------------------------------------------

@retry_with_backoff(max_retries=3, initial_delay=2.0)
def fetch_prices(
    symbols: Union[str, List[str]],
    period: str = "1y",
    interval: str = "1d",
) -> pd.DataFrame:
    """Download OHLCV data from Yahoo Finance for one or more symbols.

    Parameters
    ----------
    symbols : str or list[str]
        Ticker symbol(s) to download.
    period : str
        Valid yfinance period string (e.g. ``"1y"``, ``"6mo"``).
    interval : str
        Bar interval (e.g. ``"1d"``, ``"1h"``).

    Returns
    -------
    pd.DataFrame
        Long-format DataFrame with columns:
        ``symbol, date, open, high, low, close, volume``.
    """
    if isinstance(symbols, str):
        symbols = [symbols]

    symbols = [s.strip().upper() for s in symbols if s.strip()]
    if not symbols:
        logger.warning("fetch_prices called with empty symbol list")
        return pd.DataFrame()

    logger.info(f"Downloading prices for {len(symbols)} symbols (period={period}, interval={interval})")

    data = yf.download(
        tickers=symbols,
        period=period,
        interval=interval,
        group_by="ticker",
        auto_adjust=True,
        threads=True,
        progress=False,
    )

    if data.empty:
        logger.warning("yfinance returned empty DataFrame")
        return pd.DataFrame()

    frames: List[pd.DataFrame] = []

    if len(symbols) == 1:
        # Single ticker: columns are just Open, High, Low, Close, Volume
        sym = symbols[0]
        df = data.copy()
        df = df.reset_index()
        df.columns = [c.lower() if isinstance(c, str) else c for c in df.columns]
        df["symbol"] = sym
        df = df.rename(columns={"date": "date"})
        # Keep only the columns we need
        for col in ("open", "high", "low", "close", "volume"):
            if col not in df.columns:
                df[col] = None
        frames.append(df[["symbol", "date", "open", "high", "low", "close", "volume"]])
    else:
        # Multi-ticker: MultiIndex columns (ticker, field)
        for sym in symbols:
            try:
                sym_data = data[sym].copy()
                sym_data = sym_data.reset_index()
                sym_data.columns = [c.lower() if isinstance(c, str) else c for c in sym_data.columns]
                sym_data["symbol"] = sym
                for col in ("open", "high", "low", "close", "volume"):
                    if col not in sym_data.columns:
                        sym_data[col] = None
                frames.append(sym_data[["symbol", "date", "open", "high", "low", "close", "volume"]])
            except (KeyError, TypeError) as exc:
                logger.warning(f"No data for {sym}: {exc}")

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)
    result["date"] = pd.to_datetime(result["date"]).dt.strftime("%Y-%m-%d")
    result = result.dropna(subset=["close"])

    logger.info(f"Fetched {len(result)} price rows for {result['symbol'].nunique()} symbols")
    return result


# ---------------------------------------------------------------------------
# Upsert to DB
# ---------------------------------------------------------------------------

@retry_with_backoff(max_retries=3, initial_delay=2.0)
def fetch_and_upsert(
    symbols: Union[str, List[str]],
    period: str = "1y",
) -> int:
    """Fetch prices from Yahoo Finance and upsert into PriceOHLC table.

    Parameters
    ----------
    symbols : str or list[str]
        Ticker(s) to fetch.
    period : str
        Lookback period.

    Returns
    -------
    int
        Number of rows upserted.
    """
    df = fetch_prices(symbols, period=period)
    if df.empty:
        return 0

    count = 0
    with session_scope() as session:
        for _, row in df.iterrows():
            obj = PriceOHLC(
                symbol=row["symbol"],
                date=row["date"],
                open=float(row["open"]) if pd.notna(row["open"]) else 0.0,
                high=float(row["high"]) if pd.notna(row["high"]) else 0.0,
                low=float(row["low"]) if pd.notna(row["low"]) else 0.0,
                close=float(row["close"]) if pd.notna(row["close"]) else 0.0,
                volume=float(row["volume"]) if pd.notna(row["volume"]) else 0.0,
                asset_type="stock",
            )
            session.merge(obj)
            count += 1

    logger.info(f"Upserted {count} price rows for {df['symbol'].nunique()} symbols")
    return count


# ---------------------------------------------------------------------------
# Fundamentals
# ---------------------------------------------------------------------------

@retry_with_backoff(max_retries=3, initial_delay=2.0)
def fetch_fundamentals(symbol: str) -> Dict:
    """Fetch fundamental data for a single stock symbol.

    Returns
    -------
    dict
        Keys: market_cap, float_shares, short_percent, beta, sector.
    """
    ticker = yf.Ticker(symbol)
    info = ticker.info or {}

    result = {
        "symbol": symbol.upper(),
        "market_cap": info.get("marketCap"),
        "float_shares": info.get("floatShares"),
        "short_percent": info.get("shortPercentOfFloat"),
        "beta": info.get("beta"),
        "sector": info.get("sector"),
    }

    logger.debug(f"Fundamentals for {symbol}: market_cap={result['market_cap']}")
    return result


# ---------------------------------------------------------------------------
# Options chain
# ---------------------------------------------------------------------------

@retry_with_backoff(max_retries=3, initial_delay=2.0)
def fetch_options_chain(symbol: str) -> pd.DataFrame:
    """Fetch the full options chain for a symbol across all expiration dates.

    Returns
    -------
    pd.DataFrame
        Columns: symbol, expiry, strike, option_type, last, bid, ask, iv,
        delta, gamma, oi, volume.
    """
    ticker = yf.Ticker(symbol)

    try:
        expirations = ticker.options
    except Exception as exc:
        logger.warning(f"No options data available for {symbol}: {exc}")
        return pd.DataFrame()

    if not expirations:
        logger.debug(f"No options expirations for {symbol}")
        return pd.DataFrame()

    frames: List[pd.DataFrame] = []

    for expiry in expirations:
        try:
            chain = ticker.option_chain(expiry)

            for opt_type, df_raw in [("call", chain.calls), ("put", chain.puts)]:
                if df_raw.empty:
                    continue
                df = df_raw.copy()
                df["symbol"] = symbol.upper()
                df["expiry"] = expiry
                df["option_type"] = opt_type

                # Normalize column names (yfinance may vary)
                col_map = {
                    "strike": "strike",
                    "lastPrice": "last",
                    "bid": "bid",
                    "ask": "ask",
                    "impliedVolatility": "iv",
                    "openInterest": "oi",
                    "volume": "volume",
                }
                df = df.rename(columns=col_map)

                # delta and gamma are not always provided by yfinance
                if "delta" not in df.columns:
                    df["delta"] = None
                if "gamma" not in df.columns:
                    df["gamma"] = None

                keep = [
                    "symbol", "expiry", "strike", "option_type",
                    "last", "bid", "ask", "iv", "delta", "gamma",
                    "oi", "volume",
                ]
                for col in keep:
                    if col not in df.columns:
                        df[col] = None

                frames.append(df[keep])

        except Exception as exc:
            logger.warning(f"Error fetching options for {symbol} expiry {expiry}: {exc}")

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)
    logger.info(f"Fetched {len(result)} options rows for {symbol} across {len(expirations)} expirations")
    return result
