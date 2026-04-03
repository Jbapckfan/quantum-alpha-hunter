"""Outcome-driven stock signal weight tuning."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from qaht.signals.weights import STOCK_WEIGHTS, load_weights, save_weights

from .outcome_tracker import OutcomeTracker

logger = logging.getLogger("qaht.tracking.weight_tuner")

_DEFAULT_WEIGHTS_FILE = Path(__file__).resolve().parent.parent / "signals" / "stock_weights.json"


class WeightTuner:
    """Adjust stock signal weights based on realized outcomes."""

    def __init__(
        self,
        tracker: Optional[OutcomeTracker] = None,
        weights_file: Optional[Path] = None,
    ) -> None:
        self.tracker = tracker or OutcomeTracker()
        self.weights_file = weights_file or _DEFAULT_WEIGHTS_FILE

    def compute_adjusted_weights(self, lookback_days: int = 90) -> Dict[str, Any]:
        """Return tuned weights and an accompanying drift report."""
        current_weights = load_weights(self.weights_file, STOCK_WEIGHTS)
        stats_rows = self.tracker.get_signal_stats(lookback_days=lookback_days)
        stats = {row["signal_name"]: row for row in stats_rows}

        adjusted: Dict[str, float] = {}
        report: List[Dict[str, Any]] = []

        for signal_name, base_weight in current_weights.items():
            baseline = float(base_weight)
            stat = stats.get(signal_name)
            if stat is None or stat["times_fired"] <= 0:
                adjusted[signal_name] = baseline
                continue

            magnitude = abs(baseline)
            if magnitude == 0:
                adjusted[signal_name] = 0.0
                continue

            hit_rate = float(stat["hit_rate"])
            scaled = magnitude * (1.0 + (hit_rate - 0.5) * 2.0)
            clamped = min(max(scaled, 0.25 * magnitude), 2.0 * magnitude)
            tuned_weight = clamped if baseline >= 0 else -clamped
            adjusted[signal_name] = round(tuned_weight, 4)

            report.append(
                {
                    "signal_name": signal_name,
                    "baseline_weight": baseline,
                    "adjusted_weight": round(tuned_weight, 4),
                    "delta": round(tuned_weight - baseline, 4),
                    "hit_rate": hit_rate,
                    "avg_return": stat["avg_return"],
                    "times_fired": stat["times_fired"],
                    "direction": "improved" if abs(tuned_weight) > abs(baseline) else "degraded",
                }
            )

        report.sort(key=lambda row: abs(row["delta"]), reverse=True)
        return {
            "weights": adjusted,
            "lookback_days": lookback_days,
            "report": report,
        }

    def apply_tuned_weights(self, lookback_days: int = 90) -> Dict[str, Any]:
        """Persist tuned weights to disk."""
        payload = self.compute_adjusted_weights(lookback_days=lookback_days)
        save_weights(self.weights_file, payload["weights"])
        logger.info("Applied tuned weights using %d-day lookback", lookback_days)
        return payload

    def get_weight_drift_report(self, lookback_days: int = 90) -> List[Dict[str, Any]]:
        """Return the sorted drift report without persisting changes."""
        payload = self.compute_adjusted_weights(lookback_days=lookback_days)
        return payload["report"]
