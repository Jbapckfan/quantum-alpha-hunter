"""
LEAPS trend scanner -- ported from the SPY Options Engine backend.

Scans a universe of tickers for strong momentum trends, computes
realised volatility and (optionally) 30-day implied volatility from the
options chain, sets price targets, and ranks candidates for LEAPS
strategies.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import List, Optional

from .polygon_adapter import PolygonAdapter

logger = logging.getLogger("qaht.options.leaps_scanner")

# Default universe when none is supplied
DEFAULT_UNIVERSE = ["SPY", "QQQ", "AAPL", "MSFT", "TSLA", "SMH", "XLF"]


# ------------------------------------------------------------------
# Data structures
# ------------------------------------------------------------------

@dataclass
class LeapsCandidate:
    """A single LEAPS candidate with momentum, vol, and price targets."""

    ticker: str
    current_price: float
    trend_score: float          # 0-1
    momentum_6m: float          # fractional return
    momentum_12m: float         # fractional return
    realized_vol_60d: float     # annualised
    iv_30d: Optional[float] = None   # average 30-day implied vol
    iv_rank: Optional[float] = None  # percentile (not yet implemented)
    bull_target: float = 0.0
    bear_target: float = 0.0
    sector: Optional[str] = None
    chart_url: Optional[str] = None


# ------------------------------------------------------------------
# Math helpers (ported from main.py)
# ------------------------------------------------------------------

def momentum(prices: List[float], lookback_days: int) -> Optional[float]:
    """Fractional momentum: (P_now - P_lookback) / P_lookback.

    Returns ``None`` if the series is shorter than *lookback_days*.
    """
    if len(prices) < lookback_days:
        return None
    p0 = prices[-lookback_days]
    p1 = prices[-1]
    if p0 <= 0:
        return None
    return (p1 - p0) / p0


def realized_vol(prices: List[float], window: int = 60) -> Optional[float]:
    """Annualised realised volatility from log returns over *window* days.

    Requires at least ``window + 1`` price observations.
    """
    if len(prices) < window + 1:
        return None
    rets: List[float] = []
    for i in range(-window, -1):
        p0 = prices[i - 1]
        p1 = prices[i]
        if p0 <= 0:
            continue
        rets.append(math.log(p1 / p0))
    if not rets:
        return None
    mean = sum(rets) / len(rets)
    var = sum((x - mean) ** 2 for x in rets) / len(rets)
    return math.sqrt(var) * math.sqrt(252.0)


def trend_score(mom6: float, mom12: float) -> float:
    """Blend 6-month and 12-month momentum into a 0-1 trend score.

    ``score = clamp(0.5 + (0.6*mom6 + 0.4*mom12) * 2, 0, 1)``
    """
    raw = 0.6 * mom6 + 0.4 * mom12
    return max(0.0, min(1.0, 0.5 + raw * 2.0))


# ------------------------------------------------------------------
# Core scanner
# ------------------------------------------------------------------

async def scan_leaps_candidates(
    adapter: PolygonAdapter,
    view: str = "bull",
    universe: Optional[List[str]] = None,
    min_trend: float = 0.6,
    limit: int = 10,
    fetch_iv: bool = True,
) -> List[LeapsCandidate]:
    """Scan *universe* for LEAPS candidates ranked by trend score.

    Parameters
    ----------
    adapter : PolygonAdapter
        Initialised Polygon adapter.
    view : str
        ``"bull"`` or ``"bear"`` -- determines filtering and sort direction.
    universe : list[str], optional
        Ticker symbols to scan.  Uses :data:`DEFAULT_UNIVERSE` when omitted.
    min_trend : float
        Minimum trend score for bulls (maximum for bears is ``1 - min_trend``).
    limit : int
        Maximum number of candidates to return.
    fetch_iv : bool
        If ``True``, attempt to fetch 30-day IV from the options chain for
        each candidate.  Slower but richer output.

    Returns
    -------
    list[LeapsCandidate]
        Ranked list of candidates, best first for the chosen *view*.
    """
    tickers = [t.strip().upper() for t in (universe or DEFAULT_UNIVERSE)]
    candidates: List[LeapsCandidate] = []

    for sym in tickers:
        try:
            candidate = await _evaluate_ticker(
                adapter, sym, view, min_trend, fetch_iv
            )
            if candidate is not None:
                candidates.append(candidate)
        except Exception:
            logger.warning("Failed to evaluate %s for LEAPS scan", sym, exc_info=True)
            continue

    # Sort: bulls want highest trend score first, bears want lowest
    if view == "bull":
        candidates.sort(key=lambda c: c.trend_score, reverse=True)
    else:
        candidates.sort(key=lambda c: c.trend_score)

    return candidates[:limit]


async def _evaluate_ticker(
    adapter: PolygonAdapter,
    sym: str,
    view: str,
    min_trend: float,
    fetch_iv: bool,
) -> Optional[LeapsCandidate]:
    """Evaluate a single ticker and return a candidate or ``None``."""
    bars_df = await adapter.get_daily_bars(sym, days=420)
    if bars_df.empty or len(bars_df) < 60:
        logger.debug("Insufficient bar data for %s (%d bars)", sym, len(bars_df))
        return None

    closes = bars_df["close"].dropna().tolist()
    if not closes:
        return None

    current = closes[-1]
    mom6 = momentum(closes, 126)    # ~6 months
    mom12 = momentum(closes, 252)   # ~12 months
    rv60 = realized_vol(closes, 60)

    if mom6 is None or mom12 is None or rv60 is None:
        logger.debug("Incomplete momentum/vol for %s", sym)
        return None

    tscore = trend_score(mom6, mom12)

    if view == "bull" and tscore < min_trend:
        return None
    if view == "bear" and tscore > (1 - min_trend):
        return None

    # Approximate 30-day IV from options chain (15-45 DTE, average)
    iv30: Optional[float] = None
    if fetch_iv:
        try:
            chain = await adapter.get_options_chain(sym)
            opts_30d = [
                o
                for o in chain
                if o.get("dte") is not None
                and 15 <= o["dte"] <= 45
                and o.get("iv") is not None
            ]
            if opts_30d:
                iv30 = sum(o["iv"] for o in opts_30d) / len(opts_30d)
        except Exception:
            logger.debug("IV fetch failed for %s, leaving iv_30d as None", sym)

    # Price targets derived from 12-month momentum
    abs_12m_move = abs(mom12) * current
    bull_target = current + 0.5 * abs_12m_move
    bear_target = current - 0.4 * abs_12m_move

    return LeapsCandidate(
        ticker=sym,
        current_price=round(current, 2),
        trend_score=round(tscore, 3),
        momentum_6m=round(mom6, 3),
        momentum_12m=round(mom12, 3),
        realized_vol_60d=round(rv60, 3),
        iv_30d=round(iv30, 4) if iv30 is not None else None,
        iv_rank=None,  # requires historical IV series -- future enhancement
        bull_target=round(bull_target, 2),
        bear_target=round(bear_target, 2),
    )
