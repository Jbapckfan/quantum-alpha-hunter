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

# Disable multitasking's thread-spawning — old yfinance ignores threads=False
try:
    import multitasking
    multitasking.set_max_threads(1)
except ImportError:
    pass

from ..db import session_scope
from ..schemas import PriceOHLC
from ..utils.retry import retry_with_backoff

logger = logging.getLogger("apredator.adapters.yahoo")


# ---------------------------------------------------------------------------
# Ticker bundle — single yf.Ticker session for all data
# ---------------------------------------------------------------------------

def fetch_ticker_bundle(symbol: str) -> Dict:
    """Create a single ``yf.Ticker`` and extract all commonly-needed data at once.

    This replaces 7+ separate ``yf.Ticker()`` creations (fundamentals, sector,
    short interest, earnings, options, max pain) with **one** object reuse.

    Returns
    -------
    dict
        Keys:

        * ``info``           – ``ticker.info`` dict (fundamentals, sector, short %)
        * ``calendar``       – ``ticker.calendar`` (earnings date)
        * ``chain``          – ``(calls_df, puts_df)`` for the nearest expiry
        * ``nearest_expiry`` – expiry date string used for the chain
        * ``expirations``    – full list of option expiry strings
    """
    result: Dict = {
        "info": {},
        "calendar": None,
        "chain": (pd.DataFrame(), pd.DataFrame()),
        "nearest_expiry": None,
        "expirations": [],
    }

    try:
        ticker = yf.Ticker(symbol)

        # ── .info (fundamentals, sector, short interest) ──
        try:
            result["info"] = ticker.info or {}
        except Exception as exc:
            logger.debug("Could not fetch info for %s: %s", symbol, exc)

        # ── .calendar (earnings proximity) ──
        try:
            result["calendar"] = ticker.calendar
        except Exception as exc:
            logger.debug("Could not fetch calendar for %s: %s", symbol, exc)

        # ── .options + .option_chain(nearest) ──
        try:
            expirations = ticker.options
            result["expirations"] = list(expirations) if expirations else []

            if expirations:
                # Pick nearest future expiry
                from datetime import datetime as _dt
                today = _dt.utcnow().date()
                nearest = None
                nearest_delta = None
                for exp_str in expirations:
                    try:
                        exp_date = _dt.strptime(exp_str, "%Y-%m-%d").date()
                        delta = (exp_date - today).days
                        if delta < 0:
                            continue
                        if nearest_delta is None or delta < nearest_delta:
                            nearest_delta = delta
                            nearest = exp_str
                    except ValueError:
                        continue
                if nearest is None and expirations:
                    nearest = expirations[-1]

                if nearest:
                    result["nearest_expiry"] = nearest
                    chain = ticker.option_chain(nearest)
                    result["chain"] = (chain.calls, chain.puts)
        except Exception as exc:
            logger.debug("Could not fetch options for %s: %s", symbol, exc)

    except Exception:
        logger.exception("fetch_ticker_bundle failed for %s", symbol)

    return result


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

    # Download in batches of 20 to avoid thread-limit crashes
    BATCH = 20
    frames: List[pd.DataFrame] = []

    for i in range(0, len(symbols), BATCH):
        batch = symbols[i : i + BATCH]
        logger.debug(f"Batch {i // BATCH + 1}: downloading {len(batch)} symbols")

        try:
            data = yf.download(
                tickers=batch,
                period=period,
                interval=interval,
                group_by="ticker",
                auto_adjust=True,
                threads=False,
                progress=False,
            )
        except Exception as exc:
            logger.warning(f"Batch download failed for {batch[:3]}…: {exc}")
            continue

        if data.empty:
            continue

        if len(batch) == 1:
            sym = batch[0]
            df = data.copy()
            # Flatten MultiIndex columns (newer yfinance returns tuples like ('SOFI', 'Close'))
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[1] if isinstance(c, tuple) and len(c) > 1 else c for c in df.columns]
            df = df.reset_index()
            df.columns = [c.lower() if isinstance(c, str) else str(c).lower() for c in df.columns]
            df["symbol"] = sym
            for col in ("open", "high", "low", "close", "volume"):
                if col not in df.columns:
                    df[col] = None
            frames.append(df[["symbol", "date", "open", "high", "low", "close", "volume"]])
        else:
            for sym in batch:
                try:
                    sym_data = data[sym].copy().reset_index()
                    sym_data.columns = [c.lower() if isinstance(c, str) else str(c).lower() for c in sym_data.columns]
                    sym_data["symbol"] = sym
                    for col in ("open", "high", "low", "close", "volume"):
                        if col not in sym_data.columns:
                            sym_data[col] = None
                    frames.append(sym_data[["symbol", "date", "open", "high", "low", "close", "volume"]])
                except (KeyError, TypeError) as exc:
                    logger.warning(f"No data for {sym}: {exc}")

    if not frames:
        logger.warning("All batches returned empty — no price data")
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
