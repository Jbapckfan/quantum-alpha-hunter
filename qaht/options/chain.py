"""
Options chain analysis module.

Fetches, parses, filters, and groups a full options chain with Greeks
from Polygon via :class:`~qaht.options.polygon_adapter.PolygonAdapter`.
Provides helpers for mid-price computation, DTE/strike filtering, and
expiration grouping that are consumed by the strategy and scanner modules.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Sequence

from .polygon_adapter import PolygonAdapter

logger = logging.getLogger("qaht.options.chain")


# ------------------------------------------------------------------
# Data structures
# ------------------------------------------------------------------

@dataclass
class OptionLeg:
    """Single option contract with computed mid price."""

    contract_type: str          # "call" or "put"
    strike: float
    expiration: str             # ISO date
    dte: int
    bid: Optional[float] = None
    ask: Optional[float] = None
    mid: Optional[float] = None
    iv: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    vega: Optional[float] = None
    theta: Optional[float] = None
    open_interest: Optional[int] = None
    volume: Optional[int] = None

    @property
    def has_quote(self) -> bool:
        return self.mid is not None and self.mid > 0


@dataclass
class ParsedChain:
    """Full parsed options chain for a single underlying."""

    underlying: str
    underlying_price: float
    legs: List[OptionLeg] = field(default_factory=list)
    expirations: List[str] = field(default_factory=list)

    @property
    def calls(self) -> List[OptionLeg]:
        return [l for l in self.legs if l.contract_type == "call"]

    @property
    def puts(self) -> List[OptionLeg]:
        return [l for l in self.legs if l.contract_type == "put"]

    def by_expiration(self) -> Dict[str, List[OptionLeg]]:
        """Group legs by expiration date string."""
        groups: Dict[str, List[OptionLeg]] = defaultdict(list)
        for leg in self.legs:
            groups[leg.expiration].append(leg)
        return dict(groups)


# ------------------------------------------------------------------
# Mid-price helpers
# ------------------------------------------------------------------

def compute_mid(bid: Optional[float], ask: Optional[float], fallback: Optional[float] = None) -> Optional[float]:
    """Compute mid price from bid/ask; fall back to *fallback* if both are missing."""
    if bid is not None and ask is not None and bid >= 0 and ask >= 0:
        return round((bid + ask) / 2.0, 4)
    if bid is not None and bid > 0:
        return round(bid, 4)
    if ask is not None and ask > 0:
        return round(ask, 4)
    return fallback


def mid_price(leg: OptionLeg) -> float:
    """Return best-effort mid price for a leg, defaulting to 0."""
    if leg.mid is not None and leg.mid > 0:
        return leg.mid
    return compute_mid(leg.bid, leg.ask) or 0.0


# ------------------------------------------------------------------
# Fetch + parse
# ------------------------------------------------------------------

async def fetch_and_parse(
    adapter: PolygonAdapter,
    underlying: str,
) -> ParsedChain:
    """Fetch the options chain from Polygon and return a :class:`ParsedChain`.

    Also performs a ticker snapshot to get an accurate underlying price if the
    chain data does not supply one.
    """
    raw_options = await adapter.get_options_chain(underlying)

    underlying_price: Optional[float] = None
    legs: List[OptionLeg] = []

    for raw in raw_options:
        # Capture underlying price from first contract that has it
        if underlying_price is None and raw.get("underlying_price"):
            underlying_price = raw["underlying_price"]

        leg = OptionLeg(
            contract_type=raw["contract_type"],
            strike=raw["strike"],
            expiration=raw["expiration"],
            dte=raw["dte"],
            bid=raw.get("bid"),
            ask=raw.get("ask"),
            mid=raw.get("mid"),
            iv=raw.get("iv"),
            delta=raw.get("delta"),
            gamma=raw.get("gamma"),
            vega=raw.get("vega"),
            theta=raw.get("theta"),
            open_interest=raw.get("open_interest"),
            volume=raw.get("volume"),
        )
        # Ensure mid is always computed
        if leg.mid is None:
            leg.mid = compute_mid(leg.bid, leg.ask)
        legs.append(leg)

    # Fallback: get price from equity snapshot
    if underlying_price is None:
        try:
            snap = await adapter.get_snapshot(underlying)
            underlying_price = snap["price"]
        except Exception:
            underlying_price = 0.0
            logger.warning(
                "Could not determine underlying price for %s", underlying
            )

    # Deduplicate expiration list, sorted ascending
    expirations = sorted({leg.expiration for leg in legs})

    chain = ParsedChain(
        underlying=underlying.upper(),
        underlying_price=round(underlying_price, 2),
        legs=legs,
        expirations=expirations,
    )
    logger.info(
        "Parsed chain for %s: %d legs, %d expirations, price=%.2f",
        chain.underlying,
        len(legs),
        len(expirations),
        chain.underlying_price,
    )
    return chain


# ------------------------------------------------------------------
# Filters
# ------------------------------------------------------------------

def filter_by_dte(
    legs: Sequence[OptionLeg],
    min_dte: int = 0,
    max_dte: int = 9999,
) -> List[OptionLeg]:
    """Return legs whose DTE falls within [min_dte, max_dte]."""
    return [l for l in legs if min_dte <= l.dte <= max_dte]


def filter_by_strike_range(
    legs: Sequence[OptionLeg],
    low: float,
    high: float,
) -> List[OptionLeg]:
    """Return legs whose strike is within [low, high]."""
    return [l for l in legs if low <= l.strike <= high]


def filter_by_expiration(
    legs: Sequence[OptionLeg],
    target_date: str,
    max_drift_days: int = 14,
) -> List[OptionLeg]:
    """Return legs whose expiration is within *max_drift_days* of *target_date*.

    Parameters
    ----------
    target_date : str
        ISO date string ``YYYY-MM-DD``.
    max_drift_days : int
        Maximum calendar-day distance from *target_date*.
    """
    try:
        target = date.fromisoformat(target_date)
    except (ValueError, TypeError):
        logger.error("Invalid target_date: %s", target_date)
        return []

    result = []
    for leg in legs:
        try:
            exp = date.fromisoformat(leg.expiration)
        except (ValueError, TypeError):
            continue
        if abs((exp - target).days) <= max_drift_days:
            result.append(leg)
    return result


def filter_calls(legs: Sequence[OptionLeg]) -> List[OptionLeg]:
    """Return only call legs."""
    return [l for l in legs if l.contract_type == "call"]


def filter_puts(legs: Sequence[OptionLeg]) -> List[OptionLeg]:
    """Return only put legs."""
    return [l for l in legs if l.contract_type == "put"]


def filter_quoted(legs: Sequence[OptionLeg]) -> List[OptionLeg]:
    """Return only legs with a positive mid price."""
    return [l for l in legs if l.has_quote]


def group_by_expiration(legs: Sequence[OptionLeg]) -> Dict[str, List[OptionLeg]]:
    """Group legs by expiration date string, sorted ascending."""
    groups: Dict[str, List[OptionLeg]] = defaultdict(list)
    for leg in legs:
        groups[leg.expiration].append(leg)
    return dict(sorted(groups.items()))
