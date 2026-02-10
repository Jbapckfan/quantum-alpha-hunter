"""
Combo matcher -- validates signals against the 7 winning combos from Hedge Fund
ultimate_scanner_v5.py.  Each combo has a historically validated hit rate that
must be preserved exactly.

The module checks whether a symbol's current signal values pass the defined
activation thresholds, then matches against every combo whose *required*
signals are all active.
"""
import logging
from typing import Dict, List, Optional

logger = logging.getLogger("apredator.scoring.combo_matcher")

# ---------------------------------------------------------------------------
# 7 validated winning combos -- DO NOT change hit_rate values
# ---------------------------------------------------------------------------
WINNING_COMBOS: Dict[str, dict] = {
    "REVERSAL_EXPLOSION": {
        "required": ["vol_zscore", "gap_up", "vol_spike_count", "selling_pressure"],
        "hit_rate": 0.583,
        "description": "Volume explosion after selling exhaustion with gap catalyst",
    },
    "ACCELERATION_REVERSAL": {
        "required": ["vol_zscore", "gap_up", "vol_accel", "selling_pressure"],
        "hit_rate": 0.571,
        "description": "Accelerating volume into reversal with gap",
    },
    "REJECTION_REVERSAL": {
        "required": ["vol_zscore", "vol_spike_count", "rejection_wick", "selling_pressure"],
        "hit_rate": 0.563,
        "description": "Price rejection at lows with volume surge",
    },
    "TRIPLE_THREAT": {
        "required": ["vol_zscore", "gap_up", "selling_pressure"],
        "hit_rate": 0.507,
        "description": "Volume + gap + selling exhaustion",
    },
    "VOLUME_BREAKOUT": {
        "required": ["vol_zscore", "range_20d", "vol_spike_count"],
        "hit_rate": 0.500,
        "description": "Volume breakout from wide range",
    },
    "GAP_ACCELERATION": {
        "required": ["vol_zscore", "range_20d", "vol_accel", "gap_up"],
        "hit_rate": 0.500,
        "description": "Accelerating volume with gap from range",
    },
    "VOLUME_GAP": {
        "required": ["vol_zscore", "gap_up"],
        "hit_rate": 0.473,
        "description": "Basic volume + gap pattern",
    },
}

# ---------------------------------------------------------------------------
# Signal activation thresholds
# A signal is "active" when its value passes the threshold test.
# ---------------------------------------------------------------------------
SIGNAL_THRESHOLDS: Dict[str, tuple] = {
    "vol_zscore": (">=", 0.15),
    "gap_up": (">=", 1.5),
    "vol_spike_count": (">=", 1),
    "vol_accel": (">=", 0.10),
    "range_20d": (">=", 20.0),
    "rejection_wick": (">=", 1.0),
    "selling_pressure": ("<=", 2),       # <=2 up days = selling pressure active
    "low_in_range": ("<=", 0.40),
    "rsi_14": ("between", (30, 50)),
    "momentum_10d": ("<=", -15.0),
    "pullback_pct": ("<=", -15.0),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_signal_active(signal_name: str, value) -> bool:
    """Check whether *value* passes the activation threshold for *signal_name*.

    Returns ``False`` for unknown signals or ``None`` / NaN values.
    """
    if signal_name not in SIGNAL_THRESHOLDS:
        logger.debug("Unknown signal '%s' -- treating as inactive", signal_name)
        return False

    if value is None:
        return False

    try:
        value = float(value)
    except (TypeError, ValueError):
        return False

    # NaN check
    if value != value:
        return False

    op, threshold = SIGNAL_THRESHOLDS[signal_name]

    if op == ">=":
        return value >= threshold
    if op == "<=":
        return value <= threshold
    if op == ">":
        return value > threshold
    if op == "<":
        return value < threshold
    if op == "between":
        lo, hi = threshold
        return lo <= value <= hi

    logger.warning("Unsupported operator '%s' for signal '%s'", op, signal_name)
    return False


def match_combos(signals_dict: Dict[str, float]) -> List[dict]:
    """Match *signals_dict* against all winning combos.

    Parameters
    ----------
    signals_dict : dict
        Mapping of signal name -> current value (e.g. ``{"vol_zscore": 1.2, ...}``).

    Returns
    -------
    list[dict]
        Each element is ``{"name": str, "hit_rate": float, "matched_signals": list[str]}``.
        Only combos where **all** required signals are active are returned.
    """
    matches: List[dict] = []

    for combo_name, combo_def in WINNING_COMBOS.items():
        required = combo_def["required"]
        all_active = True
        matched_signals: List[str] = []

        for sig in required:
            val = signals_dict.get(sig)
            if is_signal_active(sig, val):
                matched_signals.append(sig)
            else:
                all_active = False
                break  # short-circuit

        if all_active:
            matches.append({
                "name": combo_name,
                "hit_rate": combo_def["hit_rate"],
                "matched_signals": matched_signals,
            })

    if matches:
        logger.info(
            "Matched %d combo(s): %s",
            len(matches),
            ", ".join(m["name"] for m in matches),
        )
    else:
        logger.debug("No combos matched for the given signals")

    return matches


def get_best_combo(matches: List[dict]) -> Optional[dict]:
    """Return the combo with the highest hit_rate from *matches*, or ``None``."""
    if not matches:
        return None
    return max(matches, key=lambda m: m["hit_rate"])


def compute_combo_strength(
    signals_dict: Dict[str, float],
    matched_combo: dict,
) -> float:
    """Compute how strongly the matched signals exceed their thresholds.

    Returns a float in ``[0, 1]`` representing the average normalised distance
    past the activation threshold.  A value of 1.0 means every signal is at
    least 2x its threshold.

    Parameters
    ----------
    signals_dict : dict
        Current signal values.
    matched_combo : dict
        A single combo dict as returned by :func:`match_combos`.
    """
    if not matched_combo or "matched_signals" not in matched_combo:
        return 0.0

    strengths: List[float] = []

    for sig in matched_combo["matched_signals"]:
        val = signals_dict.get(sig)
        if val is None:
            strengths.append(0.0)
            continue

        try:
            val = float(val)
        except (TypeError, ValueError):
            strengths.append(0.0)
            continue

        if val != val:  # NaN
            strengths.append(0.0)
            continue

        op, threshold = SIGNAL_THRESHOLDS.get(sig, (">=", 1.0))

        if op == "between":
            lo, hi = threshold
            mid = (lo + hi) / 2.0
            half_range = (hi - lo) / 2.0
            if half_range == 0:
                strengths.append(1.0)
            else:
                # 1.0 when at midpoint, tapering toward edges
                dist_from_mid = abs(val - mid)
                s = max(0.0, 1.0 - dist_from_mid / half_range)
                strengths.append(min(s, 1.0))
        elif op in (">=", ">"):
            if threshold == 0:
                strengths.append(min(val, 1.0))
            else:
                # How far past threshold: 0 = at threshold, 1 = 2x threshold
                s = (val - threshold) / abs(threshold)
                strengths.append(max(0.0, min(s, 1.0)))
        elif op in ("<=", "<"):
            if threshold == 0:
                strengths.append(min(abs(val), 1.0))
            else:
                # For "less-than" signals, further below threshold = stronger
                s = (threshold - val) / abs(threshold)
                strengths.append(max(0.0, min(s, 1.0)))
        else:
            strengths.append(0.0)

    if not strengths:
        return 0.0

    return sum(strengths) / len(strengths)
