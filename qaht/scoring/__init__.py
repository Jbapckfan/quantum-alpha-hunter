"""Scoring and model training modules"""

from .empirical_combos import (
    EmpiricalScorer,
    ComboMatcher,
    TrapDetector,
    RegimeAdjuster,
    compute_all_signals,
    score_universe,
    tier1_filter,
)
from .position_sizing import (
    KellyPositionSizer,
    ProfitTargetCalculator,
)
