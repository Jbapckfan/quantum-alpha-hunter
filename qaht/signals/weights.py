"""
Signal weight definitions for the Quantum Alpha Hunter scoring system.

Ported from RZLV Pattern Scanner. Each signal has a weight (positive or
negative) that contributes to an overall conviction score. Weights can be
tuned over time as the system learns what works best.

Stock signals cover ~45+ conditions across washout, base, volume, momentum,
MA, RSI, MACD, volatility, support/resistance, relative strength, stage,
analyst/fundamental, exceptional, risk/reward, and quality categories.

Crypto signals cover ~30+ conditions with crypto-specific patterns (BTC
comparison, altcoin season, whale volume, etc.).

Confluence multipliers reward setups where multiple *independent* signal
categories fire simultaneously.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger("qaht.signals.weights")

# ---------------------------------------------------------------------------
# Stock signal weights
# ---------------------------------------------------------------------------

STOCK_WEIGHTS: Dict[str, int] = {
    # === WASHOUT / BOTTOM FORMATION (max ~25 pts) ===
    "deep_washout_70": 8,               # Dropped 70%+ from highs
    "major_washout_60": 6,              # Dropped 60%+ from highs
    "washout_50": 4,                    # Dropped 50%+ from highs
    "washout_40": 2,                    # Dropped 40%+ from highs

    # === BASE FORMATION (max ~15 pts) ===
    "tight_base_20": 8,                 # Base range < 20%
    "tight_base_30": 6,                 # Base range < 30%
    "base_40": 4,                       # Base range < 40%
    "base_50": 2,                       # Base range < 50%

    # === VOLUME SIGNALS (max ~20 pts) ===
    "volume_dryup": 6,                  # Volume contracted (selling exhaustion)
    "volume_surge_3x": 8,              # Recent volume 3x+ above base
    "volume_surge_2x": 5,              # Recent volume 2x+ above base
    "volume_expansion": 3,             # Recent volume 1.5x+ above base
    "accumulation_days": 5,            # More up-volume days than down-volume

    # === MOMENTUM / PRICE ACTION (max ~25 pts) ===
    "big_day_15": 8,                    # Single day gain of 15%+
    "big_day_10": 5,                    # Single day gain of 10%+
    "momentum_day": 3,                 # Single day gain of 5%+
    "first_higher_low": 6,            # Price made a higher low (reversal)
    "first_higher_high": 6,           # Price made a higher high (trend change)
    "breakout_attempt": 4,            # Testing/breaking recent resistance

    # === MOVING AVERAGE SIGNALS (max ~20 pts) ===
    "ema_stack_bullish": 8,            # 5 > 10 > 20 EMA alignment
    "above_ema20": 4,                  # Price above 20 EMA
    "above_ema50": 3,                  # Price above 50 EMA
    "ema_reclaim_sequence": 5,         # Recently reclaimed EMAs in order
    "golden_cross_near": 4,            # 20 EMA approaching 50 EMA from below

    # === RSI SIGNALS (max ~15 pts) ===
    "rsi_thrust": 6,                    # RSI moved from <40 to >50 recently
    "rsi_bullish_divergence": 8,       # Price lower low, RSI higher low
    "rsi_recovering": 3,               # RSI > 50 and rising
    "rsi_oversold_bounce": 4,          # RSI bounced from <30

    # === MACD SIGNALS (max ~15 pts) ===
    "macd_bullish_cross": 6,           # MACD crossed above signal recently
    "macd_bullish": 3,                 # MACD above signal line
    "macd_bullish_divergence": 8,      # Price lower low, MACD higher low
    "macd_histogram_rising": 4,        # Histogram bars increasing

    # === VOLATILITY SIGNALS (max ~10 pts) ===
    "bollinger_squeeze": 5,            # Bollinger bands contracted (coiling)
    "atr_contracting": 3,             # ATR decreasing (stabilizing)
    "range_contraction": 4,           # Daily ranges getting tighter

    # === SUPPORT/RESISTANCE (max ~10 pts) ===
    "multiple_support_tests": 5,       # Tested support 2+ times without breaking
    "holding_above_support": 4,        # Maintaining above key support level
    "near_breakout_level": 3,          # Within 5% of resistance breakout

    # === RELATIVE STRENGTH (max ~10 pts) ===
    "outperforming_spy_5d": 4,         # Beating SPY over 5 days
    "outperforming_spy_20d": 5,        # Beating SPY over 20 days
    "sector_leader": 3,                # Outperforming sector

    # === STAGE BONUSES / PENALTIES ===
    "early_stage_bonus": 5,            # Rally < 50% from low (early entry)
    "mid_stage_bonus": 2,              # Rally 50-100% from low
    "extended_penalty": -10,           # Rally > 200% (too extended)

    # === ANALYST / FUNDAMENTAL (max ~10 pts) ===
    "analyst_buy": 3,                  # Analyst consensus is buy
    "high_upside_target": 4,           # >50% upside to mean target
    "recent_upgrade": 4,               # Upgraded in last 30 days

    # === EXCEPTIONAL SIGNALS (rare, high-conviction) ===
    "short_squeeze_setup": 12,         # High short interest + price rising + volume
    "earnings_beast": 10,              # Exceptional earnings + revenue growth
    "institutional_accumulation": 8,   # High institutional ownership + rising
    "relative_strength_leader": 10,    # Beating S&P by 2x+ over 52 weeks
    "consecutive_green_5": 7,          # 5+ green days after washout
    "gap_up_volume": 8,                # Gap up 5%+ on 2x+ volume
    "vcp_pattern": 10,                 # Volatility Contraction Pattern
    "power_earnings_gap": 12,          # Gap up on earnings with volume
    "pocket_pivot": 12,                # Up day vol > any prior down day vol
    "shakeout_rally": 10,              # False breakdown followed by recovery

    # === RISK / REWARD ADJUSTMENTS ===
    "rr_excellent": 10,                # R:R > 5:1
    "rr_good": 5,                      # R:R > 3:1
    "rr_poor": -8,                     # R:R < 2:1

    # === QUALITY FILTERS (penalties) ===
    "low_volume_penalty": -5,          # Average volume too low
    "penny_stock_penalty": -3,         # Price under $1
}

# ---------------------------------------------------------------------------
# Crypto signal weights
# ---------------------------------------------------------------------------

CRYPTO_WEIGHTS: Dict[str, int] = {
    # === TREND SIGNALS ===
    "strong_uptrend": 8,               # Price making higher highs and higher lows
    "trend_reversal": 10,              # Potential bottom reversal
    "golden_cross": 8,                 # 50 EMA crosses above 200 EMA
    "death_cross_recovery": 6,         # Recovering after death cross

    # === VOLUME SIGNALS ===
    "volume_spike_5x": 10,            # 5x average volume
    "volume_spike_3x": 7,             # 3x average volume
    "volume_spike_2x": 4,             # 2x average volume
    "volume_breakout": 8,             # Volume breakout with price move
    "accumulation_volume": 6,         # High volume on up days, low on down
    "volume_dryup_reversal": 7,       # Volume dries up then spikes

    # === PRICE ACTION ===
    "breakout_resistance": 8,          # Breaking above key resistance
    "support_bounce": 6,               # Bouncing off support level
    "higher_low": 5,                   # Making higher low
    "higher_high": 5,                  # Making higher high
    "range_breakout": 7,               # Breaking out of consolidation range
    "pullback_to_ema": 5,             # Healthy pullback to moving average

    # === MOMENTUM ===
    "crypto_rsi_oversold_bounce": 7,   # RSI bouncing from oversold
    "crypto_rsi_bullish_divergence": 9,  # Price lower low, RSI higher low
    "crypto_macd_bullish_cross": 6,    # MACD line crosses above signal
    "macd_histogram_flip": 5,          # Histogram turns positive
    "momentum_surge": 6,               # Strong momentum increase

    # === MOVING AVERAGES ===
    "above_all_emas": 7,               # Above 20, 50, 200 EMAs
    "crypto_ema_stack_bullish": 6,     # 20 > 50 > 200 EMA
    "reclaim_ema20": 4,                # Price reclaims 20 EMA
    "reclaim_ema50": 5,                # Price reclaims 50 EMA
    "reclaim_ema200": 6,               # Price reclaims 200 EMA

    # === VOLATILITY ===
    "crypto_bollinger_squeeze": 5,     # Volatility contraction
    "bollinger_breakout_up": 7,        # Breaking above upper band
    "atr_expansion": 4,                # Volatility increasing (potential move)

    # === RELATIVE STRENGTH ===
    "outperform_btc_7d": 5,            # Outperforming BTC over 7 days
    "outperform_btc_30d": 6,           # Outperforming BTC over 30 days
    "crypto_sector_leader": 4,         # Leading its sector

    # === DRAWDOWN / RECOVERY ===
    "major_washout_70": 8,             # Down 70%+ from ATH
    "crypto_washout_50": 5,            # Down 50%+ from ATH
    "recovery_from_low": 6,            # Up significantly from recent low

    # === EXCEPTIONAL SIGNALS (rare, high-conviction) ===
    "extreme_washout_recovery": 12,    # Down 80%+ from ATH, now recovering
    "btc_decoupling_bullish": 10,      # Outperforming BTC during BTC weakness
    "multi_day_breakout": 9,           # Breaking multi-week resistance on volume
    "sentiment_momentum": 8,           # Rapid sentiment improvement
    "sector_rotation_leader": 10,      # Leading a sector rotation
    "accumulation_phase_end": 11,      # Long accumulation ending with breakout
    "whale_volume_pattern": 9,         # Unusual large transaction pattern
    "consecutive_green_7": 8,          # 7+ consecutive green days
    "crypto_shakeout_rally": 10,       # False breakdown followed by recovery
    "altcoin_season_bonus": 5,         # Bonus during altcoin season

    # === PENALTIES ===
    "extreme_overbought": -5,          # RSI > 85
    "parabolic_move": -4,              # Unsustainable vertical move
    "low_liquidity": -6,               # Very low trading volume
    "death_cross": -3,                 # 50 EMA below 200 EMA
}

# ---------------------------------------------------------------------------
# Confluence categories -- used by the multiplier logic
# ---------------------------------------------------------------------------

STOCK_CONFLUENCE_CATEGORIES: Dict[str, List[str]] = {
    "washout": [
        "deep_washout_70", "major_washout_60", "washout_50", "washout_40",
    ],
    "volume": [
        "volume_dryup", "volume_surge_3x", "volume_surge_2x",
        "volume_expansion", "accumulation_days",
    ],
    "momentum": [
        "big_day_15", "big_day_10", "momentum_day",
        "first_higher_low", "first_higher_high", "breakout_attempt",
    ],
    "ma": [
        "ema_stack_bullish", "above_ema20", "above_ema50",
        "ema_reclaim_sequence", "golden_cross_near",
    ],
    "rsi": [
        "rsi_thrust", "rsi_bullish_divergence",
        "rsi_recovering", "rsi_oversold_bounce",
    ],
    "macd": [
        "macd_bullish_cross", "macd_bullish",
        "macd_bullish_divergence", "macd_histogram_rising",
    ],
}

CRYPTO_CONFLUENCE_CATEGORIES: Dict[str, List[str]] = {
    "trend": [
        "strong_uptrend", "trend_reversal",
        "golden_cross", "death_cross_recovery",
    ],
    "volume": [
        "volume_spike_5x", "volume_spike_3x", "volume_spike_2x",
        "volume_breakout", "accumulation_volume",
    ],
    "momentum": [
        "crypto_rsi_oversold_bounce", "crypto_rsi_bullish_divergence",
        "crypto_macd_bullish_cross", "momentum_surge",
    ],
    "ma": [
        "above_all_emas", "crypto_ema_stack_bullish",
        "reclaim_ema20", "reclaim_ema50", "reclaim_ema200",
    ],
    "price_action": [
        "breakout_resistance", "support_bounce",
        "higher_low", "higher_high", "range_breakout",
    ],
}


# ---------------------------------------------------------------------------
# Confluence multiplier helpers
# ---------------------------------------------------------------------------

def compute_stock_confluence(triggered: List[str]) -> float:
    """
    Return the confluence multiplier for a stock signal set.

    5+ independent categories firing = 1.5x
    4 categories = 1.3x
    Otherwise 1.0x
    """
    categories_hit = 0
    for cat_signals in STOCK_CONFLUENCE_CATEGORIES.values():
        if any(sig in triggered for sig in cat_signals):
            categories_hit += 1

    if categories_hit >= 5:
        return 1.5
    if categories_hit >= 4:
        return 1.3
    return 1.0


def compute_crypto_confluence(triggered: List[str]) -> float:
    """
    Return the confluence multiplier for a crypto signal set.

    4+ independent categories firing = 1.4x
    3 categories = 1.2x
    Otherwise 1.0x
    """
    categories_hit = 0
    for cat_signals in CRYPTO_CONFLUENCE_CATEGORIES.values():
        if any(sig in triggered for sig in cat_signals):
            categories_hit += 1

    if categories_hit >= 4:
        return 1.4
    if categories_hit >= 3:
        return 1.2
    return 1.0


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def load_weights(path: Path, defaults: Dict[str, int]) -> Dict[str, int]:
    """
    Load weights from a JSON file, merging with *defaults* so that newly
    added signals always have a weight even if the saved file is stale.
    """
    if path.exists():
        try:
            with open(path, "r") as fh:
                saved = json.load(fh)
            merged = defaults.copy()
            merged.update(saved)
            logger.info("Loaded signal weights from %s (%d entries)", path, len(merged))
            return merged
        except Exception:
            logger.warning("Failed to read weights from %s, using defaults", path, exc_info=True)
    return defaults.copy()


def save_weights(path: Path, weights: Dict[str, int]) -> None:
    """Persist weights to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        json.dump(weights, fh, indent=2)
    logger.info("Saved signal weights to %s", path)


def max_positive_score(weights: Dict[str, int]) -> int:
    """Return the sum of all positive weights (theoretical max score)."""
    return sum(v for v in weights.values() if v > 0)
