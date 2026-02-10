"""
Market regime detection -- classifies the current macro environment to
adjust position sizing and signal thresholds.

Ported from Destroyer regime analysis.
"""
import logging
from typing import Dict, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("apredator.features.regime")

# ---------------------------------------------------------------------------
# Regime states
# ---------------------------------------------------------------------------
REGIME_STATES = [
    "BULL_LOW_VOL",
    "BULL_HIGH_VOL",
    "BEAR_LOW_VOL",
    "BEAR_HIGH_VOL",
    "SIDEWAYS_LOW_VOL",
    "SIDEWAYS_HIGH_VOL",
    "CRISIS",
    "EUPHORIA",
]


# ---------------------------------------------------------------------------
# Regime detection
# ---------------------------------------------------------------------------

def detect_regime(
    spy_data: Optional[pd.DataFrame] = None,
) -> Dict[str, object]:
    """Classify the current market regime from SPY price data.

    Parameters
    ----------
    spy_data : pd.DataFrame, optional
        SPY OHLCV dataframe with at least 252 rows and a ``close`` column.
        If *None*, data is fetched via yfinance.

    Returns
    -------
    dict
        ``regime_state`` -- one of :data:`REGIME_STATES`
        ``regime_confidence`` -- float in [0, 1]
        ``details`` -- dict of intermediate indicators
    """
    try:
        if spy_data is None:
            spy_data = _fetch_spy_data()

        if spy_data is None or len(spy_data) < 50:
            logger.warning("Insufficient SPY data for regime detection")
            return {
                "regime_state": "BULL_LOW_VOL",
                "regime_confidence": 0.3,
                "details": {},
            }

        close = spy_data["close"]
        returns = close.pct_change().dropna()

        # --- Indicators ---
        # SMA-200 trend
        sma200 = close.rolling(200).mean() if len(close) >= 200 else close.rolling(50).mean()
        bullish = bool(close.iloc[-1] > sma200.iloc[-1])

        # 20-day momentum
        if len(close) >= 21:
            returns_20d = float(close.iloc[-1] / close.iloc[-21] - 1)
        else:
            returns_20d = 0.0
        momentum_positive = returns_20d > 0

        # 20-day realised vol (annualised)
        vol_20d = float(returns.iloc[-20:].std() * np.sqrt(252)) if len(returns) >= 20 else 0.15
        high_vol = vol_20d > 0.25

        # Crisis thresholds
        crisis = vol_20d > 0.40 and returns_20d < -0.20

        # RSI for euphoria check
        rsi = _compute_rsi(close, period=14)
        euphoria = vol_20d < 0.12 and rsi > 80

        # --- Classification ---
        if crisis:
            regime_state = "CRISIS"
            confidence = 0.9
        elif euphoria:
            regime_state = "EUPHORIA"
            confidence = 0.8
        elif bullish and not high_vol:
            regime_state = "BULL_LOW_VOL"
            confidence = 0.8 if momentum_positive else 0.5
        elif bullish and high_vol:
            regime_state = "BULL_HIGH_VOL"
            confidence = 0.7 if momentum_positive else 0.5
        elif not bullish and high_vol:
            regime_state = "BEAR_HIGH_VOL"
            confidence = 0.8 if not momentum_positive else 0.5
        elif not bullish and not high_vol:
            regime_state = "BEAR_LOW_VOL"
            confidence = 0.7 if not momentum_positive else 0.5
        else:
            # Sideways: close near SMA200, moderate vol
            if high_vol:
                regime_state = "SIDEWAYS_HIGH_VOL"
            else:
                regime_state = "SIDEWAYS_LOW_VOL"
            confidence = 0.5

        # Borderline cases reduce confidence
        sma_distance = abs(close.iloc[-1] - sma200.iloc[-1]) / close.iloc[-1]
        if sma_distance < 0.02:
            confidence = min(confidence, 0.5)

        details = {
            "sma200": float(sma200.iloc[-1]),
            "close": float(close.iloc[-1]),
            "bullish": bullish,
            "returns_20d": round(returns_20d, 4),
            "vol_20d": round(vol_20d, 4),
            "rsi_14": round(rsi, 2),
            "high_vol": high_vol,
        }

        logger.info(
            "Regime detected: %s (confidence=%.2f, vol_20d=%.3f, ret_20d=%.3f)",
            regime_state, confidence, vol_20d, returns_20d,
        )

        return {
            "regime_state": regime_state,
            "regime_confidence": round(confidence, 2),
            "details": details,
        }

    except Exception:
        logger.exception("Regime detection failed -- defaulting to BULL_LOW_VOL")
        return {
            "regime_state": "BULL_LOW_VOL",
            "regime_confidence": 0.3,
            "details": {},
        }


# ---------------------------------------------------------------------------
# Regime adjustments
# ---------------------------------------------------------------------------

def get_regime_adjustments(regime: str) -> Dict[str, float]:
    """Return position-sizing and threshold multipliers for the given regime.

    Parameters
    ----------
    regime : str
        One of :data:`REGIME_STATES`.

    Returns
    -------
    dict
        ``position_size_mult`` -- multiply base position size by this
        ``threshold_mult`` -- multiply score thresholds by this
    """
    adjustments = {
        "BULL_LOW_VOL":     {"position_size_mult": 1.0, "threshold_mult": 1.0},
        "BULL_HIGH_VOL":    {"position_size_mult": 0.8, "threshold_mult": 1.1},
        "BEAR_LOW_VOL":     {"position_size_mult": 0.7, "threshold_mult": 1.1},
        "BEAR_HIGH_VOL":    {"position_size_mult": 0.6, "threshold_mult": 1.2},
        "SIDEWAYS_LOW_VOL": {"position_size_mult": 0.8, "threshold_mult": 1.0},
        "SIDEWAYS_HIGH_VOL":{"position_size_mult": 0.6, "threshold_mult": 1.1},
        "CRISIS":           {"position_size_mult": 0.5, "threshold_mult": 1.3},
        "EUPHORIA":         {"position_size_mult": 0.7, "threshold_mult": 0.9},
    }

    result = adjustments.get(regime)
    if result is None:
        logger.warning("Unknown regime '%s' -- using neutral adjustments", regime)
        return {"position_size_mult": 1.0, "threshold_mult": 1.0}
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_spy_data() -> Optional[pd.DataFrame]:
    """Fetch SPY data via yfinance (last 252 trading days)."""
    try:
        import yfinance as yf
        ticker = yf.Ticker("SPY")
        df = ticker.history(period="1y", interval="1d")
        if df.empty:
            return None
        df.columns = [c.lower() for c in df.columns]
        return df
    except ImportError:
        logger.error("yfinance not installed -- cannot fetch SPY data for regime detection")
        return None
    except Exception:
        logger.exception("Failed to fetch SPY data")
        return None


def _compute_rsi(close: pd.Series, period: int = 14) -> float:
    """Quick RSI computation for regime detection."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    value = rsi.iloc[-1]
    return float(value) if not np.isnan(value) else 50.0
