"""
Tier classification and multi-factor setup scoring from Hedge Fund complete_system.py.

Each candidate receives a numeric setup score from :func:`compute_setup_score` and
is then classified into one of four conviction tiers by :func:`classify_tier`.
Tier hit rates and average gains are historically validated -- do not change.
"""
import logging
from typing import Dict, Optional

logger = logging.getLogger("apredator.scoring.tier_system")

# ---------------------------------------------------------------------------
# Tier definitions -- historically validated, do NOT change hit/gain values
# ---------------------------------------------------------------------------
TIER_DEFINITIONS = {
    1: {"hit_rate": 0.917, "avg_gain": 0.93, "conviction": "EXTREME"},
    2: {"hit_rate": 0.783, "avg_gain": 0.82, "conviction": "HIGH"},
    3: {"hit_rate": 0.677, "avg_gain": 0.60, "conviction": "MODERATE"},
    4: {"hit_rate": 0.606, "avg_gain": 0.65, "conviction": "LOW"},
}


# ---------------------------------------------------------------------------
# Multi-factor scoring
# ---------------------------------------------------------------------------

def compute_setup_score(metrics: Dict[str, float]) -> Optional[int]:
    """Compute the multi-factor setup score for a candidate.

    Parameters
    ----------
    metrics : dict
        Required keys:

        * ``atr_pct`` -- Average True Range as pct of price
        * ``price`` -- Current price
        * ``dd_120d`` -- Max drawdown over 120 days (pct, e.g. 45 means 45%)
        * ``vol_ratio`` -- Volume ratio vs 20-day average
        * ``atr_expansion`` -- ATR expansion pct (e.g. 60 means 60%)
        * ``ret_5d`` -- 5-day return (pct)
        * ``ret_20d`` -- 20-day return (pct)
        * ``rsi`` -- RSI-14 value
        * ``market_cap`` -- Market capitalisation in USD

    Returns
    -------
    int or None
        The setup score, or ``None`` if the candidate is filtered out
        (ATR% < 6 or price > $50).
    """
    atr_pct = metrics.get("atr_pct", 0)
    price = metrics.get("price", metrics.get("close", 0))
    dd_120d = metrics.get("dd_120d", 0)
    vol_ratio = metrics.get("vol_ratio", metrics.get("volume_ratio_20d", 0))
    atr_expansion = metrics.get("atr_expansion", 0)
    ret_5d = metrics.get("ret_5d", 0)
    ret_20d = metrics.get("ret_20d", metrics.get("momentum_10d", 0))
    rsi = metrics.get("rsi", metrics.get("rsi_14", 50))
    market_cap = metrics.get("market_cap", 0)

    score = 0

    # --- ATR% gating (hard filter) ---
    if atr_pct >= 15:
        score += 20
    elif atr_pct >= 10:
        score += 16
    elif atr_pct >= 8:
        score += 12
    elif atr_pct >= 6:
        score += 6
    else:
        logger.debug("Filtered out: ATR%% %.2f < 6", atr_pct)
        return None

    # --- Price gating (hard filter) ---
    if price <= 5:
        score += 15
    elif price <= 10:
        score += 12
    elif price <= 20:
        score += 8
    elif price <= 50:
        score += 3
    else:
        logger.debug("Filtered out: price $%.2f > $50", price)
        return None

    # --- Drawdown 120d ---
    if 20 <= dd_120d < 40:
        score += 12
    elif 40 <= dd_120d < 60:
        score += 8
    elif dd_120d >= 60:
        score += 4

    # --- Volume ratio ---
    if vol_ratio >= 3.0:
        score += 8

    # --- ATR expansion ---
    if atr_expansion >= 50:
        score += 6

    # --- Momentum alignment ---
    if ret_5d >= 10 and ret_20d <= 0:
        score += 6

    # --- RSI setup ---
    if 30 <= rsi <= 50:
        score += 4

    # --- Market cap ---
    if 0 < market_cap < 500_000_000:
        score += 4

    logger.debug("Setup score = %d", score)
    return score


# ---------------------------------------------------------------------------
# Tier classification
# ---------------------------------------------------------------------------

def classify_tier(
    score_or_dict,
    dd_60d: float = 0.0,
    rsi: float = 50.0,
    vol_20d: float = 10.0,
    dd_20d: float = 0.0,
    price: float = 10.0,
) -> Dict:
    """Classify a scored candidate into a conviction tier.

    Can be called in two ways:

    1. **Dict form** (preferred from pipeline): ``classify_tier(feat_dict)``
       where ``feat_dict`` contains keys like ``drawdown_60d``, ``rsi_14``,
       ``volatility_20d``, ``close``.

    2. **Explicit form**: ``classify_tier(score, dd_60d, rsi, vol_20d, dd_20d, price)``

    Returns
    -------
    dict
        ``{"tier": int, "hit_rate": float, "avg_gain": float, "conviction": str}``
    """
    # --- Unpack from dict if first arg is a dict ---
    if isinstance(score_or_dict, dict):
        fd = score_or_dict
        # Compute the setup score if not already present
        score = fd.get("setup_score")
        if score is None:
            score = compute_setup_score(fd)
        if score is None:
            return {"tier": None, "hit_rate": 0.0, "avg_gain": 0.0, "conviction": "NONE"}
        dd_60d = fd.get("drawdown_60d", 0.0)
        rsi = fd.get("rsi_14", 50.0)
        vol_20d = fd.get("volatility_20d", 10.0)
        dd_20d = fd.get("drawdown_20d", fd.get("dd_20d", 0.0))
        price = fd.get("close", fd.get("price", 10.0))
    else:
        score = score_or_dict
    # Tier 1: score>=13 AND dd60>=55% AND rsi<=35
    #   EXCLUDE vol_20d<=4% OR dd20>=50%
    if score >= 13 and dd_60d >= 55 and rsi <= 35:
        if vol_20d > 4 and dd_20d < 50:
            tier = 1
            logger.info(
                "Tier 1 classification: score=%d dd60=%.1f rsi=%.1f", score, dd_60d, rsi
            )
            return _tier_result(tier)

    # Tier 2: EXCLUDE vol_20d<=4% OR dd20>=55%
    if vol_20d > 4 and dd_20d < 55:
        tier = 2
        return _tier_result(tier)

    # Tier 3: EXCLUDE vol_20d<=4% OR price>=$50
    if vol_20d > 4 and price < 50:
        tier = 3
        return _tier_result(tier)

    # Tier 4: EXCLUDE vol_20d<=4% only
    if vol_20d > 4:
        tier = 4
        return _tier_result(tier)

    # Filtered out by all tiers (vol_20d too low)
    logger.debug("No tier assigned: vol_20d=%.2f too low", vol_20d)
    return {
        "tier": None,
        "hit_rate": 0.0,
        "avg_gain": 0.0,
        "conviction": "NONE",
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _tier_result(tier: int) -> Dict:
    """Build a tier result dict from the tier number."""
    defn = TIER_DEFINITIONS[tier]
    return {
        "tier": tier,
        "hit_rate": defn["hit_rate"],
        "avg_gain": defn["avg_gain"],
        "conviction": defn["conviction"],
    }
