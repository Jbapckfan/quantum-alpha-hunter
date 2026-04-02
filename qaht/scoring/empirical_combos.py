"""
Empirical combo scoring — validated trading patterns from Hedge-Fund-explosive-scanner

Encodes the seven winning signal combinations, trap detection, market regime
adjustments, and a hybrid scorer that layers empirical evidence on top of the
existing Ridge regression quantum_score.

All feature weights and hit-rate thresholds are calibrated from backtests on
real equity OHLCV data. See the scanner's research notebook for derivation.
"""
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from ..db import session_scope
from ..schemas import PriceOHLC, Factors, Regime, Predictions
from ..config import get_config
from .position_sizing import KellyPositionSizer, ProfitTargetCalculator, KellyResult, ExitPlan
from sqlalchemy import select

logger = logging.getLogger("qaht.scoring.empirical_combos")
config = get_config()


# ============================================================================
# Empirical feature weights (% lift vs random baseline)
# ============================================================================

EMPIRICAL_WEIGHTS: Dict[str, float] = {
    "vol_zscore":         4.43,   # +443% — most predictive
    "rejection_wicks":    1.08,   # +108%
    "vol_spikes":         0.87,   # +87%
    "gap_up":             0.72,   # +72%
    "high_vol":           0.64,   # +64%
    "avg_volume_ratio":   0.45,   # +45%
    "selling_pressure":   0.25,   # +25%
    "price_vs_20d_low":   0.10,   # +10%
    "rsi_14":            -0.15,   # -15% (contrarian — oversold helps reversals)
    "momentum_10d":      -1.70,   # -170% (negative momentum = reversal setup)
}

# Normalised weight vector for blending (absolute values, sum to 1)
_abs_total = sum(abs(v) for v in EMPIRICAL_WEIGHTS.values())
NORMALISED_WEIGHTS: Dict[str, float] = {
    k: abs(v) / _abs_total for k, v in EMPIRICAL_WEIGHTS.items()
}


# ============================================================================
# Signal detection — each function takes an OHLCV DataFrame and returns a bool
# ============================================================================

def _require_ohlcv(df: pd.DataFrame) -> None:
    """Validate that necessary columns exist."""
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"OHLCV data missing columns: {missing}")


def compute_vol_zscore(df: pd.DataFrame, window: int = 20) -> float:
    """
    Volume anomaly z-score relative to trailing window.

    Args:
        df: OHLCV DataFrame sorted ascending by date.
        window: Look-back period for mean/std.

    Returns:
        Z-score of latest volume versus trailing distribution.
    """
    if len(df) < window + 1:
        return 0.0
    vol = df["volume"].values
    trailing = vol[-(window + 1):-1]
    mu = np.mean(trailing)
    sigma = np.std(trailing)
    if sigma == 0:
        return 0.0
    return float((vol[-1] - mu) / sigma)


def detect_vol_zscore(df: pd.DataFrame, threshold: float = 2.0) -> bool:
    """Volume z-score exceeds threshold (anomalous volume day)."""
    return compute_vol_zscore(df) > threshold


def detect_gap_up(df: pd.DataFrame, min_gap_pct: float = 0.02) -> bool:
    """
    Gap-up opening: today's open is at least *min_gap_pct* above
    yesterday's close.
    """
    if len(df) < 2:
        return False
    prev_close = df["close"].iloc[-2]
    today_open = df["open"].iloc[-1]
    if prev_close <= 0:
        return False
    gap = (today_open - prev_close) / prev_close
    return gap >= min_gap_pct


def detect_vol_spikes(df: pd.DataFrame, multiple: float = 2.0, window: int = 20) -> bool:
    """Volume is at least *multiple* times the trailing average."""
    if len(df) < window + 1:
        return False
    avg_vol = np.mean(df["volume"].values[-(window + 1):-1])
    if avg_vol <= 0:
        return False
    return df["volume"].iloc[-1] >= multiple * avg_vol


def detect_selling_pressure(df: pd.DataFrame, window: int = 5) -> bool:
    """
    Bearish candles with elevated volume over the last *window* days.
    Interpreted as exhaustion selling — a contrarian bullish signal
    when combined with volume anomaly.
    """
    if len(df) < window:
        return False
    tail = df.iloc[-window:]
    bearish = tail["close"] < tail["open"]
    vol_above_avg = tail["volume"] > tail["volume"].rolling(20, min_periods=1).mean()
    # At least 60% of recent candles are bearish on above-average volume
    return float((bearish & vol_above_avg).sum()) / window >= 0.60


def detect_rejection_wicks(df: pd.DataFrame, wick_ratio: float = 0.6) -> bool:
    """
    Upper shadow rejection wick: the upper wick is at least *wick_ratio*
    of the total candle range, signalling price rejection at highs.
    """
    if len(df) < 1:
        return False
    row = df.iloc[-1]
    total_range = row["high"] - row["low"]
    if total_range <= 0:
        return False
    body_top = max(row["open"], row["close"])
    upper_wick = row["high"] - body_top
    return (upper_wick / total_range) >= wick_ratio


def detect_high_vol(df: pd.DataFrame, window: int = 20) -> bool:
    """
    High 20-day price range: (max - min) / min > 0.20 (20%).
    Identifies volatile names that are more likely to produce explosive moves.
    """
    if len(df) < window:
        return False
    tail = df.iloc[-window:]
    lo = tail["low"].min()
    hi = tail["high"].max()
    if lo <= 0:
        return False
    return (hi - lo) / lo > 0.20


def detect_vol_accel(df: pd.DataFrame, window: int = 5) -> bool:
    """
    Volume acceleration: volume is increasing over the last *window* days
    (simple linear trend is positive).
    """
    if len(df) < window:
        return False
    vols = df["volume"].values[-window:]
    x = np.arange(window, dtype=float)
    # Quick linear regression slope
    slope = np.polyfit(x, vols, 1)[0]
    return slope > 0


def detect_rsi_oversold(df: pd.DataFrame, threshold: float = 30.0) -> bool:
    """RSI-14 is below the oversold threshold."""
    rsi = _compute_rsi(df)
    if rsi is None:
        return False
    return rsi <= threshold


def detect_low_in_range(df: pd.DataFrame, window: int = 20, pct: float = 0.20) -> bool:
    """
    Price is in the bottom *pct* of its trailing *window*-day range.
    """
    if len(df) < window:
        return False
    tail = df.iloc[-window:]
    lo = tail["low"].min()
    hi = tail["high"].max()
    if hi == lo:
        return False
    position = (df["close"].iloc[-1] - lo) / (hi - lo)
    return position <= pct


def compute_avg_volume_ratio(df: pd.DataFrame, window: int = 20) -> float:
    """Current volume divided by trailing *window*-day average."""
    if len(df) < window + 1:
        return 1.0
    avg = np.mean(df["volume"].values[-(window + 1):-1])
    if avg <= 0:
        return 1.0
    return float(df["volume"].iloc[-1] / avg)


def compute_momentum_10d(df: pd.DataFrame) -> float:
    """10-day return (negative = reversal setup)."""
    if len(df) < 11:
        return 0.0
    return float(df["close"].iloc[-1] / df["close"].iloc[-11] - 1.0)


def compute_price_vs_20d_low(df: pd.DataFrame) -> float:
    """Fraction above 20-day low."""
    if len(df) < 20:
        return 0.0
    lo = df["low"].iloc[-20:].min()
    if lo <= 0:
        return 0.0
    return float(df["close"].iloc[-1] / lo - 1.0)


def _compute_rsi(df: pd.DataFrame, period: int = 14) -> Optional[float]:
    """Compute RSI-14 from close prices. Returns None if insufficient data."""
    if len(df) < period + 1:
        return None
    close = df["close"].values
    delta = np.diff(close[-(period + 1):])
    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)
    avg_gain = np.mean(gains)
    avg_loss = np.mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100.0 - (100.0 / (1.0 + rs)))


# ============================================================================
# Convenience: compute all signals at once
# ============================================================================

@dataclass
class SignalSnapshot:
    """All empirical signals for a single symbol on a single day."""

    symbol: str
    vol_zscore: float = 0.0
    vol_zscore_flag: bool = False
    gap_up: bool = False
    vol_spikes: bool = False
    selling_pressure: bool = False
    rejection_wicks: bool = False
    high_vol: bool = False
    vol_accel: bool = False
    rsi_oversold: bool = False
    low_in_range: bool = False
    avg_volume_ratio: float = 1.0
    momentum_10d: float = 0.0
    price_vs_20d_low: float = 0.0
    rsi_14: Optional[float] = None


def compute_all_signals(symbol: str, df: pd.DataFrame) -> SignalSnapshot:
    """
    Compute every empirical signal for the latest bar.

    Args:
        symbol: Ticker symbol (for logging/labelling only).
        df: OHLCV DataFrame sorted ascending by date.

    Returns:
        SignalSnapshot with all boolean flags and continuous values.
    """
    _require_ohlcv(df)

    snap = SignalSnapshot(symbol=symbol)
    snap.vol_zscore = compute_vol_zscore(df)
    snap.vol_zscore_flag = snap.vol_zscore > 2.0
    snap.gap_up = detect_gap_up(df)
    snap.vol_spikes = detect_vol_spikes(df)
    snap.selling_pressure = detect_selling_pressure(df)
    snap.rejection_wicks = detect_rejection_wicks(df)
    snap.high_vol = detect_high_vol(df)
    snap.vol_accel = detect_vol_accel(df)
    snap.rsi_oversold = detect_rsi_oversold(df)
    snap.low_in_range = detect_low_in_range(df)
    snap.avg_volume_ratio = compute_avg_volume_ratio(df)
    snap.momentum_10d = compute_momentum_10d(df)
    snap.price_vs_20d_low = compute_price_vs_20d_low(df)
    snap.rsi_14 = _compute_rsi(df)

    return snap


# ============================================================================
# 7 Winning Combinations
# ============================================================================

class ComboName(str, Enum):
    """Empirically validated combo identifiers."""

    REVERSAL_EXPLOSION     = "REVERSAL_EXPLOSION"
    ACCELERATION_REVERSAL  = "ACCELERATION_REVERSAL"
    REJECTION_REVERSAL     = "REJECTION_REVERSAL"
    TRIPLE_THREAT          = "TRIPLE_THREAT"
    VOLUME_BREAKOUT        = "VOLUME_BREAKOUT"
    OVERSOLD_BOUNCE        = "OVERSOLD_BOUNCE"
    CAPITULATION_REVERSAL  = "CAPITULATION_REVERSAL"


@dataclass
class ComboDefinition:
    """Definition of one winning combination."""

    name: ComboName
    hit_rate: float                # empirical win rate (0-1)
    required_signals: List[str]    # signal attribute names on SignalSnapshot


# Definitions in descending hit-rate order
COMBO_DEFINITIONS: List[ComboDefinition] = [
    ComboDefinition(
        name=ComboName.REVERSAL_EXPLOSION,
        hit_rate=0.583,
        required_signals=["vol_zscore_flag", "gap_up", "vol_spikes", "selling_pressure"],
    ),
    ComboDefinition(
        name=ComboName.ACCELERATION_REVERSAL,
        hit_rate=0.571,
        required_signals=["vol_zscore_flag", "gap_up", "vol_accel", "selling_pressure"],
    ),
    ComboDefinition(
        name=ComboName.REJECTION_REVERSAL,
        hit_rate=0.563,
        required_signals=["vol_zscore_flag", "vol_spikes", "rejection_wicks", "selling_pressure"],
    ),
    ComboDefinition(
        name=ComboName.TRIPLE_THREAT,
        hit_rate=0.507,
        required_signals=["vol_zscore_flag", "gap_up", "selling_pressure"],
    ),
    ComboDefinition(
        name=ComboName.VOLUME_BREAKOUT,
        hit_rate=0.500,
        required_signals=["vol_zscore_flag", "high_vol", "vol_spikes"],
    ),
    ComboDefinition(
        name=ComboName.OVERSOLD_BOUNCE,
        hit_rate=0.485,
        required_signals=["rsi_oversold", "vol_zscore_flag", "selling_pressure"],
    ),
    ComboDefinition(
        name=ComboName.CAPITULATION_REVERSAL,
        hit_rate=0.470,
        required_signals=["low_in_range", "vol_zscore_flag", "selling_pressure"],
    ),
]


@dataclass
class ComboMatch:
    """A matched combo with its empirical hit rate."""

    name: str
    hit_rate: float
    signals_present: List[str]


class ComboMatcher:
    """
    Checks which of the 7 empirically-validated winning combinations
    are active for a given SignalSnapshot.
    """

    def __init__(self, definitions: Optional[List[ComboDefinition]] = None):
        self.definitions = definitions or COMBO_DEFINITIONS

    def match(self, snap: SignalSnapshot) -> List[ComboMatch]:
        """
        Return all combos whose required signals are satisfied.

        Args:
            snap: SignalSnapshot for one symbol.

        Returns:
            List of ComboMatch objects sorted by descending hit rate.
        """
        matches: List[ComboMatch] = []

        for combo in self.definitions:
            if all(getattr(snap, sig, False) for sig in combo.required_signals):
                matches.append(
                    ComboMatch(
                        name=combo.name.value,
                        hit_rate=combo.hit_rate,
                        signals_present=combo.required_signals,
                    )
                )

        matches.sort(key=lambda m: m.hit_rate, reverse=True)

        if matches:
            logger.info(
                "%s matched %d combos: %s",
                snap.symbol,
                len(matches),
                [m.name for m in matches],
            )

        return matches


# ============================================================================
# Trap Detection
# ============================================================================

@dataclass
class TrapWarning:
    """Warning for a trap signal firing without volume confirmation."""

    signal: str
    solo_lift: float       # negative lift when used alone
    mitigated: bool        # True if vol_zscore is also present
    message: str


TRAP_SIGNALS: Dict[str, float] = {
    "rsi_oversold":  -0.217,   # -21.7% lift alone
    "low_in_range":  -0.211,   # -21.1% lift alone
    # "pullback" has no direct flag in SignalSnapshot — it is proxied
    # by negative momentum_10d without vol_zscore confirmation
}


class TrapDetector:
    """
    Flags when historically-negative signals fire without volume
    confirmation (vol_zscore).  These signals *become* powerful when
    accompanied by anomalous volume, but are traps on their own.
    """

    def check(self, snap: SignalSnapshot) -> List[TrapWarning]:
        """
        Scan a SignalSnapshot for unconfirmed trap signals.

        Args:
            snap: SignalSnapshot to inspect.

        Returns:
            List of TrapWarning objects (empty if no traps detected).
        """
        warnings: List[TrapWarning] = []
        has_vol = snap.vol_zscore_flag

        for sig_name, solo_lift in TRAP_SIGNALS.items():
            if getattr(snap, sig_name, False):
                warning = TrapWarning(
                    signal=sig_name,
                    solo_lift=solo_lift,
                    mitigated=has_vol,
                    message=(
                        f"{sig_name} active with vol_zscore confirmation — combo valid"
                        if has_vol
                        else f"{sig_name} active WITHOUT vol_zscore — historical lift {solo_lift:+.1%}, likely trap"
                    ),
                )
                warnings.append(warning)

        # Pullback proxy: negative momentum without volume
        if snap.momentum_10d < -0.10 and not has_vol:
            warnings.append(
                TrapWarning(
                    signal="pullback_proxy",
                    solo_lift=-0.284,
                    mitigated=False,
                    message="Negative 10d momentum without vol_zscore — pullback trap (-28.4% lift alone)",
                )
            )

        if warnings:
            unmitigated = [w for w in warnings if not w.mitigated]
            if unmitigated:
                logger.warning(
                    "%s has %d unmitigated trap signals: %s",
                    snap.symbol,
                    len(unmitigated),
                    [w.signal for w in unmitigated],
                )

        return warnings


# ============================================================================
# Market Regime Adjustments
# ============================================================================

class RegimeType(str, Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    HIGH_VOL = "HIGH_VOL"
    LOW_VOL = "LOW_VOL"
    NEUTRAL = "NEUTRAL"


@dataclass
class RegimeState:
    """Current market regime with EV and position multipliers."""

    regime: RegimeType
    ev_adjustment: float           # additive adjustment to expected value
    position_size_mult: float      # multiplicative adjustment to position size

    @property
    def label(self) -> str:
        return self.regime.value


# Regime rules from backtests
REGIME_RULES: Dict[RegimeType, Dict[str, float]] = {
    RegimeType.BULL:     {"ev_adj": 0.20, "size_mult": 1.00},
    RegimeType.BEAR:     {"ev_adj": -0.20, "size_mult": 0.70},
    RegimeType.HIGH_VOL: {"ev_adj": 0.10, "size_mult": 0.80},
    RegimeType.LOW_VOL:  {"ev_adj": -0.10, "size_mult": 1.00},
    RegimeType.NEUTRAL:  {"ev_adj": 0.00, "size_mult": 1.00},
}


class RegimeAdjuster:
    """
    Classifies market regime from SPY trend and VIX level, then applies
    empirically-derived EV and position-size adjustments.

    Rules:
        BULL    : SPY > 50-MA and trend > +3%  ->  +20% EV
        BEAR    : SPY < 50-MA and trend < -3%  ->  -20% EV, -30% position
        HIGH_VOL: VIX > 25                     ->  +10% EV, -20% position
        LOW_VOL : VIX < 15                     ->  -10% EV
    """

    def classify(
        self,
        spy_price: Optional[float] = None,
        spy_ma50: Optional[float] = None,
        spy_trend_pct: Optional[float] = None,
        vix_level: Optional[float] = None,
    ) -> RegimeState:
        """
        Determine regime from market indicators.

        Args:
            spy_price:     Latest SPY close.
            spy_ma50:      SPY 50-day moving average.
            spy_trend_pct: SPY trend as % (e.g. 0.05 = +5%).
            vix_level:     Current VIX closing level.

        Returns:
            RegimeState with the classified regime and adjustments.
        """
        # VIX-based volatility regime takes priority for sizing
        vol_regime: Optional[RegimeType] = None
        if vix_level is not None:
            if vix_level > 25:
                vol_regime = RegimeType.HIGH_VOL
            elif vix_level < 15:
                vol_regime = RegimeType.LOW_VOL

        # Trend regime from SPY
        trend_regime: Optional[RegimeType] = None
        if spy_price is not None and spy_ma50 is not None and spy_trend_pct is not None:
            if spy_price > spy_ma50 and spy_trend_pct > 0.03:
                trend_regime = RegimeType.BULL
            elif spy_price < spy_ma50 and spy_trend_pct < -0.03:
                trend_regime = RegimeType.BEAR

        # Combine: trend regime dominates for EV; vol regime adjusts sizing
        if trend_regime == RegimeType.BEAR:
            # Bear overrides everything — reduce risk
            rules = REGIME_RULES[RegimeType.BEAR]
            regime = RegimeType.BEAR
        elif trend_regime == RegimeType.BULL:
            rules = REGIME_RULES[RegimeType.BULL].copy()
            regime = RegimeType.BULL
            # If also high-vol, blend the size reduction
            if vol_regime == RegimeType.HIGH_VOL:
                rules["size_mult"] = REGIME_RULES[RegimeType.HIGH_VOL]["size_mult"]
        elif vol_regime is not None:
            rules = REGIME_RULES[vol_regime]
            regime = vol_regime
        else:
            rules = REGIME_RULES[RegimeType.NEUTRAL]
            regime = RegimeType.NEUTRAL

        state = RegimeState(
            regime=regime,
            ev_adjustment=rules["ev_adj"],
            position_size_mult=rules["size_mult"],
        )
        logger.debug("Regime classified: %s (EV adj=%.2f, size mult=%.2f)", regime.value, state.ev_adjustment, state.position_size_mult)
        return state

    def from_db(self, date_str: Optional[str] = None) -> RegimeState:
        """
        Load regime from the database Regime table.

        Falls back to NEUTRAL if no row is found.

        Args:
            date_str: ISO date string. None = latest.

        Returns:
            RegimeState.
        """
        with session_scope() as session:
            query = select(Regime).order_by(Regime.date.desc()).limit(1)
            if date_str:
                query = select(Regime).where(Regime.date == date_str)

            row = session.execute(query).scalar_one_or_none()

            if row is None:
                logger.warning("No regime data found, defaulting to NEUTRAL")
                return RegimeState(
                    regime=RegimeType.NEUTRAL,
                    ev_adjustment=0.0,
                    position_size_mult=1.0,
                )

            # We don't have SPY trend % stored directly — approximate from flags
            vix = row.vix_level
            is_bull = row.spy_above_200ma and row.risk_on_equities

            return self.classify(
                spy_price=1.0 if is_bull else 0.0,    # proxy
                spy_ma50=0.5,                          # proxy
                spy_trend_pct=0.05 if is_bull else -0.05,
                vix_level=vix,
            )


# ============================================================================
# Tier 1 Filter (91.7% hit rate on backtest)
# ============================================================================

@dataclass
class Tier1Result:
    """Result of the Tier 1 high-conviction filter."""

    passes: bool
    reason: str
    score: Optional[float] = None
    max_drawdown_60d: Optional[float] = None
    rsi: Optional[float] = None


def tier1_filter(
    score: float,
    max_drawdown_60d: float,
    rsi: float,
    volatility_20d: float,
    max_drawdown_20d: float,
) -> Tier1Result:
    """
    Tier 1 ultra-high-conviction filter: 91.7% hit rate on backtest.

    Inclusion: score >= 13 AND max_drawdown_60d >= 55% AND rsi <= 35
    Exclusion: volatility_20d <= 4% (fake-outs) OR max_drawdown_20d >= 50% (falling knives)

    Args:
        score:            Empirical combo score (0-20 scale).
        max_drawdown_60d: Max drawdown over 60 days (e.g. 0.55 = 55%).
        rsi:              Current RSI-14 value.
        volatility_20d:   20-day annualised volatility (e.g. 0.04 = 4%).
        max_drawdown_20d: Max drawdown over 20 days (e.g. 0.50 = 50%).

    Returns:
        Tier1Result with pass/fail and reason.
    """
    # Exclusion rules first
    if volatility_20d <= 0.04:
        return Tier1Result(
            passes=False,
            reason=f"Excluded: vol_20d={volatility_20d:.1%} <= 4% (fake-out risk)",
            score=score, max_drawdown_60d=max_drawdown_60d, rsi=rsi,
        )

    if max_drawdown_20d >= 0.50:
        return Tier1Result(
            passes=False,
            reason=f"Excluded: max_dd_20d={max_drawdown_20d:.1%} >= 50% (falling knife)",
            score=score, max_drawdown_60d=max_drawdown_60d, rsi=rsi,
        )

    # Inclusion rules
    passes = score >= 13 and max_drawdown_60d >= 0.55 and rsi <= 35

    if passes:
        reason = (
            f"TIER 1 PASS: score={score:.1f} dd60={max_drawdown_60d:.1%} rsi={rsi:.1f}"
        )
        logger.info(reason)
    else:
        parts = []
        if score < 13:
            parts.append(f"score={score:.1f}<13")
        if max_drawdown_60d < 0.55:
            parts.append(f"dd60={max_drawdown_60d:.1%}<55%")
        if rsi > 35:
            parts.append(f"rsi={rsi:.1f}>35")
        reason = f"Tier 1 fail: {', '.join(parts)}"

    return Tier1Result(
        passes=passes,
        reason=reason,
        score=score,
        max_drawdown_60d=max_drawdown_60d,
        rsi=rsi,
    )


# ============================================================================
# Empirical Scorer — hybrid of combo matching + quantum_score
# ============================================================================

@dataclass
class EmpiricalResult:
    """Full scoring output for one symbol."""

    symbol: str

    # Combo layer
    signals: SignalSnapshot
    matched_combos: List[ComboMatch]
    best_combo_hit_rate: float
    combo_score: float              # 0-100 scale from combo analysis

    # Trap detection
    trap_warnings: List[TrapWarning]
    has_unmitigated_traps: bool

    # Regime
    regime: RegimeState

    # Position sizing
    kelly: Optional[KellyResult] = None
    exit_plan: Optional[ExitPlan] = None

    # Hybrid score
    quantum_score: Optional[int] = None       # from Ridge model
    hybrid_score: float = 0.0                 # blended final score (0-100)
    conviction: str = "LOW"

    # Tier 1
    tier1: Optional[Tier1Result] = None


class EmpiricalScorer:
    """
    Combines empirical combo matching with the existing Ridge regression
    quantum_score to produce a hybrid score.

    Hybrid formula:
        hybrid = COMBO_WEIGHT * combo_score + RIDGE_WEIGHT * quantum_score
        adjusted by regime EV modifier

    The combo_score is derived from:
        1. Best matched combo hit rate (scaled 0-100)
        2. Number of combos matched (bonus)
        3. Continuous signal strengths (vol_zscore magnitude, momentum reversal depth)
    """

    # Blending weights — combo evidence gets 60%, Ridge ML gets 40%
    COMBO_WEIGHT = 0.60
    RIDGE_WEIGHT = 0.40

    def __init__(self):
        self.combo_matcher = ComboMatcher()
        self.trap_detector = TrapDetector()
        self.regime_adjuster = RegimeAdjuster()
        self.kelly_sizer = KellyPositionSizer()
        self.profit_calc = ProfitTargetCalculator()

    def score_symbol(
        self,
        symbol: str,
        df: pd.DataFrame,
        quantum_score: Optional[int] = None,
        entry_price: Optional[float] = None,
        regime: Optional[RegimeState] = None,
        max_drawdown_60d: Optional[float] = None,
        max_drawdown_20d: Optional[float] = None,
    ) -> EmpiricalResult:
        """
        Full empirical scoring pipeline for one symbol.

        Args:
            symbol:           Ticker symbol.
            df:               OHLCV DataFrame sorted ascending by date.
            quantum_score:    Existing Ridge model score (0-100), or None.
            entry_price:      Current price for exit-plan computation.
            regime:           Pre-computed regime (None = load from DB).
            max_drawdown_60d: 60-day max drawdown (for Tier 1 filter).
            max_drawdown_20d: 20-day max drawdown (for Tier 1 exclusion).

        Returns:
            EmpiricalResult with all scoring layers populated.
        """
        _require_ohlcv(df)

        # 1. Compute signals
        snap = compute_all_signals(symbol, df)

        # 2. Match combos
        combos = self.combo_matcher.match(snap)
        best_hit = max((c.hit_rate for c in combos), default=0.0)

        # 3. Compute combo_score (0-100)
        combo_score = self._compute_combo_score(snap, combos, best_hit)

        # 4. Trap detection
        traps = self.trap_detector.check(snap)
        has_unmitigated = any(not t.mitigated for t in traps)

        # 5. Penalise combo_score if unmitigated traps are present
        if has_unmitigated and not combos:
            combo_score = max(0.0, combo_score * 0.50)

        # 6. Regime adjustment
        if regime is None:
            regime = self.regime_adjuster.from_db()

        # 7. Hybrid score
        if quantum_score is not None:
            raw_hybrid = (
                self.COMBO_WEIGHT * combo_score
                + self.RIDGE_WEIGHT * float(quantum_score)
            )
        else:
            raw_hybrid = combo_score

        # Apply regime EV adjustment
        hybrid = raw_hybrid * (1.0 + regime.ev_adjustment)
        hybrid = float(np.clip(hybrid, 0.0, 100.0))

        # 8. Conviction
        conviction = self._classify_conviction(hybrid, combos, has_unmitigated)

        # 9. Kelly sizing (use best combo hit rate as win probability)
        kelly_result: Optional[KellyResult] = None
        if best_hit > 0:
            kelly_result = self.kelly_sizer.compute(win_prob=best_hit)
            # Apply regime sizing multiplier
            if kelly_result.clamped_size > 0:
                adjusted_size = kelly_result.clamped_size * regime.position_size_mult
                kelly_result = KellyResult(
                    full_kelly=kelly_result.full_kelly,
                    fractional_kelly=kelly_result.fractional_kelly,
                    clamped_size=float(np.clip(adjusted_size, 0.02, 0.10)),
                    edge=kelly_result.edge,
                    payoff_ratio=kelly_result.payoff_ratio,
                    win_prob=kelly_result.win_prob,
                )

        # 10. Exit plan
        exit_plan: Optional[ExitPlan] = None
        if entry_price and entry_price > 0:
            exit_plan = self.profit_calc.plan(entry_price)

        # 11. Tier 1 check (if drawdown data is available)
        tier1_result: Optional[Tier1Result] = None
        if max_drawdown_60d is not None and max_drawdown_20d is not None:
            vol_20d = snap.rsi_14  # We'll use the Factors table volatility below
            # Use volatility from the df if we can compute it
            if len(df) >= 20:
                returns = np.diff(np.log(df["close"].values[-21:]))
                vol_20d_computed = float(np.std(returns) * np.sqrt(252))
            else:
                vol_20d_computed = 0.0

            rsi_for_tier1 = snap.rsi_14 if snap.rsi_14 is not None else 50.0
            tier1_result = tier1_filter(
                score=combo_score / 5.0,  # Rescale 0-100 to approx 0-20 for tier 1
                max_drawdown_60d=max_drawdown_60d,
                rsi=rsi_for_tier1,
                volatility_20d=vol_20d_computed,
                max_drawdown_20d=max_drawdown_20d,
            )

        result = EmpiricalResult(
            symbol=symbol,
            signals=snap,
            matched_combos=combos,
            best_combo_hit_rate=best_hit,
            combo_score=combo_score,
            trap_warnings=traps,
            has_unmitigated_traps=has_unmitigated,
            regime=regime,
            kelly=kelly_result,
            exit_plan=exit_plan,
            quantum_score=quantum_score,
            hybrid_score=hybrid,
            conviction=conviction,
            tier1=tier1_result,
        )

        logger.info(
            "%s => hybrid=%.1f combo=%.1f quantum=%s conviction=%s combos=%d traps=%d regime=%s",
            symbol,
            hybrid,
            combo_score,
            quantum_score,
            conviction,
            len(combos),
            len(traps),
            regime.label,
        )

        return result

    def _compute_combo_score(
        self,
        snap: SignalSnapshot,
        combos: List[ComboMatch],
        best_hit: float,
    ) -> float:
        """
        Derive a 0-100 combo score from signal strengths and matched combos.

        Components:
            - Base: best combo hit rate * 100 (0-58 range for top combo)
            - Bonus: +5 per additional matched combo
            - Volume strength: vol_zscore / 5 * 20 (up to +20)
            - Reversal depth: abs(momentum_10d) * 30 if negative (up to +15)
        """
        if not combos:
            # No combos matched — score from continuous signals only, heavily penalised
            base = 0.0
        else:
            base = best_hit * 100.0  # e.g. 58.3% -> 58.3

        # Multi-combo bonus
        bonus = max(0, (len(combos) - 1)) * 5.0

        # Volume strength bonus (diminishing returns via sqrt)
        vol_bonus = min(20.0, np.sqrt(max(0.0, snap.vol_zscore)) / np.sqrt(5.0) * 20.0)

        # Negative momentum = reversal setup (contrarian edge)
        mom_bonus = 0.0
        if snap.momentum_10d < 0:
            mom_bonus = min(15.0, abs(snap.momentum_10d) * 30.0)

        raw = base + bonus + vol_bonus + mom_bonus
        return float(np.clip(raw, 0.0, 100.0))

    def _classify_conviction(
        self,
        hybrid: float,
        combos: List[ComboMatch],
        has_traps: bool,
    ) -> str:
        """Map hybrid score to conviction label, downgrading if traps present."""
        if hybrid >= 80 and len(combos) >= 2 and not has_traps:
            return "MAX"
        elif hybrid >= 65 and combos:
            return "HIGH" if not has_traps else "MED"
        elif hybrid >= 50:
            return "MED"
        else:
            return "LOW"

    def score_from_db(
        self,
        symbol: str,
        regime: Optional[RegimeState] = None,
    ) -> Optional[EmpiricalResult]:
        """
        Load OHLCV from the PriceOHLC table and existing quantum_score from
        Predictions, then run the full empirical scorer.

        Args:
            symbol: Ticker symbol.
            regime: Pre-computed regime state (None = auto-load).

        Returns:
            EmpiricalResult or None if insufficient data.
        """
        with session_scope() as session:
            # Load OHLCV
            prices = session.execute(
                select(PriceOHLC)
                .where(PriceOHLC.symbol == symbol)
                .order_by(PriceOHLC.date)
            ).scalars().all()

            if not prices or len(prices) < 30:
                logger.warning("Insufficient OHLCV data for %s (%d rows)", symbol, len(prices) if prices else 0)
                return None

            df = pd.DataFrame([{
                "date": p.date,
                "open": p.open,
                "high": p.high,
                "low": p.low,
                "close": p.close,
                "volume": p.volume,
            } for p in prices])

            # Load existing quantum_score
            pred = session.execute(
                select(Predictions)
                .where(Predictions.symbol == symbol)
                .order_by(Predictions.date.desc())
                .limit(1)
            ).scalar_one_or_none()

            quantum_score = pred.quantum_score if pred else None
            entry_price = df["close"].iloc[-1]

        return self.score_symbol(
            symbol=symbol,
            df=df,
            quantum_score=quantum_score,
            entry_price=entry_price,
            regime=regime,
        )


# ============================================================================
# Batch scoring convenience
# ============================================================================

def score_universe(
    symbols: List[str],
    regime: Optional[RegimeState] = None,
) -> pd.DataFrame:
    """
    Score a list of symbols and return a sorted DataFrame.

    Args:
        symbols: List of ticker symbols.
        regime:  Pre-computed regime (None = auto-load once).

    Returns:
        DataFrame with columns: symbol, hybrid_score, combo_score, quantum_score,
        conviction, best_combo, n_combos, n_traps, regime, kelly_size.
    """
    scorer = EmpiricalScorer()

    if regime is None:
        regime = scorer.regime_adjuster.from_db()

    rows: List[Dict] = []
    for sym in symbols:
        result = scorer.score_from_db(sym, regime=regime)
        if result is None:
            continue

        rows.append({
            "symbol": result.symbol,
            "hybrid_score": round(result.hybrid_score, 1),
            "combo_score": round(result.combo_score, 1),
            "quantum_score": result.quantum_score,
            "conviction": result.conviction,
            "best_combo": result.matched_combos[0].name if result.matched_combos else None,
            "best_hit_rate": round(result.best_combo_hit_rate, 3),
            "n_combos": len(result.matched_combos),
            "n_traps": len(result.trap_warnings),
            "regime": result.regime.label,
            "kelly_size": round(result.kelly.clamped_size, 4) if result.kelly else 0.0,
            "tier1_pass": result.tier1.passes if result.tier1 else None,
        })

    if not rows:
        logger.warning("No symbols scored successfully")
        return pd.DataFrame()

    df = pd.DataFrame(rows).sort_values("hybrid_score", ascending=False).reset_index(drop=True)
    logger.info("Scored %d symbols. Top 5:\n%s", len(df), df.head().to_string(index=False))
    return df
