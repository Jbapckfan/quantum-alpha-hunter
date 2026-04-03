"""
Resistance-level analysis with 6-method confluence scoring.

Ported from the RZLV Pattern Scanner ``ResistanceAnalyzer``.  Identifies
overhead resistance using six independent methods, clusters nearby levels,
counts confirmations, and returns the top levels ranked by strength.

Methods
-------
1. **Swing highs** -- local maxima via ``scipy.signal.argrelextrema``
   (tight order=3 for recent, loose order=7 for major)
2. **Volume clusters** -- volume-profile histogram (50 bins, >80th pctile)
3. **Round numbers** -- psychological price levels ($5, $10, $50, ...)
4. **Gap levels** -- unfilled overnight gaps (>3% threshold)
5. **Moving averages** -- SMA 20, 50, 100, 200
6. **Fibonacci** -- retracements (0.236, 0.382, 0.5, 0.618, 0.786) and
   extensions (1.0, 1.272, 1.618)

Confluence scoring clusters all levels within 3% tolerance, counts how many
methods confirmed each cluster, and returns the top 10 by strength.

Usage::

    analyzer = ResistanceAnalyzer("AAPL")
    levels   = analyzer.find_all_levels()
    for lvl in levels:
        print(f"${lvl['level']:.2f}  strength={lvl['strength']}  +{lvl['pct_above']:.1f}%")
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.signal import argrelextrema

logger = logging.getLogger("qaht.signals.resistance")


class ResistanceAnalyzer:
    """
    Identifies resistance levels using 6 independent methods and combines
    them with confluence scoring.

    Parameters
    ----------
    ticker : str
        The stock or crypto ticker symbol (e.g. ``"AAPL"`` or ``"BTC-USD"``).
    period : str
        yfinance history period (default ``"1y"``).
    df : pd.DataFrame, optional
        If provided, skip the yfinance fetch and use this DataFrame directly.
        Must contain OHLCV columns (``Open, High, Low, Close, Volume``).
    """

    def __init__(
        self,
        ticker: str,
        period: str = "1y",
        df: Optional[pd.DataFrame] = None,
    ) -> None:
        self.ticker = ticker

        if df is not None:
            self.df = df.copy()
        else:
            stock = yf.Ticker(ticker)
            self.df = stock.history(period=period, interval="1d")

        if self.df.empty:
            raise ValueError(f"No data found for {ticker}")

        self.current_price: float = float(self.df.iloc[-1]["Close"])
        self.levels: Dict[str, Any] = {}
        self.key_levels: List[Dict[str, Any]] = []

        # Set after find_fibonacci_levels
        self.swing_low: float = 0.0
        self.swing_high: float = 0.0

    # ------------------------------------------------------------------
    # Method 1: Swing highs (local maxima)
    # ------------------------------------------------------------------

    def find_swing_highs(
        self, order_sensitive: int = 3, order_major: int = 7
    ) -> List[float]:
        """
        Find swing-high levels using ``argrelextrema``.

        *order_sensitive* (default 3) catches recent minor swing highs;
        *order_major* (default 7) catches broader, more significant ones.
        """
        high = self.df["High"].values
        current = self.current_price

        swing_highs_tight = argrelextrema(high, np.greater, order=order_sensitive)[0]
        swing_highs_loose = argrelextrema(high, np.greater, order=order_major)[0]

        swing_levels: List[float] = []

        # Major swing highs above 90% of current price
        for idx in swing_highs_loose:
            level = float(high[idx])
            if level > current * 0.9:
                swing_levels.append(round(level, 2))

        # Recent (last 60 bars) tight swing highs above 95% of current price
        recent_swings = [i for i in swing_highs_tight if i > len(self.df) - 60]
        for idx in recent_swings:
            level = float(high[idx])
            if level > current * 0.95:
                swing_levels.append(round(level, 2))

        self.levels["swing_highs"] = sorted(set(swing_levels))
        return self.levels["swing_highs"]

    # ------------------------------------------------------------------
    # Method 2: Volume clusters (volume profile)
    # ------------------------------------------------------------------

    def find_volume_clusters(
        self, num_bins: int = 50, threshold_pct: int = 80
    ) -> List[float]:
        """
        Build a volume profile and return price levels where traded volume
        exceeds the *threshold_pct* percentile.
        """
        low = self.df["Low"].values
        high = self.df["High"].values
        volume = self.df["Volume"].values
        current = self.current_price

        price_min, price_max = float(low.min()), float(high.max())
        bins = np.linspace(price_min, price_max, num_bins)

        volume_profile = np.zeros(num_bins - 1)

        for i in range(len(self.df)):
            candle_low = float(low[i])
            candle_high = float(high[i])
            candle_vol = float(volume[i])
            candle_range = candle_high - candle_low if candle_high > candle_low else 0.01

            for j in range(len(bins) - 1):
                bin_low, bin_high = float(bins[j]), float(bins[j + 1])
                if candle_low <= bin_high and candle_high >= bin_low:
                    overlap = min(candle_high, bin_high) - max(candle_low, bin_low)
                    volume_profile[j] += candle_vol * (overlap / candle_range)

        threshold = float(np.percentile(volume_profile, threshold_pct))
        high_vol_bins = np.where(volume_profile > threshold)[0]

        volume_levels: List[float] = []
        for bin_idx in high_vol_bins:
            level = float((bins[bin_idx] + bins[bin_idx + 1]) / 2)
            if level > current:
                volume_levels.append(round(level, 2))

        self.levels["volume_clusters"] = sorted(set(volume_levels))
        return self.levels["volume_clusters"]

    # ------------------------------------------------------------------
    # Method 3: Round numbers (psychological)
    # ------------------------------------------------------------------

    def find_round_numbers(self) -> List[float]:
        """
        Return psychological round-number levels above current price.
        Increment size adapts to the price magnitude.
        """
        current = self.current_price
        round_levels: List[float] = []

        if current < 5:
            increments = np.arange(0.5, 15, 0.5)
        elif current < 20:
            increments = list(range(1, 50, 1))
        else:
            increments = list(range(5, 200, 5))

        for level in increments:
            fl = float(level)
            if current < fl < current * 2.5:
                round_levels.append(fl)

        self.levels["round_numbers"] = round_levels[:10]
        return self.levels["round_numbers"]

    # ------------------------------------------------------------------
    # Method 4: Gap levels
    # ------------------------------------------------------------------

    def find_gap_levels(self, gap_threshold: float = 0.03) -> List[float]:
        """
        Find unfilled gap levels (overnight gaps > *gap_threshold*).
        Both gap-down (prior close above current) and gap-up (open above
        prior close) are captured when they remain above the current price.
        """
        close = self.df["Close"].values
        current = self.current_price
        gap_levels: List[float] = []

        for i in range(1, len(self.df)):
            prev_close = float(close[i - 1])
            curr_open = float(self.df.iloc[i]["Open"])

            # Gap down: prior close above current price
            if curr_open < prev_close * (1 - gap_threshold):
                if prev_close > current:
                    gap_levels.append(round(prev_close, 2))

            # Gap up: open above prior close
            if curr_open > prev_close * (1 + gap_threshold):
                if curr_open > current:
                    gap_levels.append(round(curr_open, 2))

        self.levels["gap_levels"] = sorted(set(gap_levels))
        return self.levels["gap_levels"]

    # ------------------------------------------------------------------
    # Method 5: Moving averages
    # ------------------------------------------------------------------

    def find_moving_averages(self) -> List[Tuple[str, float]]:
        """
        Return SMA levels (20, 50, 100, 200) that sit above the current price.
        Each entry is ``(name, level)`` -- e.g. ``("MA200", 175.32)``.
        """
        current = self.current_price

        self.df["MA20"] = self.df["Close"].rolling(20).mean()
        self.df["MA50"] = self.df["Close"].rolling(50).mean()
        self.df["MA100"] = self.df["Close"].rolling(100).mean()
        self.df["MA200"] = self.df["Close"].rolling(200).mean()

        ma_levels: List[Tuple[str, float]] = []
        for ma_name in ("MA20", "MA50", "MA100", "MA200"):
            ma_val = self.df[ma_name].iloc[-1]
            if pd.notna(ma_val) and float(ma_val) > current:
                ma_levels.append((ma_name, round(float(ma_val), 2)))

        self.levels["moving_averages"] = ma_levels
        return self.levels["moving_averages"]

    # ------------------------------------------------------------------
    # Method 6: Fibonacci retracements & extensions
    # ------------------------------------------------------------------

    def find_fibonacci_levels(self) -> List[Tuple[str, float]]:
        """
        Compute Fibonacci retracement and extension levels relative to the
        52-week swing low/high.

        Retracement ratios: 0.236, 0.382, 0.5, 0.618, 0.786
        Extension ratios:   1.0, 1.272, 1.618
        """
        current = self.current_price
        swing_low = float(self.df["Low"].min())
        swing_high = float(self.df["High"].max())

        fib_levels: List[Tuple[str, float]] = []

        # Retracements (measured from high)
        fib_ratios = [0.236, 0.382, 0.5, 0.618, 0.786]
        for ratio in fib_ratios:
            fib_level = swing_high - (swing_high - swing_low) * ratio
            if fib_level > current:
                fib_levels.append((f"Fib {ratio * 100:.1f}%", round(fib_level, 2)))

        # Extensions (measured from low)
        ext_ratios = [1.0, 1.272, 1.618]
        for ratio in ext_ratios:
            ext_level = swing_low + (swing_high - swing_low) * ratio
            if ext_level > current:
                fib_levels.append((f"Ext {ratio * 100:.0f}%", round(ext_level, 2)))

        self.levels["fibonacci"] = fib_levels
        self.swing_low = round(swing_low, 2)
        self.swing_high = round(swing_high, 2)

        return self.levels["fibonacci"]

    # ------------------------------------------------------------------
    # Confluence: combine all methods
    # ------------------------------------------------------------------

    def find_all_levels(self) -> List[Dict[str, Any]]:
        """
        Run all six methods, cluster nearby levels (3% tolerance), count
        how many methods confirmed each cluster, and return the top 10
        levels ranked by confirmation strength.

        Returns a list of dicts::

            [
                {"level": 12.50, "strength": 4, "pct_above": 8.3},
                ...
            ]
        """
        self.find_swing_highs()
        self.find_volume_clusters()
        self.find_round_numbers()
        self.find_gap_levels()
        self.find_moving_averages()
        self.find_fibonacci_levels()

        # Flatten all levels into a single list of floats
        all_levels: List[float] = []
        all_levels.extend(self.levels.get("swing_highs", []))
        all_levels.extend(self.levels.get("volume_clusters", []))
        all_levels.extend(self.levels.get("round_numbers", []))
        all_levels.extend(self.levels.get("gap_levels", []))
        all_levels.extend(
            [lvl for _, lvl in self.levels.get("moving_averages", [])]
        )
        all_levels.extend(
            [lvl for _, lvl in self.levels.get("fibonacci", [])]
        )

        # Cluster and count confirmations
        clustered = self._cluster_levels(all_levels, tolerance_pct=0.03)
        # Sort by strength descending, then by level ascending
        clustered = sorted(clustered, key=lambda x: (-x[1], x[0]))

        self.key_levels = []
        for level, count in clustered[:10]:
            if level > self.current_price:
                pct = (level - self.current_price) / self.current_price * 100
                self.key_levels.append(
                    {
                        "level": round(level, 2),
                        "strength": count,
                        "pct_above": round(pct, 1),
                    }
                )

        logger.info(
            "%s: found %d resistance levels (current $%.2f)",
            self.ticker,
            len(self.key_levels),
            self.current_price,
        )
        return self.key_levels

    # ------------------------------------------------------------------
    # Internal clustering
    # ------------------------------------------------------------------

    @staticmethod
    def _cluster_levels(
        levels: List[float], tolerance_pct: float = 0.03
    ) -> List[Tuple[float, int]]:
        """
        Cluster nearby price levels and return ``(mean_level, count)`` pairs.

        Two levels are in the same cluster if the gap between them is less
        than *tolerance_pct* of the first level in the cluster.
        """
        if not levels:
            return []

        levels = sorted(levels)
        clusters: List[List[float]] = []
        current_cluster = [levels[0]]

        for level in levels[1:]:
            if (level - current_cluster[0]) / current_cluster[0] < tolerance_pct:
                current_cluster.append(level)
            else:
                clusters.append(current_cluster)
                current_cluster = [level]
        clusters.append(current_cluster)

        return [(float(np.mean(c)), len(c)) for c in clusters]

    # ------------------------------------------------------------------
    # Convenience: get raw level dict
    # ------------------------------------------------------------------

    def get_raw_levels(self) -> Dict[str, Any]:
        """Return the raw (un-clustered) levels dict after ``find_all_levels``."""
        return self.levels.copy()
