"""Shared technical indicator helpers with per-DataFrame caching."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MACDResult:
    """MACD line, signal line, and histogram."""

    line: pd.Series
    signal: pd.Series
    hist: pd.Series


@dataclass(frozen=True)
class BollingerBands:
    """Bollinger band components."""

    mid: pd.Series
    std: pd.Series
    upper: pd.Series
    lower: pd.Series
    width: pd.Series


def ema(series: pd.Series, period: int, adjust: bool = True) -> pd.Series:
    """Exponential moving average."""
    return series.ewm(span=period, adjust=adjust).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index using simple rolling averages."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    values = 100.0 - (100.0 / (1.0 + rs))
    values = values.where(avg_loss != 0.0, 100.0)
    values = values.where(~((avg_gain == 0.0) & (avg_loss == 0.0)), 50.0)
    return values


def macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
    adjust: bool = True,
) -> MACDResult:
    """MACD indicator set."""
    fast_ema = ema(series, fast, adjust=adjust)
    slow_ema = ema(series, slow, adjust=adjust)
    line = fast_ema - slow_ema
    signal = line.ewm(span=signal_period, adjust=adjust).mean()
    hist = line - signal
    return MACDResult(line=line, signal=signal, hist=hist)


def atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Average True Range."""
    high_low = high - low
    high_close = (high - close.shift()).abs()
    low_close = (low - close.shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.rolling(window=period, min_periods=period).mean()


def bollinger_bands(
    series: pd.Series,
    window: int = 20,
    num_std: float = 2.0,
) -> BollingerBands:
    """Bollinger band components."""
    mid = series.rolling(window=window, min_periods=window).mean()
    std = series.rolling(window=window, min_periods=window).std()
    upper = mid + (num_std * std)
    lower = mid - (num_std * std)
    width = (upper - lower) / mid.replace(0.0, np.nan)
    return BollingerBands(mid=mid, std=std, upper=upper, lower=lower, width=width)


class IndicatorCache:
    """Lazy indicator cache bound to a single OHLCV DataFrame."""

    def __init__(
        self,
        df: pd.DataFrame,
        close_col: str = "Close",
        high_col: str = "High",
        low_col: str = "Low",
    ) -> None:
        self.df = df
        self.close_col = close_col
        self.high_col = high_col
        self.low_col = low_col
        self._cache: Dict[Tuple[Any, ...], Any] = {}

    @property
    def close(self) -> pd.Series:
        return self.df[self.close_col]

    @property
    def high(self) -> pd.Series:
        return self.df[self.high_col]

    @property
    def low(self) -> pd.Series:
        return self.df[self.low_col]

    def ema(self, period: int, adjust: bool = True) -> pd.Series:
        key = ("ema", period, adjust)
        if key not in self._cache:
            self._cache[key] = ema(self.close, period, adjust=adjust)
        return self._cache[key]

    def rsi(self, period: int = 14) -> pd.Series:
        key = ("rsi", period)
        if key not in self._cache:
            self._cache[key] = rsi(self.close, period=period)
        return self._cache[key]

    def macd(
        self,
        fast: int = 12,
        slow: int = 26,
        signal_period: int = 9,
        adjust: bool = True,
    ) -> MACDResult:
        key = ("macd", fast, slow, signal_period, adjust)
        if key not in self._cache:
            self._cache[key] = macd(
                self.close,
                fast=fast,
                slow=slow,
                signal_period=signal_period,
                adjust=adjust,
            )
        return self._cache[key]

    def atr(self, period: int = 14) -> pd.Series:
        key = ("atr", period)
        if key not in self._cache:
            self._cache[key] = atr(self.high, self.low, self.close, period=period)
        return self._cache[key]

    def bollinger_bands(
        self,
        window: int = 20,
        num_std: float = 2.0,
    ) -> BollingerBands:
        key = ("bollinger", window, num_std)
        if key not in self._cache:
            self._cache[key] = bollinger_bands(
                self.close,
                window=window,
                num_std=num_std,
            )
        return self._cache[key]
