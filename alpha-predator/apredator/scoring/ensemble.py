"""
Ensemble scoring -- combines ML predictions, combo matches, tier classification,
and regime state into a single ensemble score with conviction.

Also provides :class:`AdaptiveLearner` for self-learning threshold and weight
adjustments based on rolling prediction accuracy.

Logic ported from Hedge Fund ml_scoring_engine.py.
"""
import logging
from collections import deque
from typing import Dict, List, Optional

import numpy as np

from ..config import get_config
from ..features.regime import get_regime_adjustments

logger = logging.getLogger("apredator.scoring.ensemble")


# ---------------------------------------------------------------------------
# Ensemble scoring
# ---------------------------------------------------------------------------

def combine_scores(
    feat_dict_or_ml_score,
    ml_prob: float = 0.0,
    combo_matches: Optional[List[dict]] = None,
    tier_info: Optional[Dict] = None,
    regime_state: Optional[str] = None,
) -> Dict:
    """Combine all scoring layers into a final ensemble score.

    Can be called in two ways:

    1. **Dict form** (preferred from pipeline): ``combine_scores(feat_dict)``
       where ``feat_dict`` contains keys like ``quantum_score``, ``prob_hit_10d``,
       ``combos``, ``tier``, ``regime_state``.

    2. **Explicit form**: ``combine_scores(ml_score, ml_prob, combo_matches, tier_info, regime_state)``

    Returns
    -------
    dict
        ``{"ensemble_score": int, "final_conviction": str,
          "confidence": float, "ensemble_prob": float,
          "best_combo": str or None, "tier": int or None}``
    """
    # --- Unpack from dict if first arg is a dict ---
    if isinstance(feat_dict_or_ml_score, dict):
        fd = feat_dict_or_ml_score
        ml_score = fd.get("quantum_score", fd.get("ensemble_score", 50))
        ml_prob = fd.get("prob_hit_10d", ml_score / 100.0)
        combo_matches = fd.get("combos", [])
        tier_info = {"tier": fd.get("tier"), "_trap_signals": fd.get("_trap_signals", {})}
        regime_state = fd.get("regime_state")
    else:
        ml_score = feat_dict_or_ml_score
        if combo_matches is None:
            combo_matches = []
        if tier_info is None:
            tier_info = {}

    # --- Step 1: Combo confirmation adjustment ---
    best_combo = None
    if combo_matches:
        best = max(combo_matches, key=lambda m: m["hit_rate"])
        best_combo = best["name"]
        best_hit_rate = best["hit_rate"]
        # Use the higher of combo hit rate and ML probability
        ensemble_prob = max(best_hit_rate, ml_prob)
    else:
        # Penalty for no combo confirmation
        ensemble_prob = ml_prob * 0.85

    # --- Step 2: Trap penalty ---
    # If low_in_range or rsi_oversold active WITHOUT vol_zscore confirmation,
    # apply a 5% penalty.  We check via tier_info which propagates from the
    # signal dict; the caller should populate these fields if available.
    trap_signals = tier_info.get("_trap_signals", {})
    low_in_range_active = trap_signals.get("low_in_range", False)
    rsi_oversold_active = trap_signals.get("rsi_oversold", False)
    vol_confirmed = trap_signals.get("vol_zscore", False)

    if (low_in_range_active or rsi_oversold_active) and not vol_confirmed:
        ensemble_prob *= 0.95
        logger.debug("Trap penalty applied: ensemble_prob=%.4f", ensemble_prob)

    # --- Step 3: Regime adjustment ---
    if regime_state is not None:
        adjustments = get_regime_adjustments(regime_state)
        threshold_mult = adjustments.get("threshold_mult", 1.0)
        ensemble_prob *= threshold_mult
        logger.debug(
            "Regime adjustment (%s): mult=%.2f, ensemble_prob=%.4f",
            regime_state,
            threshold_mult,
            ensemble_prob,
        )

    # Clamp
    ensemble_prob = float(np.clip(ensemble_prob, 0.0, 1.0))

    # --- Step 4: Final score and conviction ---
    ensemble_score = int(ensemble_prob * 100)
    final_conviction = _conviction_from_ensemble(ensemble_score)

    tier = tier_info.get("tier")

    result = {
        "ensemble_score": ensemble_score,
        "ensemble_prob": round(ensemble_prob, 4),
        "final_conviction": final_conviction,
        "confidence": round(ensemble_prob, 4),
        "best_combo": best_combo,
        "tier": tier,
    }
    logger.info(
        "Ensemble: score=%d conviction=%s combo=%s tier=%s",
        ensemble_score,
        final_conviction,
        best_combo or "NONE",
        tier,
    )
    return result


def _conviction_from_ensemble(score: int) -> str:
    """Map ensemble score to final conviction label."""
    if score >= 85:
        return "EXTREME"
    if score >= 75:
        return "HIGH"
    if score >= 65:
        return "MODERATE"
    if score >= 55:
        return "LOW"
    return "SPECULATIVE"


# ---------------------------------------------------------------------------
# Adaptive self-learning
# ---------------------------------------------------------------------------

class AdaptiveLearner:
    """Tracks rolling prediction accuracy and adjusts thresholds / weights.

    Maintains a rolling window of (prediction, actual_outcome) pairs and
    computes false-positive rates to decide whether scoring thresholds
    should be raised.

    Uses exponential moving average for smoother adaptation.
    """

    def __init__(self, window_size: int = 200, ema_alpha: float = 0.05):
        """
        Parameters
        ----------
        window_size : int
            Maximum number of recent outcomes to track.
        ema_alpha : float
            Smoothing factor for exponential moving average (0 < alpha <= 1).
        """
        self._window_size = window_size
        self._ema_alpha = ema_alpha
        self._outcomes: deque = deque(maxlen=window_size)
        self._ema_fp_rate: float = 0.0
        self._initialised: bool = False

    def update(self, prediction: float, actual_outcome: float) -> None:
        """Record a new (prediction, actual_outcome) observation.

        Parameters
        ----------
        prediction : float
            The model's predicted probability (0-1).
        actual_outcome : float
            The realised return or binary outcome.
        """
        is_positive_prediction = prediction >= 0.5
        is_actual_hit = actual_outcome > 0
        is_false_positive = is_positive_prediction and not is_actual_hit

        self._outcomes.append({
            "prediction": prediction,
            "actual": actual_outcome,
            "false_positive": is_false_positive,
            "positive_prediction": is_positive_prediction,
        })

        # Update EMA of false positive rate
        fp_val = 1.0 if is_false_positive else 0.0
        if not self._initialised:
            self._ema_fp_rate = fp_val
            self._initialised = True
        else:
            self._ema_fp_rate = (
                self._ema_alpha * fp_val + (1 - self._ema_alpha) * self._ema_fp_rate
            )

    def get_threshold_adjustment(self) -> float:
        """Return a threshold adjustment value.

        If the rolling false-positive rate exceeds the configured threshold,
        returns a positive number (raise threshold to be more selective).
        Otherwise returns 0.0.

        Returns
        -------
        float
            Threshold adjustment (add to base threshold). Typically 0.0-0.10.
        """
        config = get_config()
        fp_threshold = config.learning.fp_rate_threshold

        if not self._outcomes:
            return 0.0

        if self._ema_fp_rate > fp_threshold:
            # Scale adjustment proportionally to how far above threshold
            excess = self._ema_fp_rate - fp_threshold
            adjustment = min(excess * 0.5, 0.10)  # cap at 10 points
            logger.info(
                "Threshold adjustment: +%.4f (FP rate EMA=%.3f > threshold=%.3f)",
                adjustment,
                self._ema_fp_rate,
                fp_threshold,
            )
            return adjustment

        return 0.0

    def get_weight_adjustments(self) -> Dict[str, float]:
        """Return per-signal weight multipliers based on recent performance.

        Queries the ``SignalPerformance`` table for the most recent period
        and returns the stored ``weight_adjustment`` values.

        Returns
        -------
        dict[str, float]
            Mapping of signal name to weight multiplier (e.g. ``{"vol_zscore": 1.15}``).
            Defaults to 1.0 for signals without performance data.
        """
        from ..db import session_scope
        from ..schemas import SignalPerformance

        weights: Dict[str, float] = {}

        try:
            with session_scope() as session:
                from sqlalchemy import func

                # Get the most recent period_end
                latest = session.query(func.max(SignalPerformance.period_end)).scalar()
                if latest is None:
                    logger.debug("No signal performance data available")
                    return weights

                rows = (
                    session.query(SignalPerformance)
                    .filter(SignalPerformance.period_end == latest)
                    .all()
                )

                for row in rows:
                    w = row.weight_adjustment if row.weight_adjustment else 1.0
                    weights[row.signal_name] = w

        except Exception as exc:
            logger.warning("Failed to load signal performance weights: %s", exc)

        logger.debug("Loaded %d signal weight adjustments", len(weights))
        return weights

    @property
    def ema_fp_rate(self) -> float:
        """Current exponential moving average of the false-positive rate."""
        return self._ema_fp_rate

    @property
    def n_observations(self) -> int:
        """Number of observations in the rolling window."""
        return len(self._outcomes)
