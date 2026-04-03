"""Multi-timeframe confluence analysis."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import pandas as pd
import yfinance as yf

from .detector import StockSignalDetector

logger = logging.getLogger("qaht.signals.multiframe")

_CACHE_TTL = timedelta(minutes=15)


class MultiFrameAnalyzer:
    """Compare weekly, daily, and 4-hour signal alignment."""

    _CACHE: Dict[str, tuple[datetime, Dict[str, Any]]] = {}

    def __init__(self, detector: Optional[StockSignalDetector] = None) -> None:
        self.detector = detector or StockSignalDetector()

    def analyze(self, ticker: str) -> Dict[str, Any]:
        """Return confluence scoring and timeframe breakdown."""
        ticker = ticker.upper()
        cached = self._CACHE.get(ticker)
        now = datetime.utcnow()
        if cached and (now - cached[0]) < _CACHE_TTL:
            return cached[1]

        info = self._safe_info(ticker)
        weekly_df = self.detector._fetch_history(ticker, timeframe="1wk")
        daily_df = self.detector._fetch_history(ticker, timeframe="1d")
        intraday_df = self.detector._fetch_history(ticker, timeframe="4h")

        weekly_result = self.detector.scan_from_history(
            ticker=ticker,
            df=weekly_df,
            info=info,
            timeframe="1wk",
            apply_multiframe=False,
        )
        daily_result = self.detector.scan_from_history(
            ticker=ticker,
            df=daily_df,
            info=info,
            timeframe="1d",
            apply_multiframe=False,
        )
        intraday_result = self.detector.scan_from_history(
            ticker=ticker,
            df=intraday_df,
            info=info,
            timeframe="4h",
            apply_multiframe=False,
        )

        timeframe_breakdown = {
            "weekly": self._build_timeframe_view(weekly_df, weekly_result),
            "daily": self._build_timeframe_view(daily_df, daily_result),
            "4h": self._build_timeframe_view(intraday_df, intraday_result),
        }
        category_matrix = {
            category: {
                timeframe: data["categories"].get(category, 0)
                for timeframe, data in timeframe_breakdown.items()
            }
            for category in ("ma", "rsi", "macd", "volume", "momentum")
        }
        alignment_score = self._alignment_score(category_matrix)
        multiplier = self._confluence_multiplier(alignment_score)

        payload = {
            "ticker": ticker,
            "timeframes": timeframe_breakdown,
            "category_matrix": category_matrix,
            "alignment_score": alignment_score,
            "multiplier": multiplier,
            "confluence_multiplier": multiplier,
            "flag": "MTF_ALIGNED" if alignment_score >= 6 else None,
        }
        self._CACHE[ticker] = (now, payload)
        return payload

    def get_timeframe_breakdown(self, ticker: str) -> Dict[str, Any]:
        """Convenience wrapper returning the full timeframe payload."""
        return self.analyze(ticker)

    @staticmethod
    def _build_timeframe_view(df: pd.DataFrame, scan_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        categories = MultiFrameAnalyzer._category_states(df)
        return {
            "score": scan_result.get("score") if scan_result else None,
            "stage": scan_result.get("stage") if scan_result else None,
            "flags": scan_result.get("flags", []) if scan_result else [],
            "categories": categories,
        }

    @staticmethod
    def _category_states(df: pd.DataFrame) -> Dict[str, int]:
        if df is None or df.empty or len(df) < 20:
            return {"ma": 0, "rsi": 0, "macd": 0, "volume": 0, "momentum": 0}

        close = df["Close"].astype(float)
        volume = df["Volume"].astype(float)
        ema20 = close.ewm(span=20, adjust=False).mean()
        ema50 = close.ewm(span=50, adjust=False).mean()
        delta = close.diff()
        gains = delta.clip(lower=0.0)
        losses = (-delta).clip(lower=0.0)
        avg_gain = gains.rolling(14, min_periods=14).mean()
        avg_loss = losses.rolling(14, min_periods=14).mean().replace(0.0, pd.NA)
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        macd_signal = macd.ewm(span=9, adjust=False).mean()
        volume_ma20 = volume.rolling(20, min_periods=5).mean()
        momentum_ref = close.shift(5)

        latest_close = float(close.iloc[-1])
        ma_state = 1 if latest_close > float(ema20.iloc[-1]) > float(ema50.iloc[-1]) else -1 if latest_close < float(ema20.iloc[-1]) and latest_close < float(ema50.iloc[-1]) else 0
        rsi_value = float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else 50.0
        rsi_state = 1 if rsi_value >= 55 else -1 if rsi_value <= 45 else 0
        macd_state = 1 if float(macd.iloc[-1]) > float(macd_signal.iloc[-1]) else -1 if float(macd.iloc[-1]) < float(macd_signal.iloc[-1]) else 0
        volume_ratio = float(volume.iloc[-1] / volume_ma20.iloc[-1]) if pd.notna(volume_ma20.iloc[-1]) and float(volume_ma20.iloc[-1]) > 0 else 1.0
        volume_state = 1 if volume_ratio >= 1.2 else -1 if volume_ratio <= 0.8 else 0
        momentum_state = 1 if pd.notna(momentum_ref.iloc[-1]) and latest_close > float(momentum_ref.iloc[-1]) else -1 if pd.notna(momentum_ref.iloc[-1]) and latest_close < float(momentum_ref.iloc[-1]) else 0

        return {
            "ma": ma_state,
            "rsi": rsi_state,
            "macd": macd_state,
            "volume": volume_state,
            "momentum": momentum_state,
        }

    @staticmethod
    def _alignment_score(category_matrix: Dict[str, Dict[str, int]]) -> int:
        score = 0
        for states in category_matrix.values():
            values = list(states.values())
            bullish = sum(1 for value in values if value > 0)
            bearish = sum(1 for value in values if value < 0)
            if bullish == 3:
                score += 3
            elif bearish == 3:
                score -= 3
            elif bullish == 2 and bearish == 0:
                score += 1
            elif bearish == 2 and bullish == 0:
                score -= 1
            elif bullish > 0 and bearish > 0:
                score -= 1
        return score

    @staticmethod
    def _confluence_multiplier(alignment_score: int) -> float:
        if alignment_score >= 10:
            return 2.0
        if alignment_score >= 6:
            return 1.5
        if alignment_score >= 3:
            return 1.2
        if alignment_score < 0:
            return 0.7
        return 1.0

    @staticmethod
    def _safe_info(ticker: str) -> Dict[str, Any]:
        try:
            return yf.Ticker(ticker).info or {}
        except Exception:
            logger.warning("Failed to load info for %s during multiframe analysis", ticker, exc_info=True)
            return {}
