"""Dataclasses describing outbound alert payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class BaseAlert:
    """Normalized alert payload shared across notification backends."""

    ticker: str
    alert_type: str
    title: str
    body: str
    priority: int = 3
    tags: List[str] = field(default_factory=list)
    click_url: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    data: Dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> Dict[str, Any]:
        """Return a JSON-serializable alert record."""
        return {
            "ticker": self.ticker,
            "alert_type": self.alert_type,
            "title": self.title,
            "body": self.body,
            "priority": self.priority,
            "tags": list(self.tags),
            "click_url": self.click_url,
            "timestamp": self.timestamp,
            "data": dict(self.data),
        }


@dataclass
class ComboAlert(BaseAlert):
    """Triggered when a new empirical combo becomes active."""

    combo_name: str = ""
    hit_rate: float = 0.0

    @classmethod
    def from_result(
        cls,
        ticker: str,
        combo_name: str,
        hit_rate: float,
        price: float,
        stop: float,
        t1: float,
        click_url: Optional[str] = None,
    ) -> "ComboAlert":
        hit_rate_pct = round(hit_rate * 100, 1)
        body = (
            f"{ticker}: {combo_name} combo active - {hit_rate_pct}% hit rate - "
            f"Entry ${price:.2f}, Stop ${stop:.2f}, T1 ${t1:.2f}"
        )
        return cls(
            ticker=ticker,
            alert_type="combo",
            title=f"{ticker} combo active",
            body=body,
            priority=4,
            tags=["combo", "alpha"],
            click_url=click_url,
            combo_name=combo_name,
            hit_rate=hit_rate,
            data={"combo_name": combo_name, "hit_rate": hit_rate},
        )


@dataclass
class TrapClearedAlert(BaseAlert):
    """Triggered when a previously unmitigated trap becomes volume-confirmed."""

    trap_name: str = ""

    @classmethod
    def from_result(
        cls,
        ticker: str,
        trap_name: str,
        score: float,
        price: float,
        click_url: Optional[str] = None,
    ) -> "TrapClearedAlert":
        return cls(
            ticker=ticker,
            alert_type="trap_cleared",
            title=f"{ticker} trap cleared",
            body=(
                f"{ticker}: {trap_name} trap is now volume-mitigated - "
                f"score {score:.0f} at ${price:.2f}"
            ),
            priority=3,
            tags=["trap", "cleared"],
            click_url=click_url,
            trap_name=trap_name,
            data={"trap_name": trap_name, "score": score, "price": price},
        )


@dataclass
class Tier1Alert(BaseAlert):
    """Triggered when a symbol qualifies for Tier 1 status."""

    reason: str = ""

    @classmethod
    def from_result(
        cls,
        ticker: str,
        score: float,
        reason: str,
        price: float,
        stop: float,
        t1: float,
        click_url: Optional[str] = None,
    ) -> "Tier1Alert":
        return cls(
            ticker=ticker,
            alert_type="tier1",
            title=f"{ticker} Tier 1 setup",
            body=(
                f"{ticker}: Tier 1 eligible - score {score:.0f} - "
                f"Entry ${price:.2f}, Stop ${stop:.2f}, T1 ${t1:.2f}"
            ),
            priority=5,
            tags=["tier1", "urgent"],
            click_url=click_url,
            reason=reason,
            data={"reason": reason, "score": score},
        )


@dataclass
class NewHighConfAlert(BaseAlert):
    """Triggered when a symbol crosses the high-confidence score threshold."""

    @classmethod
    def from_result(
        cls,
        ticker: str,
        score: float,
        price: float,
        stop: float,
        t1: float,
        click_url: Optional[str] = None,
    ) -> "NewHighConfAlert":
        return cls(
            ticker=ticker,
            alert_type="high_confidence",
            title=f"{ticker} high-confidence setup",
            body=(
                f"{ticker}: score crossed 70+ - score {score:.0f} - "
                f"Entry ${price:.2f}, Stop ${stop:.2f}, T1 ${t1:.2f}"
            ),
            priority=3,
            tags=["high-conf", "setup"],
            click_url=click_url,
            data={"score": score},
        )
