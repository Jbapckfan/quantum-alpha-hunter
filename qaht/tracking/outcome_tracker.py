"""Outcome tracking for fired signals."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional

import yfinance as yf
from sqlalchemy import desc, select

from qaht.db import init_db, session_scope
from qaht.schemas import SignalEvent, SignalOutcome

logger = logging.getLogger("qaht.tracking.outcome_tracker")

_SYNTHETIC_SIGNALS = {
    "momentum_confirmation_bonus",
    "multiframe_bonus",
    "multiframe_penalty",
}


class OutcomeTracker:
    """Persist scan events and periodically evaluate their outcomes."""

    def __init__(self) -> None:
        init_db()

    def record_signals(self, scan_results: Iterable[Dict[str, Any]]) -> int:
        """Store fired signal events from a scan result set."""
        today = date.today().isoformat()
        inserted = 0

        with session_scope() as session:
            for result in scan_results:
                ticker = str(result.get("ticker", "")).upper()
                entry_price = result.get("price")
                score_at_fire = result.get("score")
                if not ticker or entry_price is None or score_at_fire is None:
                    continue

                combo_name = self._extract_combo_name(result)
                context = {
                    "stage": result.get("stage"),
                    "flags": result.get("flags", []),
                }

                for signal_name in self._extract_signal_names(result):
                    existing = session.execute(
                        select(SignalEvent).where(
                            SignalEvent.ticker == ticker,
                            SignalEvent.signal_name == signal_name,
                            SignalEvent.fired_date == today,
                        )
                    ).scalar_one_or_none()
                    if existing is not None:
                        continue

                    session.add(
                        SignalEvent(
                            ticker=ticker,
                            signal_name=signal_name,
                            fired_date=today,
                            entry_price=float(entry_price),
                            score_at_fire=float(score_at_fire),
                            combo_matched=combo_name,
                            stop_price=self._safe_float(result.get("stop")),
                            t1_price=self._safe_float(result.get("t1")),
                            t2_price=self._safe_float(result.get("t2")),
                            t3_price=self._safe_float(result.get("t3")),
                            context=context,
                        )
                    )
                    inserted += 1

        if inserted:
            logger.info("Recorded %d signal events", inserted)
        return inserted

    def check_outcomes(self) -> int:
        """Evaluate open events older than five days and append outcome rows."""
        cutoff = date.today() - timedelta(days=5)
        checked = 0

        with session_scope() as session:
            events = session.execute(
                select(SignalEvent).where(
                    SignalEvent.completed == False,  # noqa: E712
                    SignalEvent.fired_date <= cutoff.isoformat(),
                )
            ).scalars().all()

            for event in events:
                outcome = self._build_outcome(event)
                if outcome is None:
                    continue

                existing = session.execute(
                    select(SignalOutcome).where(
                        SignalOutcome.event_id == event.id,
                        SignalOutcome.check_date == outcome.check_date,
                    )
                ).scalar_one_or_none()
                if existing is None:
                    session.add(outcome)
                    checked += 1
                else:
                    existing.price_at_check = outcome.price_at_check
                    existing.return_pct = outcome.return_pct
                    existing.hit_t1 = outcome.hit_t1
                    existing.hit_t2 = outcome.hit_t2
                    existing.hit_t3 = outcome.hit_t3
                    existing.hit_stop = outcome.hit_stop
                    existing.days_elapsed = outcome.days_elapsed
                    existing.final = outcome.final

                if outcome.final or outcome.hit_stop:
                    event.completed = True
                    event.completed_at = datetime.utcnow().isoformat()

        if checked:
            logger.info("Recorded %d signal outcome checkpoints", checked)
        return checked

    def mark_completed(self, event_id: int) -> bool:
        """Mark a signal event complete."""
        with session_scope() as session:
            event = session.get(SignalEvent, event_id)
            if event is None:
                return False
            event.completed = True
            event.completed_at = datetime.utcnow().isoformat()
            return True

    def get_signal_stats(self, lookback_days: int = 90) -> List[Dict[str, Any]]:
        """Aggregate hit rates and returns per signal over a lookback window."""
        cutoff = date.today() - timedelta(days=lookback_days)
        stats: Dict[str, Dict[str, Any]] = {}

        with session_scope() as session:
            events = session.execute(
                select(SignalEvent).where(SignalEvent.fired_date >= cutoff.isoformat())
            ).scalars().all()

            for event in events:
                signal_stats = stats.setdefault(
                    event.signal_name,
                    {
                        "signal_name": event.signal_name,
                        "times_fired": 0,
                        "t1_hits": 0,
                        "win_count": 0,
                        "returns": [],
                        "avg_days_elapsed": [],
                    },
                )
                signal_stats["times_fired"] += 1

                latest = session.execute(
                    select(SignalOutcome)
                    .where(SignalOutcome.event_id == event.id)
                    .order_by(desc(SignalOutcome.days_elapsed))
                    .limit(1)
                ).scalar_one_or_none()

                if latest is None:
                    continue

                signal_stats["t1_hits"] += int(bool(latest.hit_t1))
                signal_stats["win_count"] += int(latest.return_pct > 0)
                signal_stats["returns"].append(float(latest.return_pct))
                signal_stats["avg_days_elapsed"].append(int(latest.days_elapsed))

        rows: List[Dict[str, Any]] = []
        for row in stats.values():
            times_fired = max(1, row["times_fired"])
            returns = row.pop("returns")
            elapsed = row.pop("avg_days_elapsed")
            row["hit_rate"] = round(row["t1_hits"] / times_fired, 4)
            row["avg_return"] = round(mean(returns), 4) if returns else 0.0
            row["win_rate"] = round(row["win_count"] / times_fired, 4)
            row["avg_days_elapsed"] = round(mean(elapsed), 1) if elapsed else 0.0
            rows.append(row)

        rows.sort(key=lambda item: (item["hit_rate"], item["avg_return"]), reverse=True)
        return rows

    def _build_outcome(self, event: SignalEvent) -> Optional[SignalOutcome]:
        try:
            history = yf.Ticker(event.ticker).history(start=event.fired_date, end=None)
        except Exception:
            logger.warning("Failed to fetch price history for %s", event.ticker, exc_info=True)
            return None

        if history.empty:
            return None

        latest_close = float(history["Close"].iloc[-1])
        max_high = float(history["High"].max())
        min_low = float(history["Low"].min())
        fired_dt = date.fromisoformat(event.fired_date)
        days_elapsed = max(0, (history.index[-1].date() - fired_dt).days)

        hit_t1 = bool(event.t1_price and max_high >= event.t1_price)
        hit_t2 = bool(event.t2_price and max_high >= event.t2_price)
        hit_t3 = bool(event.t3_price and max_high >= event.t3_price)
        hit_stop = bool(event.stop_price and min_low <= event.stop_price)
        final = days_elapsed >= 30 or hit_stop

        return SignalOutcome(
            event_id=event.id,
            check_date=date.today().isoformat(),
            price_at_check=latest_close,
            return_pct=((latest_close / event.entry_price) - 1.0) if event.entry_price else 0.0,
            hit_t1=hit_t1,
            hit_t2=hit_t2,
            hit_t3=hit_t3,
            hit_stop=hit_stop,
            days_elapsed=days_elapsed,
            final=final,
        )

    def _extract_signal_names(self, result: Dict[str, Any]) -> List[str]:
        breakdown = result.get("signal_breakdown", {}) or {}
        signals: List[str] = []
        for name in breakdown:
            if name.startswith("confluence_"):
                continue
            if name.startswith("rr_"):
                continue
            if name in _SYNTHETIC_SIGNALS:
                continue
            signals.append(name)
        return signals

    def _extract_combo_name(self, result: Dict[str, Any]) -> Optional[str]:
        if result.get("combo_name"):
            return str(result["combo_name"])
        combos = result.get("matched_combos") or []
        if combos:
            first = combos[0]
            if isinstance(first, dict):
                return str(first.get("name")) if first.get("name") else None
            return str(first)
        return None

    def _safe_float(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
