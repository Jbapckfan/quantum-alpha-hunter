"""
Auto-scan scheduler with Discord and Telegram alert delivery.

Runs the Alpha Predator scan pipeline on a configurable interval and
dispatches rich alerts to Discord webhooks and/or Telegram bots.
Includes a 4-hour cooldown per symbol and logs all alerts to a SQLite DB.
"""
import json
import logging
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("apredator.alerts.scheduler")

# ---------------------------------------------------------------------------
# Conviction helpers
# ---------------------------------------------------------------------------

CONVICTION_EMOJI = {
    "EXTREME": "🟢",
    "HIGH": "🟡",
    "MODERATE": "🟠",
    "LOW": "🔴",
    "SPECULATIVE": "⚪",
}

CONVICTION_COLORS_HEX = {
    "EXTREME": 0x00FF00,
    "HIGH": 0xFFFF00,
    "MODERATE": 0xFF8C00,
    "LOW": 0xFF0000,
    "SPECULATIVE": 0x808080,
}


def _conviction_from_score(score: int) -> str:
    """Derive a conviction label from a numeric score (0-100)."""
    if score >= 90:
        return "EXTREME"
    elif score >= 75:
        return "HIGH"
    elif score >= 60:
        return "MODERATE"
    elif score >= 40:
        return "LOW"
    return "SPECULATIVE"


# ---------------------------------------------------------------------------
# Alert DB helper (lightweight SQLite, separate from the main ORM DB)
# ---------------------------------------------------------------------------

_DEFAULT_DB_PATH = Path("data/signal_tracker.db")


def _init_alert_db(db_path: Path) -> sqlite3.Connection:
    """Create (or open) the alert log database and ensure the table exists."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scheduler_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            score INTEGER,
            conviction TEXT,
            tier INTEGER,
            combo TEXT,
            price REAL,
            kelly_size REAL,
            reasons TEXT,
            channel TEXT,
            timestamp TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# AlertScheduler
# ---------------------------------------------------------------------------

class AlertScheduler:
    """Runs Alpha Predator scans on a schedule and dispatches alerts.

    Parameters
    ----------
    scan_interval_minutes : int
        Minutes between automatic scans (used by :meth:`start`).
    discord_webhook : str, optional
        Discord webhook URL for alert delivery.
    telegram_bot_token : str, optional
        Telegram Bot API token.
    telegram_chat_id : str, optional
        Telegram chat / channel ID to send messages to.
    db_path : str or Path, optional
        Path to the SQLite alert log database.  Defaults to
        ``data/signal_tracker.db``.
    cooldown_hours : float
        Hours before the same symbol can be re-alerted.
    """

    def __init__(
        self,
        scan_interval_minutes: int = 60,
        discord_webhook: Optional[str] = None,
        telegram_bot_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        db_path: Optional[str] = None,
        cooldown_hours: float = 4.0,
    ):
        self.scan_interval_minutes = scan_interval_minutes
        self.discord_webhook = discord_webhook
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.cooldown_hours = cooldown_hours

        # Alert cooldown tracking: symbol -> last alert UTC datetime
        self._last_alert: Dict[str, datetime] = {}

        # Alert log database
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        self._db_conn = _init_alert_db(self._db_path)

        logger.info(
            "AlertScheduler initialised: interval=%dm, discord=%s, telegram=%s, db=%s",
            scan_interval_minutes,
            "configured" if discord_webhook else "off",
            "configured" if (telegram_bot_token and telegram_chat_id) else "off",
            self._db_path,
        )

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

    def run_scan(self) -> List[dict]:
        """Execute a single scan using the daily pipeline.

        Returns a list of signal dicts from the pipeline output.  Each dict
        has at minimum: ``symbol``, ``score``, ``conviction``, ``tier``,
        ``combo``, ``price``.
        """
        logger.info("Running scheduled scan ...")
        try:
            from ..pipeline.daily_scan import run_daily_scan

            result = run_daily_scan(send_alerts=False)

            signals = result.get("top_signals", [])
            logger.info(
                "Scan complete: %d symbols scanned, %d signals found",
                result.get("n_symbols", 0),
                result.get("n_signals", 0),
            )
            return signals

        except Exception:
            logger.exception("Scan failed")
            return []

    # ------------------------------------------------------------------
    # Cooldown
    # ------------------------------------------------------------------

    def _is_on_cooldown(self, symbol: str) -> bool:
        """Check whether *symbol* is within the alert cooldown window."""
        last = self._last_alert.get(symbol)
        if last is None:
            return False
        elapsed = datetime.now(timezone.utc) - last
        return elapsed < timedelta(hours=self.cooldown_hours)

    def _mark_alerted(self, symbol: str) -> None:
        """Record the current time as the last alert for *symbol*."""
        self._last_alert[symbol] = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    @staticmethod
    def format_signal(result: dict) -> str:
        """Format a signal result dict into a clean plain-text message.

        Parameters
        ----------
        result : dict
            Signal dict with keys like symbol, score, conviction, tier,
            combo, price, kelly_size, reasons.

        Returns
        -------
        str
        """
        symbol = result.get("symbol", "???")
        score = result.get("score", 0)
        conviction = result.get("conviction", _conviction_from_score(int(score)))
        tier = result.get("tier", "?")
        combo = result.get("combo") or "None"
        price = result.get("price", 0)
        kelly = result.get("kelly_size", result.get("kelly_fraction", 0))
        reasons = result.get("reasons", result.get("signals", []))

        lines = [
            f"{'=' * 40}",
            f"  {symbol}  --  {conviction} Conviction",
            f"{'=' * 40}",
            f"  Score : {score}",
            f"  Tier  : {tier}",
            f"  Price : ${price:,.4f}" if price else "  Price : N/A",
            f"  Combo : {combo}",
        ]

        if kelly:
            lines.append(f"  Kelly : {float(kelly):.2%}")

        if reasons:
            if isinstance(reasons, list):
                top_reasons = reasons[:3]
            else:
                top_reasons = [str(reasons)]
            lines.append(f"  Reasons: {', '.join(str(r) for r in top_reasons)}")

        lines.append(f"  Time  : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Discord
    # ------------------------------------------------------------------

    def send_discord_alert(self, signal: dict) -> bool:
        """Send a rich embed alert to Discord via webhook.

        Parameters
        ----------
        signal : dict
            Signal dict (see :meth:`format_signal` for expected keys).

        Returns
        -------
        bool
            ``True`` if the message was delivered successfully.
        """
        if not self.discord_webhook:
            logger.debug("Discord webhook not configured -- skipping")
            return False

        symbol = signal.get("symbol", "???")
        score = int(signal.get("score", 0))
        conviction = signal.get("conviction", _conviction_from_score(score))
        tier = signal.get("tier", "?")
        combo = signal.get("combo") or "None"
        price = signal.get("price", 0)
        kelly = signal.get("kelly_size", signal.get("kelly_fraction", 0))
        reasons = signal.get("reasons", signal.get("signals", []))

        color = CONVICTION_COLORS_HEX.get(conviction.upper(), 0x808080)

        fields: List[dict] = [
            {"name": "Score", "value": str(score), "inline": True},
            {"name": "Tier", "value": str(tier), "inline": True},
            {"name": "Combo", "value": combo, "inline": True},
        ]

        if price:
            fields.append({"name": "Price", "value": f"${price:,.4f}", "inline": True})

        if kelly:
            fields.append(
                {"name": "Kelly Size", "value": f"{float(kelly):.2%}", "inline": True}
            )

        if reasons:
            if isinstance(reasons, list):
                top_3 = reasons[:3]
            else:
                top_3 = [str(reasons)]
            fields.append(
                {"name": "Top Reasons", "value": ", ".join(str(r) for r in top_3), "inline": False}
            )

        embed = {
            "title": f"{symbol} -- {conviction} Conviction",
            "color": color,
            "fields": fields,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": "Alpha Predator | Educational purposes only"},
        }

        payload = {"embeds": [embed]}

        try:
            resp = requests.post(
                self.discord_webhook,
                json=payload,
                timeout=10,
            )
            if 200 <= resp.status_code < 300:
                logger.info("Discord alert sent for %s (score=%s)", symbol, score)
                return True
            else:
                logger.warning(
                    "Discord webhook returned %s for %s: %s",
                    resp.status_code, symbol, resp.text[:200],
                )
                return False
        except Exception:
            logger.exception("Discord alert failed for %s", symbol)
            return False

    # ------------------------------------------------------------------
    # Telegram
    # ------------------------------------------------------------------

    def send_telegram_alert(self, signal: dict) -> bool:
        """Send a Markdown-formatted alert via the Telegram Bot API.

        Parameters
        ----------
        signal : dict
            Signal dict (see :meth:`format_signal` for expected keys).

        Returns
        -------
        bool
            ``True`` if the message was delivered successfully.
        """
        if not self.telegram_bot_token or not self.telegram_chat_id:
            logger.debug("Telegram not configured -- skipping")
            return False

        symbol = signal.get("symbol", "???")
        score = int(signal.get("score", 0))
        conviction = signal.get("conviction", _conviction_from_score(score))
        tier = signal.get("tier", "?")
        combo = signal.get("combo") or "None"
        price = signal.get("price", 0)
        kelly = signal.get("kelly_size", signal.get("kelly_fraction", 0))
        reasons = signal.get("reasons", signal.get("signals", []))

        emoji = CONVICTION_EMOJI.get(conviction.upper(), "")

        lines = [
            f"{emoji} *{symbol}* -- {conviction} Conviction",
            "",
            f"*Score:* {score}",
            f"*Tier:* {tier}",
        ]

        if price:
            lines.append(f"*Price:* ${price:,.4f}")

        lines.append(f"*Combo:* {combo}")

        if kelly:
            lines.append(f"*Kelly Size:* {float(kelly):.2%}")

        if reasons:
            if isinstance(reasons, list):
                top_3 = reasons[:3]
            else:
                top_3 = [str(reasons)]
            lines.append(f"*Reasons:* {', '.join(str(r) for r in top_3)}")

        lines.append("")
        lines.append(f"_{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_")
        lines.append("_Educational purposes only. Not financial advice._")

        text = "\n".join(lines)

        url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": self.telegram_chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }

        try:
            resp = requests.post(url, json=payload, timeout=10)
            data = resp.json()
            if data.get("ok"):
                logger.info("Telegram alert sent for %s (score=%s)", symbol, score)
                return True
            else:
                logger.warning(
                    "Telegram API error for %s: %s",
                    symbol, data.get("description", resp.text[:200]),
                )
                return False
        except Exception:
            logger.exception("Telegram alert failed for %s", symbol)
            return False

    # ------------------------------------------------------------------
    # Alert DB logging
    # ------------------------------------------------------------------

    def _log_alert_to_db(self, signal: dict, channel: str) -> None:
        """Persist an alert record to the SQLite database."""
        try:
            reasons = signal.get("reasons", signal.get("signals", []))
            if isinstance(reasons, list):
                reasons_str = json.dumps(reasons)
            else:
                reasons_str = str(reasons)

            self._db_conn.execute(
                """
                INSERT INTO scheduler_alerts
                    (symbol, score, conviction, tier, combo, price, kelly_size, reasons, channel, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.get("symbol"),
                    int(signal.get("score", 0)),
                    signal.get("conviction", ""),
                    signal.get("tier"),
                    signal.get("combo"),
                    signal.get("price"),
                    signal.get("kelly_size", signal.get("kelly_fraction")),
                    reasons_str,
                    channel,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            self._db_conn.commit()
        except Exception:
            logger.exception("Failed to log alert to DB for %s", signal.get("symbol"))

    # ------------------------------------------------------------------
    # Single scan + alert cycle
    # ------------------------------------------------------------------

    def run_once(self) -> List[dict]:
        """Run a single scan-and-alert cycle.

        Suitable for calling from cron, an external scheduler, or manual
        invocation.

        Returns
        -------
        list[dict]
            The signals that were alerted on (after cooldown filtering).
        """
        signals = self.run_scan()
        alerted: List[dict] = []

        for sig in signals:
            symbol = sig.get("symbol", "")
            if not symbol:
                continue

            # Derive conviction if missing
            score = int(sig.get("score", 0))
            if "conviction" not in sig:
                sig["conviction"] = _conviction_from_score(score)

            # Cooldown check
            if self._is_on_cooldown(symbol):
                logger.debug("Skipping %s -- on cooldown", symbol)
                continue

            # Dispatch alerts
            sent_any = False

            if self.discord_webhook:
                ok = self.send_discord_alert(sig)
                if ok:
                    self._log_alert_to_db(sig, "discord")
                    sent_any = True

            if self.telegram_bot_token and self.telegram_chat_id:
                ok = self.send_telegram_alert(sig)
                if ok:
                    self._log_alert_to_db(sig, "telegram")
                    sent_any = True

            if sent_any:
                self._mark_alerted(symbol)
                alerted.append(sig)
                logger.info(
                    "Alerted on %s: score=%s conviction=%s tier=%s",
                    symbol, score, sig.get("conviction"), sig.get("tier"),
                )

        logger.info(
            "Alert cycle complete: %d signals scanned, %d alerts sent",
            len(signals), len(alerted),
        )
        return alerted

    # ------------------------------------------------------------------
    # Continuous loop
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Run scans in a blocking loop at the configured interval.

        This method never returns under normal operation.  It catches and
        logs exceptions within each cycle so that transient failures do not
        kill the scheduler.
        """
        logger.info(
            "Starting AlertScheduler loop (interval=%dm) ...",
            self.scan_interval_minutes,
        )

        while True:
            try:
                self.run_once()
            except KeyboardInterrupt:
                logger.info("Scheduler interrupted by user -- exiting")
                break
            except Exception:
                logger.exception("Unhandled error in scheduler loop")

            logger.info(
                "Sleeping %d minutes until next scan ...",
                self.scan_interval_minutes,
            )
            try:
                time.sleep(self.scan_interval_minutes * 60)
            except KeyboardInterrupt:
                logger.info("Scheduler interrupted during sleep -- exiting")
                break

        self._db_conn.close()
        logger.info("AlertScheduler stopped")
