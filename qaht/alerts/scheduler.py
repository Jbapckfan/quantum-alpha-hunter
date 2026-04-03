"""Timer-driven live alert scheduler."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd
import yfinance as yf
from sqlalchemy import func, select

from qaht.ai.thesis_generator import ThesisGenerator
from qaht.db import init_db, session_scope
from qaht.options.flow_detector import FlowDetector
from qaht.schemas import AlertHistory
from qaht.scoring.empirical_combos import EmpiricalResult, EmpiricalScorer
from qaht.signals.detector import StockSignalDetector
from qaht.tracking.outcome_tracker import OutcomeTracker

from .alert_types import BaseAlert, ComboAlert, NewHighConfAlert, Tier1Alert, TrapClearedAlert
from .ntfy import NtfyClient

logger = logging.getLogger("qaht.alerts.scheduler")


@dataclass
class AlertState:
    """State snapshot for comparing one scan to the prior scan."""

    ticker: str
    score: float
    combos: List[str]
    best_combo_hit_rate: float
    unmitigated_traps: List[str]
    tier1: bool
    tier1_reason: str


class AlertScheduler:
    """Periodic live scanner with ntfy push delivery."""

    def __init__(
        self,
        universe: Sequence[str],
        interval_minutes: int = 30,
        ntfy_client: Optional[NtfyClient] = None,
        max_alerts_per_hour: int = 10,
        dedupe_hours: int = 4,
        click_base_url: Optional[str] = None,
    ) -> None:
        init_db()
        self.universe = [ticker.upper() for ticker in universe]
        self.interval_minutes = interval_minutes
        self.ntfy_client = ntfy_client or NtfyClient()
        self.max_alerts_per_hour = max_alerts_per_hour
        self.dedupe_hours = dedupe_hours
        self.click_base_url = click_base_url or os.environ.get(
            "QAHT_ALERT_CLICK_BASE_URL",
            "http://localhost:8200/app",
        )

        self.detector = StockSignalDetector()
        self.empirical = EmpiricalScorer()
        self.outcome_tracker = OutcomeTracker()
        self.thesis_generator = ThesisGenerator()

        self._flow_detector: Optional[FlowDetector] = None
        self._scan_timer: Optional[threading.Timer] = None
        self._daily_timer: Optional[threading.Timer] = None
        self._lock = threading.RLock()
        self._running = False
        self._last_scan_at: Optional[str] = None
        self._next_scan_at: Optional[str] = None
        self._last_states: Dict[str, AlertState] = {}

    def start(self) -> Dict[str, Any]:
        """Start periodic scanning and daily outcome checks."""
        with self._lock:
            if self._running:
                return self.get_status()
            self._running = True
            self._schedule_scan(delay_seconds=0.0)
            self._schedule_daily_outcomes()
            logger.info("Alert scheduler started")
            return self.get_status()

    def stop(self) -> Dict[str, Any]:
        """Stop the background timers."""
        with self._lock:
            self._running = False
            if self._scan_timer is not None:
                self._scan_timer.cancel()
                self._scan_timer = None
            if self._daily_timer is not None:
                self._daily_timer.cancel()
                self._daily_timer = None
            self._next_scan_at = None
            logger.info("Alert scheduler stopped")
            return self.get_status()

    def get_status(self) -> Dict[str, Any]:
        """Return current scheduler state."""
        with session_scope() as session:
            alert_count = session.execute(select(func.count(AlertHistory.id))).scalar_one()
        return {
            "running": self._running,
            "last_scan": self._last_scan_at,
            "next_scan": self._next_scan_at,
            "alert_count": int(alert_count or 0),
            "topic": self.ntfy_client.topic,
            "interval_minutes": self.interval_minutes,
        }

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent alert history entries."""
        with session_scope() as session:
            rows = session.execute(
                select(AlertHistory)
                .order_by(AlertHistory.timestamp.desc())
                .limit(limit)
            ).scalars().all()
        return [
            {
                "id": row.id,
                "ticker": row.ticker,
                "alert_type": row.alert_type,
                "timestamp": row.timestamp,
                "data": row.data,
            }
            for row in rows
        ]

    def run_scan_once(self) -> Dict[str, Any]:
        """Execute a single scan cycle."""
        results = self.detector.scan_universe(self.universe, min_score=35, include_multiframe=True)
        self.outcome_tracker.record_signals(results)

        alerts: List[BaseAlert] = []
        for result in results:
            state = self._build_state(result)
            previous = self._last_states.get(state.ticker)
            alerts.extend(self._compare_states(previous, state, result))
            alerts.extend(self._maybe_flow_alerts(result))
            self._last_states[state.ticker] = state

        sent = 0
        skipped = 0
        for alert in alerts:
            if self._is_duplicate(alert) or self._is_rate_limited():
                skipped += 1
                continue
            self._dispatch(alert)
            sent += 1

        now = datetime.utcnow()
        self._last_scan_at = now.isoformat()
        if self._running:
            self._next_scan_at = (now + timedelta(minutes=self.interval_minutes)).isoformat()

        logger.info("Alert scan complete: %d results, %d alerts sent, %d skipped", len(results), sent, skipped)
        return {
            "scan_time": self._last_scan_at,
            "results": len(results),
            "alerts_sent": sent,
            "alerts_skipped": skipped,
        }

    def _schedule_scan(self, delay_seconds: float) -> None:
        if not self._running:
            return
        self._scan_timer = threading.Timer(delay_seconds, self._run_scan_loop)
        self._scan_timer.daemon = True
        self._scan_timer.start()
        self._next_scan_at = (datetime.utcnow() + timedelta(seconds=delay_seconds)).isoformat()

    def _run_scan_loop(self) -> None:
        try:
            self.run_scan_once()
        except Exception:
            logger.exception("Alert scan loop failed")
        finally:
            with self._lock:
                if self._running:
                    self._schedule_scan(delay_seconds=self.interval_minutes * 60)

    def _schedule_daily_outcomes(self) -> None:
        if not self._running:
            return
        now = datetime.now()
        next_midnight = datetime.combine(now.date() + timedelta(days=1), time.min)
        delay = max(1.0, (next_midnight - now).total_seconds())
        self._daily_timer = threading.Timer(delay, self._run_daily_outcomes)
        self._daily_timer.daemon = True
        self._daily_timer.start()

    def _run_daily_outcomes(self) -> None:
        try:
            self.outcome_tracker.check_outcomes()
        except Exception:
            logger.exception("Daily outcome check failed")
        finally:
            with self._lock:
                if self._running:
                    self._schedule_daily_outcomes()

    def _build_state(self, result: Dict[str, Any]) -> AlertState:
        empirical = self._score_empirical(result["ticker"], result["score"], result["price"])
        combo_names = [combo.name for combo in empirical.matched_combos]
        traps = [trap.signal for trap in empirical.trap_warnings if not trap.mitigated]
        tier1 = bool(empirical.tier1 and empirical.tier1.passes)
        tier1_reason = empirical.tier1.reason if empirical.tier1 else ""
        return AlertState(
            ticker=result["ticker"],
            score=float(result["score"]),
            combos=combo_names,
            best_combo_hit_rate=float(empirical.best_combo_hit_rate),
            unmitigated_traps=traps,
            tier1=tier1,
            tier1_reason=tier1_reason,
        )

    def _compare_states(
        self,
        previous: Optional[AlertState],
        current: AlertState,
        result: Dict[str, Any],
    ) -> List[BaseAlert]:
        alerts: List[BaseAlert] = []
        click_url = self._build_click_url(current.ticker)

        previous_combos = set(previous.combos) if previous else set()
        for combo_name in current.combos:
            if combo_name not in previous_combos:
                alerts.append(
                    self._attach_thesis(
                        ComboAlert.from_result(
                            ticker=current.ticker,
                            combo_name=combo_name,
                            hit_rate=current.best_combo_hit_rate,
                            price=float(result["price"]),
                            stop=float(result["stop"]),
                            t1=float(result["t1"]),
                            click_url=click_url,
                        ),
                        result,
                    )
                )

        crossed_high_conf = current.score >= 70 and (previous is None or previous.score < 70)
        if crossed_high_conf:
            alerts.append(
                self._attach_thesis(
                    NewHighConfAlert.from_result(
                        ticker=current.ticker,
                        score=current.score,
                        price=float(result["price"]),
                        stop=float(result["stop"]),
                        t1=float(result["t1"]),
                        click_url=click_url,
                    ),
                    result,
                )
            )

        if current.tier1 and (previous is None or not previous.tier1):
            alerts.append(
                self._attach_thesis(
                    Tier1Alert.from_result(
                        ticker=current.ticker,
                        score=current.score,
                        reason=current.tier1_reason,
                        price=float(result["price"]),
                        stop=float(result["stop"]),
                        t1=float(result["t1"]),
                        click_url=click_url,
                    ),
                    result,
                )
            )

        if previous and previous.unmitigated_traps and not current.unmitigated_traps:
            trap_name = previous.unmitigated_traps[0]
            alerts.append(
                TrapClearedAlert.from_result(
                    ticker=current.ticker,
                    trap_name=trap_name,
                    score=current.score,
                    price=float(result["price"]),
                    click_url=click_url,
                )
            )

        return alerts

    def _maybe_flow_alerts(self, result: Dict[str, Any]) -> List[BaseAlert]:
        if float(result.get("score", 0.0)) <= 100:
            return []
        try:
            detector = self._get_flow_detector()
        except RuntimeError:
            return []

        try:
            flow_alerts = asyncio.run(detector.scan_unusual_activity([result["ticker"]], min_score=6))
        except Exception:
            logger.warning("Options flow scan failed for %s", result["ticker"], exc_info=True)
            return []

        if not flow_alerts:
            return []

        flow = flow_alerts[0]
        body = (
            f"{result['ticker']}: Dark Flow + Technical Confluence - "
            f"flow score {flow.score:.0f}, technical score {float(result['score']):.0f}, "
            f"direction {flow.direction}"
        )
        alert = BaseAlert(
            ticker=result["ticker"],
            alert_type="flow_confluence",
            title=f"{result['ticker']} flow confluence",
            body=body,
            priority=4,
            tags=["options", "flow"],
            click_url=self._build_click_url(result["ticker"]),
            data=flow.to_dict(),
        )
        return [self._attach_thesis(alert, result)]

    def _score_empirical(self, ticker: str, quantum_score: float, entry_price: float) -> EmpiricalResult:
        history = yf.Ticker(ticker).history(period="1y", interval="1d")
        if history.empty:
            raise ValueError(f"No history available for {ticker}")
        df = history.rename(columns=str.lower)
        return self.empirical.score_symbol(
            symbol=ticker,
            df=df,
            quantum_score=int(round(quantum_score)),
            entry_price=entry_price,
            max_drawdown_60d=self._max_drawdown(df, 60),
            max_drawdown_20d=self._max_drawdown(df, 20),
        )

    def _dispatch(self, alert: BaseAlert) -> None:
        self.ntfy_client.publish_alert(alert)
        with session_scope() as session:
            session.add(
                AlertHistory(
                    ticker=alert.ticker,
                    alert_type=alert.alert_type,
                    timestamp=alert.timestamp,
                    data=alert.to_record(),
                )
            )

    def _is_duplicate(self, alert: BaseAlert) -> bool:
        cutoff = datetime.utcnow() - timedelta(hours=self.dedupe_hours)
        with session_scope() as session:
            existing = session.execute(
                select(AlertHistory).where(
                    AlertHistory.ticker == alert.ticker,
                    AlertHistory.alert_type == alert.alert_type,
                    AlertHistory.timestamp >= cutoff.isoformat(),
                )
            ).scalar_one_or_none()
        return existing is not None

    def _is_rate_limited(self) -> bool:
        cutoff = datetime.utcnow() - timedelta(hours=1)
        with session_scope() as session:
            count = session.execute(
                select(func.count(AlertHistory.id)).where(AlertHistory.timestamp >= cutoff.isoformat())
            ).scalar_one()
        return int(count or 0) >= self.max_alerts_per_hour

    def _attach_thesis(self, alert: BaseAlert, result: Dict[str, Any]) -> BaseAlert:
        try:
            thesis = self.thesis_generator.generate(result, resistance_levels=[])
        except Exception:
            logger.debug("Failed to generate thesis for %s", result.get("ticker"), exc_info=True)
            return alert

        if thesis:
            alert.body = f"{alert.body}\n\n{thesis}"
            alert.data["thesis"] = thesis
        return alert

    def _get_flow_detector(self) -> FlowDetector:
        if self._flow_detector is None:
            self._flow_detector = FlowDetector()
        return self._flow_detector

    def _build_click_url(self, ticker: str) -> str:
        base = self.click_base_url.rstrip("/")
        return f"{base}/{ticker.upper()}"

    def _max_drawdown(self, df: pd.DataFrame, window: int) -> float:
        if df.empty:
            return 0.0
        recent = df.tail(window)
        peak = float(recent["high"].max())
        trough = float(recent["low"].min())
        if peak <= 0:
            return 0.0
        return max(0.0, (peak - trough) / peak)
