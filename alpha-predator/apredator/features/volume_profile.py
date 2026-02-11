"""
Volume Profile (VPOC) Calculator -- compute the Volume Point of Control,
Value Area High/Low, and a binned volume distribution from OHLCV data.

The Volume Profile distributes each bar's volume into a price bin based on
the bar's typical price ``(high + low + close) / 3``.  The bin with the
highest accumulated volume is the **VPOC** (Volume Point of Control).
The **Value Area** is the narrowest contiguous range of bins centred on VPOC
that captures a configurable percentage (default 70 %) of total volume.

Pure pandas/numpy -- no external dependencies.
"""

import logging
from typing import Any, Dict, List

import numpy as np
import pandas as pd

logger = logging.getLogger("apredator.features.volume_profile")

# ---------------------------------------------------------------------------
# Default empty result
# ---------------------------------------------------------------------------

_EMPTY: Dict[str, Any] = {
    "vpoc_price": None,
    "value_area_high": None,
    "value_area_low": None,
    "price_vs_value_area": "unknown",
    "vpoc_distance_pct": 0.0,
    "volume_profile": [],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_volume_profile(
    df: pd.DataFrame,
    lookback: int = 60,
    num_bins: int = 50,
    value_area_pct: float = 0.70,
) -> Dict[str, Any]:
    """Compute Volume Profile, VPOC, and Value Area from OHLCV data.

    Parameters
    ----------
    df : pd.DataFrame
        Daily OHLCV with columns ``date, open, high, low, close, volume``.
    lookback : int, optional
        Number of most-recent bars to include in the profile (default 60).
    num_bins : int, optional
        Number of horizontal price bins spanning the lookback range (default 50).
    value_area_pct : float, optional
        Fraction of total volume that the Value Area must capture (default 0.70).

    Returns
    -------
    dict
        ``vpoc_price``          -- price level of the Volume Point of Control
        ``value_area_high``     -- upper boundary of the Value Area
        ``value_area_low``      -- lower boundary of the Value Area
        ``price_vs_value_area`` -- ``"above"``, ``"below"``, or ``"inside"``
        ``vpoc_distance_pct``   -- distance from current price to VPOC (%)
        ``volume_profile``      -- list of ``{price_level, volume}`` dicts
    """
    if len(df) < 2:
        logger.debug("Insufficient data for volume profile: %d bars", len(df))
        return dict(_EMPTY)

    # ------------------------------------------------------------------
    # Slice to lookback window
    # ------------------------------------------------------------------
    window = df.tail(lookback).copy().reset_index(drop=True)

    high = window["high"].astype(float)
    low = window["low"].astype(float)
    close = window["close"].astype(float)
    volume = window["volume"].astype(float)

    # ------------------------------------------------------------------
    # Price range for bins
    # ------------------------------------------------------------------
    price_low = float(low.min())
    price_high = float(high.max())

    if price_high <= price_low or np.isnan(price_low) or np.isnan(price_high):
        logger.debug("Degenerate price range (low=%.4f, high=%.4f)", price_low, price_high)
        return dict(_EMPTY)

    # ------------------------------------------------------------------
    # Build price bins
    # ------------------------------------------------------------------
    bin_edges = np.linspace(price_low, price_high, num_bins + 1)
    bin_centres = (bin_edges[:-1] + bin_edges[1:]) / 2.0
    bin_volumes = np.zeros(num_bins, dtype=float)

    # ------------------------------------------------------------------
    # Assign each bar's volume to the nearest bin (by typical price)
    # ------------------------------------------------------------------
    typical_prices = (high + low + close) / 3.0
    for i in range(len(window)):
        tp = typical_prices.iloc[i]
        vol = volume.iloc[i]
        if np.isnan(tp) or np.isnan(vol):
            continue
        # Find nearest bin index
        bin_idx = int(np.clip(
            np.searchsorted(bin_edges, tp, side="right") - 1,
            0,
            num_bins - 1,
        ))
        bin_volumes[bin_idx] += vol

    total_volume = bin_volumes.sum()
    if total_volume == 0:
        logger.debug("Zero total volume in lookback window")
        return dict(_EMPTY)

    # ------------------------------------------------------------------
    # VPOC -- bin with the highest accumulated volume
    # ------------------------------------------------------------------
    vpoc_bin_idx = int(np.argmax(bin_volumes))
    vpoc_price = float(bin_centres[vpoc_bin_idx])

    # ------------------------------------------------------------------
    # Value Area -- expand from VPOC until value_area_pct is captured
    # ------------------------------------------------------------------
    va_low_idx = vpoc_bin_idx
    va_high_idx = vpoc_bin_idx
    accumulated = float(bin_volumes[vpoc_bin_idx])
    target_volume = total_volume * value_area_pct

    while accumulated < target_volume:
        # Peek one bin in each direction, choose the side with more volume
        can_expand_down = va_low_idx > 0
        can_expand_up = va_high_idx < num_bins - 1

        if not can_expand_down and not can_expand_up:
            break

        vol_below = bin_volumes[va_low_idx - 1] if can_expand_down else -1.0
        vol_above = bin_volumes[va_high_idx + 1] if can_expand_up else -1.0

        if vol_below >= vol_above:
            va_low_idx -= 1
            accumulated += bin_volumes[va_low_idx]
        else:
            va_high_idx += 1
            accumulated += bin_volumes[va_high_idx]

    # Value Area boundaries are the outer edges of the boundary bins
    value_area_low = float(bin_edges[va_low_idx])
    value_area_high = float(bin_edges[va_high_idx + 1])

    # ------------------------------------------------------------------
    # Current price relative to the Value Area
    # ------------------------------------------------------------------
    current_price = float(close.iloc[-1])

    if current_price > value_area_high:
        price_vs_value_area = "above"
    elif current_price < value_area_low:
        price_vs_value_area = "below"
    else:
        price_vs_value_area = "inside"

    # ------------------------------------------------------------------
    # VPOC distance
    # ------------------------------------------------------------------
    vpoc_distance_pct = (
        (current_price - vpoc_price) / vpoc_price * 100.0
        if vpoc_price != 0
        else 0.0
    )

    # ------------------------------------------------------------------
    # Build volume profile list (non-zero bins only for compactness)
    # ------------------------------------------------------------------
    volume_profile: List[Dict[str, Any]] = []
    for idx in range(num_bins):
        if bin_volumes[idx] > 0:
            volume_profile.append({
                "price_level": round(float(bin_centres[idx]), 6),
                "volume": round(float(bin_volumes[idx]), 2),
            })

    return {
        "vpoc_price": round(vpoc_price, 6),
        "value_area_high": round(value_area_high, 6),
        "value_area_low": round(value_area_low, 6),
        "price_vs_value_area": price_vs_value_area,
        "vpoc_distance_pct": round(vpoc_distance_pct, 4),
        "volume_profile": volume_profile,
    }
