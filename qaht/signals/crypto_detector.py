"""
Crypto signal detector -- ported from RZLV crypto_scanner.py.

Detects 30+ bullish/bearish signals on cryptocurrency OHLCV data, with
BTC-relative strength, altcoin-season detection, and whale-volume patterns.

Usage::

    detector = CryptoSignalDetector()
    result   = detector.scan("ETH-USD")

    # or scan a whole universe:
    scanner  = CryptoScanner()
    results  = scanner.scan(min_score=20)
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import yfinance as yf

from .weights import (
    CRYPTO_WEIGHTS,
    compute_crypto_confluence,
    load_weights,
    max_positive_score,
    save_weights,
)

logger = logging.getLogger("qaht.signals.crypto_detector")

WEIGHTS_FILE = Path(__file__).resolve().parent / "crypto_weights.json"

# Default universe -- majors, DeFi, gaming, AI, infra, memes
DEFAULT_CRYPTO_UNIVERSE: List[str] = [
    # Major coins
    "BTC-USD", "ETH-USD", "BNB-USD", "XRP-USD", "ADA-USD", "SOL-USD",
    "DOGE-USD", "DOT-USD", "MATIC-USD", "SHIB-USD", "TRX-USD", "AVAX-USD",
    "LINK-USD", "ATOM-USD", "UNI-USD", "XMR-USD", "ETC-USD", "XLM-USD",
    "BCH-USD", "LTC-USD",
    # DeFi & Layer 2
    "AAVE-USD", "MKR-USD", "CRV-USD", "LDO-USD", "ARB-USD", "OP-USD",
    "IMX-USD",
    # Gaming & Metaverse
    "MANA-USD", "SAND-USD", "AXS-USD", "GALA-USD", "ENJ-USD", "ILV-USD",
    # AI & Data
    "FET-USD", "RNDR-USD", "GRT-USD", "OCEAN-USD",
    # Infrastructure
    "FIL-USD", "NEAR-USD", "ALGO-USD", "VET-USD", "HBAR-USD", "ICP-USD",
    "EGLD-USD", "INJ-USD", "APT-USD", "SUI-USD", "SEI-USD",
    # Meme coins
    "PEPE-USD", "FLOKI-USD", "BONK-USD", "WIF-USD",
]

# Sector groupings for sector-rotation-leader detection
_GAMING_COINS = {"MANA-USD", "SAND-USD", "AXS-USD", "GALA-USD", "ENJ-USD", "ILV-USD"}
_AI_COINS = {"FET-USD", "RNDR-USD", "GRT-USD", "OCEAN-USD"}
_DEFI_COINS = {"AAVE-USD", "MKR-USD", "CRV-USD", "LDO-USD", "UNI-USD"}
_L2_COINS = {"ARB-USD", "OP-USD", "MATIC-USD", "IMX-USD"}


# ---------------------------------------------------------------------------
# Internal signal engine -- operates on a single prepared DataFrame
# ---------------------------------------------------------------------------

class _CryptoSignalEngine:
    """
    Low-level signal detection for a single cryptocurrency.

    Consumers should use :class:`CryptoScanner` or instantiate this directly
    only when they already have OHLCV data in hand.
    """

    def __init__(self, df: pd.DataFrame, ticker: str) -> None:
        self.df = df.copy()
        self.ticker = ticker.upper()
        self.signals: Dict[str, bool] = {}
        self._calculate_indicators()

    # ----- indicators -------------------------------------------------------

    def _calculate_indicators(self) -> None:
        df = self.df

        # EMAs
        df["ema20"] = df["Close"].ewm(span=20).mean()
        df["ema50"] = df["Close"].ewm(span=50).mean()
        df["ema200"] = df["Close"].ewm(span=200).mean()

        # RSI (14)
        delta = df["Close"].diff()
        gain = delta.where(delta > 0, 0).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df["rsi"] = 100 - (100 / (1 + rs))

        # MACD (12/26/9)
        exp1 = df["Close"].ewm(span=12).mean()
        exp2 = df["Close"].ewm(span=26).mean()
        df["macd"] = exp1 - exp2
        df["macd_signal"] = df["macd"].ewm(span=9).mean()
        df["macd_hist"] = df["macd"] - df["macd_signal"]

        # Bollinger Bands (20, 2)
        df["bb_mid"] = df["Close"].rolling(window=20).mean()
        df["bb_std"] = df["Close"].rolling(window=20).std()
        df["bb_upper"] = df["bb_mid"] + df["bb_std"] * 2
        df["bb_lower"] = df["bb_mid"] - df["bb_std"] * 2
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]

        # ATR (14)
        high_low = df["High"] - df["Low"]
        high_close = (df["High"] - df["Close"].shift()).abs()
        low_close = (df["Low"] - df["Close"].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = tr.rolling(window=14).mean()

        # Volume metrics
        df["vol_sma20"] = df["Volume"].rolling(window=20).mean()
        df["vol_ratio"] = df["Volume"] / df["vol_sma20"]

    # ----- orchestrator -----------------------------------------------------

    def detect_all_signals(
        self, btc_df: Optional[pd.DataFrame] = None
    ) -> Dict[str, bool]:
        """Detect every crypto signal and return the signal dict."""
        self._detect_trend_signals()
        self._detect_volume_signals()
        self._detect_price_action()
        self._detect_momentum()
        self._detect_moving_average_signals()
        self._detect_volatility()
        self._detect_drawdown_recovery()
        if btc_df is not None:
            self._detect_relative_strength(btc_df)
            self._detect_exceptional_signals(btc_df)
        else:
            self._detect_exceptional_signals(None)
        self._detect_penalties()
        return self.signals

    # ----- trend signals ----------------------------------------------------

    def _detect_trend_signals(self) -> None:
        df = self.df
        if len(df) < 50:
            return

        # Strong uptrend: higher highs and higher lows
        recent_highs = df["High"].rolling(window=10).max()
        recent_lows = df["Low"].rolling(window=10).min()

        if len(df) >= 40:
            hh_count = int(
                (recent_highs.iloc[-20:] > recent_highs.iloc[-40:-20].max()).sum()
            )
            hl_count = int(
                (recent_lows.iloc[-20:] > recent_lows.iloc[-40:-20].min()).sum()
            )
            if hh_count >= 5 and hl_count >= 5:
                self.signals["strong_uptrend"] = True

        # Golden cross / death cross detection
        if len(df) >= 200:
            ema50_prev = float(df["ema50"].iloc[-5])
            ema200_prev = float(df["ema200"].iloc[-5])
            ema50_now = float(df["ema50"].iloc[-1])
            ema200_now = float(df["ema200"].iloc[-1])

            if ema50_prev < ema200_prev and ema50_now > ema200_now:
                self.signals["golden_cross"] = True

            if ema50_now < ema200_now:
                self.signals["death_cross"] = True
                if df["Close"].iloc[-1] > df["ema50"].iloc[-1]:
                    self.signals["death_cross_recovery"] = True

        # Trend reversal from bottom
        current = float(df["Close"].iloc[-1])
        low_20d = float(df["Low"].iloc[-20:].min())
        if len(df) >= 60:
            low_60d = float(df["Low"].iloc[-60:].min())
            if current > low_20d * 1.15 and low_20d <= low_60d * 1.05:
                self.signals["trend_reversal"] = True

    # ----- volume signals ---------------------------------------------------

    def _detect_volume_signals(self) -> None:
        df = self.df
        if len(df) < 20:
            return

        current_vol = float(df["Volume"].iloc[-1])
        avg_vol = float(df["vol_sma20"].iloc[-1])
        vol_ratio = current_vol / avg_vol if avg_vol > 0 else 0

        # Volume spikes
        if vol_ratio >= 5:
            self.signals["volume_spike_5x"] = True
        elif vol_ratio >= 3:
            self.signals["volume_spike_3x"] = True
        elif vol_ratio >= 2:
            self.signals["volume_spike_2x"] = True

        # Volume breakout (high volume + price up)
        price_change = (
            (df["Close"].iloc[-1] - df["Close"].iloc[-2]) / df["Close"].iloc[-2]
        )
        if vol_ratio >= 2 and price_change > 0.03:
            self.signals["volume_breakout"] = True

        # Accumulation pattern (up-day vol > down-day vol)
        if len(df) >= 10:
            up_vol = float(
                df[df["Close"] > df["Open"]]["Volume"].iloc[-10:].mean()
            ) if len(df[df["Close"] > df["Open"]]) >= 1 else 0
            down_vol = float(
                df[df["Close"] < df["Open"]]["Volume"].iloc[-10:].mean()
            ) if len(df[df["Close"] < df["Open"]]) >= 1 else 1
            if up_vol > down_vol * 1.5:
                self.signals["accumulation_volume"] = True

        # Volume dryup then spike
        if len(df) >= 10:
            prev_vol_avg = float(df["Volume"].iloc[-10:-3].mean())
            recent_vol = float(df["Volume"].iloc[-3:].mean())
            if (
                avg_vol > 0
                and prev_vol_avg < avg_vol * 0.6
                and recent_vol > prev_vol_avg * 2
            ):
                self.signals["volume_dryup_reversal"] = True

    # ----- price action -----------------------------------------------------

    def _detect_price_action(self) -> None:
        df = self.df
        if len(df) < 30:
            return

        current = float(df["Close"].iloc[-1])

        # Higher high
        high_20d = float(df["High"].iloc[-20:-1].max())
        if current > high_20d:
            self.signals["higher_high"] = True

        # Higher low
        low_10d = float(df["Low"].iloc[-10:].min())
        low_20d_prev = float(df["Low"].iloc[-30:-10].min())
        if low_10d > low_20d_prev:
            self.signals["higher_low"] = True

        # Support bounce
        low_30d = float(df["Low"].iloc[-30:].min())
        if df["Low"].iloc[-3:].min() <= low_30d * 1.02 and current > low_30d * 1.05:
            self.signals["support_bounce"] = True

        # Breakout resistance
        resistance = float(
            df["High"].iloc[-30:-5].max() if len(df) >= 30 else df["High"].iloc[:-5].max()
        )
        if current > resistance:
            self.signals["breakout_resistance"] = True

        # Range breakout (tight consolidation then move)
        if len(df) >= 20:
            range_high = float(df["High"].iloc[-20:-3].max())
            range_low = float(df["Low"].iloc[-20:-3].min())
            range_pct = (range_high - range_low) / range_low if range_low > 0 else 0
            if range_pct < 0.15 and current > range_high:
                self.signals["range_breakout"] = True

        # Pullback to EMA
        ema20 = float(df["ema20"].iloc[-1])
        if ema20 > 0 and abs(current - ema20) / ema20 < 0.02 and current > ema20:
            if len(df) >= 5 and df["Close"].iloc[-5] > ema20 * 1.03:
                self.signals["pullback_to_ema"] = True

    # ----- momentum ---------------------------------------------------------

    def _detect_momentum(self) -> None:
        df = self.df
        if len(df) < 20:
            return

        rsi = float(df["rsi"].iloc[-1])
        rsi_prev = float(df["rsi"].iloc[-5]) if len(df) >= 5 else rsi

        # RSI oversold bounce
        if rsi_prev < 30 and rsi > 35:
            self.signals["crypto_rsi_oversold_bounce"] = True

        # RSI bullish divergence
        if len(df) >= 20:
            price_low_recent = float(df["Close"].iloc[-10:].min())
            price_low_prev = float(df["Close"].iloc[-20:-10].min())
            rsi_low_recent = float(df["rsi"].iloc[-10:].min())
            rsi_low_prev = float(df["rsi"].iloc[-20:-10].min())
            if price_low_recent < price_low_prev and rsi_low_recent > rsi_low_prev:
                self.signals["crypto_rsi_bullish_divergence"] = True

        # MACD bullish cross
        macd = float(df["macd"].iloc[-1])
        macd_signal = float(df["macd_signal"].iloc[-1])
        macd_prev = float(df["macd"].iloc[-3]) if len(df) >= 3 else macd
        signal_prev = float(df["macd_signal"].iloc[-3]) if len(df) >= 3 else macd_signal

        if macd_prev < signal_prev and macd > macd_signal:
            self.signals["crypto_macd_bullish_cross"] = True

        # MACD histogram flip
        hist = float(df["macd_hist"].iloc[-1])
        hist_prev = float(df["macd_hist"].iloc[-3]) if len(df) >= 3 else hist
        if hist_prev < 0 and hist > 0:
            self.signals["macd_histogram_flip"] = True

        # Momentum surge (>10% in 5 days)
        if len(df) >= 5:
            momentum_5d = (df["Close"].iloc[-1] - df["Close"].iloc[-5]) / df["Close"].iloc[-5]
            if momentum_5d > 0.10:
                self.signals["momentum_surge"] = True

    # ----- moving averages --------------------------------------------------

    def _detect_moving_average_signals(self) -> None:
        df = self.df
        if len(df) < 50:
            return

        current = float(df["Close"].iloc[-1])
        ema20 = float(df["ema20"].iloc[-1])
        ema50 = float(df["ema50"].iloc[-1])

        if current > ema20:
            self.signals["reclaim_ema20"] = True
        if current > ema50:
            self.signals["reclaim_ema50"] = True

        if len(df) >= 200:
            ema200 = float(df["ema200"].iloc[-1])
            if current > ema200:
                self.signals["reclaim_ema200"] = True
            if current > ema20 and current > ema50 and current > ema200:
                self.signals["above_all_emas"] = True
            if ema20 > ema50 > ema200:
                self.signals["crypto_ema_stack_bullish"] = True

    # ----- volatility -------------------------------------------------------

    def _detect_volatility(self) -> None:
        df = self.df
        if len(df) < 20:
            return

        current = float(df["Close"].iloc[-1])
        bb_width = float(df["bb_width"].iloc[-1])
        bb_width_avg = float(
            df["bb_width"].iloc[-50:].mean() if len(df) >= 50 else bb_width
        )

        if bb_width < bb_width_avg * 0.6:
            self.signals["crypto_bollinger_squeeze"] = True

        if current > df["bb_upper"].iloc[-1]:
            self.signals["bollinger_breakout_up"] = True

        atr = float(df["atr"].iloc[-1])
        atr_avg = float(df["atr"].iloc[-20:].mean())
        if atr_avg > 0 and atr > atr_avg * 1.5:
            self.signals["atr_expansion"] = True

    # ----- relative strength vs BTC -----------------------------------------

    def _detect_relative_strength(self, btc_df: pd.DataFrame) -> None:
        df = self.df
        if len(df) < 30 or len(btc_df) < 30:
            return

        # 7-day
        if len(df) >= 7 and len(btc_df) >= 7:
            coin_perf_7d = (
                (df["Close"].iloc[-1] - df["Close"].iloc[-7]) / df["Close"].iloc[-7]
            )
            btc_perf_7d = (
                (btc_df["Close"].iloc[-1] - btc_df["Close"].iloc[-7]) / btc_df["Close"].iloc[-7]
            )
            if coin_perf_7d > btc_perf_7d + 0.05:
                self.signals["outperform_btc_7d"] = True

        # 30-day
        if len(df) >= 30 and len(btc_df) >= 30:
            coin_perf_30d = (
                (df["Close"].iloc[-1] - df["Close"].iloc[-30]) / df["Close"].iloc[-30]
            )
            btc_perf_30d = (
                (btc_df["Close"].iloc[-1] - btc_df["Close"].iloc[-30]) / btc_df["Close"].iloc[-30]
            )
            if coin_perf_30d > btc_perf_30d + 0.10:
                self.signals["outperform_btc_30d"] = True

    # ----- drawdown / recovery ----------------------------------------------

    def _detect_drawdown_recovery(self) -> None:
        df = self.df
        if len(df) < 60:
            return

        current = float(df["Close"].iloc[-1])
        high_all = float(df["High"].max())
        low_60d = float(df["Low"].iloc[-60:].min())

        drawdown = (high_all - current) / high_all * 100

        if drawdown >= 70:
            self.signals["major_washout_70"] = True
        elif drawdown >= 50:
            self.signals["crypto_washout_50"] = True

        recovery = (current - low_60d) / low_60d * 100
        if recovery >= 30:
            self.signals["recovery_from_low"] = True

    # ----- exceptional signals ----------------------------------------------

    def _detect_exceptional_signals(
        self, btc_df: Optional[pd.DataFrame] = None
    ) -> None:
        df = self.df
        if len(df) < 60:
            return

        current = float(df["Close"].iloc[-1])

        # --- EXTREME WASHOUT RECOVERY ---
        high_all = float(df["High"].max())
        drawdown = (high_all - current) / high_all * 100
        low_30d = float(df["Low"].iloc[-30:].min())
        recovery_pct = (current - low_30d) / low_30d * 100
        if drawdown >= 80 and recovery_pct >= 30:
            self.signals["extreme_washout_recovery"] = True

        # --- BTC DECOUPLING (BULLISH) ---
        if btc_df is not None and len(btc_df) >= 14:
            btc_change_14d = (
                (btc_df["Close"].iloc[-1] - btc_df["Close"].iloc[-14])
                / btc_df["Close"].iloc[-14]
            )
            coin_change_14d = (current - df["Close"].iloc[-14]) / df["Close"].iloc[-14]
            if btc_change_14d < 0.05 and coin_change_14d > btc_change_14d + 0.20:
                self.signals["btc_decoupling_bullish"] = True

        # --- MULTI-DAY BREAKOUT ---
        high_30d = float(df["High"].iloc[-30:-1].max())
        if current > high_30d:
            vol_ratio = float(
                df["Volume"].iloc[-3:].mean() / df["Volume"].iloc[-30:].mean()
            )
            if vol_ratio > 1.5:
                self.signals["multi_day_breakout"] = True

        # --- ACCUMULATION PHASE END ---
        if len(df) >= 45:
            range_30d = (
                (df["High"].iloc[-45:-15].max() - df["Low"].iloc[-45:-15].min())
                / df["Close"].iloc[-30]
            )
            range_recent = (
                (df["High"].iloc[-15:].max() - df["Low"].iloc[-15:].min())
                / df["Close"].iloc[-7]
            )
            if range_30d < 0.25:
                if current > df["High"].iloc[-45:-15].max() and range_recent > range_30d:
                    vol_breakout = (
                        df["Volume"].iloc[-5:].mean()
                        > df["Volume"].iloc[-45:-15].mean() * 1.5
                    )
                    if vol_breakout:
                        self.signals["accumulation_phase_end"] = True

        # --- WHALE VOLUME PATTERN ---
        if len(df) >= 20:
            avg_vol = float(
                df["Volume"].iloc[-60:].mean() if len(df) >= 60 else df["Volume"].mean()
            )
            whale_days = int((df["Volume"].iloc[-10:] > avg_vol * 3).sum())
            if whale_days >= 3 and df["Close"].iloc[-1] > df["Close"].iloc[-10]:
                self.signals["whale_volume_pattern"] = True

        # --- CONSECUTIVE GREEN 7 ---
        green_streak = 0
        for i in range(-1, -15, -1):
            if df["Close"].iloc[i] > df["Open"].iloc[i]:
                green_streak += 1
            else:
                break
        if green_streak >= 7:
            self.signals["consecutive_green_7"] = True

        # --- SECTOR ROTATION LEADER ---
        change_7d = (
            (current - df["Close"].iloc[-7]) / df["Close"].iloc[-7]
            if len(df) >= 7
            else 0
        )
        if change_7d > 0.15:
            if self.ticker in (_GAMING_COINS | _AI_COINS | _DEFI_COINS | _L2_COINS):
                self.signals["sector_rotation_leader"] = True

        # --- SHAKEOUT + RALLY ---
        if len(df) >= 30:
            support = float(df["Low"].iloc[-30:-10].min())
            broke_support = False
            for i in range(-5, -1):
                if df["Low"].iloc[i] < support * 0.97:
                    broke_support = True
                    break
            if broke_support and df["Close"].iloc[-1] > support * 1.02:
                self.signals["crypto_shakeout_rally"] = True

    # ----- penalties --------------------------------------------------------

    def _detect_penalties(self) -> None:
        df = self.df
        if len(df) < 14:
            return

        rsi = float(df["rsi"].iloc[-1])
        current = float(df["Close"].iloc[-1])

        if rsi > 85:
            self.signals["extreme_overbought"] = True

        if len(df) >= 7:
            gain_7d = (current - df["Close"].iloc[-7]) / df["Close"].iloc[-7]
            if gain_7d > 0.50:
                self.signals["parabolic_move"] = True

        avg_vol = float(
            df["Volume"].iloc[-20:].mean() if len(df) >= 20 else df["Volume"].mean()
        )
        avg_dollar_vol = avg_vol * current
        if avg_dollar_vol < 100_000:
            self.signals["low_liquidity"] = True


# ---------------------------------------------------------------------------
# Public scanner class
# ---------------------------------------------------------------------------

class CryptoScanner:
    """
    Scans a universe of cryptocurrencies for bullish setups.

    Usage::

        scanner = CryptoScanner()
        results = scanner.scan(min_score=20)
    """

    def __init__(
        self,
        universe: Optional[List[str]] = None,
        weights: Optional[Dict[str, int]] = None,
        weights_file: Optional[Path] = None,
    ) -> None:
        self.universe = universe or DEFAULT_CRYPTO_UNIVERSE
        wf = weights_file or WEIGHTS_FILE
        self.weights: Dict[str, int] = weights or load_weights(wf, CRYPTO_WEIGHTS)
        self.btc_data: Optional[pd.DataFrame] = None
        self.altcoin_season: bool = False

    # ----- BTC reference data -----------------------------------------------

    def _fetch_btc_data(self) -> pd.DataFrame:
        """Fetch BTC-USD data for relative-strength comparisons."""
        if self.btc_data is None:
            try:
                btc = yf.Ticker("BTC-USD")
                self.btc_data = btc.history(period="1y")
            except Exception:
                logger.warning("Failed to fetch BTC data", exc_info=True)
                self.btc_data = pd.DataFrame()
        return self.btc_data

    # ----- altcoin season detection -----------------------------------------

    def _detect_altcoin_season(self, btc_df: pd.DataFrame) -> bool:
        """
        Detect altcoin season: 75%+ of top altcoins outperforming BTC
        over the trailing 7 days.
        """
        if btc_df is None or btc_df.empty or len(btc_df) < 7:
            return False

        btc_change_7d = (
            (btc_df["Close"].iloc[-1] - btc_df["Close"].iloc[-7])
            / btc_df["Close"].iloc[-7]
        )

        top_alts = [
            "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD",
            "AVAX-USD", "DOT-USD", "LINK-USD", "MATIC-USD",
        ]
        outperforming = 0

        for alt in top_alts:
            try:
                alt_data = yf.Ticker(alt).history(period="10d")
                if len(alt_data) >= 7:
                    alt_change = (
                        (alt_data["Close"].iloc[-1] - alt_data["Close"].iloc[-7])
                        / alt_data["Close"].iloc[-7]
                    )
                    if alt_change > btc_change_7d:
                        outperforming += 1
            except Exception:
                continue

        return outperforming >= 6

    # ----- single ticker analysis -------------------------------------------

    def _analyze_crypto(
        self, ticker: str, btc_df: pd.DataFrame
    ) -> Optional[Dict[str, Any]]:
        """Analyze a single cryptocurrency and return a result dict."""
        try:
            crypto = yf.Ticker(ticker)
            df = crypto.history(period="1y")

            if df.empty or len(df) < 30:
                return None

            info = crypto.info or {}
            name = info.get("name") or info.get("shortName") or ticker.replace("-USD", "")

            # Detect signals
            engine = _CryptoSignalEngine(df, ticker)
            signals = engine.detect_all_signals(btc_df)

            # Weighted scoring
            score = 0
            signal_breakdown: Dict[str, int] = {}
            triggered_signals: List[str] = []

            for signal, fired in signals.items():
                if fired and signal in self.weights:
                    weight = self.weights[signal]
                    score += weight
                    signal_breakdown[signal] = weight
                    triggered_signals.append(signal)

            # Confluence multiplier
            multiplier = compute_crypto_confluence(triggered_signals)
            if multiplier > 1.0:
                bonus_key = f"confluence_{int((multiplier - 1) * 10)}_cats"
                signal_breakdown[bonus_key] = int(score * (multiplier - 1))
            score = int(score * multiplier)

            # Altcoin season bonus
            is_altcoin = ticker not in ("BTC-USD", "ETH-USD")
            if is_altcoin and self.altcoin_season:
                bonus = self.weights.get("altcoin_season_bonus", 5)
                score += bonus
                signal_breakdown["altcoin_season_bonus"] = bonus

            # Metrics
            current = float(df["Close"].iloc[-1])
            high_all = float(df["High"].max())
            low_all = float(df["Low"].min())
            low_30d = float(df["Low"].iloc[-30:].min())
            vol_24h = float(df["Volume"].iloc[-1]) * current
            vol_avg = float(df["Volume"].iloc[-20:].mean()) * current
            rsi = float(df["rsi"].iloc[-1]) if "rsi" in df.columns else 50.0

            ema20 = float(df["ema20"].iloc[-1]) if "ema20" in df.columns else current
            ema50 = float(df["ema50"].iloc[-1]) if "ema50" in df.columns else current

            # Trend label
            if current > ema20 > ema50:
                trend = "BULLISH"
            elif current > ema20:
                trend = "RECOVERING"
            elif current > ema50:
                trend = "NEUTRAL"
            else:
                trend = "BEARISH"

            # Period changes
            change_24h = (
                (current - df["Close"].iloc[-2]) / df["Close"].iloc[-2] * 100
                if len(df) >= 2 else 0
            )
            change_7d = (
                (current - df["Close"].iloc[-7]) / df["Close"].iloc[-7] * 100
                if len(df) >= 7 else 0
            )
            change_30d = (
                (current - df["Close"].iloc[-30]) / df["Close"].iloc[-30] * 100
                if len(df) >= 30 else 0
            )

            drawdown = (high_all - current) / high_all * 100
            rally_from_low = (current - low_30d) / low_30d * 100

            # Flags for quick visual summary
            flags: List[str] = []
            if signals.get("volume_spike_5x"):
                flags.append("VOL 5X")
            elif signals.get("volume_spike_3x"):
                flags.append("VOL 3X")
            elif signals.get("volume_spike_2x"):
                flags.append("VOL 2X")
            if signals.get("golden_cross"):
                flags.append("GOLDEN CROSS")
            if signals.get("trend_reversal"):
                flags.append("REVERSAL")
            if signals.get("crypto_rsi_bullish_divergence"):
                flags.append("RSI DIVERGENCE")
            if signals.get("breakout_resistance"):
                flags.append("BREAKOUT")
            if signals.get("range_breakout"):
                flags.append("RANGE BREAK")
            if signals.get("major_washout_70"):
                flags.append("MAJOR WASHOUT")
            if signals.get("above_all_emas"):
                flags.append("ABOVE ALL EMAs")
            if signals.get("outperform_btc_30d"):
                flags.append("OUTPERFORM BTC")

            price_decimals = 6 if current < 1 else 2

            return {
                "ticker": ticker,
                "name": name,
                "price": round(current, price_decimals),
                "score": int(score),
                "max_score": max_positive_score(self.weights),
                "signals_triggered": len([s for s in signals.values() if s]),
                "trend": trend,
                "flags": flags,
                "signal_breakdown": signal_breakdown,
                "change_24h": round(change_24h, 2),
                "change_7d": round(change_7d, 2),
                "change_30d": round(change_30d, 2),
                "volume_24h": round(vol_24h, 0),
                "volume_avg": round(vol_avg, 0),
                "volume_ratio": round(vol_24h / vol_avg, 2) if vol_avg > 0 else 0,
                "rsi": round(rsi, 1),
                "drawdown_from_ath": round(drawdown, 1),
                "rally_from_30d_low": round(rally_from_low, 1),
                "high_all_time": round(high_all, price_decimals),
                "low_30d": round(low_30d, price_decimals),
                "ema20": round(ema20, price_decimals),
                "ema50": round(ema50, price_decimals),
                "altcoin_season": self.altcoin_season,
            }

        except Exception:
            logger.warning("Failed to analyze %s", ticker, exc_info=True)
            return None

    # ----- universe scan ----------------------------------------------------

    def scan(
        self,
        min_score: int = 20,
        max_workers: int = 8,
    ) -> List[Dict[str, Any]]:
        """
        Scan the full crypto universe and return results sorted by score
        (descending), filtered to *min_score*.
        """
        btc_df = self._fetch_btc_data()
        self.altcoin_season = self._detect_altcoin_season(btc_df)

        results: List[Dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._analyze_crypto, t, btc_df): t
                for t in self.universe
            }
            for future in as_completed(futures):
                ticker = futures[future]
                try:
                    result = future.result()
                    if result and result["score"] >= min_score:
                        results.append(result)
                except Exception:
                    logger.warning("Error scanning %s", ticker, exc_info=True)

        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    # ----- weight management ------------------------------------------------

    def get_weights(self) -> Dict[str, int]:
        return self.weights.copy()

    def update_weights(self, updates: Dict[str, int]) -> None:
        self.weights.update(updates)
        save_weights(WEIGHTS_FILE, self.weights)
