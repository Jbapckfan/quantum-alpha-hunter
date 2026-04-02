"""
Position sizing via Kelly criterion and multi-target profit taking
Calibrated from empirical backtests on the Hedge-Fund-explosive-scanner dataset
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("qaht.scoring.position_sizing")


# ---------------------------------------------------------------------------
# Constants from backtest calibration
# ---------------------------------------------------------------------------

# Risk/reward profile from explosive scanner empirical results
DEFAULT_WIN_RATE = 0.40
DEFAULT_WIN_RETURN = 0.40       # average winner +40%
DEFAULT_LOSS_RETURN = 0.15      # average loser -15%
DEFAULT_PAYOFF_RATIO = DEFAULT_WIN_RETURN / DEFAULT_LOSS_RETURN  # b = 2.67

# Quarter Kelly is standard practice to account for estimation error
KELLY_FRACTION = 0.25

# Hard limits on position size (fraction of portfolio)
POSITION_CAP = 0.10
POSITION_FLOOR = 0.02

# Multi-target profit exits (empirical)
DEFAULT_STOP_LOSS = -0.15
DEFAULT_TARGETS: List[Tuple[float, float]] = [
    (0.30, 0.25),   # T1: +30% -> take 25% of position
    (0.50, 0.25),   # T2: +50% -> take 25% of position
    (1.00, 0.50),   # T3: +100% -> trail remaining 50%
]


# ---------------------------------------------------------------------------
# Kelly Criterion
# ---------------------------------------------------------------------------

@dataclass
class KellyResult:
    """Output of Kelly position sizing calculation."""

    full_kelly: float
    fractional_kelly: float
    clamped_size: float
    edge: float
    payoff_ratio: float
    win_prob: float


class KellyPositionSizer:
    """
    Kelly-criterion position sizer calibrated on explosive scanner data.

    The full Kelly fraction is f* = (b*p - q) / b where
        p = probability of winning
        q = 1 - p
        b = ratio of win size to loss size (payoff ratio)

    In practice we use *quarter* Kelly to avoid over-betting due to
    estimation uncertainty in p and b.
    """

    def __init__(
        self,
        kelly_fraction: float = KELLY_FRACTION,
        position_cap: float = POSITION_CAP,
        position_floor: float = POSITION_FLOOR,
    ):
        self.kelly_fraction = kelly_fraction
        self.position_cap = position_cap
        self.position_floor = position_floor

    def compute(
        self,
        win_prob: float,
        avg_win: float = DEFAULT_WIN_RETURN,
        avg_loss: float = DEFAULT_LOSS_RETURN,
    ) -> KellyResult:
        """
        Compute position size for a single trade.

        Args:
            win_prob: Estimated probability of a winning trade (0-1).
            avg_win:  Expected return when the trade wins (e.g. 0.40 = +40%).
            avg_loss: Expected loss magnitude when the trade loses (e.g. 0.15 = -15%).

        Returns:
            KellyResult with full, fractional, and clamped position sizes.
        """
        if avg_loss <= 0:
            logger.warning("avg_loss must be positive; defaulting to %.2f", DEFAULT_LOSS_RETURN)
            avg_loss = DEFAULT_LOSS_RETURN

        b = avg_win / avg_loss  # payoff ratio
        p = np.clip(win_prob, 0.0, 1.0)
        q = 1.0 - p

        # Full Kelly: (b*p - q) / b
        full_kelly = (b * p - q) / b if b > 0 else 0.0
        edge = b * p - q  # expected value per unit risked

        # Fractional Kelly
        fractional = full_kelly * self.kelly_fraction

        # Clamp to [floor, cap] — but only if edge is positive
        if edge <= 0:
            clamped = 0.0
        else:
            clamped = float(np.clip(fractional, self.position_floor, self.position_cap))

        result = KellyResult(
            full_kelly=float(full_kelly),
            fractional_kelly=float(fractional),
            clamped_size=clamped,
            edge=float(edge),
            payoff_ratio=float(b),
            win_prob=float(p),
        )
        logger.debug(
            "Kelly sizing: p=%.3f b=%.2f edge=%.3f full=%.4f frac=%.4f clamped=%.4f",
            p, b, edge, full_kelly, fractional, clamped,
        )
        return result


# ---------------------------------------------------------------------------
# Multi-Target Profit Taking
# ---------------------------------------------------------------------------

@dataclass
class ProfitTarget:
    """A single profit target level."""

    label: str
    return_pct: float       # trigger return (e.g. 0.30 = +30%)
    exit_fraction: float    # fraction of *remaining* position to sell

    @property
    def is_trailing(self) -> bool:
        return self.exit_fraction >= 0.50 and self.return_pct >= 1.0


@dataclass
class ExitPlan:
    """Complete exit plan for a position."""

    entry_price: float
    stop_loss_price: float
    targets: List[Dict]
    risk_per_share: float
    reward_risk_ratio: float


class ProfitTargetCalculator:
    """
    Multi-target exit strategy derived from explosive scanner backtests.

    Default plan:
        Stop Loss : -15%
        T1        : +30% -> sell 25% of position
        T2        : +50% -> sell 25% of position
        T3        : +100% -> trail remaining 50%
    """

    def __init__(
        self,
        stop_loss_pct: float = DEFAULT_STOP_LOSS,
        targets: Optional[List[Tuple[float, float]]] = None,
    ):
        self.stop_loss_pct = stop_loss_pct
        raw_targets = targets or DEFAULT_TARGETS

        self.targets: List[ProfitTarget] = []
        for i, (ret_pct, exit_frac) in enumerate(raw_targets, start=1):
            self.targets.append(
                ProfitTarget(label=f"T{i}", return_pct=ret_pct, exit_fraction=exit_frac)
            )

    def plan(self, entry_price: float) -> ExitPlan:
        """
        Build a concrete exit plan given an entry price.

        Args:
            entry_price: Price at which the position was entered.

        Returns:
            ExitPlan with absolute price levels and risk metrics.
        """
        if entry_price <= 0:
            raise ValueError(f"entry_price must be positive, got {entry_price}")

        stop_price = entry_price * (1.0 + self.stop_loss_pct)
        risk_per_share = entry_price - stop_price  # positive value

        target_details: List[Dict] = []
        for t in self.targets:
            target_price = entry_price * (1.0 + t.return_pct)
            target_details.append({
                "label": t.label,
                "price": round(target_price, 4),
                "return_pct": t.return_pct,
                "exit_fraction": t.exit_fraction,
                "is_trailing": t.is_trailing,
            })

        # Reward/risk using first target
        first_reward = self.targets[0].return_pct * entry_price if self.targets else 0.0
        rr_ratio = first_reward / risk_per_share if risk_per_share > 0 else 0.0

        plan = ExitPlan(
            entry_price=entry_price,
            stop_loss_price=round(stop_price, 4),
            targets=target_details,
            risk_per_share=round(risk_per_share, 4),
            reward_risk_ratio=round(rr_ratio, 2),
        )

        logger.debug(
            "Exit plan: entry=%.2f stop=%.2f targets=%s R:R=%.1f",
            entry_price, stop_price,
            [(t["label"], t["price"]) for t in target_details],
            rr_ratio,
        )
        return plan

    def check_exit(
        self,
        current_price: float,
        entry_price: float,
        targets_hit: Optional[List[str]] = None,
    ) -> Optional[Dict]:
        """
        Check whether the current price triggers any exit level.

        Args:
            current_price: Current market price.
            entry_price:   Original entry price.
            targets_hit:   Labels of targets already taken (e.g. ["T1"]).

        Returns:
            Dict describing the triggered exit, or None.
        """
        targets_hit = targets_hit or []
        pct_return = (current_price / entry_price) - 1.0

        # Stop loss check first
        if pct_return <= self.stop_loss_pct:
            return {
                "action": "STOP_LOSS",
                "price": current_price,
                "return_pct": round(pct_return, 4),
                "exit_fraction": 1.0,
            }

        # Walk through targets in order
        for t in self.targets:
            if t.label in targets_hit:
                continue
            if pct_return >= t.return_pct:
                return {
                    "action": f"TARGET_{t.label}",
                    "price": current_price,
                    "return_pct": round(pct_return, 4),
                    "exit_fraction": t.exit_fraction,
                    "is_trailing": t.is_trailing,
                }

        return None
