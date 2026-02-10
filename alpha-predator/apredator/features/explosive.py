"""
The 11 explosive signals from Hedge Fund ``ultimate_scanner_v5.py``.

This module computes **raw signal values** only.  Thresholding and
combo-pattern matching live in ``apredator.scoring.combo_matcher``.

Signal thresholds and ML-validated feature weights are exported as
module-level constants so that other parts of the system can reference
them without circular imports.
"""
import logging
from typing import Dict

import numpy as np
import pandas as pd

logger = logging.getLogger("apredator.features.explosive")

# ---------------------------------------------------------------------------
# Signal thresholds (empirically validated)
# ---------------------------------------------------------------------------
THRESHOLDS: Dict[str, float] = {
    "vol_zscore": 0.15,          # 443% lift -- most predictive
    "gap_up_pct": 1.5,           # 72% lift
    "vol_spike_min": 1,          # in 5 days, vol > 1.5x avg
    "vol_accel_min": 0.10,       # 10% acceleration
    "range_20d_min": 20.0,       # 20% range
    "rejection_wick_min": 1.0,   # 1% wick
    "selling_pressure_max": 2,   # <=2 up days in 5
    "low_in_range_max": 0.40,    # bottom 40%
    "rsi_low": 30,
    "rsi_high": 50,
    "pullback_min": -15.0,       # -15% momentum
}

# ---------------------------------------------------------------------------
# Validated feature weights from ml_scoring_engine.py
# ---------------------------------------------------------------------------
FEATURE_WEIGHTS: Dict[str, float] = {
    "vol_zscore": 4.43,
    "momentum_10d": -1.70,
    "rejection_wick": 1.08,
    "vol_spike_count": 0.87,
    "gap_up": 0.72,
    "range_20d": 0.64,
    "vol_accel": 0.23,
    "low_in_range": -0.37,
    "selling_pressure": -0.25,
    "rsi_14": -0.15,
}


# ---------------------------------------------------------------------------
# Individual signal computations
# ---------------------------------------------------------------------------

def compute_vol_zscore(df: pd.DataFrame) -> float:
    """Z-score of current volume relative to 20-day distribution.

    Returns
    -------
    float
        (current_vol - 20d_mean) / 20d_std
    """
    volume = df["volume"]
    mean_20 = volume.iloc[-20:].mean()
    std_20 = volume.iloc[-20:].std()
    if std_20 == 0 or np.isnan(std_20):
        return 0.0
    return float((volume.iloc[-1] - mean_20) / std_20)


def compute_gap_up(df: pd.DataFrame) -> float:
    """Gap-up percentage: (open - prev_close) / prev_close * 100."""
    close = df["close"]
    open_ = df["open"]
    if len(close) < 2:
        return 0.0
    prev_close = close.iloc[-2]
    if prev_close == 0:
        return 0.0
    return float((open_.iloc[-1] - prev_close) / prev_close * 100)


def compute_vol_spikes(df: pd.DataFrame, window: int = 5) -> int:
    """Count of days where volume > 1.5x 20-day average in last *window* days."""
    volume = df["volume"]
    avg_20 = volume.rolling(20).mean()
    tail = volume.iloc[-window:]
    avg_tail = avg_20.iloc[-window:]
    count = int(((tail > 1.5 * avg_tail) & avg_tail.notna()).sum())
    return count


def compute_vol_accel(df: pd.DataFrame) -> float:
    """Volume acceleration: (recent_5d_avg / prior_5d_avg) - 1."""
    volume = df["volume"]
    if len(volume) < 10:
        return 0.0
    recent = volume.iloc[-5:].mean()
    prior = volume.iloc[-10:-5].mean()
    if prior == 0:
        return 0.0
    return float(recent / prior - 1)


def compute_range_20d(df: pd.DataFrame) -> float:
    """20-day price range as percentage of current close."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    high_20 = high.iloc[-20:].max()
    low_20 = low.iloc[-20:].min()
    last_close = close.iloc[-1]
    if last_close == 0:
        return 0.0
    return float((high_20 - low_20) / last_close * 100)


def compute_rejection_wicks(df: pd.DataFrame) -> float:
    """Rejection (upper) wick size as percentage of close for the last bar."""
    high = df["high"].iloc[-1]
    close = df["close"].iloc[-1]
    open_ = df["open"].iloc[-1]
    body_top = max(close, open_)
    if close == 0:
        return 0.0
    return float((high - body_top) / close * 100)


def compute_selling_pressure(df: pd.DataFrame) -> int:
    """Count of up-days in the last 5 trading days.

    Lower count = more selling pressure (bearish short-term action that
    precedes explosive reversals).
    """
    close = df["close"]
    changes = close.diff().iloc[-5:]
    return int((changes > 0).sum())


def compute_low_in_range(df: pd.DataFrame) -> float:
    """Position of current close within the 20-day high/low range.

    Returns
    -------
    float
        0 = at the 20-day low, 1 = at the 20-day high.
    """
    high_20 = df["high"].iloc[-20:].max()
    low_20 = df["low"].iloc[-20:].min()
    last_close = df["close"].iloc[-1]
    rng = high_20 - low_20
    if rng == 0:
        return 0.5
    return float((last_close - low_20) / rng)


def compute_momentum_10d(df: pd.DataFrame) -> float:
    """10-day momentum: (close / close[-10] - 1) * 100."""
    close = df["close"]
    if len(close) < 11:
        return 0.0
    prev = close.iloc[-11]
    if prev == 0:
        return 0.0
    return float((close.iloc[-1] / prev - 1) * 100)


def compute_pullback(df: pd.DataFrame) -> float:
    """Pullback from 20-day high: (close / 20d_high - 1) * 100.

    Always <= 0 when below the high.
    """
    high_20 = df["high"].iloc[-20:].max()
    last_close = df["close"].iloc[-1]
    if high_20 == 0:
        return 0.0
    return float((last_close / high_20 - 1) * 100)


def compute_drawdown_60d(df: pd.DataFrame) -> float:
    """Drawdown from 60-day rolling high: (rolling_high - close) / rolling_high * 100.

    Always >= 0 when below the high.
    """
    close = df["close"]
    if len(close) < 60:
        rolling_high = close.max()
    else:
        rolling_high = close.iloc[-60:].max()
    last_close = close.iloc[-1]
    if rolling_high == 0:
        return 0.0
    return float((rolling_high - last_close) / rolling_high * 100)


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

def compute_all_explosive(df: pd.DataFrame) -> Dict[str, float]:
    """Compute all 11 explosive signal values and return a merged dict.

    Each computation is individually wrapped in try/except so that a single
    failure does not block the rest.
    """
    result: Dict[str, float] = {}

    computations = [
        ("vol_zscore", lambda: compute_vol_zscore(df)),
        ("gap_up", lambda: compute_gap_up(df)),
        ("vol_spike_count", lambda: compute_vol_spikes(df)),
        ("vol_accel", lambda: compute_vol_accel(df)),
        ("range_20d", lambda: compute_range_20d(df)),
        ("rejection_wick", lambda: compute_rejection_wicks(df)),
        ("selling_pressure", lambda: compute_selling_pressure(df)),
        ("low_in_range", lambda: compute_low_in_range(df)),
        ("momentum_10d", lambda: compute_momentum_10d(df)),
        ("pullback_pct", lambda: compute_pullback(df)),
        ("drawdown_60d", lambda: compute_drawdown_60d(df)),
    ]

    for name, fn in computations:
        try:
            result[name] = fn()
        except Exception:
            logger.exception("Failed to compute explosive signal: %s", name)
            result[name] = np.nan

    return result


# ---------------------------------------------------------------------------
# V2 weighted score
# ---------------------------------------------------------------------------

def compute_v2_score(signals_dict: Dict[str, float]) -> float:
    """Compute the V2 weighted score from raw signal values.

    Parameters
    ----------
    signals_dict : dict
        Keys must match the names in :data:`FEATURE_WEIGHTS`.
        Missing keys contribute zero to the score.

    Returns
    -------
    float
        Weighted sum of available features.
    """
    score = 0.0
    for feature, weight in FEATURE_WEIGHTS.items():
        value = signals_dict.get(feature)
        if value is not None and not np.isnan(value):
            score += weight * value
    return round(score, 4)
