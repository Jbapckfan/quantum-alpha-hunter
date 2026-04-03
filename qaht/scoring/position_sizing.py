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

MAX_TOTAL_PORTFOLIO_ALLOCATION = 0.30
MAX_POSITIONS_PER_SECTOR = 3
HIGH_CORRELATION_THRESHOLD = 0.70
MAX_CORRELATION_SIZE_CUT = 0.50
VAR_ZSCORE_95 = 1.65


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


@dataclass
class PortfolioPosition:
    """Tracked portfolio position used by PortfolioRiskManager."""

    symbol: str
    weight: float
    sector: str
    volatility: float
    correlations: Dict[str, float] = field(default_factory=dict)


@dataclass
class PositionDecision:
    """Sizing decision for a proposed portfolio position."""

    symbol: str
    requested_weight: float
    approved_weight: float
    sector: str
    total_exposure: float
    remaining_capacity: float
    sector_count: int
    correlation_multiplier: float
    accepted: bool
    reasons: List[str] = field(default_factory=list)


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


class PortfolioRiskManager:
    """
    Portfolio-level risk controls for candidate sizing decisions.

    Controls:
        - Max 30% aggregate portfolio allocation
        - Max 3 positions per sector
        - Correlation-based size haircuts
        - Portfolio-level VaR from weights, volatilities, and correlations
    """

    def __init__(
        self,
        max_total_allocation: float = MAX_TOTAL_PORTFOLIO_ALLOCATION,
        max_positions_per_sector: int = MAX_POSITIONS_PER_SECTOR,
        high_correlation_threshold: float = HIGH_CORRELATION_THRESHOLD,
        max_correlation_size_cut: float = MAX_CORRELATION_SIZE_CUT,
        var_zscore: float = VAR_ZSCORE_95,
    ):
        self.max_total_allocation = max_total_allocation
        self.max_positions_per_sector = max_positions_per_sector
        self.high_correlation_threshold = high_correlation_threshold
        self.max_correlation_size_cut = max_correlation_size_cut
        self.var_zscore = var_zscore
        self.positions: Dict[str, PortfolioPosition] = {}

    def total_exposure(self) -> float:
        """Current aggregate portfolio allocation."""
        return float(sum(position.weight for position in self.positions.values()))

    def sector_counts(self) -> Dict[str, int]:
        """Count active positions by sector."""
        counts: Dict[str, int] = {}
        for position in self.positions.values():
            counts[position.sector] = counts.get(position.sector, 0) + 1
        return counts

    def _correlation_multiplier(
        self,
        symbol: str,
        correlations: Optional[Dict[str, float]] = None,
    ) -> float:
        correlations = correlations or {}
        relevant = [
            abs(correlations[held_symbol])
            for held_symbol in self.positions
            if held_symbol != symbol and held_symbol in correlations
        ]
        if not relevant:
            return 1.0

        max_corr = max(relevant)
        if max_corr < self.high_correlation_threshold:
            return 1.0

        scaled_excess = (max_corr - self.high_correlation_threshold) / max(
            1e-9,
            1.0 - self.high_correlation_threshold,
        )
        size_cut = min(self.max_correlation_size_cut, scaled_excess * self.max_correlation_size_cut)
        return float(max(0.0, 1.0 - size_cut))

    def register_position(
        self,
        symbol: str,
        target_weight: float,
        sector: str,
        volatility: float,
        correlations: Optional[Dict[str, float]] = None,
    ) -> PositionDecision:
        """
        Add or update a position after applying portfolio-level constraints.

        Returns the approved size along with the gating reasons used.
        """
        correlations = correlations or {}
        existing = self.positions.get(symbol)
        existing_weight = existing.weight if existing else 0.0
        requested_weight = max(0.0, float(target_weight))

        active_sector_count = sum(
            1 for held_symbol, position in self.positions.items()
            if position.sector == sector and held_symbol != symbol and position.weight > 0
        )
        is_new_sector_slot = existing is None or existing.sector != sector
        reasons: List[str] = []

        if active_sector_count >= self.max_positions_per_sector and is_new_sector_slot:
            decision = PositionDecision(
                symbol=symbol,
                requested_weight=requested_weight,
                approved_weight=0.0,
                sector=sector,
                total_exposure=self.total_exposure(),
                remaining_capacity=max(0.0, self.max_total_allocation - self.total_exposure()),
                sector_count=active_sector_count,
                correlation_multiplier=1.0,
                accepted=False,
                reasons=[f"Sector cap reached for {sector} ({self.max_positions_per_sector} positions)"],
            )
            logger.info("Rejected %s due to sector cap: %s", symbol, decision.reasons[0])
            return decision

        gross_exposure_excluding_symbol = self.total_exposure() - existing_weight
        remaining_capacity = max(0.0, self.max_total_allocation - gross_exposure_excluding_symbol)
        approved_weight = min(requested_weight, remaining_capacity)
        if approved_weight < requested_weight:
            reasons.append(
                f"Clamped by portfolio exposure cap to {approved_weight:.2%} (max {self.max_total_allocation:.0%})"
            )

        correlation_multiplier = self._correlation_multiplier(symbol, correlations=correlations)
        if correlation_multiplier < 1.0 and approved_weight > 0:
            approved_weight *= correlation_multiplier
            reasons.append(
                f"Reduced for correlation overlap (multiplier {correlation_multiplier:.2f})"
            )

        approved_weight = float(max(0.0, approved_weight))
        accepted = approved_weight > 0

        if accepted:
            self.positions[symbol] = PortfolioPosition(
                symbol=symbol,
                weight=approved_weight,
                sector=sector,
                volatility=max(0.0, float(volatility)),
                correlations={k: float(v) for k, v in correlations.items()},
            )
        else:
            self.positions.pop(symbol, None)

        total_exposure = self.total_exposure()
        decision = PositionDecision(
            symbol=symbol,
            requested_weight=requested_weight,
            approved_weight=approved_weight,
            sector=sector,
            total_exposure=total_exposure,
            remaining_capacity=max(0.0, self.max_total_allocation - total_exposure),
            sector_count=active_sector_count + (1 if accepted else 0),
            correlation_multiplier=correlation_multiplier,
            accepted=accepted,
            reasons=reasons,
        )
        logger.debug(
            "Portfolio decision: symbol=%s requested=%.4f approved=%.4f total=%.4f reasons=%s",
            symbol,
            requested_weight,
            approved_weight,
            total_exposure,
            reasons,
        )
        return decision

    def remove_position(self, symbol: str) -> None:
        """Drop a tracked position from the portfolio view."""
        self.positions.pop(symbol, None)

    def _pairwise_correlation(self, left: str, right: str) -> float:
        if left == right:
            return 1.0
        if left in self.positions and right in self.positions[left].correlations:
            return float(self.positions[left].correlations[right])
        if right in self.positions and left in self.positions[right].correlations:
            return float(self.positions[right].correlations[left])
        return 0.0

    def compute_portfolio_var(self, zscore: Optional[float] = None) -> float:
        """
        Compute 1-day portfolio VaR as a fraction of portfolio value.

        Formula:
            VaR = z * sqrt(w^T Sigma w)
        where Sigma_ij = corr_ij * vol_i * vol_j
        """
        if not self.positions:
            return 0.0

        symbols = list(self.positions.keys())
        weights = np.array([self.positions[symbol].weight for symbol in symbols], dtype=float)
        vols = np.array([max(0.0, self.positions[symbol].volatility) for symbol in symbols], dtype=float)

        covariance = np.zeros((len(symbols), len(symbols)), dtype=float)
        for i, left in enumerate(symbols):
            for j, right in enumerate(symbols):
                correlation = self._pairwise_correlation(left, right)
                covariance[i, j] = correlation * vols[i] * vols[j]

        portfolio_variance = float(weights.T @ covariance @ weights)
        portfolio_volatility = np.sqrt(max(0.0, portfolio_variance))
        return float((zscore or self.var_zscore) * portfolio_volatility)
