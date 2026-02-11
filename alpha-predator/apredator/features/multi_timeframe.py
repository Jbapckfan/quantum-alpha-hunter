"""
Multi-Timeframe Master Score -- aggregates technical bias across daily,
weekly, and monthly timeframes to determine overall trend alignment.

Three timeframes are scored on four sub-signals each (RSI, MACD, MA-20
position, and higher-low structure).  The individual scores are weighted
to produce a single 0-100 master score and a categorical signal label.

Pure pandas/numpy -- no external dependencies.
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("apredator.features.multi_timeframe")

# ---------------------------------------------------------------------------
# Default / empty return
# ---------------------------------------------------------------------------

_EMPTY: Dict[str, Any] = {
    "daily_bias": "neutral",
    "weekly_bias": "neutral",
    "monthly_bias": "neutral",
    "tf_alignment": 0,
    "mtf_score": 50.0,
    "mtf_signal": "Neutral",
    "daily_detail": {},
    "weekly_detail": {},
    "monthly_detail": {},
}

# ---------------------------------------------------------------------------
# Timeframe weights for the master score
# ---------------------------------------------------------------------------
_TF_WEIGHTS: Dict[str, float] = {
    "daily": 0.3,
    "weekly": 0.4,
    "monthly": 0.3,
}

# Maximum sub-signal score per timeframe
_MAX_SUB_SIGNALS: int = 4


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_multi_timeframe_score(
    df: pd.DataFrame,
) -> Dict[str, Any]:
    """Score trend alignment across daily, weekly, and monthly timeframes.

    Parameters
    ----------
    df : pd.DataFrame
        Daily OHLCV data with columns ``date, open, high, low, close, volume``.
        At least 100 rows recommended; fewer rows degrade the monthly view.

    Returns
    -------
    dict
        ``daily_bias``    -- ``"bullish"`` / ``"bearish"`` / ``"neutral"``
        ``weekly_bias``   -- same
        ``monthly_bias``  -- same
        ``tf_alignment``  -- count of bullish timeframes (0-3)
        ``mtf_score``     -- weighted 0-100 composite score
        ``mtf_signal``    -- ``"Strong Bull"``/``"Bull"``/``"Neutral"``/
                            ``"Bear"``/``"Strong Bear"``
        ``daily_detail``  -- sub-signal breakdown dict
        ``weekly_detail``  -- sub-signal breakdown dict
        ``monthly_detail`` -- sub-signal breakdown dict
    """
    try:
        required_cols = {"date", "open", "high", "low", "close", "volume"}
        missing = required_cols - set(df.columns)
        if missing:
            logger.warning("Missing columns %s -- returning defaults", missing)
            return dict(_EMPTY)

        if len(df) < 20:
            logger.warning("Insufficient data (%d rows) for MTF analysis", len(df))
            return dict(_EMPTY)

        # Ensure date index for resampling ----------------------------------
        ohlcv = df.copy()
        ohlcv["date"] = pd.to_datetime(ohlcv["date"])
        ohlcv = ohlcv.sort_values("date").set_index("date")

        # Build OHLCV for each timeframe ------------------------------------
        daily = ohlcv.copy()
        weekly = _resample_ohlcv(ohlcv, "W")
        monthly = _resample_ohlcv(ohlcv, "ME")

        # Score each timeframe ----------------------------------------------
        daily_detail = _score_timeframe(daily, "daily")
        weekly_detail = _score_timeframe(weekly, "weekly")
        monthly_detail = _score_timeframe(monthly, "monthly")

        daily_bias = daily_detail["bias"]
        weekly_bias = weekly_detail["bias"]
        monthly_bias = monthly_detail["bias"]

        # Alignment: count of bullish timeframes ----------------------------
        tf_alignment = sum(
            1 for b in [daily_bias, weekly_bias, monthly_bias] if b == "bullish"
        )

        # Composite score: weighted average of per-TF percentages -----------
        daily_pct = daily_detail["score"] / _MAX_SUB_SIGNALS * 100
        weekly_pct = weekly_detail["score"] / _MAX_SUB_SIGNALS * 100
        monthly_pct = monthly_detail["score"] / _MAX_SUB_SIGNALS * 100

        mtf_score = round(
            _TF_WEIGHTS["daily"] * daily_pct
            + _TF_WEIGHTS["weekly"] * weekly_pct
            + _TF_WEIGHTS["monthly"] * monthly_pct,
            1,
        )

        mtf_signal = _score_to_signal(mtf_score)

        logger.info(
            "MTF score=%.1f (%s), alignment=%d/3, biases=%s/%s/%s",
            mtf_score,
            mtf_signal,
            tf_alignment,
            daily_bias,
            weekly_bias,
            monthly_bias,
        )

        return {
            "daily_bias": daily_bias,
            "weekly_bias": weekly_bias,
            "monthly_bias": monthly_bias,
            "tf_alignment": tf_alignment,
            "mtf_score": mtf_score,
            "mtf_signal": mtf_signal,
            "daily_detail": daily_detail,
            "weekly_detail": weekly_detail,
            "monthly_detail": monthly_detail,
        }

    except Exception:
        logger.exception("Multi-timeframe score computation failed")
        return dict(_EMPTY)


# ---------------------------------------------------------------------------
# Per-timeframe scoring
# ---------------------------------------------------------------------------

def _score_timeframe(ohlcv: pd.DataFrame, label: str) -> Dict[str, Any]:
    """Evaluate four sub-signals on a single timeframe's OHLCV data.

    Sub-signals (each 0 or 1):
      1. RSI-14 > 50  (bullish momentum)
      2. MACD line > signal line  (bullish crossover)
      3. Close > 20-period MA  (above trend)
      4. Higher lows: last 3 swing lows ascending  (bullish structure)

    Returns a detail dict with individual flags and aggregate bias.
    """
    close = ohlcv["close"].astype(float)
    low = ohlcv["low"].astype(float)

    if len(close) < 5:
        return {
            "rsi": 50.0,
            "macd_bullish": False,
            "above_ma20": False,
            "higher_lows": False,
            "score": 2,
            "bias": "neutral",
        }

    # 1. RSI-14 -----------------------------------------------------------------
    rsi = _compute_rsi(close, period=14)
    rsi_bullish: bool = rsi > 50.0

    # 2. MACD line vs signal line -----------------------------------------------
    macd_line, signal_line = _compute_macd(close)
    macd_bullish: bool = macd_line > signal_line

    # 3. Close vs 20-period MA --------------------------------------------------
    ma_period = min(20, len(close))
    ma20 = close.rolling(ma_period).mean()
    above_ma20: bool = bool(close.iloc[-1] > ma20.iloc[-1])

    # 4. Higher lows (last 3 swing lows ascending) ------------------------------
    higher_lows = _check_higher_lows(low)

    # Aggregate -----------------------------------------------------------------
    score = int(rsi_bullish) + int(macd_bullish) + int(above_ma20) + int(higher_lows)
    if score >= 3:
        bias = "bullish"
    elif score <= 1:
        bias = "bearish"
    else:
        bias = "neutral"

    return {
        "rsi": round(rsi, 2),
        "macd_bullish": macd_bullish,
        "above_ma20": above_ma20,
        "higher_lows": higher_lows,
        "score": score,
        "bias": bias,
    }


# ---------------------------------------------------------------------------
# Indicator helpers
# ---------------------------------------------------------------------------

def _compute_rsi(close: pd.Series, period: int = 14) -> float:
    """Compute RSI using exponential-weighted moving average."""
    if len(close) < period + 1:
        return 50.0

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)

    value = rsi.iloc[-1]
    return float(value) if not np.isnan(value) else 50.0


def _compute_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> tuple:
    """Return ``(macd_line, signal_line)`` as the most recent scalar values.

    Uses standard EMA-12/26 for the MACD line and EMA-9 of the MACD line
    for the signal.  Returns ``(0.0, 0.0)`` when data is insufficient.
    """
    if len(close) < slow + signal_period:
        return 0.0, 0.0

    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line_series = ema_fast - ema_slow
    signal_series = macd_line_series.ewm(span=signal_period, adjust=False).mean()

    macd_val = float(macd_line_series.iloc[-1])
    signal_val = float(signal_series.iloc[-1])

    if np.isnan(macd_val) or np.isnan(signal_val):
        return 0.0, 0.0

    return macd_val, signal_val


def _check_higher_lows(low: pd.Series, window: int = 5, n_lows: int = 3) -> bool:
    """Check whether the last *n_lows* swing lows are ascending.

    Swing lows are identified via a rolling minimum over *window* bars.
    A bar is a swing low if its low equals the rolling-min centred on it.
    """
    if len(low) < window * n_lows:
        return False

    # Rolling min (left-aligned, so min of [i, i+window) )
    rolling_min = low.rolling(window, center=True).min()
    swing_mask = low == rolling_min
    swing_indices = low.index[swing_mask]

    if len(swing_indices) < n_lows:
        return False

    # Take the last n_lows swing lows
    recent_lows = low.loc[swing_indices].iloc[-n_lows:]
    values = recent_lows.values.astype(float)

    # Check strictly ascending
    return bool(np.all(np.diff(values) > 0))


# ---------------------------------------------------------------------------
# Resampling helper
# ---------------------------------------------------------------------------

def _resample_ohlcv(ohlcv: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample a DatetimeIndex-ed OHLCV DataFrame to *rule* frequency.

    Parameters
    ----------
    ohlcv : pd.DataFrame
        Must have columns ``open, high, low, close, volume`` with a
        DatetimeIndex.
    rule : str
        Pandas offset alias, e.g. ``"W"`` for weekly, ``"ME"`` for
        month-end.
    """
    resampled = ohlcv.resample(rule).agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    ).dropna(subset=["close"])

    return resampled


# ---------------------------------------------------------------------------
# Signal labelling
# ---------------------------------------------------------------------------

def _score_to_signal(score: float) -> str:
    """Map a 0-100 composite score to a categorical signal label."""
    if score >= 80:
        return "Strong Bull"
    if score >= 60:
        return "Bull"
    if score >= 40:
        return "Neutral"
    if score >= 20:
        return "Bear"
    return "Strong Bear"
