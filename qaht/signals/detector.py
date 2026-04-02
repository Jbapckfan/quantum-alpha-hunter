"""
Stock signal detector -- ported from RZLV Pattern Scanner.

Detects 45+ bullish/bearish signals from OHLCV + analyst data and produces
a weighted conviction score.  Designed to work standalone:

    detector = StockSignalDetector()
    result   = detector.scan("AAPL")
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.signal import argrelextrema

from .weights import (
    STOCK_WEIGHTS,
    STOCK_CONFLUENCE_CATEGORIES,
    compute_stock_confluence,
    load_weights,
    max_positive_score,
    save_weights,
)

logger = logging.getLogger("qaht.signals.detector")

WEIGHTS_FILE = Path(__file__).resolve().parent / "stock_weights.json"


# ---------------------------------------------------------------------------
# Internal helper -- detects raw signals on a prepared DataFrame
# ---------------------------------------------------------------------------

class _SignalEngine:
    """
    Low-level signal detection on an already-fetched DataFrame.

    Consumers should use :class:`StockSignalDetector` which handles data
    fetching, scoring, and result packaging.
    """

    def __init__(self, df: pd.DataFrame, info: Optional[Dict[str, Any]] = None) -> None:
        self.df = df.copy()
        self.info = info or {}
        self.current: float = float(df.iloc[-1]["Close"])
        self.signals: Dict[str, bool] = {}
        self.signal_details: Dict[str, Any] = {}

        self._calculate_indicators()

    # ----- indicators -------------------------------------------------------

    def _calculate_indicators(self) -> None:
        """Pre-calculate all technical indicators on *self.df*."""
        df = self.df

        # EMAs
        df["EMA5"] = df["Close"].ewm(span=5).mean()
        df["EMA10"] = df["Close"].ewm(span=10).mean()
        df["EMA20"] = df["Close"].ewm(span=20).mean()
        df["EMA50"] = df["Close"].ewm(span=50).mean()

        # SMAs
        df["SMA20"] = df["Close"].rolling(20).mean()
        df["SMA50"] = df["Close"].rolling(50).mean()
        df["SMA200"] = df["Close"].rolling(200).mean()

        # RSI (14-period Wilder)
        delta = df["Close"].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df["RSI"] = 100 - (100 / (1 + rs))

        # MACD (12/26/9)
        ema12 = df["Close"].ewm(span=12).mean()
        ema26 = df["Close"].ewm(span=26).mean()
        df["MACD"] = ema12 - ema26
        df["MACD_Signal"] = df["MACD"].ewm(span=9).mean()
        df["MACD_Hist"] = df["MACD"] - df["MACD_Signal"]

        # Bollinger Bands (20, 2)
        df["BB_Mid"] = df["Close"].rolling(20).mean()
        df["BB_Std"] = df["Close"].rolling(20).std()
        df["BB_Upper"] = df["BB_Mid"] + 2 * df["BB_Std"]
        df["BB_Lower"] = df["BB_Mid"] - 2 * df["BB_Std"]
        df["BB_Width"] = (df["BB_Upper"] - df["BB_Lower"]) / df["BB_Mid"]

        # ATR (14)
        high_low = df["High"] - df["Low"]
        high_close = (df["High"] - df["Close"].shift()).abs()
        low_close = (df["Low"] - df["Close"].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["ATR"] = tr.rolling(14).mean()

        # Volume averages
        df["Vol_SMA20"] = df["Volume"].rolling(20).mean()
        df["Vol_SMA50"] = df["Volume"].rolling(50).mean()

        # Daily returns (%)
        df["Return"] = df["Close"].pct_change() * 100

        # 52-week extremes
        self.high_52w: float = float(df["High"].max())
        self.low_52w: float = float(df["Low"].min())

    # ----- orchestrator -----------------------------------------------------

    def detect_all_signals(self) -> Tuple[Dict[str, bool], Dict[str, Any]]:
        """Run every signal detector and return *(signals, details)*."""
        self._detect_washout_signals()
        self._detect_base_signals()
        self._detect_volume_signals()
        self._detect_momentum_signals()
        self._detect_ma_signals()
        self._detect_rsi_signals()
        self._detect_macd_signals()
        self._detect_volatility_signals()
        self._detect_support_signals()
        self._detect_relative_strength()
        self._detect_stage()
        self._detect_analyst_signals()
        self._detect_exceptional_signals()
        self._detect_quality_filters()
        return self.signals, self.signal_details

    # ----- washout ----------------------------------------------------------

    def _detect_washout_signals(self) -> None:
        """Detect drawdown/washout signals."""
        drawdown = (self.low_52w - self.high_52w) / self.high_52w * 100
        self.signal_details["drawdown"] = round(drawdown, 1)

        if drawdown <= -70:
            self.signals["deep_washout_70"] = True
        elif drawdown <= -60:
            self.signals["major_washout_60"] = True
        elif drawdown <= -50:
            self.signals["washout_50"] = True
        elif drawdown <= -40:
            self.signals["washout_40"] = True

    # ----- base formation ---------------------------------------------------

    def _detect_base_signals(self) -> None:
        """Detect base formation signals (consolidation near lows)."""
        base_threshold = self.low_52w * 1.30
        base_days = self.df[self.df["Close"] < base_threshold]

        if len(base_days) >= 10:
            base_low = float(base_days["Low"].min())
            base_high = float(base_days["High"].max())
            base_range = (base_high - base_low) / base_low * 100
            self.signal_details["base_tightness"] = round(base_range, 1)

            if base_range < 20:
                self.signals["tight_base_20"] = True
            elif base_range < 30:
                self.signals["tight_base_30"] = True
            elif base_range < 40:
                self.signals["base_40"] = True
            elif base_range < 50:
                self.signals["base_50"] = True

    # ----- volume -----------------------------------------------------------

    def _detect_volume_signals(self) -> None:
        """Detect volume-based signals (dryup, surge, accumulation)."""
        df = self.df

        # Volume dry-up during base period
        base_threshold = self.low_52w * 1.30
        base_days = df[df["Close"] < base_threshold]

        if len(base_days) >= 10:
            base_vol = float(base_days["Volume"].mean())
            vol_50d_avg = float(df["Vol_SMA50"].iloc[-1])

            if vol_50d_avg > 0 and base_vol < vol_50d_avg * 0.5:
                self.signals["volume_dryup"] = True
                self.signal_details["volume_dryup_ratio"] = round(base_vol / vol_50d_avg, 2)

        # Recent volume expansion vs base
        recent_vol = float(df.tail(5)["Volume"].mean())
        if len(base_days) > 0:
            base_vol_mean = float(base_days["Volume"].mean())
        else:
            base_vol_mean = float(df["Vol_SMA50"].iloc[-1])
        vol_expansion = recent_vol / base_vol_mean if base_vol_mean > 0 else 1.0
        self.signal_details["vol_expansion"] = round(vol_expansion, 1)

        if vol_expansion >= 3:
            self.signals["volume_surge_3x"] = True
        elif vol_expansion >= 2:
            self.signals["volume_surge_2x"] = True
        elif vol_expansion >= 1.5:
            self.signals["volume_expansion"] = True

        # Accumulation days (up-volume > down-volume over last 20 days)
        recent = df.tail(20)
        up_days_vol = float(recent[recent["Close"] > recent["Open"]]["Volume"].sum())
        down_days_vol = float(recent[recent["Close"] <= recent["Open"]]["Volume"].sum())

        if up_days_vol > down_days_vol * 1.3:
            self.signals["accumulation_days"] = True
            self.signal_details["accumulation_ratio"] = round(
                up_days_vol / max(down_days_vol, 1), 2
            )

    # ----- momentum / price action ------------------------------------------

    def _detect_momentum_signals(self) -> None:
        """Detect momentum and price-action signals."""
        df = self.df
        recent = df.tail(10)

        # Best single-day return in last 10 days
        best_day = float(recent["Return"].max())
        self.signal_details["best_day"] = round(best_day, 1)

        if best_day >= 15:
            self.signals["big_day_15"] = True
        elif best_day >= 10:
            self.signals["big_day_10"] = True
        elif best_day >= 5:
            self.signals["momentum_day"] = True

        # First higher low detection via argrelextrema
        lows = argrelextrema(df["Low"].values, np.less, order=5)[0]
        if len(lows) >= 2:
            recent_lows = lows[-2:]
            if df["Low"].iloc[recent_lows[-1]] > df["Low"].iloc[recent_lows[-2]]:
                self.signals["first_higher_low"] = True
                self.signal_details["higher_low_date"] = str(
                    df.index[recent_lows[-1]].date()
                )

        # First higher high detection
        highs = argrelextrema(df["High"].values, np.greater, order=5)[0]
        if len(highs) >= 2:
            recent_highs = highs[-2:]
            if df["High"].iloc[recent_highs[-1]] > df["High"].iloc[recent_highs[-2]]:
                self.signals["first_higher_high"] = True
                self.signal_details["higher_high_date"] = str(
                    df.index[recent_highs[-1]].date()
                )

        # Breakout attempt (near 20-day high)
        high_20d = float(df.tail(20)["High"].max())
        if self.current >= high_20d * 0.95:
            self.signals["breakout_attempt"] = True

    # ----- moving averages --------------------------------------------------

    def _detect_ma_signals(self) -> None:
        """Detect moving-average signals."""
        df = self.df
        latest = df.iloc[-1]

        # EMA stack: close > 5 > 10 > 20
        ema_bullish = (
            latest["Close"] > latest["EMA5"] > latest["EMA10"] > latest["EMA20"]
        )
        self.signal_details["ema_bullish"] = bool(ema_bullish)
        if ema_bullish:
            self.signals["ema_stack_bullish"] = True

        if latest["Close"] > latest["EMA20"]:
            self.signals["above_ema20"] = True

        if pd.notna(latest["EMA50"]) and latest["Close"] > latest["EMA50"]:
            self.signals["above_ema50"] = True

        # EMA reclaim sequence (recently crossed above EMAs)
        lookback = df.tail(10)
        crossed_ema20 = (
            (lookback["Close"] > lookback["EMA20"]).any()
            and (lookback["Close"] < lookback["EMA20"]).any()
        )
        if crossed_ema20 and latest["Close"] > latest["EMA20"]:
            self.signals["ema_reclaim_sequence"] = True

        # Golden cross approaching (20 EMA converging on 50 EMA from below)
        if pd.notna(latest["EMA50"]):
            ema20_50_gap = (
                (latest["EMA20"] - latest["EMA50"]) / latest["EMA50"] * 100
            )
            if -5 < ema20_50_gap < 5 and latest["EMA20"] > df.iloc[-5]["EMA20"]:
                self.signals["golden_cross_near"] = True

    # ----- RSI --------------------------------------------------------------

    def _detect_rsi_signals(self) -> None:
        """Detect RSI-based signals."""
        df = self.df
        current_rsi = float(df["RSI"].iloc[-1])
        self.signal_details["rsi"] = round(current_rsi, 1)

        # RSI thrust: moved from oversold (<40) to neutral/bullish (>50)
        rsi_20d_low = float(df["RSI"].tail(20).min())
        if rsi_20d_low < 40 and current_rsi > 50:
            self.signals["rsi_thrust"] = True

        # RSI recovering
        if current_rsi > 50 and df["RSI"].iloc[-1] > df["RSI"].iloc[-3]:
            self.signals["rsi_recovering"] = True

        # RSI oversold bounce
        rsi_5d_low = float(df["RSI"].tail(5).min())
        if rsi_5d_low < 30 and current_rsi > 35:
            self.signals["rsi_oversold_bounce"] = True

        # RSI bullish divergence (price lower low, RSI higher low)
        price_lows = argrelextrema(df["Low"].values, np.less, order=5)[0]
        if len(price_lows) >= 2:
            recent_price_lows = price_lows[-2:]
            price_ll = (
                df["Low"].iloc[recent_price_lows[-1]]
                < df["Low"].iloc[recent_price_lows[-2]]
            )
            rsi_hl = (
                df["RSI"].iloc[recent_price_lows[-1]]
                > df["RSI"].iloc[recent_price_lows[-2]]
            )
            if price_ll and rsi_hl:
                self.signals["rsi_bullish_divergence"] = True

    # ----- MACD -------------------------------------------------------------

    def _detect_macd_signals(self) -> None:
        """Detect MACD-based signals."""
        df = self.df
        latest = df.iloc[-1]

        macd_bullish = latest["MACD"] > latest["MACD_Signal"]
        self.signal_details["macd_bullish"] = bool(macd_bullish)

        if macd_bullish:
            self.signals["macd_bullish"] = True

        # Recent bullish cross in last 5 days
        lookback = df.tail(5)
        crossed = (lookback["MACD"] < lookback["MACD_Signal"]).any() and macd_bullish
        if crossed:
            self.signals["macd_bullish_cross"] = True

        # Histogram rising
        hist_rising = df["MACD_Hist"].iloc[-1] > df["MACD_Hist"].iloc[-3]
        if hist_rising and latest["MACD_Hist"] > df["MACD_Hist"].tail(5).min():
            self.signals["macd_histogram_rising"] = True

        # MACD bullish divergence (price lower low, MACD higher low)
        price_lows = argrelextrema(df["Low"].values, np.less, order=5)[0]
        if len(price_lows) >= 2:
            recent_price_lows = price_lows[-2:]
            price_ll = (
                df["Low"].iloc[recent_price_lows[-1]]
                < df["Low"].iloc[recent_price_lows[-2]]
            )
            macd_hl = (
                df["MACD"].iloc[recent_price_lows[-1]]
                > df["MACD"].iloc[recent_price_lows[-2]]
            )
            if price_ll and macd_hl:
                self.signals["macd_bullish_divergence"] = True

    # ----- volatility -------------------------------------------------------

    def _detect_volatility_signals(self) -> None:
        """Detect volatility-based signals (squeeze, contraction)."""
        df = self.df

        # Bollinger Band squeeze
        bb_width_current = float(df["BB_Width"].iloc[-1])
        bb_width_avg = float(df["BB_Width"].tail(50).mean())

        if bb_width_current < bb_width_avg * 0.7:
            self.signals["bollinger_squeeze"] = True
            self.signal_details["bb_squeeze_ratio"] = round(
                bb_width_current / bb_width_avg, 2
            )

        # ATR contracting
        atr_current = float(df["ATR"].iloc[-1])
        atr_avg = float(df["ATR"].tail(50).mean())
        if atr_current < atr_avg * 0.8:
            self.signals["atr_contracting"] = True

        # Range contraction (last 10 days vs prior 20)
        recent_range = float(df.tail(10)["High"].max() - df.tail(10)["Low"].min())
        prior_range = float(
            df.tail(30).head(20)["High"].max() - df.tail(30).head(20)["Low"].min()
        )
        if prior_range > 0 and recent_range < prior_range * 0.6:
            self.signals["range_contraction"] = True

    # ----- support / resistance ---------------------------------------------

    def _detect_support_signals(self) -> None:
        """Detect support/resistance proximity signals."""
        df = self.df

        # Support level: clustering of recent lows
        recent_lows = df.tail(60)["Low"]
        low_mean = float(recent_lows.min())

        # Count touches near the low
        touches = int(
            ((recent_lows >= low_mean * 0.97) & (recent_lows <= low_mean * 1.03)).sum()
        )

        if touches >= 3:
            self.signals["multiple_support_tests"] = True
            self.signal_details["support_touches"] = touches

        # Holding above support
        if self.current > low_mean * 1.05:
            self.signals["holding_above_support"] = True

        # Near breakout level
        high_20d = float(df.tail(20)["High"].max())
        if high_20d * 0.95 <= self.current < high_20d:
            self.signals["near_breakout_level"] = True

    # ----- relative strength vs SPY -----------------------------------------

    def _detect_relative_strength(self) -> None:
        """Detect relative strength vs SPY."""
        df = self.df
        try:
            spy = yf.Ticker("SPY").history(period="1mo")
            if spy.empty:
                return

            # 5-day relative strength
            stock_5d = (df["Close"].iloc[-1] / df["Close"].iloc[-5] - 1) * 100
            spy_5d = (spy["Close"].iloc[-1] / spy["Close"].iloc[-5] - 1) * 100
            if stock_5d > spy_5d:
                self.signals["outperforming_spy_5d"] = True

            # 20-day relative strength
            if len(df) >= 20 and len(spy) >= 20:
                stock_20d = (df["Close"].iloc[-1] / df["Close"].iloc[-20] - 1) * 100
                spy_20d = (spy["Close"].iloc[-1] / spy["Close"].iloc[-20] - 1) * 100
                if stock_20d > spy_20d:
                    self.signals["outperforming_spy_20d"] = True
                self.signal_details["rs_vs_spy_20d"] = round(stock_20d - spy_20d, 1)
        except Exception:
            logger.debug("Failed to fetch SPY data for relative strength", exc_info=True)

    # ----- stage determination ----------------------------------------------

    def _detect_stage(self) -> None:
        """Determine rally stage (EARLY / MID / LATE / EXTENDED)."""
        rally_from_low = (self.current - self.low_52w) / self.low_52w * 100
        self.signal_details["rally_from_low"] = round(rally_from_low, 1)

        if rally_from_low < 50:
            self.signals["early_stage_bonus"] = True
            self.signal_details["stage"] = "EARLY"
        elif rally_from_low < 100:
            self.signals["mid_stage_bonus"] = True
            self.signal_details["stage"] = "MID"
        elif rally_from_low < 200:
            self.signal_details["stage"] = "LATE"
        else:
            self.signals["extended_penalty"] = True
            self.signal_details["stage"] = "EXTENDED"

    # ----- analyst / fundamental --------------------------------------------

    def _detect_analyst_signals(self) -> None:
        """Detect analyst consensus and price-target signals."""
        info = self.info

        rec = info.get("recommendationKey", "")
        if rec in ("buy", "strong_buy"):
            self.signals["analyst_buy"] = True

        target_mean = info.get("targetMeanPrice")
        if target_mean and target_mean > 0:
            upside = (target_mean - self.current) / self.current * 100
            self.signal_details["upside_to_target"] = round(upside, 1)
            if upside > 50:
                self.signals["high_upside_target"] = True

    # ----- exceptional (rare, high-conviction) ------------------------------

    def _detect_exceptional_signals(self) -> None:
        """Detect rare, high-conviction exceptional signals."""
        df = self.df
        info = self.info

        # --- SHORT SQUEEZE SETUP ---
        short_ratio = info.get("shortRatio", 0) or 0
        short_pct = info.get("shortPercentOfFloat", 0) or 0
        if short_ratio > 5 or short_pct > 0.15:
            price_up_5d = df["Close"].iloc[-1] > df["Close"].iloc[-5] * 1.05
            vol_elevated = (
                df["Volume"].iloc[-5:].mean() > df["Volume"].iloc[-20:].mean() * 1.5
            )
            if price_up_5d and vol_elevated:
                self.signals["short_squeeze_setup"] = True
                self.signal_details["short_ratio"] = short_ratio
                self.signal_details["short_pct"] = round(short_pct * 100, 1)

        # --- EARNINGS BEAST ---
        earnings_growth = info.get("earningsGrowth", 0) or 0
        revenue_growth = info.get("revenueGrowth", 0) or 0
        if earnings_growth > 0.25 and revenue_growth > 0.20:
            self.signals["earnings_beast"] = True
            self.signal_details["earnings_growth"] = round(earnings_growth * 100, 1)
            self.signal_details["revenue_growth"] = round(revenue_growth * 100, 1)

        # --- INSTITUTIONAL ACCUMULATION ---
        inst_pct = info.get("heldPercentInstitutions", 0) or 0
        if inst_pct > 0.70:
            self.signals["institutional_accumulation"] = True
            self.signal_details["institutional_pct"] = round(inst_pct * 100, 1)

        # --- RELATIVE STRENGTH LEADER ---
        stock_52w_change = info.get("52WeekChange", 0) or 0
        sp_52w_change = info.get("SandP52WeekChange", 0) or 0
        if stock_52w_change > 0 and sp_52w_change > 0:
            if stock_52w_change > sp_52w_change * 2:
                self.signals["relative_strength_leader"] = True
                self.signal_details["vs_sp500"] = round(
                    (stock_52w_change - sp_52w_change) * 100, 1
                )

        # --- CONSECUTIVE GREEN DAYS (5+) after washout ---
        if len(df) >= 10:
            green_streak = 0
            for i in range(-1, -11, -1):
                if df["Close"].iloc[i] > df["Open"].iloc[i]:
                    green_streak += 1
                else:
                    break
            if green_streak >= 5 and self.signal_details.get("drawdown", 0) < -40:
                self.signals["consecutive_green_5"] = True
                self.signal_details["green_streak"] = green_streak

        # --- GAP UP ON VOLUME ---
        if len(df) >= 2:
            gap_pct = (df["Open"].iloc[-1] - df["Close"].iloc[-2]) / df["Close"].iloc[-2]
            vol_ratio = df["Volume"].iloc[-1] / df["Volume"].iloc[-20:].mean()
            if gap_pct > 0.05 and vol_ratio > 2:
                self.signals["gap_up_volume"] = True
                self.signal_details["gap_pct"] = round(gap_pct * 100, 1)

        # --- VCP (Volatility Contraction Pattern) ---
        if len(df) >= 40:
            range1 = (
                (df["High"].iloc[-40:-30].max() - df["Low"].iloc[-40:-30].min())
                / df["Close"].iloc[-35]
            )
            range2 = (
                (df["High"].iloc[-30:-15].max() - df["Low"].iloc[-30:-15].min())
                / df["Close"].iloc[-22]
            )
            range3 = (
                (df["High"].iloc[-15:].max() - df["Low"].iloc[-15:].min())
                / df["Close"].iloc[-7]
            )
            vol1 = float(df["Volume"].iloc[-40:-30].mean())
            vol2 = float(df["Volume"].iloc[-30:-15].mean())
            vol3 = float(df["Volume"].iloc[-15:-3].mean())

            if range1 > range2 > range3 and vol1 > vol2 > vol3:
                if range3 < 0.15:
                    self.signals["vcp_pattern"] = True

        # --- POWER EARNINGS GAP ---
        if len(df) >= 5:
            for i in range(-5, 0):
                if i == -1:
                    continue
                gap = (df["Open"].iloc[i] - df["Close"].iloc[i - 1]) / df["Close"].iloc[i - 1]
                if gap > 0.10:
                    if df["Close"].iloc[-1] >= df["Open"].iloc[i] * 0.95:
                        vol_on_gap = df["Volume"].iloc[i] / df["Volume"].iloc[i - 20 : i].mean()
                        if vol_on_gap > 3:
                            self.signals["power_earnings_gap"] = True
                            break

        # --- POCKET PIVOT (Gil Morales / Chris Kacher) ---
        if len(df) >= 12:
            today_close = float(df["Close"].iloc[-1])
            today_open = float(df["Open"].iloc[-1])
            today_vol = float(df["Volume"].iloc[-1])

            if today_close > today_open:  # up day
                max_down_vol = 0.0
                for i in range(-11, -1):
                    if df["Close"].iloc[i] < df["Open"].iloc[i]:
                        max_down_vol = max(max_down_vol, float(df["Volume"].iloc[i]))

                if max_down_vol > 0 and today_vol > max_down_vol:
                    ema21 = float(df["Close"].ewm(span=21).mean().iloc[-1])
                    if today_close <= ema21 * 1.10:
                        self.signals["pocket_pivot"] = True

        # --- SHAKEOUT + RALLY ---
        if len(df) >= 30:
            support = float(df["Low"].iloc[-30:-10].min())
            broke_support = False
            for i in range(-5, -1):
                if df["Low"].iloc[i] < support * 0.98:
                    broke_support = True
                    break
            if broke_support and df["Close"].iloc[-1] > support * 1.02:
                self.signals["shakeout_rally"] = True

    # ----- quality filters --------------------------------------------------

    def _detect_quality_filters(self) -> None:
        """Apply quality-filter penalties."""
        df = self.df
        avg_vol = float(df["Volume"].tail(20).mean())
        if avg_vol < 100_000:
            self.signals["low_volume_penalty"] = True

        if self.current < 1:
            self.signals["penny_stock_penalty"] = True


# ---------------------------------------------------------------------------
# Public detector class
# ---------------------------------------------------------------------------

class StockSignalDetector:
    """
    Full-featured stock signal scanner.

    Usage::

        detector = StockSignalDetector()
        result = detector.scan("AAPL")
        print(result["score"], result["signals_triggered"])

    Or scan a list::

        results = detector.scan_universe(["AAPL", "NVDA", "SOFI"])
    """

    def __init__(
        self,
        weights: Optional[Dict[str, int]] = None,
        weights_file: Optional[Path] = None,
    ) -> None:
        wf = weights_file or WEIGHTS_FILE
        self.weights: Dict[str, int] = weights or load_weights(wf, STOCK_WEIGHTS)

    # ----- single ticker scan -----------------------------------------------

    def scan(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Perform a full scan of *ticker* and return a result dict, or ``None``
        if the ticker is ineligible (insufficient data, price filters, etc.).
        """
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period="1y", interval="1d")

            if df.empty or len(df) < 60:
                logger.debug("%s: insufficient data (%d bars)", ticker, len(df))
                return None

            info = stock.info or {}
            current = float(df.iloc[-1]["Close"])

            # --- run signal detection ---
            engine = _SignalEngine(df, info)
            signals, details = engine.detect_all_signals()

            # --- weighted scoring ---
            score = 0
            triggered_signals: List[str] = []
            signal_scores: Dict[str, int] = {}

            for signal, triggered in signals.items():
                if triggered and signal in self.weights:
                    weight = self.weights[signal]
                    score += weight
                    triggered_signals.append(signal)
                    signal_scores[signal] = weight

            # --- confluence multiplier ---
            multiplier = compute_stock_confluence(triggered_signals)
            if multiplier > 1.0:
                bonus_key = f"confluence_{int((multiplier - 1) * 10)}"
                signal_scores[bonus_key] = int(score * (multiplier - 1))
            score = int(score * multiplier)

            # --- risk/reward adjustment ---
            high_52w = engine.high_52w
            low_52w = engine.low_52w
            atr = float(df["ATR"].iloc[-1]) if "ATR" in df.columns else float(
                (df["High"] - df["Low"]).tail(14).mean()
            )
            stop = max(low_52w * 0.95, current - 2 * atr)
            r_unit = current - stop

            target_mean = info.get("targetMeanPrice")
            reward_target = (
                target_mean
                if target_mean and target_mean > current
                else current + 10 * r_unit
            )
            potential_reward = reward_target - current
            potential_risk = current - stop
            rr_ratio = potential_reward / potential_risk if potential_risk > 0 else 0

            if rr_ratio > 5:
                rr_weight = self.weights.get("rr_excellent", 10)
                score += rr_weight
                signal_scores["rr_excellent"] = rr_weight
            elif rr_ratio > 3:
                rr_weight = self.weights.get("rr_good", 5)
                score += rr_weight
                signal_scores["rr_good"] = rr_weight
            elif rr_ratio < 2:
                rr_weight = self.weights.get("rr_poor", -8)
                score += rr_weight
                signal_scores["rr_poor"] = rr_weight

            # --- build flags from top signals ---
            flags: List[str] = []
            sorted_signals = sorted(signal_scores.items(), key=lambda x: x[1], reverse=True)
            for sig, _weight in sorted_signals[:8]:
                flag_name = sig.upper().replace("_", " ")
                if len(flag_name) <= 15:
                    flags.append(flag_name)

            return {
                "ticker": ticker,
                "name": info.get("shortName", ticker)[:30],
                "sector": info.get("sector", "Unknown"),
                "industry": info.get("industry", "Unknown"),
                "price": round(current, 2),
                "score": score,
                "max_possible_score": max_positive_score(self.weights),
                "signals_triggered": len(triggered_signals),
                "total_signals": len(self.weights),
                "flags": flags,
                "signal_breakdown": signal_scores,
                "details": details,
                "drawdown": details.get("drawdown", 0),
                "rally_from_low": details.get("rally_from_low", 0),
                "base_tightness": details.get("base_tightness", 0),
                "vol_expansion": details.get("vol_expansion", 1),
                "best_day": details.get("best_day", 0),
                "rsi": details.get("rsi", 50),
                "ema_bullish": details.get("ema_bullish", False),
                "macd_bullish": details.get("macd_bullish", False),
                "stage": details.get("stage", "UNKNOWN"),
                "stop": round(stop, 2),
                "R": round(r_unit, 3),
                "t1": round(current + 2 * r_unit, 2),
                "t2": round(current + 4 * r_unit, 2),
                "t3": round(current + 6 * r_unit, 2),
                "t4": round(current + 10 * r_unit, 2),
                "pct_to_t2": round((4 * r_unit) / current * 100, 1) if current else 0,
                "pct_to_10r": round((10 * r_unit) / current * 100, 1) if current else 0,
                "high_52w": round(high_52w, 2),
                "low_52w": round(low_52w, 2),
                "target_mean": round(target_mean, 2) if target_mean else None,
                "mcap_m": round(info.get("marketCap", 0) / 1e6) if info.get("marketCap") else 0,
            }

        except Exception:
            logger.warning("Failed to scan %s", ticker, exc_info=True)
            return None

    # ----- multi-ticker scan ------------------------------------------------

    def scan_universe(
        self,
        tickers: List[str],
        min_score: int = 35,
        max_workers: int = 8,
    ) -> List[Dict[str, Any]]:
        """
        Scan a list of tickers in parallel and return results sorted by score
        (descending), filtered to *min_score*.
        """
        results: List[Dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.scan, t): t for t in tickers}
            for future in as_completed(futures):
                result = future.result()
                if result and result["score"] >= min_score:
                    results.append(result)

        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    # ----- weight management ------------------------------------------------

    def get_weights(self) -> Dict[str, int]:
        """Return current weight dictionary."""
        return self.weights.copy()

    def update_weights(self, updates: Dict[str, int]) -> None:
        """Merge *updates* into current weights and persist."""
        self.weights.update(updates)
        save_weights(WEIGHTS_FILE, self.weights)
