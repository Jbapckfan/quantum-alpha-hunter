"""
FINRA Short Interest & Dark Pool Proxy Features
================================================

Provides two main functions:

* ``fetch_short_interest(symbol)`` -- retrieves short interest data from
  Yahoo Finance (which aggregates FINRA/exchange-reported data) and computes
  a squeeze-potential flag.

* ``compute_dark_pool_proxy(df)`` -- estimates institutional accumulation or
  distribution using volume/price-range divergence and On Balance Volume (OBV)
  trend analysis.  This is a *proxy* because real dark pool (ATS) data
  requires a paid FINRA feed.

Dependencies: yfinance, numpy, pandas (all already in the project).
"""

import logging
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger("apredator.features.finra")


# ---------------------------------------------------------------------------
# Short Interest (via Yahoo Finance / FINRA)
# ---------------------------------------------------------------------------

def fetch_short_interest(symbol: str) -> Dict[str, Any]:
    """Fetch short interest metrics for *symbol* from Yahoo Finance.

    Yahoo exposes FINRA-reported short interest through the ``Ticker.info``
    dict.  We extract the key fields, normalise them, and derive a simple
    squeeze-potential flag.

    Parameters
    ----------
    symbol : str
        Ticker symbol (e.g. ``"GME"``).

    Returns
    -------
    dict
        Keys:

        * ``short_pct_float`` -- short interest as % of float (0-100 scale).
        * ``short_ratio`` -- days to cover (short shares / avg daily volume).
        * ``shares_short`` -- absolute number of shares sold short.
        * ``date_short_interest`` -- date of the most recent FINRA report.
        * ``squeeze_potential`` -- *True* when shortPctFloat > 15 **and**
          shortRatio > 3.
        * ``short_signal`` -- human-readable label:
          ``"Squeeze Risk"`` | ``"High Short"`` | ``"Moderate"`` | ``"Low"``.
    """
    empty: Dict[str, Any] = {
        "short_pct_float": 0.0,
        "short_ratio": 0.0,
        "shares_short": 0,
        "date_short_interest": None,
        "squeeze_potential": False,
        "short_signal": "Low",
    }

    try:
        ticker = yf.Ticker(symbol)
        info: Dict = ticker.info or {}
    except Exception:
        logger.exception("Failed to fetch info for %s", symbol)
        return empty

    try:
        # shortPercentOfFloat from yfinance is already a ratio (e.g. 0.15
        # means 15 %).  Convert to percentage for readability.
        raw_pct = info.get("shortPercentOfFloat")
        short_pct_float = round(float(raw_pct) * 100, 2) if raw_pct else 0.0

        short_ratio = float(info.get("shortRatio") or 0.0)
        shares_short = int(info.get("sharesShort") or 0)

        # dateShortInterest is a Unix timestamp (seconds).
        raw_date = info.get("dateShortInterest")
        if raw_date:
            date_short_interest = pd.Timestamp(raw_date, unit="s").strftime(
                "%Y-%m-%d"
            )
        else:
            date_short_interest = None

        # --- Derived signals ------------------------------------------------
        squeeze_potential = short_pct_float > 15.0 and short_ratio > 3.0

        if squeeze_potential:
            short_signal = "Squeeze Risk"
        elif short_pct_float > 10.0:
            short_signal = "High Short"
        elif short_pct_float > 5.0:
            short_signal = "Moderate"
        else:
            short_signal = "Low"

        return {
            "short_pct_float": short_pct_float,
            "short_ratio": round(short_ratio, 2),
            "shares_short": shares_short,
            "date_short_interest": date_short_interest,
            "squeeze_potential": squeeze_potential,
            "short_signal": short_signal,
        }

    except Exception:
        logger.exception("Error parsing short interest for %s", symbol)
        return empty


# ---------------------------------------------------------------------------
# Dark Pool Proxy (volume/price divergence + OBV)
# ---------------------------------------------------------------------------

def compute_dark_pool_proxy(df: pd.DataFrame) -> Dict[str, Any]:
    """Estimate institutional accumulation/distribution from OHLCV data.

    Real dark pool (ATS) trade data requires a FINRA subscription.  This
    function uses two publicly-observable proxies:

    1. **Volume-range divergence** -- when volume is significantly above its
       20-day average *but* the intraday price range (high - low) is
       unusually narrow, it suggests large institutional orders are being
       executed algorithmically, suppressing price impact (i.e. dark-pool
       style accumulation).  Conversely, high volume + wide range + bearish
       close suggests distribution.

    2. **On Balance Volume (OBV) trend** -- when OBV is rising while price
       is flat or falling, someone is accumulating.

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV DataFrame with columns ``open``, ``high``, ``low``, ``close``,
        ``volume``.  Must contain at least 20 rows.

    Returns
    -------
    dict
        Keys:

        * ``accumulation_days`` -- count of high-volume, narrow-range days
          in the last 20 sessions.
        * ``distribution_days`` -- count of high-volume, wide-range, bearish
          days in the last 20 sessions.
        * ``obv_trend`` -- ``"accumulation"`` | ``"distribution"`` |
          ``"confirming"``.
        * ``dark_pool_signal`` -- composite label:
          ``"Strong Accumulation"`` | ``"Accumulation"`` |
          ``"Distribution"`` | ``"Neutral"``.
    """
    neutral: Dict[str, Any] = {
        "accumulation_days": 0,
        "distribution_days": 0,
        "obv_trend": "confirming",
        "dark_pool_signal": "Neutral",
    }

    try:
        required_cols = {"open", "high", "low", "close", "volume"}
        if not required_cols.issubset(set(df.columns)):
            logger.warning(
                "DataFrame missing required columns: %s",
                required_cols - set(df.columns),
            )
            return neutral

        if len(df) < 20:
            logger.debug("Not enough data for dark pool proxy (need >= 20 rows)")
            return neutral

        # Work on a copy of the tail to avoid mutating the caller's data.
        data = df.copy()

        # ---- Volume / range divergence (last 20 bars) ---------------------
        tail = data.iloc[-20:].copy()

        avg_volume_20 = data["volume"].rolling(20).mean()
        tail["vol_ratio"] = (
            tail["volume"].values
            / avg_volume_20.iloc[-20:].values
        )

        tail["range_pct"] = (
            (tail["high"].values - tail["low"].values)
            / tail["close"].values
            * 100
        )
        avg_range = tail["range_pct"].rolling(20, min_periods=1).mean()

        # Accumulation day: high volume + narrow range
        accumulation_mask = (tail["vol_ratio"] > 1.5) & (
            tail["range_pct"] < avg_range * 0.7
        )
        accumulation_days = int(accumulation_mask.sum())

        # Distribution day: high volume + wide range + bearish close
        distribution_mask = (
            (tail["vol_ratio"] > 1.5)
            & (tail["close"].values < tail["open"].values)
            & (tail["range_pct"] > avg_range * 1.3)
        )
        distribution_days = int(distribution_mask.sum())

        # ---- OBV trend ----------------------------------------------------
        close = data["close"].values.astype(float)
        volume = data["volume"].values.astype(float)

        price_diff = np.diff(close, prepend=close[0])
        signed_volume = np.where(price_diff > 0, volume, -volume)
        obv = np.cumsum(signed_volume)

        # Compare OBV now vs 20 bars ago; same for price.
        obv_now = obv[-1]
        obv_20ago = obv[-20] if len(obv) >= 20 else obv[0]
        close_now = close[-1]
        close_20ago = close[-20] if len(close) >= 20 else close[0]

        if obv_now > obv_20ago and close_now <= close_20ago:
            obv_trend = "accumulation"
        elif obv_now < obv_20ago and close_now >= close_20ago:
            obv_trend = "distribution"
        else:
            obv_trend = "confirming"

        # ---- Composite signal ---------------------------------------------
        if accumulation_days >= 5 and obv_trend == "accumulation":
            dark_pool_signal = "Strong Accumulation"
        elif accumulation_days >= 3:
            dark_pool_signal = "Accumulation"
        elif distribution_days >= 3:
            dark_pool_signal = "Distribution"
        else:
            dark_pool_signal = "Neutral"

        return {
            "accumulation_days": accumulation_days,
            "distribution_days": distribution_days,
            "obv_trend": obv_trend,
            "dark_pool_signal": dark_pool_signal,
        }

    except Exception:
        logger.exception("Dark pool proxy computation failed")
        return neutral
