"""
RSI / MACD Divergence Detector -- identify bullish and bearish divergences
between price action and momentum indicators.

A divergence occurs when price makes a new extreme (higher high or lower low)
while the corresponding momentum indicator fails to confirm, signalling a
potential trend reversal.

Pure pandas/numpy -- no external dependencies.
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("apredator.features.divergence")

# ---------------------------------------------------------------------------
# Default empty result
# ---------------------------------------------------------------------------

_EMPTY: Dict[str, Any] = {
    "has_bullish_div": False,
    "has_bearish_div": False,
    "divergence_type": "None",
    "divergence_strength": 0,
    "divergence_bars_ago": None,
    "divergences": [],
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Compute Wilder-smoothed RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    return rsi


def _compute_macd_histogram(close: pd.Series) -> pd.Series:
    """Compute MACD histogram (MACD line minus signal line, 12/26/9)."""
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    return macd_line - signal_line


def _find_pivot_lows(
    series: pd.Series, pivot_window: int, start_idx: int, end_idx: int
) -> List[int]:
    """Return indices of pivot lows within [start_idx, end_idx).

    A pivot low at index *i* means ``series[i]`` is the minimum of
    ``series[i - pivot_window : i + pivot_window + 1]``.
    """
    pivots: List[int] = []
    values = series.values
    for i in range(max(start_idx, pivot_window), min(end_idx, len(values) - pivot_window)):
        window_slice = values[i - pivot_window: i + pivot_window + 1]
        if values[i] == np.nanmin(window_slice):
            pivots.append(i)
    return pivots


def _find_pivot_highs(
    series: pd.Series, pivot_window: int, start_idx: int, end_idx: int
) -> List[int]:
    """Return indices of pivot highs within [start_idx, end_idx).

    A pivot high at index *i* means ``series[i]`` is the maximum of
    ``series[i - pivot_window : i + pivot_window + 1]``.
    """
    pivots: List[int] = []
    values = series.values
    for i in range(max(start_idx, pivot_window), min(end_idx, len(values) - pivot_window)):
        window_slice = values[i - pivot_window: i + pivot_window + 1]
        if values[i] == np.nanmax(window_slice):
            pivots.append(i)
    return pivots


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_divergences(
    df: pd.DataFrame,
    lookback: int = 60,
    pivot_window: int = 5,
) -> Dict[str, Any]:
    """Detect RSI and MACD divergences against price action.

    Parameters
    ----------
    df : pd.DataFrame
        Daily OHLCV with columns ``date, open, high, low, close, volume``.
    lookback : int, optional
        Number of most-recent bars to scan for divergences (default 60).
    pivot_window : int, optional
        Half-width of the window used to identify pivot extremes (default 5).
        A pivot low at index *i* requires ``low[i]`` to be the minimum of
        ``low[i - pivot_window : i + pivot_window + 1]``.

    Returns
    -------
    dict
        ``has_bullish_div``      -- bool
        ``has_bearish_div``      -- bool
        ``divergence_type``      -- descriptive label (e.g. ``"RSI Bullish"``,
                                    ``"MACD Bearish"``, ``"RSI+MACD Bullish"``,
                                    or ``"None"``)
        ``divergence_strength``  -- 0-3 integer score
        ``divergence_bars_ago``  -- bars since the most recent divergence pivot
        ``divergences``          -- list of detail dicts
    """
    # Minimum data guard: need enough bars for indicator warm-up + lookback
    min_required = max(lookback, 26 + 9) + pivot_window
    if len(df) < min_required:
        logger.debug(
            "Insufficient data for divergence detection: %d bars (need %d)",
            len(df),
            min_required,
        )
        return dict(_EMPTY)

    # ------------------------------------------------------------------
    # Compute indicators
    # ------------------------------------------------------------------
    close = df["close"].astype(float)
    low = df["low"].astype(float)
    high = df["high"].astype(float)

    rsi = _compute_rsi(close)
    macd_hist = _compute_macd_histogram(close)

    # Lookback window boundaries (indices into the full DataFrame)
    end_idx = len(df)
    start_idx = end_idx - lookback

    # ------------------------------------------------------------------
    # Find pivot lows and highs in price, RSI, and MACD histogram
    # ------------------------------------------------------------------
    price_pivot_lows = _find_pivot_lows(low, pivot_window, start_idx, end_idx)
    price_pivot_highs = _find_pivot_highs(high, pivot_window, start_idx, end_idx)

    rsi_pivot_lows = _find_pivot_lows(rsi, pivot_window, start_idx, end_idx)
    rsi_pivot_highs = _find_pivot_highs(rsi, pivot_window, start_idx, end_idx)

    macd_pivot_lows = _find_pivot_lows(macd_hist, pivot_window, start_idx, end_idx)
    macd_pivot_highs = _find_pivot_highs(macd_hist, pivot_window, start_idx, end_idx)

    # ------------------------------------------------------------------
    # Check for divergences
    # ------------------------------------------------------------------
    divergences: List[Dict[str, Any]] = []
    rsi_bullish = False
    rsi_bearish = False
    macd_bullish = False
    macd_bearish = False

    # --- RSI bullish divergence: price lower low, RSI higher low ---
    if len(price_pivot_lows) >= 2 and len(rsi_pivot_lows) >= 2:
        p1, p2 = price_pivot_lows[-2], price_pivot_lows[-1]
        # Find the RSI pivot lows closest to each price pivot low
        r1 = _nearest_pivot(rsi_pivot_lows, p1)
        r2 = _nearest_pivot(rsi_pivot_lows, p2)
        if r1 is not None and r2 is not None and r1 != r2:
            if low.iloc[p2] < low.iloc[p1] and rsi.iloc[r2] > rsi.iloc[r1]:
                rsi_bullish = True
                divergences.append({
                    "type": "bullish",
                    "indicator": "RSI",
                    "bar_index": p2,
                    "price_pivot": round(float(low.iloc[p2]), 6),
                    "indicator_pivot": round(float(rsi.iloc[r2]), 4),
                })

    # --- RSI bearish divergence: price higher high, RSI lower high ---
    if len(price_pivot_highs) >= 2 and len(rsi_pivot_highs) >= 2:
        p1, p2 = price_pivot_highs[-2], price_pivot_highs[-1]
        r1 = _nearest_pivot(rsi_pivot_highs, p1)
        r2 = _nearest_pivot(rsi_pivot_highs, p2)
        if r1 is not None and r2 is not None and r1 != r2:
            if high.iloc[p2] > high.iloc[p1] and rsi.iloc[r2] < rsi.iloc[r1]:
                rsi_bearish = True
                divergences.append({
                    "type": "bearish",
                    "indicator": "RSI",
                    "bar_index": p2,
                    "price_pivot": round(float(high.iloc[p2]), 6),
                    "indicator_pivot": round(float(rsi.iloc[r2]), 4),
                })

    # --- MACD bullish divergence: price lower low, MACD hist higher low ---
    if len(price_pivot_lows) >= 2 and len(macd_pivot_lows) >= 2:
        p1, p2 = price_pivot_lows[-2], price_pivot_lows[-1]
        m1 = _nearest_pivot(macd_pivot_lows, p1)
        m2 = _nearest_pivot(macd_pivot_lows, p2)
        if m1 is not None and m2 is not None and m1 != m2:
            if low.iloc[p2] < low.iloc[p1] and macd_hist.iloc[m2] > macd_hist.iloc[m1]:
                macd_bullish = True
                divergences.append({
                    "type": "bullish",
                    "indicator": "MACD",
                    "bar_index": p2,
                    "price_pivot": round(float(low.iloc[p2]), 6),
                    "indicator_pivot": round(float(macd_hist.iloc[m2]), 6),
                })

    # --- MACD bearish divergence: price higher high, MACD hist lower high ---
    if len(price_pivot_highs) >= 2 and len(macd_pivot_highs) >= 2:
        p1, p2 = price_pivot_highs[-2], price_pivot_highs[-1]
        m1 = _nearest_pivot(macd_pivot_highs, p1)
        m2 = _nearest_pivot(macd_pivot_highs, p2)
        if m1 is not None and m2 is not None and m1 != m2:
            if high.iloc[p2] > high.iloc[p1] and macd_hist.iloc[m2] < macd_hist.iloc[m1]:
                macd_bearish = True
                divergences.append({
                    "type": "bearish",
                    "indicator": "MACD",
                    "bar_index": p2,
                    "price_pivot": round(float(high.iloc[p2]), 6),
                    "indicator_pivot": round(float(macd_hist.iloc[m2]), 6),
                })

    # ------------------------------------------------------------------
    # No divergences found
    # ------------------------------------------------------------------
    if not divergences:
        return dict(_EMPTY)

    # ------------------------------------------------------------------
    # Aggregate results
    # ------------------------------------------------------------------
    has_bullish = rsi_bullish or macd_bullish
    has_bearish = rsi_bearish or macd_bearish

    # Determine divergence type label
    divergence_type = _build_type_label(
        rsi_bullish, rsi_bearish, macd_bullish, macd_bearish
    )

    # Bars ago: distance from most recent divergence pivot to the last bar
    most_recent_bar = max(d["bar_index"] for d in divergences)
    divergence_bars_ago = (end_idx - 1) - most_recent_bar

    # Strength scoring (0-3)
    both_bullish = rsi_bullish and macd_bullish
    both_bearish = rsi_bearish and macd_bearish
    both_agree = both_bullish or both_bearish

    if both_agree and divergence_bars_ago <= 15:
        strength = 3
    elif both_agree:
        strength = 2
    else:
        strength = 1

    return {
        "has_bullish_div": has_bullish,
        "has_bearish_div": has_bearish,
        "divergence_type": divergence_type,
        "divergence_strength": strength,
        "divergence_bars_ago": divergence_bars_ago,
        "divergences": divergences,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _nearest_pivot(pivot_indices: List[int], target: int) -> Optional[int]:
    """Return the pivot index closest to *target*, or ``None`` if empty."""
    if not pivot_indices:
        return None
    return min(pivot_indices, key=lambda idx: abs(idx - target))


def _build_type_label(
    rsi_bull: bool, rsi_bear: bool, macd_bull: bool, macd_bear: bool
) -> str:
    """Build a human-readable divergence type label."""
    parts: List[str] = []

    # Bullish labels
    if rsi_bull and macd_bull:
        parts.append("RSI+MACD Bullish")
    elif rsi_bull:
        parts.append("RSI Bullish")
    elif macd_bull:
        parts.append("MACD Bullish")

    # Bearish labels
    if rsi_bear and macd_bear:
        parts.append("RSI+MACD Bearish")
    elif rsi_bear:
        parts.append("RSI Bearish")
    elif macd_bear:
        parts.append("MACD Bearish")

    return " / ".join(parts) if parts else "None"
