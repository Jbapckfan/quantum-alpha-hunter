"""
Options strategy calculators -- ported from the SPY Options Engine frontend JS.

Three calculators:

1. **Target-Price Calculator** -- given a ticker, current price, target price,
   and target date, generate long call / put and debit-spread strategies ranked
   by ROI at target.

2. **LEAPS Strategy Builder** -- given a :class:`LeapsCandidate` and a parsed
   options chain, build long LEAP call, PMCC, long LEAP put, and diagonal put
   strategies.

3. **Covered Call Finder** -- given a ticker and strategy preference (keep /
   okay / max income), filter for covered-call candidates by delta range and
   compute annualised returns.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Sequence

from .chain import OptionLeg, ParsedChain, mid_price, filter_by_dte, filter_calls, filter_puts, filter_quoted

logger = logging.getLogger("qaht.options.strategies")


# ------------------------------------------------------------------
# Shared data structures
# ------------------------------------------------------------------

@dataclass
class StrategyLeg:
    """A single leg in a multi-leg strategy."""
    side: str        # "long" or "short"
    option_type: str  # "call" or "put"
    strike: float
    dte: Optional[int] = None


@dataclass
class StrategyResult:
    """Computed strategy with P&L at the scenario price."""

    kind: str                   # e.g. "Long Call", "Call Debit Spread"
    direction: str              # "bull" or "bear"
    legs: List[StrategyLeg]
    expiration: str = ""
    dte: int = 0
    cost: float = 0.0          # total debit in dollars (per 1 contract = 100 shares)
    payoff_at_target: float = 0.0
    profit_at_target: float = 0.0
    roi_at_target: float = 0.0
    breakeven: float = 0.0
    max_loss: float = 0.0
    max_profit: float = 0.0    # math.inf for uncapped
    scenario_price: float = 0.0
    note: str = ""


# =====================================================================
# 1. Target-Price Calculator
# =====================================================================

def target_price_strategies(
    chain: ParsedChain,
    target_price: float,
    target_date: str,
    view: str = "bull",
    max_dte_drift: int = 14,
    capital: float = 1000.0,
    current_price: Optional[float] = None,
    top_n: int = 10,
) -> List[StrategyResult]:
    """Generate and rank strategies for a target-price scenario.

    Parameters
    ----------
    chain : ParsedChain
        Parsed options chain from :func:`chain.fetch_and_parse`.
    target_price : float
        The user's price target for *underlying*.
    target_date : str
        ISO date ``YYYY-MM-DD`` by which the target should be reached.
    view : str
        ``"bull"`` or ``"bear"``.
    max_dte_drift : int
        Maximum calendar days between available expirations and *target_date*.
    capital : float
        Approximate capital budget per idea (used to cap spread width).
    current_price : float, optional
        Override the chain's underlying price.
    top_n : int
        Return at most this many strategies.

    Returns
    -------
    list[StrategyResult]
        Strategies with positive ROI at target, ranked by ROI descending.
    """
    s0 = current_price or chain.underlying_price
    st = target_price
    if not s0 or s0 <= 0:
        logger.error("No valid current price for target-price calc")
        return []

    today_str = date.today().isoformat()

    # Filter legs near the target date
    near: List[OptionLeg] = []
    try:
        target_d = date.fromisoformat(target_date)
    except (ValueError, TypeError):
        logger.error("Invalid target_date: %s", target_date)
        return []

    for leg in chain.legs:
        try:
            exp_d = date.fromisoformat(leg.expiration)
        except (ValueError, TypeError):
            continue
        days_diff = (exp_d - target_d).days
        # Only include options expiring ON or AFTER the target date, within drift
        if -max_dte_drift <= days_diff <= max_dte_drift and exp_d >= target_d:
            near.append(leg)

    if not near:
        logger.info("No options within %d days of target date %s", max_dte_drift, target_date)
        return []

    # Group by expiration
    grouped: Dict[str, List[OptionLeg]] = {}
    for leg in near:
        grouped.setdefault(leg.expiration, []).append(leg)

    strategies: List[StrategyResult] = []

    for exp, opts in grouped.items():
        dte = _days_between(today_str, exp)

        calls = sorted(filter_quoted(filter_calls(opts)), key=lambda l: l.strike)
        puts = sorted(filter_quoted(filter_puts(opts)), key=lambda l: l.strike)

        if view == "bull":
            _add_long_calls(strategies, calls, st, exp, dte)
            _add_call_debit_spreads(strategies, calls, st, exp, dte, capital)

        if view == "bear":
            _add_long_puts(strategies, puts, st, exp, dte)
            _add_put_debit_spreads(strategies, puts, st, exp, dte, capital)

    # Keep only positive-ROI ideas, rank by ROI then profit
    positive = [s for s in strategies if s.roi_at_target > 0]
    positive.sort(key=lambda s: (s.roi_at_target, s.profit_at_target), reverse=True)
    return positive[:top_n]


# ------------------------------------------------------------------
# Target-price internals
# ------------------------------------------------------------------

def _days_between(a: str, b: str) -> int:
    try:
        da = date.fromisoformat(a)
        db = date.fromisoformat(b)
        return (db - da).days
    except (ValueError, TypeError):
        return 0


def _add_long_calls(
    out: List[StrategyResult],
    calls: List[OptionLeg],
    st: float,
    exp: str,
    dte: int,
) -> None:
    for c in calls:
        premium = mid_price(c) * 100
        if premium <= 0:
            continue
        payoff = max(st - c.strike, 0) * 100
        profit = payoff - premium
        roi = profit / premium if premium > 0 else -1

        out.append(
            StrategyResult(
                kind="Long Call",
                direction="bull",
                legs=[StrategyLeg("long", "call", c.strike)],
                expiration=exp,
                dte=dte,
                cost=premium,
                payoff_at_target=payoff,
                profit_at_target=profit,
                roi_at_target=roi,
                breakeven=c.strike + premium / 100,
                max_loss=premium,
                max_profit=math.inf,
                scenario_price=st,
            )
        )


def _add_call_debit_spreads(
    out: List[StrategyResult],
    calls: List[OptionLeg],
    st: float,
    exp: str,
    dte: int,
    capital: float,
) -> None:
    for i in range(len(calls)):
        for j in range(i + 1, len(calls)):
            c_buy = calls[i]
            c_sell = calls[j]
            k1 = c_buy.strike
            k2 = c_sell.strike
            buy_prem = mid_price(c_buy) * 100
            sell_prem = mid_price(c_sell) * 100
            net_debit = buy_prem - sell_prem
            if net_debit <= 0 or net_debit > capital * 3:
                continue

            spread_width = (k2 - k1) * 100
            if st <= k1:
                payoff = 0.0
            elif st >= k2:
                payoff = spread_width
            else:
                payoff = (st - k1) * 100

            profit = payoff - net_debit
            roi = profit / net_debit if net_debit > 0 else -1

            out.append(
                StrategyResult(
                    kind="Call Debit Spread",
                    direction="bull",
                    legs=[
                        StrategyLeg("long", "call", k1),
                        StrategyLeg("short", "call", k2),
                    ],
                    expiration=exp,
                    dte=dte,
                    cost=net_debit,
                    payoff_at_target=payoff,
                    profit_at_target=profit,
                    roi_at_target=roi,
                    breakeven=k1 + net_debit / 100,
                    max_loss=net_debit,
                    max_profit=spread_width - net_debit,
                    scenario_price=st,
                )
            )


def _add_long_puts(
    out: List[StrategyResult],
    puts: List[OptionLeg],
    st: float,
    exp: str,
    dte: int,
) -> None:
    for p in puts:
        premium = mid_price(p) * 100
        if premium <= 0:
            continue
        payoff = max(p.strike - st, 0) * 100
        profit = payoff - premium
        roi = profit / premium if premium > 0 else -1

        out.append(
            StrategyResult(
                kind="Long Put",
                direction="bear",
                legs=[StrategyLeg("long", "put", p.strike)],
                expiration=exp,
                dte=dte,
                cost=premium,
                payoff_at_target=payoff,
                profit_at_target=profit,
                roi_at_target=roi,
                breakeven=p.strike - premium / 100,
                max_loss=premium,
                max_profit=math.inf,
                scenario_price=st,
            )
        )


def _add_put_debit_spreads(
    out: List[StrategyResult],
    puts: List[OptionLeg],
    st: float,
    exp: str,
    dte: int,
    capital: float,
) -> None:
    for i in range(len(puts)):
        for j in range(i + 1, len(puts)):
            p_buy = puts[j]     # higher strike (more expensive)
            p_sell = puts[i]    # lower strike
            if p_buy.strike <= p_sell.strike:
                continue

            k1 = p_buy.strike
            k2 = p_sell.strike
            buy_prem = mid_price(p_buy) * 100
            sell_prem = mid_price(p_sell) * 100
            net_debit = buy_prem - sell_prem
            if net_debit <= 0 or net_debit > capital * 3:
                continue

            spread_width = (k1 - k2) * 100
            if st >= k1:
                payoff = 0.0
            elif st <= k2:
                payoff = spread_width
            else:
                payoff = (k1 - st) * 100

            profit = payoff - net_debit
            roi = profit / net_debit if net_debit > 0 else -1

            out.append(
                StrategyResult(
                    kind="Put Debit Spread",
                    direction="bear",
                    legs=[
                        StrategyLeg("long", "put", k1),
                        StrategyLeg("short", "put", k2),
                    ],
                    expiration=exp,
                    dte=dte,
                    cost=net_debit,
                    payoff_at_target=payoff,
                    profit_at_target=profit,
                    roi_at_target=roi,
                    breakeven=k1 - net_debit / 100,
                    max_loss=net_debit,
                    max_profit=spread_width - net_debit,
                    scenario_price=st,
                )
            )


# =====================================================================
# 2. LEAPS Strategy Builder
# =====================================================================

def build_leaps_strategies(
    chain: ParsedChain,
    view: str = "bull",
    bull_target: Optional[float] = None,
    bear_target: Optional[float] = None,
    min_leap_dte: int = 270,
    capital: float = 5000.0,
) -> List[StrategyResult]:
    """Build LEAPS strategies for a single underlying.

    Strategies produced
    ~~~~~~~~~~~~~~~~~~~
    **Bull view:**
      - Long LEAP Call (~90% strike, high DTE)
      - Poor Man's Covered Call (PMCC): long LEAP + short 30-60 DTE ~110%

    **Bear view:**
      - Long LEAP Put (~110% strike)
      - Diagonal Put Spread: long LEAP put + short 30-60 DTE ~90%

    Parameters
    ----------
    chain : ParsedChain
        Full parsed chain for the underlying.
    view : str
        ``"bull"`` or ``"bear"``.
    bull_target / bear_target : float, optional
        Scenario prices.  Default to +30% / -30% of current price.
    min_leap_dte : int
        Minimum DTE to qualify as a LEAP.
    capital : float
        Approximate capital budget (used for sizing notes only).

    Returns
    -------
    list[StrategyResult]
        Strategies with positive scenario ROI, best first.
    """
    s0 = chain.underlying_price
    if not s0 or s0 <= 0:
        return []

    all_legs = chain.legs
    leap_opts = filter_by_dte(all_legs, min_dte=min_leap_dte)
    if not leap_opts:
        logger.info("No LEAP-dated options for %s (min DTE=%d)", chain.underlying, min_leap_dte)
        return []

    # Pick the nearest LEAP expiration
    best_exp: Optional[str] = None
    best_dte = 99999
    for o in leap_opts:
        if o.dte < best_dte:
            best_dte = o.dte
            best_exp = o.expiration
    leap_for_exp = [o for o in leap_opts if o.expiration == best_exp]

    calls = sorted(filter_quoted(filter_calls(leap_for_exp)), key=lambda l: l.strike)
    puts = sorted(filter_quoted(filter_puts(leap_for_exp)), key=lambda l: l.strike)

    strategies: List[StrategyResult] = []

    # ------------------------------------------------------------------
    # Bull strategies
    # ------------------------------------------------------------------
    if view == "bull" and calls:
        st = bull_target or s0 * 1.3

        # Pick deep ITM call (~90% strike)
        target_itm = s0 * 0.9
        best_call = _closest(calls, target_itm, max_strike=s0 * 1.05)

        leap_prem = mid_price(best_call) * 100
        breakeven = best_call.strike + leap_prem / 100
        intrinsic = max(st - best_call.strike, 0) * 100
        profit = intrinsic - leap_prem
        roi = profit / leap_prem if leap_prem > 0 else -1

        strategies.append(
            StrategyResult(
                kind="Long LEAP Call",
                direction="bull",
                legs=[StrategyLeg("long", "call", best_call.strike, best_call.dte)],
                expiration=best_call.expiration,
                dte=best_call.dte,
                cost=leap_prem,
                payoff_at_target=intrinsic,
                profit_at_target=profit,
                roi_at_target=roi,
                breakeven=breakeven,
                max_loss=leap_prem,
                max_profit=math.inf,
                scenario_price=st,
                note=(
                    "Classic LEAP: deep trend exposure with limited capital "
                    "vs stock. Prefer ITM for higher delta and less theta burn."
                ),
            )
        )

        # PMCC: long LEAP call + short 30-60 DTE call at ~110%
        near_calls = sorted(
            filter_quoted(
                filter_calls(
                    filter_by_dte(all_legs, min_dte=30, max_dte=60)
                )
            ),
            key=lambda l: l.strike,
        )
        otm_near = [c for c in near_calls if c.strike >= s0 * 1.02]
        if otm_near:
            target_otm = s0 * 1.1
            short_call = _closest(otm_near, target_otm)
            short_prem = mid_price(short_call) * 100
            net_debit = leap_prem - short_prem
            spread_width = max(short_call.strike - best_call.strike, 0) * 100

            if st <= best_call.strike:
                payoff = 0.0
            elif st >= short_call.strike:
                payoff = spread_width
            else:
                payoff = (st - best_call.strike) * 100

            pmcc_profit = payoff - net_debit
            pmcc_roi = pmcc_profit / net_debit if net_debit > 0 else -1

            strategies.append(
                StrategyResult(
                    kind="Poor Man's Covered Call (PMCC)",
                    direction="bull",
                    legs=[
                        StrategyLeg("long", "call", best_call.strike, best_call.dte),
                        StrategyLeg("short", "call", short_call.strike, short_call.dte),
                    ],
                    expiration=best_call.expiration,
                    dte=best_call.dte,
                    cost=net_debit,
                    payoff_at_target=payoff,
                    profit_at_target=pmcc_profit,
                    roi_at_target=pmcc_roi,
                    breakeven=best_call.strike + net_debit / 100,
                    max_loss=net_debit,
                    max_profit=spread_width - net_debit,
                    scenario_price=st,
                    note=(
                        "Synthetic covered call with much less capital than "
                        "owning 100 shares. You give up some upside for "
                        "steady income."
                    ),
                )
            )

    # ------------------------------------------------------------------
    # Bear strategies
    # ------------------------------------------------------------------
    if view == "bear" and puts:
        st = bear_target or s0 * 0.7

        # Pick slightly ITM put (~110% strike)
        target_put_strike = s0 * 1.1
        best_put = _closest(puts, target_put_strike, min_strike=s0 * 0.95)

        leap_prem = mid_price(best_put) * 100
        breakeven = best_put.strike - leap_prem / 100
        intrinsic = max(best_put.strike - st, 0) * 100
        profit = intrinsic - leap_prem
        roi = profit / leap_prem if leap_prem > 0 else -1

        strategies.append(
            StrategyResult(
                kind="Long LEAP Put",
                direction="bear",
                legs=[StrategyLeg("long", "put", best_put.strike, best_put.dte)],
                expiration=best_put.expiration,
                dte=best_put.dte,
                cost=leap_prem,
                payoff_at_target=intrinsic,
                profit_at_target=profit,
                roi_at_target=roi,
                breakeven=breakeven,
                max_loss=leap_prem,
                max_profit=math.inf,
                scenario_price=st,
                note=(
                    "Long-term downside exposure with defined risk; behaves "
                    "like a leveraged short with capped loss."
                ),
            )
        )

        # Diagonal put spread: long LEAP put + short 30-60 DTE put at ~90%
        near_puts = sorted(
            filter_quoted(
                filter_puts(
                    filter_by_dte(all_legs, min_dte=30, max_dte=60)
                )
            ),
            key=lambda l: l.strike,
        )
        otm_near = [p for p in near_puts if p.strike <= s0 * 0.98]
        if otm_near:
            target_short = s0 * 0.9
            short_put = _closest(otm_near, target_short)
            short_prem = mid_price(short_put) * 100
            net_debit = leap_prem - short_prem
            spread_width = max(best_put.strike - short_put.strike, 0) * 100

            if st >= best_put.strike:
                payoff = 0.0
            elif st <= short_put.strike:
                payoff = spread_width
            else:
                payoff = (best_put.strike - st) * 100

            diag_profit = payoff - net_debit
            diag_roi = diag_profit / net_debit if net_debit > 0 else -1

            strategies.append(
                StrategyResult(
                    kind="Bear Put Diagonal",
                    direction="bear",
                    legs=[
                        StrategyLeg("long", "put", best_put.strike, best_put.dte),
                        StrategyLeg("short", "put", short_put.strike, short_put.dte),
                    ],
                    expiration=best_put.expiration,
                    dte=best_put.dte,
                    cost=net_debit,
                    payoff_at_target=payoff,
                    profit_at_target=diag_profit,
                    roi_at_target=diag_roi,
                    breakeven=best_put.strike - net_debit / 100,
                    max_loss=net_debit,
                    max_profit=spread_width - net_debit,
                    scenario_price=st,
                    note=(
                        "Diagonal put spread: defined risk short with added "
                        "income from nearer-term short put."
                    ),
                )
            )

    # Filter to positive ROI and sort
    result = [s for s in strategies if s.roi_at_target > 0]
    result.sort(key=lambda s: s.roi_at_target, reverse=True)
    return result


# =====================================================================
# 3. Covered Call Finder
# =====================================================================

@dataclass
class CoveredCallStrategy:
    """Predefined covered-call approach with delta bounds."""
    name: str
    delta_min: float
    delta_max: float
    description: str


COVERED_CALL_STRATEGIES = {
    "keep": CoveredCallStrategy(
        name="Keep Shares",
        delta_min=0.05,
        delta_max=0.15,
        description="Conservative: ~90% probability of keeping shares.",
    ),
    "okay": CoveredCallStrategy(
        name="Okay to Sell",
        delta_min=0.15,
        delta_max=0.30,
        description="Balanced: ~78% probability of keeping shares.",
    ),
    "max": CoveredCallStrategy(
        name="Max Income",
        delta_min=0.30,
        delta_max=0.50,
        description="Aggressive: ~60% probability of keeping shares.",
    ),
}


@dataclass
class CoveredCallResult:
    """A single covered-call candidate."""

    expiration: str
    dte: int
    strike: float
    premium: float               # mid price per share
    delta: Optional[float]
    iv: Optional[float]
    otm_pct: float               # how far OTM (%)
    annualized_return: float     # (premium/price)*(52/weeks)*100
    max_profit: float            # premium per share
    breakeven: float             # current_price - premium


def find_covered_calls(
    chain: ParsedChain,
    strategy: str = "keep",
    min_dte: int = 3,
    max_dte: int = 60,
) -> List[CoveredCallResult]:
    """Find covered-call candidates matching a strategy profile.

    Parameters
    ----------
    chain : ParsedChain
        Full parsed options chain.
    strategy : str
        One of ``"keep"``, ``"okay"``, ``"max"``.
    min_dte / max_dte : int
        DTE window for candidate selection.

    Returns
    -------
    list[CoveredCallResult]
        Candidates sorted by annualised return descending.
    """
    strat = COVERED_CALL_STRATEGIES.get(strategy)
    if strat is None:
        logger.error("Unknown covered-call strategy: %s", strategy)
        return []

    s0 = chain.underlying_price
    if not s0 or s0 <= 0:
        return []

    calls = filter_quoted(
        filter_calls(
            filter_by_dte(chain.legs, min_dte=min_dte, max_dte=max_dte)
        )
    )

    results: List[CoveredCallResult] = []
    for c in calls:
        # Filter by delta range
        delta = abs(c.delta) if c.delta is not None else None
        if delta is not None and not (strat.delta_min <= delta <= strat.delta_max):
            continue
        # If delta is missing, use OTM % as a rough proxy
        if delta is None:
            otm_frac = (c.strike - s0) / s0
            if otm_frac < 0.02 or otm_frac > 0.20:
                continue

        premium = mid_price(c)
        if premium <= 0:
            continue

        otm_pct = ((c.strike - s0) / s0) * 100
        weeks = max(c.dte / 7.0, 0.15)
        ann_ret = (premium / s0) * (52 / weeks) * 100

        results.append(
            CoveredCallResult(
                expiration=c.expiration,
                dte=c.dte,
                strike=c.strike,
                premium=round(premium, 2),
                delta=round(delta, 3) if delta is not None else None,
                iv=round(c.iv, 4) if c.iv is not None else None,
                otm_pct=round(otm_pct, 1),
                annualized_return=round(ann_ret, 1),
                max_profit=round(premium, 2),
                breakeven=round(s0 - premium, 2),
            )
        )

    results.sort(key=lambda r: r.annualized_return, reverse=True)
    return results


# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------

def _closest(
    legs: List[OptionLeg],
    target_strike: float,
    min_strike: Optional[float] = None,
    max_strike: Optional[float] = None,
) -> OptionLeg:
    """Return the leg whose strike is closest to *target_strike*.

    Optionally restrict to strikes within [min_strike, max_strike].
    Falls back to absolute-closest if no leg satisfies the bounds.
    """
    filtered = legs
    if min_strike is not None:
        filtered = [l for l in filtered if l.strike >= min_strike]
    if max_strike is not None:
        filtered = [l for l in filtered if l.strike <= max_strike]

    if not filtered:
        filtered = legs  # fall back

    return min(filtered, key=lambda l: abs(l.strike - target_strike))
