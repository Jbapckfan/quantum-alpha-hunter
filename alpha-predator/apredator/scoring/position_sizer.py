"""
Position sizing via the Kelly criterion and tier-based allocation.

Core formula from Hedge Fund ml_scoring_engine.py.  Uses quarter-Kelly by
default to reduce variance while preserving the favourable edge.
"""
import logging
from typing import Dict, Optional

from ..features.regime import get_regime_adjustments

logger = logging.getLogger("apredator.scoring.position_sizer")

# ---------------------------------------------------------------------------
# Tier parameters: (win_rate, avg_win_pct, avg_loss_pct)
# ---------------------------------------------------------------------------
TIER_PARAMS: Dict[int, tuple] = {
    1: (0.45, 1.20, 0.20),
    2: (0.38, 1.05, 0.20),
    3: (0.32, 0.95, 0.20),
    4: (0.25, 0.85, 0.20),
}


# ---------------------------------------------------------------------------
# Kelly criterion
# ---------------------------------------------------------------------------

def kelly_position_size(
    probability: float,
    expected_win: float = 0.40,
    expected_loss: float = 0.15,
    fraction: float = 0.25,
    min_pct: float = 0.02,
    max_pct: float = 0.15,
) -> float:
    """Compute the Kelly-optimal position size (as fraction of capital).

    Parameters
    ----------
    probability : float
        Estimated probability of a winning trade (0-1).
    expected_win : float
        Expected gain on a win (e.g. 0.40 = 40%).
    expected_loss : float
        Expected loss on a loss (e.g. 0.15 = 15%).
    fraction : float
        Kelly fraction (0.25 = quarter-Kelly).
    min_pct : float
        Minimum position size; returns 0.0 if below this.
    max_pct : float
        Maximum position size cap.

    Returns
    -------
    float
        Position size as a fraction of capital, clamped to ``[min_pct, max_pct]``
        or 0.0 if the raw Kelly is below ``min_pct``.
    """
    if expected_loss <= 0:
        logger.warning("expected_loss must be > 0, returning 0.0")
        return 0.0

    if probability <= 0 or probability >= 1:
        logger.debug("Probability %.4f out of (0,1), returning 0.0", probability)
        return 0.0

    # b = win/loss ratio (= 2.67 with defaults)
    b = expected_win / expected_loss

    # Full Kelly fraction: f* = (b*p - q) / b
    q = 1.0 - probability
    f_star = (b * probability - q) / b

    # Fractional Kelly (quarter by default)
    quarter_kelly = f_star * fraction

    # Clamp
    if quarter_kelly < min_pct:
        return 0.0

    position = min(quarter_kelly, max_pct)

    logger.debug(
        "Kelly: p=%.3f b=%.2f f*=%.4f quarter=%.4f -> size=%.4f",
        probability,
        b,
        f_star,
        quarter_kelly,
        position,
    )
    return position


# ---------------------------------------------------------------------------
# Tier-based sizing
# ---------------------------------------------------------------------------

def size_by_tier(
    tier: int,
    capital: float,
    base_config: Optional[Dict] = None,
) -> float:
    """Compute position size in dollars based on the conviction tier.

    Parameters
    ----------
    tier : int
        Conviction tier (1-4).
    capital : float
        Total available capital in USD.
    base_config : dict or None
        Optional overrides.  Keys can include ``fraction``, ``min_pct``,
        ``max_pct``.

    Returns
    -------
    float
        Dollar amount to allocate for this position.
    """
    if tier not in TIER_PARAMS:
        logger.warning("Unknown tier %s, defaulting to tier 4", tier)
        tier = 4

    win_rate, avg_win_pct, avg_loss_pct = TIER_PARAMS[tier]

    kwargs = {
        "probability": win_rate,
        "expected_win": avg_win_pct,
        "expected_loss": avg_loss_pct,
    }
    if base_config:
        if "fraction" in base_config:
            kwargs["fraction"] = base_config["fraction"]
        if "min_pct" in base_config:
            kwargs["min_pct"] = base_config["min_pct"]
        if "max_pct" in base_config:
            kwargs["max_pct"] = base_config["max_pct"]

    pct = kelly_position_size(**kwargs)
    dollar_amount = pct * capital

    logger.info(
        "Tier %d sizing: kelly_pct=%.4f * capital=$%.0f = $%.2f",
        tier,
        pct,
        capital,
        dollar_amount,
    )
    return dollar_amount


# ---------------------------------------------------------------------------
# Regime-adjusted sizing
# ---------------------------------------------------------------------------

def apply_regime_sizing(
    base_size: float,
    regime_state: str,
) -> float:
    """Adjust a base position size by the current market regime multiplier.

    Parameters
    ----------
    base_size : float
        Base dollar position size (from :func:`size_by_tier` or manual).
    regime_state : str
        Current regime label (e.g. ``"RISK_ON"``, ``"RISK_OFF"``).

    Returns
    -------
    float
        Adjusted dollar position size.
    """
    adjustments = get_regime_adjustments(regime_state)
    mult = adjustments.get("position_size_mult", 1.0)
    adjusted = base_size * mult

    logger.debug(
        "Regime sizing (%s): $%.2f * %.2f = $%.2f",
        regime_state,
        base_size,
        mult,
        adjusted,
    )
    return adjusted
