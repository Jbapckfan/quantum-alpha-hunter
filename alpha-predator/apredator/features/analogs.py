"""
Historical Analog Engine -- find past instances of similar setups in a
stock's own price history, then compute forward returns for each match.

Given the current feature state (drawdown%, RSI, volume ratio, BB position),
this module searches the full daily OHLCV history for dates where the same
features were within a configurable distance threshold.  Forward 5/10/20-day
returns for every match are aggregated into win-rate and median statistics.

Pure pandas/numpy -- no external dependencies beyond the standard scientific
stack.
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("apredator.features.analogs")

# ---------------------------------------------------------------------------
# Vectorised feature computation
# ---------------------------------------------------------------------------

_FIB_LEVELS: List[float] = []  # not used here; kept for grep clarity


def _compute_rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    """Vectorised RSI-14 for the entire series (Wilder smoothing via EWM)."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    return rsi


def _compute_feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Return a DataFrame aligned with *df* containing the four analog features.

    Columns produced:
        drawdown_60d, rsi_14, volume_ratio_20d, bb_position

    All heavy lifting is vectorised over the full history so that the caller
    only needs a single pass to score every candidate date.
    """
    close = df["close"].astype(float)
    volume = df["volume"].astype(float)

    # 1. Drawdown from 60-day rolling high ----------------------------------
    rolling_60d_high = close.rolling(60, min_periods=1).max()
    drawdown_60d = (rolling_60d_high - close) / rolling_60d_high * 100.0

    # 2. RSI-14 -------------------------------------------------------------
    rsi_14 = _compute_rsi_series(close, period=14)

    # 3. Volume ratio (today vs 20-day average) -----------------------------
    avg_vol_20 = volume.rolling(20, min_periods=1).mean()
    volume_ratio_20d = volume / avg_vol_20.replace(0, np.nan)
    volume_ratio_20d = volume_ratio_20d.fillna(1.0)

    # 4. Bollinger Band position (20-period, 2 std) -------------------------
    middle = close.rolling(20, min_periods=20).mean()
    std = close.rolling(20, min_periods=20).std()
    upper = middle + 2.0 * std
    lower = middle - 2.0 * std
    band_width = upper - lower
    bb_position = (close - lower) / band_width.replace(0, np.nan)
    bb_position = bb_position.clip(0.0, 1.0).fillna(0.5)

    features = pd.DataFrame(
        {
            "drawdown_60d": drawdown_60d,
            "rsi_14": rsi_14,
            "volume_ratio_20d": volume_ratio_20d,
            "bb_position": bb_position,
        },
        index=df.index,
    )
    return features


# ---------------------------------------------------------------------------
# Similarity scoring
# ---------------------------------------------------------------------------

# Normalisation denominators for each feature dimension.
_NORM: Dict[str, float] = {
    "drawdown_60d": 20.0,
    "rsi_14": 30.0,
    "volume_ratio_20d": 2.0,
    "bb_position": 1.0,
}


def _compute_distances(
    feature_matrix: pd.DataFrame,
    current: Dict[str, float],
) -> pd.Series:
    """Return a Series of mean normalised distances from *current* for every row."""
    dist = pd.DataFrame(index=feature_matrix.index, dtype=float)
    for col, norm in _NORM.items():
        dist[col] = (feature_matrix[col] - current[col]).abs() / norm
    return dist.mean(axis=1)


# ---------------------------------------------------------------------------
# Forward returns
# ---------------------------------------------------------------------------

def _compute_forward_returns(
    close: pd.Series,
    indices: pd.Index,
) -> pd.DataFrame:
    """Compute forward 5d, 10d, 20d percentage returns for each index position.

    Parameters
    ----------
    close : pd.Series
        Full close-price series (positional integer index expected).
    indices : pd.Index
        Integer positions within *close* at which to compute forward returns.
    """
    results: List[Dict[str, Optional[float]]] = []
    close_arr = close.values
    n = len(close_arr)

    for idx in indices:
        row: Dict[str, Optional[float]] = {}
        base = close_arr[idx]
        for label, horizon in [("fwd_5d", 5), ("fwd_10d", 10), ("fwd_20d", 20)]:
            target = idx + horizon
            if target < n and base != 0:
                row[label] = (close_arr[target] / base - 1.0) * 100.0
            else:
                row[label] = None
        results.append(row)

    return pd.DataFrame(results, index=indices)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_historical_analogs(
    df: pd.DataFrame,
    current_features: Dict[str, float],
    min_matches: int = 5,
    distance_threshold: float = 0.3,
) -> Dict[str, Any]:
    """Search a stock's own price history for past instances of a similar setup.

    Parameters
    ----------
    df : pd.DataFrame
        Daily OHLCV with columns ``date, open, high, low, close, volume``.
        At least ~1 year of history recommended.
    current_features : dict
        Must contain exactly these keys:
        ``drawdown_60d``, ``rsi_14``, ``volume_ratio_20d``, ``bb_position``.
    min_matches : int, optional
        Minimum number of matches required to report results (default 5).
    distance_threshold : float, optional
        Maximum mean normalised distance to qualify as a match (default 0.3).

    Returns
    -------
    dict
        ``matches`` -- list of per-match dicts sorted by similarity (best first).
        ``stats``   -- aggregate statistics across all matches.
        ``summary`` -- human-readable one-liner.
    """
    # Validate inputs -------------------------------------------------------
    required_cols = {"date", "open", "high", "low", "close", "volume"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"DataFrame is missing required columns: {missing}")

    required_keys = {"drawdown_60d", "rsi_14", "volume_ratio_20d", "bb_position"}
    missing_keys = required_keys - set(current_features.keys())
    if missing_keys:
        raise ValueError(f"current_features is missing keys: {missing_keys}")

    # Work on a clean copy with integer positional index --------------------
    work = df.copy().reset_index(drop=True)
    n = len(work)

    if n < 80:
        # Not enough history for meaningful 60-day features + 20-day forward
        return _empty_result("Insufficient historical data")

    # Compute features for every bar ----------------------------------------
    feature_matrix = _compute_feature_matrix(work)

    # Drop rows that don't have valid features (warm-up period) and the last
    # 20 bars (we need room for forward returns).
    valid_mask = feature_matrix.notna().all(axis=1)
    candidate_mask = valid_mask.copy()
    candidate_mask.iloc[-(20):] = False  # exclude last 20 days
    candidate_idx = candidate_mask[candidate_mask].index

    if len(candidate_idx) == 0:
        return _empty_result("Insufficient historical data")

    # Score every candidate -------------------------------------------------
    distances = _compute_distances(feature_matrix.loc[candidate_idx], current_features)
    match_mask = distances < distance_threshold
    match_idx = distances[match_mask].sort_values().index
    match_distances = distances[match_mask].sort_values()

    if len(match_idx) < min_matches:
        return _empty_result("Insufficient historical data")

    # Forward returns -------------------------------------------------------
    fwd = _compute_forward_returns(work["close"], match_idx)

    # Build match list ------------------------------------------------------
    matches: List[Dict[str, Any]] = []
    for pos in match_idx:
        row_feats = feature_matrix.loc[pos].to_dict()
        fwd_row = fwd.loc[pos]
        date_val = work.loc[pos, "date"]
        # Normalise date to string
        if hasattr(date_val, "strftime"):
            date_str = date_val.strftime("%Y-%m-%d")
        else:
            date_str = str(date_val)

        matches.append(
            {
                "date": date_str,
                "similarity": round(1.0 - float(match_distances.loc[pos]), 4),
                "fwd_5d": _safe_round(fwd_row.get("fwd_5d")),
                "fwd_10d": _safe_round(fwd_row.get("fwd_10d")),
                "fwd_20d": _safe_round(fwd_row.get("fwd_20d")),
                "features": {k: round(float(v), 4) for k, v in row_feats.items()},
            }
        )

    # Aggregate statistics --------------------------------------------------
    fwd_10d_vals = fwd["fwd_10d"].dropna()
    fwd_20d_vals = fwd["fwd_20d"].dropna()

    count = len(matches)
    win_rate_10d = (
        float((fwd_10d_vals > 5.0).sum() / len(fwd_10d_vals) * 100.0)
        if len(fwd_10d_vals) > 0
        else 0.0
    )
    win_rate_20d = (
        float((fwd_20d_vals > 10.0).sum() / len(fwd_20d_vals) * 100.0)
        if len(fwd_20d_vals) > 0
        else 0.0
    )
    median_10d = float(fwd_10d_vals.median()) if len(fwd_10d_vals) > 0 else 0.0
    median_20d = float(fwd_20d_vals.median()) if len(fwd_20d_vals) > 0 else 0.0
    best_20d = float(fwd_20d_vals.max()) if len(fwd_20d_vals) > 0 else 0.0
    worst_20d = float(fwd_20d_vals.min()) if len(fwd_20d_vals) > 0 else 0.0

    stats: Dict[str, Any] = {
        "count": count,
        "win_rate_10d": round(win_rate_10d, 1),
        "win_rate_20d": round(win_rate_20d, 1),
        "median_10d": round(median_10d, 2),
        "median_20d": round(median_20d, 2),
        "best_20d": round(best_20d, 2),
        "worst_20d": round(worst_20d, 2),
    }

    summary = (
        f"{count} similar setups found. "
        f"{win_rate_20d:.0f}% rallied 10%+ in 20d. "
        f"Median: {median_20d:+.1f}%"
    )

    return {"matches": matches, "stats": stats, "summary": summary}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_round(val: Any, decimals: int = 2) -> Optional[float]:
    """Round a value, returning None if it is NaN or already None."""
    if val is None:
        return None
    try:
        f = float(val)
        if np.isnan(f):
            return None
        return round(f, decimals)
    except (TypeError, ValueError):
        return None


def _empty_result(message: str) -> Dict[str, Any]:
    """Return the canonical empty-result structure."""
    return {
        "matches": [],
        "stats": {
            "count": 0,
            "win_rate_10d": 0.0,
            "win_rate_20d": 0.0,
            "median_10d": 0.0,
            "median_20d": 0.0,
            "best_20d": 0.0,
            "worst_20d": 0.0,
        },
        "summary": message,
    }
