"""
Fibonacci Retracement Engine -- compute standard Fibonacci retracement levels
from the most recent swing high / swing low within a configurable lookback
window.

The module determines trend direction by comparing the chronological order of
the swing extremes:
    * swing high **before** swing low  -->  downtrend  (retrace upward)
    * swing low  **before** swing high -->  uptrend    (retrace downward)

Pure pandas/numpy -- no external dependencies.
"""

import logging
from typing import Any, Dict, List

import numpy as np
import pandas as pd

logger = logging.getLogger("apredator.features.fibonacci")

# Standard Fibonacci retracement percentages --------------------------------
_FIB_PCTS: List[float] = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
_FIB_LABELS: List[str] = ["0%", "23.6%", "38.2%", "50%", "61.8%", "78.6%", "100%"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_fibonacci_levels(
    df: pd.DataFrame,
    lookback: int = 120,
) -> Dict[str, Any]:
    """Compute Fibonacci retracement levels from recent swing high/low.

    Parameters
    ----------
    df : pd.DataFrame
        Daily OHLCV with columns ``date, open, high, low, close, volume``.
        At least *lookback* rows are recommended; fewer rows will use whatever
        history is available.
    lookback : int, optional
        Number of most-recent bars to scan for the swing high and swing low
        (default 120, roughly 6 trading months).

    Returns
    -------
    dict
        ``levels``          -- list of dicts ``{level, price, fib_pct}``
        ``swing_high``      -- price of the swing high
        ``swing_low``       -- price of the swing low
        ``swing_high_date`` -- date string of the swing high
        ``swing_low_date``  -- date string of the swing low
        ``trend``           -- ``"up"`` or ``"down"``
    """
    # Validate inputs -------------------------------------------------------
    required_cols = {"date", "open", "high", "low", "close", "volume"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"DataFrame is missing required columns: {missing}")

    if len(df) == 0:
        raise ValueError("DataFrame is empty -- cannot compute Fibonacci levels")

    # Slice to lookback window (use tail to keep most recent data) ----------
    window = df.tail(lookback).copy().reset_index(drop=True)

    # Identify swing high and swing low -------------------------------------
    high_series = window["high"].astype(float)
    low_series = window["low"].astype(float)

    swing_high_idx: int = int(high_series.idxmax())
    swing_low_idx: int = int(low_series.idxmin())

    swing_high: float = float(high_series.iloc[swing_high_idx])
    swing_low: float = float(low_series.iloc[swing_low_idx])

    swing_high_date = _date_to_str(window.loc[swing_high_idx, "date"])
    swing_low_date = _date_to_str(window.loc[swing_low_idx, "date"])

    # Determine trend direction ---------------------------------------------
    # Swing high came first chronologically --> downtrend (retrace upward)
    if swing_high_idx < swing_low_idx:
        trend = "down"
    else:
        trend = "up"

    # Compute fib levels ----------------------------------------------------
    diff = swing_high - swing_low
    levels: List[Dict[str, Any]] = []

    for pct, label in zip(_FIB_PCTS, _FIB_LABELS):
        if trend == "down":
            # Downtrend: retracement goes UP from the swing low
            price = swing_low + pct * diff
        else:
            # Uptrend: retracement goes DOWN from the swing high
            price = swing_high - pct * diff

        levels.append(
            {
                "level": label,
                "price": round(float(price), 2),
                "fib_pct": pct,
            }
        )

    return {
        "levels": levels,
        "swing_high": round(swing_high, 2),
        "swing_low": round(swing_low, 2),
        "swing_high_date": swing_high_date,
        "swing_low_date": swing_low_date,
        "trend": trend,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _date_to_str(date_val: Any) -> str:
    """Convert a date-like value to an ISO-format string."""
    if hasattr(date_val, "strftime"):
        return date_val.strftime("%Y-%m-%d")
    return str(date_val)
