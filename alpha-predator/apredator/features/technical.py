"""
Technical feature computations -- pure pandas/numpy, no talib dependency.
Ported from QAHT features/tech.py.
"""
import logging
from typing import Dict

import numpy as np
import pandas as pd

logger = logging.getLogger("apredator.features.technical")


# ---------------------------------------------------------------------------
# Bollinger Bands
# ---------------------------------------------------------------------------

def compute_bollinger(df: pd.DataFrame, window: int = 20) -> Dict[str, float]:
    """Compute Bollinger Band width (%) and position within the bands.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain a ``close`` column with at least *window* rows.

    Returns
    -------
    dict
        ``bb_width_pct`` -- (upper - lower) / middle * 100
        ``bb_position`` -- (close - lower) / (upper - lower), clipped to [0, 1]
    """
    close = df["close"]
    middle = close.rolling(window).mean()
    std = close.rolling(window).std()
    upper = middle + 2 * std
    lower = middle - 2 * std

    last_upper = upper.iloc[-1]
    last_lower = lower.iloc[-1]
    last_middle = middle.iloc[-1]
    last_close = close.iloc[-1]

    band_width = last_upper - last_lower
    bb_width_pct = (band_width / last_middle * 100) if last_middle != 0 else 0.0
    bb_position = (
        (last_close - last_lower) / band_width if band_width != 0 else 0.5
    )
    bb_position = float(np.clip(bb_position, 0.0, 1.0))

    return {"bb_width_pct": round(bb_width_pct, 4), "bb_position": round(bb_position, 4)}


# ---------------------------------------------------------------------------
# Moving-Average Compression
# ---------------------------------------------------------------------------

def compute_ma_compression(
    df: pd.DataFrame, windows: list = None
) -> Dict[str, float]:
    """Compute MA spread (%) and alignment score.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain a ``close`` column.
    windows : list[int]
        Moving-average windows to use (default ``[20, 50, 200]``).

    Returns
    -------
    dict
        ``ma_spread_pct`` -- (max_ma - min_ma) / close * 100
        ``ma_alignment_score`` -- fraction of shorter MAs that are above all
            longer MAs (1.0 = perfectly bullish alignment).
    """
    if windows is None:
        windows = [20, 50, 200]
    close = df["close"]
    last_close = close.iloc[-1]

    mas = {}
    for w in windows:
        ma = close.rolling(w).mean()
        if ma.iloc[-1] is not None and not np.isnan(ma.iloc[-1]):
            mas[w] = ma.iloc[-1]

    if len(mas) < 2:
        return {"ma_spread_pct": 0.0, "ma_alignment_score": 0.5}

    values = list(mas.values())
    ma_spread_pct = (max(values) - min(values)) / last_close * 100 if last_close != 0 else 0.0

    # Alignment: count how many (shorter, longer) pairs are bullishly aligned
    sorted_windows = sorted(mas.keys())
    aligned = 0
    total_pairs = 0
    for i in range(len(sorted_windows)):
        for j in range(i + 1, len(sorted_windows)):
            total_pairs += 1
            if mas[sorted_windows[i]] > mas[sorted_windows[j]]:
                aligned += 1
    ma_alignment_score = aligned / total_pairs if total_pairs > 0 else 0.5

    return {
        "ma_spread_pct": round(ma_spread_pct, 4),
        "ma_alignment_score": round(ma_alignment_score, 4),
    }


# ---------------------------------------------------------------------------
# ATR & Volatility
# ---------------------------------------------------------------------------

def compute_atr(df: pd.DataFrame, window: int = 14) -> Dict[str, float]:
    """Compute Average True Range (%) and annualised 20-day realised volatility.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain ``high``, ``low``, ``close`` columns.

    Returns
    -------
    dict
        ``atr_pct`` -- ATR / close * 100
        ``volatility_20d`` -- annualised standard deviation of daily returns
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)

    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)

    atr = tr.rolling(window).mean().iloc[-1]
    last_close = close.iloc[-1]
    atr_pct = (atr / last_close * 100) if last_close != 0 else 0.0

    # 20-day realised volatility (annualised)
    returns = close.pct_change().dropna()
    vol_20d = returns.iloc[-20:].std() * np.sqrt(252) if len(returns) >= 20 else 0.0

    return {
        "atr_pct": round(float(atr_pct), 4),
        "volatility_20d": round(float(vol_20d), 4),
    }


# ---------------------------------------------------------------------------
# Volume
# ---------------------------------------------------------------------------

def compute_volume(df: pd.DataFrame) -> Dict[str, float]:
    """Compute volume ratio and OBV trend.

    Returns
    -------
    dict
        ``volume_ratio_20d`` -- today's volume / 20-day average volume
        ``obv_trend_5d`` -- 5-day linear-regression slope of OBV
    """
    volume = df["volume"]
    close = df["close"]

    # Volume ratio
    avg_vol = volume.rolling(20).mean().iloc[-1]
    current_vol = volume.iloc[-1]
    volume_ratio = (current_vol / avg_vol) if avg_vol != 0 else 1.0

    # On-Balance Volume
    sign = np.sign(close.diff())
    obv = (sign * volume).cumsum()

    # 5-day OBV slope via simple linear regression
    obv_tail = obv.iloc[-5:]
    if len(obv_tail) >= 5:
        x = np.arange(len(obv_tail), dtype=float)
        y = obv_tail.values.astype(float)
        # Normalise OBV values to avoid huge slope numbers
        y_mean = np.mean(y)
        if y_mean != 0:
            y_norm = y / abs(y_mean)
        else:
            y_norm = y
        slope = np.polyfit(x, y_norm, 1)[0]
    else:
        slope = 0.0

    return {
        "volume_ratio_20d": round(float(volume_ratio), 4),
        "obv_trend_5d": round(float(slope), 6),
    }


# ---------------------------------------------------------------------------
# RSI & MACD
# ---------------------------------------------------------------------------

def compute_momentum(df: pd.DataFrame) -> Dict[str, float]:
    """Compute RSI-14 and MACD (12/26/9).

    Returns
    -------
    dict
        ``rsi_14`` -- Relative Strength Index (0-100)
        ``macd`` -- MACD line value
        ``macd_signal`` -- MACD signal line value
    """
    close = df["close"]

    # --- RSI ---
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    rsi_value = rsi.iloc[-1]
    if np.isnan(rsi_value):
        rsi_value = 50.0

    # --- MACD ---
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()

    return {
        "rsi_14": round(float(rsi_value), 2),
        "macd": round(float(macd_line.iloc[-1]), 6),
        "macd_signal": round(float(signal_line.iloc[-1]), 6),
    }


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

def compute_all_technical(df: pd.DataFrame) -> Dict[str, float]:
    """Compute **all** technical features and return a merged dict.

    Each sub-computation is wrapped in a try/except so a single failure does
    not prevent the remaining features from being returned.
    """
    result: Dict[str, float] = {}

    for name, fn in [
        ("bollinger", compute_bollinger),
        ("ma_compression", compute_ma_compression),
        ("atr", compute_atr),
        ("volume", compute_volume),
        ("momentum", compute_momentum),
    ]:
        try:
            result.update(fn(df))
        except Exception:
            logger.exception("Failed to compute %s features", name)

    return result
