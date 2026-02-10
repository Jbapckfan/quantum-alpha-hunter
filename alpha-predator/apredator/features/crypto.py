"""
Crypto-specific features -- funding rate, open interest, BTC decoupling,
and volatility compression.

Ported from QAHT derivatives.py and Destroyer crypto modules.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

import numpy as np
import pandas as pd

from ..db import session_scope
from ..schemas import FuturesMetrics, PriceOHLC

logger = logging.getLogger("apredator.features.crypto")


# ---------------------------------------------------------------------------
# Funding Rate Delta
# ---------------------------------------------------------------------------

def compute_funding_delta(
    symbol: str,
    window: int = 7,
) -> Dict[str, float]:
    """Compute change in average funding rate over *window* days vs 30-day baseline.

    Parameters
    ----------
    symbol : str
        Crypto symbol (e.g. ``"BTC"``).
    window : int
        Short-window days (default 7).

    Returns
    -------
    dict
        ``funding_rate_delta_7d`` -- 7d_avg_funding - 30d_avg_funding.
        Positive = increasingly bullish leverage; negative = bearish shift.
    """
    try:
        today = datetime.utcnow().date()
        date_30d_ago = (today - timedelta(days=30)).isoformat()
        date_7d_ago = (today - timedelta(days=window)).isoformat()

        with session_scope() as session:
            rows = (
                session.query(FuturesMetrics)
                .filter(
                    FuturesMetrics.symbol == symbol.upper(),
                    FuturesMetrics.date >= date_30d_ago,
                )
                .order_by(FuturesMetrics.date)
                .all()
            )

        if not rows:
            return {"funding_rate_delta_7d": 0.0}

        rates_30d = [r.funding_rate for r in rows if r.funding_rate is not None]
        rates_7d = [
            r.funding_rate
            for r in rows
            if r.funding_rate is not None and r.date >= date_7d_ago
        ]

        avg_30d = np.mean(rates_30d) if rates_30d else 0.0
        avg_7d = np.mean(rates_7d) if rates_7d else 0.0

        return {"funding_rate_delta_7d": round(float(avg_7d - avg_30d), 6)}

    except Exception:
        logger.exception("Funding delta computation failed for %s", symbol)
        return {"funding_rate_delta_7d": 0.0}


# ---------------------------------------------------------------------------
# Open Interest Delta
# ---------------------------------------------------------------------------

def compute_oi_delta(
    symbol: str,
    window: int = 7,
) -> Dict[str, float]:
    """Percent change in open interest over *window* days.

    Returns
    -------
    dict
        ``oi_delta_7d`` -- OI percent change (e.g. 5.0 = +5%).
    """
    try:
        today = datetime.utcnow().date()
        date_start = (today - timedelta(days=window + 5)).isoformat()

        with session_scope() as session:
            rows = (
                session.query(FuturesMetrics)
                .filter(
                    FuturesMetrics.symbol == symbol.upper(),
                    FuturesMetrics.date >= date_start,
                )
                .order_by(FuturesMetrics.date)
                .all()
            )

        if len(rows) < 2:
            return {"oi_delta_7d": 0.0}

        oi_values = [(r.date, r.oi) for r in rows if r.oi is not None]
        if len(oi_values) < 2:
            return {"oi_delta_7d": 0.0}

        oi_old = oi_values[0][1]
        oi_new = oi_values[-1][1]

        if oi_old == 0:
            return {"oi_delta_7d": 0.0}

        pct_change = (oi_new - oi_old) / oi_old * 100
        return {"oi_delta_7d": round(float(pct_change), 4)}

    except Exception:
        logger.exception("OI delta computation failed for %s", symbol)
        return {"oi_delta_7d": 0.0}


# ---------------------------------------------------------------------------
# BTC Decoupling
# ---------------------------------------------------------------------------

def compute_btc_decoupling(
    symbol: str,
    btc_returns: Optional[pd.Series] = None,
    window: int = 30,
) -> Dict[str, float]:
    """Measure how decoupled *symbol* is from BTC over *window* days.

    Parameters
    ----------
    symbol : str
        Crypto symbol.
    btc_returns : pd.Series, optional
        Pre-computed BTC daily returns indexed by date string.  If *None*,
        BTC prices are fetched from the database.
    window : int
        Rolling correlation window (default 30).

    Returns
    -------
    dict
        ``btc_decoupling`` -- 1 - correlation.  Higher = more decoupled.
        Range [0, 2] theoretically, but typically [0, 1].
    """
    try:
        today = datetime.utcnow().date()
        date_start = (today - timedelta(days=window + 10)).isoformat()

        # Fetch symbol prices
        with session_scope() as session:
            sym_rows = (
                session.query(PriceOHLC)
                .filter(
                    PriceOHLC.symbol == symbol.upper(),
                    PriceOHLC.date >= date_start,
                )
                .order_by(PriceOHLC.date)
                .all()
            )

        if len(sym_rows) < window // 2:
            return {"btc_decoupling": 0.0}

        sym_df = pd.DataFrame(
            [{"date": r.date, "close": r.close} for r in sym_rows]
        ).set_index("date")
        sym_returns = sym_df["close"].pct_change().dropna()

        # Fetch or use BTC returns
        if btc_returns is None:
            with session_scope() as session:
                btc_rows = (
                    session.query(PriceOHLC)
                    .filter(
                        PriceOHLC.symbol == "BTC",
                        PriceOHLC.date >= date_start,
                    )
                    .order_by(PriceOHLC.date)
                    .all()
                )
            if len(btc_rows) < window // 2:
                return {"btc_decoupling": 0.0}
            btc_df = pd.DataFrame(
                [{"date": r.date, "close": r.close} for r in btc_rows]
            ).set_index("date")
            btc_returns = btc_df["close"].pct_change().dropna()

        # Align on common dates
        common = sym_returns.index.intersection(btc_returns.index)
        if len(common) < 10:
            return {"btc_decoupling": 0.0}

        corr = sym_returns.loc[common].corr(btc_returns.loc[common])
        if np.isnan(corr):
            corr = 0.0
        decoupling = 1.0 - corr

        return {"btc_decoupling": round(float(decoupling), 4)}

    except Exception:
        logger.exception("BTC decoupling computation failed for %s", symbol)
        return {"btc_decoupling": 0.0}


# ---------------------------------------------------------------------------
# Volatility Compression
# ---------------------------------------------------------------------------

def compute_vol_compression(
    df: pd.DataFrame,
    short: int = 7,
    long: int = 60,
) -> Dict[str, float]:
    """Ratio of short-term to long-term realised volatility.

    Values < 0.5 indicate compressed volatility -- often a precursor to
    explosive moves in crypto markets.

    Parameters
    ----------
    df : pd.DataFrame
        Price dataframe with ``close`` column.
    short : int
        Short-window days (default 7).
    long : int
        Long-window days (default 60).

    Returns
    -------
    dict
        ``vol_compression`` -- short_vol / long_vol ratio.
    """
    try:
        close = df["close"]
        returns = close.pct_change().dropna()

        if len(returns) < long:
            return {"vol_compression": 1.0}

        vol_short = returns.iloc[-short:].std() * np.sqrt(365)
        vol_long = returns.iloc[-long:].std() * np.sqrt(365)

        if vol_long == 0 or np.isnan(vol_long):
            return {"vol_compression": 1.0}

        ratio = vol_short / vol_long

        return {"vol_compression": round(float(ratio), 4)}

    except Exception:
        logger.exception("Vol compression computation failed")
        return {"vol_compression": 1.0}


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

def compute_crypto_features(
    symbol: str,
    df: Optional[pd.DataFrame] = None,
) -> Dict[str, float]:
    """Compute all crypto-specific features for *symbol*.

    Parameters
    ----------
    symbol : str
        Crypto symbol (e.g. ``"ETH"``).
    df : pd.DataFrame, optional
        Price OHLCV dataframe.  Required for ``vol_compression``.

    Returns
    -------
    dict
        Combined dict of all crypto features.
    """
    result: Dict[str, float] = {}

    # Funding rate delta
    try:
        result.update(compute_funding_delta(symbol))
    except Exception:
        logger.exception("Funding delta failed for %s", symbol)
        result["funding_rate_delta_7d"] = 0.0

    # OI delta
    try:
        result.update(compute_oi_delta(symbol))
    except Exception:
        logger.exception("OI delta failed for %s", symbol)
        result["oi_delta_7d"] = 0.0

    # BTC decoupling
    try:
        result.update(compute_btc_decoupling(symbol))
    except Exception:
        logger.exception("BTC decoupling failed for %s", symbol)
        result["btc_decoupling"] = 0.0

    # Volatility compression (requires price df)
    if df is not None and not df.empty:
        try:
            result.update(compute_vol_compression(df))
        except Exception:
            logger.exception("Vol compression failed for %s", symbol)
            result["vol_compression"] = 1.0
    else:
        result["vol_compression"] = 1.0

    return result
