"""
Alert monitoring with conviction tracking, cooldown management, and
self-learning outcome tracking.

Ported from the Hedge Fund ``realtime_monitor.py`` with additions for
the Alpha Predator self-learning loop that fills alert outcomes after
the fact, enabling continuous model improvement.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from ..config import get_config
from ..db import session_scope
from ..schemas import AlertLog, PriceOHLC

logger = logging.getLogger("apredator.alerts.monitor")

# ---------------------------------------------------------------------------
# Conviction ordering (higher = stronger)
# ---------------------------------------------------------------------------
CONVICTION_ORDER: Dict[str, int] = {
    "SPECULATIVE": 0,
    "LOW": 1,
    "MODERATE": 2,
    "HIGH": 3,
    "EXTREME": 4,
}


class AlertMonitor:
    """Manages alert gating, conviction change detection, and outcome tracking.

    Parameters
    ----------
    config : optional
        A ``ConfigManager`` instance.  If ``None``, the global config is used.
    """

    def __init__(self, config=None):
        self._config = config or get_config()
        self._cooldown_hours: int = self._config.alerts.cooldown_hours

        # Internal state --------------------------------------------------
        # symbol -> datetime of the last alert sent
        self._last_alert: Dict[str, datetime] = {}
        # symbol -> last conviction string
        self._conviction_state: Dict[str, str] = {}
        # Full history of alert records within this session
        self._alert_history: List[dict] = []

    # ------------------------------------------------------------------
    # Gating
    # ------------------------------------------------------------------

    def should_alert(self, symbol: str, conviction: str, score: int) -> bool:
        """Decide whether an alert should be sent for *symbol*.

        Rules
        -----
        1. **Always** alert on a conviction *upgrade* (e.g. LOW -> HIGH).
        2. Block if the same conviction was already sent within the cooldown.
        3. Block if the score is below the configured minimum confidence.

        Returns
        -------
        bool
        """
        min_score = self._config.alerts.min_confidence * 100
        if score < min_score:
            logger.debug(
                "Blocking alert for %s: score %s < min %s",
                symbol, score, min_score,
            )
            return False

        conviction_upper = conviction.upper()

        # Check for conviction upgrade
        prev_conviction = self._conviction_state.get(symbol)
        if prev_conviction is not None:
            prev_rank = CONVICTION_ORDER.get(prev_conviction.upper(), -1)
            curr_rank = CONVICTION_ORDER.get(conviction_upper, -1)
            if curr_rank > prev_rank:
                logger.info(
                    "Conviction upgrade for %s: %s -> %s -- allowing alert",
                    symbol, prev_conviction, conviction,
                )
                return True

        # Cooldown check
        last_ts = self._last_alert.get(symbol)
        if last_ts is not None:
            elapsed = datetime.utcnow() - last_ts
            if elapsed < timedelta(hours=self._cooldown_hours):
                # Same or lower conviction within cooldown -- block
                if prev_conviction and conviction_upper == prev_conviction.upper():
                    logger.debug(
                        "Blocking alert for %s: same conviction %s within cooldown (%s remaining)",
                        symbol,
                        conviction,
                        timedelta(hours=self._cooldown_hours) - elapsed,
                    )
                    return False

        return True

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_alert(
        self,
        symbol: str,
        conviction: str,
        score: int,
        price: float,
    ) -> None:
        """Record that an alert was sent, updating internal state and the DB.

        Inserts a row into the ``AlertLog`` table for later outcome tracking.
        """
        now = datetime.utcnow()

        # Update in-memory state
        self._last_alert[symbol] = now
        self._conviction_state[symbol] = conviction.upper()
        self._alert_history.append({
            "symbol": symbol,
            "conviction": conviction,
            "score": score,
            "price": price,
            "timestamp": now.isoformat(),
        })

        # Persist to DB
        try:
            with session_scope() as session:
                alert_row = AlertLog(
                    symbol=symbol,
                    timestamp=now.isoformat(),
                    channel="discord",
                    conviction_level=conviction.upper(),
                    quantum_score=score,
                    entry_price=price,
                )
                session.add(alert_row)
            logger.info(
                "Recorded alert for %s: conviction=%s score=%s price=%.4f",
                symbol, conviction, score, price,
            )
        except Exception:
            logger.exception("Failed to persist alert for %s to DB", symbol)

    # ------------------------------------------------------------------
    # Conviction change detection
    # ------------------------------------------------------------------

    def get_conviction_changes(
        self,
        current_signals: List[dict],
    ) -> List[dict]:
        """Compare *current_signals* against stored conviction state.

        Parameters
        ----------
        current_signals : list[dict]
            Each element must have keys ``"symbol"`` and ``"conviction"``.

        Returns
        -------
        list[dict]
            Each dict has keys ``symbol``, ``old_conviction``, ``new_conviction``,
            and ``direction`` (one of ``"upgrade"``, ``"downgrade"``, ``"new"``).
        """
        changes: List[dict] = []

        for sig in current_signals:
            symbol = sig["symbol"]
            new_conv = sig["conviction"].upper()
            old_conv = self._conviction_state.get(symbol)

            if old_conv is None:
                changes.append({
                    "symbol": symbol,
                    "old_conviction": None,
                    "new_conviction": new_conv,
                    "direction": "new",
                })
            else:
                old_rank = CONVICTION_ORDER.get(old_conv.upper(), -1)
                new_rank = CONVICTION_ORDER.get(new_conv, -1)
                if new_rank > old_rank:
                    changes.append({
                        "symbol": symbol,
                        "old_conviction": old_conv,
                        "new_conviction": new_conv,
                        "direction": "upgrade",
                    })
                elif new_rank < old_rank:
                    changes.append({
                        "symbol": symbol,
                        "old_conviction": old_conv,
                        "new_conviction": new_conv,
                        "direction": "downgrade",
                    })
                # Equal rank with no change => omit from list

        if changes:
            logger.info(
                "Conviction changes detected: %d (upgrades=%d, downgrades=%d, new=%d)",
                len(changes),
                sum(1 for c in changes if c["direction"] == "upgrade"),
                sum(1 for c in changes if c["direction"] == "downgrade"),
                sum(1 for c in changes if c["direction"] == "new"),
            )

        return changes

    # ------------------------------------------------------------------
    # Self-learning outcome tracking
    # ------------------------------------------------------------------

    def fill_outcomes(self) -> None:
        """Back-fill outcome columns for matured alerts.

        Queries ``AlertLog`` rows where ``outcome_10d`` is NULL and the alert
        is older than 10 days.  For each qualifying row, the current price is
        fetched from ``PriceOHLC`` and the 5-day, 10-day, and 30-day returns
        are computed.  ``max_gain_30d`` is the peak return over the 30-day
        window.  ``hit_target`` is True if the 30-day max gain exceeds the
        configured profit target.

        This is the core of the self-learning feedback loop: by tracking
        whether past alerts led to profitable moves, the system can
        adaptively adjust signal weights and retrain models.
        """
        config = self._config
        profit_target = config.backtest.profit_target

        try:
            with session_scope() as session:
                cutoff_10d = (datetime.utcnow() - timedelta(days=10)).isoformat()

                stale_alerts = (
                    session.query(AlertLog)
                    .filter(
                        AlertLog.outcome_10d.is_(None),
                        AlertLog.timestamp <= cutoff_10d,
                    )
                    .all()
                )

                if not stale_alerts:
                    logger.debug("No matured alerts to update outcomes for")
                    return

                logger.info(
                    "Filling outcomes for %d matured alerts", len(stale_alerts)
                )

                for alert in stale_alerts:
                    try:
                        self._fill_single_outcome(
                            session, alert, profit_target
                        )
                    except Exception:
                        logger.exception(
                            "Failed to fill outcome for alert id=%s symbol=%s",
                            alert.id,
                            alert.symbol,
                        )

        except Exception:
            logger.exception("fill_outcomes failed at query level")

    @staticmethod
    def _fill_single_outcome(session, alert: AlertLog, profit_target: float) -> None:
        """Compute and update outcome columns for a single AlertLog row."""
        alert_date = alert.timestamp[:10]  # ISO date portion
        entry_price = alert.entry_price
        if not entry_price or entry_price <= 0:
            return

        # Fetch price rows after the alert date
        prices = (
            session.query(PriceOHLC)
            .filter(
                PriceOHLC.symbol == alert.symbol,
                PriceOHLC.date > alert_date,
            )
            .order_by(PriceOHLC.date)
            .all()
        )

        if not prices:
            return

        # Helper: return pct from entry
        def _ret(p: PriceOHLC) -> float:
            return (p.close - entry_price) / entry_price

        # 5-day outcome
        if len(prices) >= 5:
            alert.outcome_5d = round(_ret(prices[4]), 6)

        # 10-day outcome
        if len(prices) >= 10:
            alert.outcome_10d = round(_ret(prices[9]), 6)

        # 30-day outcome and max gain
        window_30 = prices[:30] if len(prices) >= 30 else prices
        if window_30:
            returns_30 = [_ret(p) for p in window_30]
            max_gain = max(returns_30) if returns_30 else 0.0
            alert.max_gain_30d = round(max_gain, 6)
            alert.outcome_30d = round(returns_30[-1], 6) if len(prices) >= 30 else None
            alert.hit_target = max_gain >= profit_target

        logger.debug(
            "Updated outcomes for %s (alert %s): 5d=%.4f 10d=%s 30d=%s max=%.4f hit=%s",
            alert.symbol,
            alert.id,
            alert.outcome_5d or 0,
            alert.outcome_10d,
            alert.outcome_30d,
            alert.max_gain_30d or 0,
            alert.hit_target,
        )
