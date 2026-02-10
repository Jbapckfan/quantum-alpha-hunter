"""
Institutional signal detection -- gamma squeeze, short squeeze, order flow,
and smart money indicators.

Ported from Destroyer institutional analysis modules.
"""
import logging
from typing import Dict, Optional

import numpy as np
import pandas as pd

from ..adapters.yahoo import fetch_options_chain, fetch_fundamentals

logger = logging.getLogger("apredator.features.institutional")


# ---------------------------------------------------------------------------
# Gamma Squeeze Detection
# ---------------------------------------------------------------------------

class GammaSqueezeDetector:
    """Detect gamma-squeeze probability from options-chain data."""

    def detect(
        self,
        symbol: str,
        options_df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, float]:
        """Analyse options chain for gamma-squeeze setup.

        Parameters
        ----------
        symbol : str
            Ticker symbol.
        options_df : pd.DataFrame, optional
            Pre-fetched options chain.  If *None*, fetched via the Yahoo
            adapter.  Expected columns: ``option_type``, ``oi``, ``volume``,
            ``strike``.

        Returns
        -------
        dict
            ``probability`` -- estimated gamma-squeeze probability [0, 1]
            ``expected_move`` -- estimated percentage move if squeeze fires
            ``call_oi_ratio`` -- call OI / total OI
        """
        try:
            if options_df is None:
                options_df = fetch_options_chain(symbol)
            if options_df is None or options_df.empty:
                return {"probability": 0.0, "expected_move": 0.0, "call_oi_ratio": 0.0}

            # Separate calls and puts
            calls = options_df[options_df["option_type"].str.lower() == "call"]
            puts = options_df[options_df["option_type"].str.lower() == "put"]

            call_oi = calls["oi"].sum()
            put_oi = puts["oi"].sum()
            total_oi = call_oi + put_oi

            if total_oi == 0:
                return {"probability": 0.0, "expected_move": 0.0, "call_oi_ratio": 0.0}

            call_oi_ratio = call_oi / total_oi

            # Volume surge: compare recent volume to OI
            call_volume = calls["volume"].sum() if "volume" in calls.columns else 0
            put_volume = puts["volume"].sum() if "volume" in puts.columns else 0
            total_volume = call_volume + put_volume
            volume_surge = total_volume / total_oi if total_oi > 0 else 0.0

            # ATM concentration: near-strike OI vs total OI
            # (simplified -- we do not have current price here so use median
            # strike as proxy)
            if "strike" in options_df.columns and len(options_df) > 0:
                median_strike = options_df["strike"].median()
                near_mask = (options_df["strike"] - median_strike).abs() / median_strike < 0.05
                atm_oi = options_df.loc[near_mask, "oi"].sum()
                atm_ratio = atm_oi / total_oi if total_oi > 0 else 0.0
            else:
                atm_ratio = 0.0

            # Gamma-squeeze probability
            if call_oi_ratio > 0.7 and volume_surge > 1.5:
                volume_factor = min(volume_surge / 3.0, 1.0)
                probability = call_oi_ratio * 0.6 + volume_factor * 0.4
                probability = min(probability, 1.0)
            else:
                probability = call_oi_ratio * 0.3 * min(volume_surge, 1.0)
                probability = min(probability, 0.3)

            # Rough expected move based on concentration and OI skew
            expected_move = probability * 15.0 * (1 + atm_ratio)

            return {
                "probability": round(probability, 4),
                "expected_move": round(expected_move, 2),
                "call_oi_ratio": round(call_oi_ratio, 4),
            }

        except Exception:
            logger.exception("Gamma squeeze detection failed for %s", symbol)
            return {"probability": 0.0, "expected_move": 0.0, "call_oi_ratio": 0.0}


# ---------------------------------------------------------------------------
# Short Squeeze Detection
# ---------------------------------------------------------------------------

class ShortSqueezeDetector:
    """Detect short-squeeze probability from fundamental/short data."""

    def detect(
        self,
        symbol: str,
        fundamentals: Optional[Dict] = None,
    ) -> Dict[str, float]:
        """Estimate short-squeeze probability.

        Parameters
        ----------
        symbol : str
            Ticker symbol.
        fundamentals : dict, optional
            Pre-fetched fundamentals dict.  Expected keys:
            ``short_pct_float``, ``days_to_cover``, ``recent_price_change``.

        Returns
        -------
        dict
            ``probability`` -- estimated squeeze probability [0, 1]
            ``short_pct_float`` -- short interest as % of float
            ``days_to_cover`` -- estimated days to cover
        """
        try:
            if fundamentals is None:
                fundamentals = fetch_fundamentals(symbol)
            if fundamentals is None:
                return {"probability": 0.0, "short_pct_float": 0.0, "days_to_cover": 0.0}

            short_pct = float(fundamentals.get("short_pct_float", 0) or 0)
            dtc = float(fundamentals.get("days_to_cover", 0) or 0)
            price_change = float(fundamentals.get("recent_price_change", 0) or 0)

            if short_pct > 15 and dtc > 3 and price_change > 5:
                short_squeeze_prob = min(
                    (short_pct / 30) * 0.5
                    + (dtc / 10) * 0.3
                    + (price_change / 20) * 0.2,
                    1.0,
                )
            elif short_pct > 10:
                # Moderate setup
                short_squeeze_prob = min(
                    (short_pct / 30) * 0.3 + (dtc / 10) * 0.2,
                    0.4,
                )
            else:
                short_squeeze_prob = 0.0

            return {
                "probability": round(short_squeeze_prob, 4),
                "short_pct_float": round(short_pct, 2),
                "days_to_cover": round(dtc, 2),
            }

        except Exception:
            logger.exception("Short squeeze detection failed for %s", symbol)
            return {"probability": 0.0, "short_pct_float": 0.0, "days_to_cover": 0.0}


# ---------------------------------------------------------------------------
# VWAP helper
# ---------------------------------------------------------------------------

def _compute_vwap(df: pd.DataFrame) -> pd.Series:
    """Compute intraday-style cumulative VWAP.

    typical_price = (high + low + close) / 3
    VWAP = cumulative(volume * typical_price) / cumulative(volume)
    """
    typical = (df["high"] + df["low"] + df["close"]) / 3
    cum_vol = df["volume"].cumsum()
    cum_vp = (typical * df["volume"]).cumsum()
    vwap = cum_vp / cum_vol.replace(0, np.nan)
    return vwap


# ---------------------------------------------------------------------------
# Order Flow Score
# ---------------------------------------------------------------------------

def compute_order_flow(df: pd.DataFrame) -> Dict[str, float]:
    """Compute a composite order-flow score (0-100).

    Components
    ----------
    - VWAP bias: (close - vwap) / close * 100   (weight 0.3)
    - Buy pressure: up_volume / total_volume     (weight 0.3)
    - Volume directional: signed-volume trend    (weight 0.2)
    - Large-bar direction: direction of largest volume bar (weight 0.2)

    Returns
    -------
    dict
        ``order_flow_score`` -- composite score normalised to [0, 100]
    """
    try:
        close = df["close"]
        volume = df["volume"]

        # 1. VWAP bias (use recent window)
        vwap = _compute_vwap(df)
        last_close = close.iloc[-1]
        last_vwap = vwap.iloc[-1]
        if last_close != 0 and not np.isnan(last_vwap):
            vwap_bias = (last_close - last_vwap) / last_close * 100
        else:
            vwap_bias = 0.0
        # Normalise to 0-100 range (clip at +/-5%)
        vwap_component = (np.clip(vwap_bias, -5, 5) + 5) / 10 * 100

        # 2. Buy pressure: fraction of volume on up-closes
        price_change = close.diff()
        up_vol = volume[price_change > 0].iloc[-20:].sum()
        total_vol = volume.iloc[-20:].sum()
        buy_pressure = (up_vol / total_vol * 100) if total_vol > 0 else 50.0

        # 3. Signed-volume trend
        signed_vol = np.sign(price_change) * volume
        sv_tail = signed_vol.iloc[-10:].dropna()
        if len(sv_tail) >= 5:
            x = np.arange(len(sv_tail), dtype=float)
            y = sv_tail.values.astype(float)
            y_mean = np.mean(np.abs(y))
            y_norm = y / y_mean if y_mean != 0 else y
            slope = np.polyfit(x, y_norm, 1)[0]
            vol_directional = (np.clip(slope, -1, 1) + 1) / 2 * 100
        else:
            vol_directional = 50.0

        # 4. Largest volume bar direction
        recent = df.iloc[-20:]
        if len(recent) > 0:
            max_vol_idx = recent["volume"].idxmax()
            max_bar_change = recent.loc[max_vol_idx, "close"] - recent.loc[max_vol_idx, "open"]
            large_bar_dir = 100.0 if max_bar_change > 0 else (0.0 if max_bar_change < 0 else 50.0)
        else:
            large_bar_dir = 50.0

        # Weighted score
        score = (
            vwap_component * 0.3
            + buy_pressure * 0.3
            + vol_directional * 0.2
            + large_bar_dir * 0.2
        )
        score = float(np.clip(score, 0, 100))

        return {"order_flow_score": round(score, 2)}

    except Exception:
        logger.exception("Order flow computation failed")
        return {"order_flow_score": 50.0}


# ---------------------------------------------------------------------------
# Smart Money Score
# ---------------------------------------------------------------------------

def compute_smart_money(df: pd.DataFrame) -> Dict[str, float]:
    """Detect smart-money accumulation patterns.

    Pattern: volume increasing while price range contracts (accumulation).
    Volume up + range down = institutional buying before a move.

    Returns
    -------
    dict
        ``smart_money_score`` -- composite score [0, 100]
    """
    try:
        close = df["close"]
        volume = df["volume"]
        high = df["high"]
        low = df["low"]

        if len(df) < 20:
            return {"smart_money_score": 50.0}

        # Volume trend (is volume increasing?)
        vol_recent = volume.iloc[-5:].mean()
        vol_prior = volume.iloc[-20:-5].mean()
        vol_expansion = vol_recent / vol_prior if vol_prior > 0 else 1.0

        # Range contraction (is daily range decreasing?)
        daily_range = (high - low) / close
        range_recent = daily_range.iloc[-5:].mean()
        range_prior = daily_range.iloc[-20:-5].mean()
        range_contraction = range_prior / range_recent if range_recent > 0 else 1.0

        # Price stability (small close-to-close changes)
        returns_abs = close.pct_change().abs()
        stability_recent = returns_abs.iloc[-5:].mean()
        stability_prior = returns_abs.iloc[-20:-5].mean()
        stability_ratio = stability_prior / stability_recent if stability_recent > 0 else 1.0

        # Close position in range (accumulation = closes near highs)
        close_pos = ((close - low) / (high - low).replace(0, np.nan)).dropna()
        avg_close_pos = close_pos.iloc[-5:].mean() if len(close_pos) >= 5 else 0.5

        # Composite score
        # Volume expansion + range contraction + stability + close position
        raw_score = (
            min(vol_expansion, 3.0) / 3.0 * 25
            + min(range_contraction, 3.0) / 3.0 * 25
            + min(stability_ratio, 3.0) / 3.0 * 25
            + avg_close_pos * 25
        )
        score = float(np.clip(raw_score, 0, 100))

        return {"smart_money_score": round(score, 2)}

    except Exception:
        logger.exception("Smart money computation failed")
        return {"smart_money_score": 50.0}
