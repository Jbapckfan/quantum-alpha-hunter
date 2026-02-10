"""
Discord webhook alerts for Alpha Predator.

Sends rich embed messages to Discord channels when the Options Scanner detects
high-conviction setups.  Supports both synchronous (requests) and asynchronous
(aiohttp) delivery so callers can choose the appropriate path for their
execution context.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests

logger = logging.getLogger("apredator.alerts.discord")

# ---------------------------------------------------------------------------
# Conviction -> embed colour mapping
# ---------------------------------------------------------------------------
CONVICTION_COLORS: Dict[str, int] = {
    "EXTREME": 0x00FF00,      # green
    "HIGH": 0xFFFF00,         # yellow
    "MODERATE": 0xFF8C00,     # orange
    "LOW": 0xFF0000,          # red
    "SPECULATIVE": 0x808080,  # gray
}


# ---------------------------------------------------------------------------
# Embed construction (shared by sync and async senders)
# ---------------------------------------------------------------------------

def _build_embed(
    symbol: str,
    score: int,
    conviction: str,
    price: float,
    combo_name: Optional[str] = None,
    tier: Optional[int] = None,
    signals: Optional[List[str]] = None,
    kelly_size: Optional[float] = None,
    educational_disclaimer: bool = True,
) -> dict:
    """Build a Discord embed payload dict for a single alert."""
    color = CONVICTION_COLORS.get(conviction.upper(), 0x808080)

    fields: List[dict] = [
        {"name": "Score", "value": str(score), "inline": True},
    ]

    if tier is not None:
        fields.append({"name": "Tier", "value": str(tier), "inline": True})

    if combo_name is not None:
        fields.append({"name": "Combo", "value": combo_name, "inline": True})

    fields.append({"name": "Price", "value": f"${price:,.4f}", "inline": True})

    if kelly_size is not None:
        fields.append(
            {"name": "Kelly Size", "value": f"{kelly_size:.2%}", "inline": True}
        )

    if signals:
        fields.append(
            {"name": "Top Signals", "value": ", ".join(signals), "inline": False}
        )

    embed: dict = {
        "title": f"{symbol} \u2014 {conviction} Conviction",
        "color": color,
        "fields": fields,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if educational_disclaimer:
        embed["footer"] = {
            "text": "Educational purposes only. Not financial advice."
        }

    return embed


# ---------------------------------------------------------------------------
# Synchronous sender (requests)
# ---------------------------------------------------------------------------

def send_discord_alert(
    webhook_url: str,
    symbol: str,
    score: int,
    conviction: str,
    price: float,
    combo_name: Optional[str] = None,
    tier: Optional[int] = None,
    signals: Optional[List[str]] = None,
    kelly_size: Optional[float] = None,
    educational_disclaimer: bool = True,
) -> bool:
    """Send a rich-embed Discord alert via webhook (synchronous).

    Parameters
    ----------
    webhook_url : str
        Full Discord webhook URL.
    symbol : str
        Ticker / token symbol (e.g. ``"AAPL"`` or ``"BTC"``).
    score : int
        Quantum score (0-100).
    conviction : str
        One of EXTREME, HIGH, MODERATE, LOW, SPECULATIVE.
    price : float
        Current price at time of alert.
    combo_name : str, optional
        Matched combo pattern name.
    tier : int, optional
        Signal tier (1-5).
    signals : list[str], optional
        List of active signal names.
    kelly_size : float, optional
        Kelly criterion position size as fraction (e.g. 0.05 for 5%).
    educational_disclaimer : bool
        Whether to append the educational disclaimer footer.

    Returns
    -------
    bool
        ``True`` on successful delivery (HTTP 2xx), ``False`` otherwise.
    """
    try:
        embed = _build_embed(
            symbol=symbol,
            score=score,
            conviction=conviction,
            price=price,
            combo_name=combo_name,
            tier=tier,
            signals=signals,
            kelly_size=kelly_size,
            educational_disclaimer=educational_disclaimer,
        )

        payload = {"embeds": [embed]}

        response = requests.post(webhook_url, json=payload, timeout=10)

        if 200 <= response.status_code < 300:
            logger.info(
                "Discord alert sent for %s (score=%s, conviction=%s)",
                symbol,
                score,
                conviction,
            )
            return True
        else:
            logger.warning(
                "Discord webhook returned %s for %s: %s",
                response.status_code,
                symbol,
                response.text[:200],
            )
            return False

    except Exception:
        logger.exception("Failed to send Discord alert for %s", symbol)
        return False


# ---------------------------------------------------------------------------
# Asynchronous sender (aiohttp)
# ---------------------------------------------------------------------------

async def send_discord_alert_async(
    webhook_url: str,
    symbol: str,
    score: int,
    conviction: str,
    price: float,
    combo_name: Optional[str] = None,
    tier: Optional[int] = None,
    signals: Optional[List[str]] = None,
    kelly_size: Optional[float] = None,
    educational_disclaimer: bool = True,
) -> bool:
    """Send a rich-embed Discord alert via webhook (asynchronous).

    Same payload construction as :func:`send_discord_alert` but uses
    ``aiohttp.ClientSession`` for non-blocking HTTP delivery.

    Parameters
    ----------
    See :func:`send_discord_alert` for parameter descriptions.

    Returns
    -------
    bool
        ``True`` on successful delivery (HTTP 2xx), ``False`` otherwise.
    """
    try:
        import aiohttp
    except ImportError:
        logger.error("aiohttp is required for async Discord alerts -- falling back to sync")
        return send_discord_alert(
            webhook_url=webhook_url,
            symbol=symbol,
            score=score,
            conviction=conviction,
            price=price,
            combo_name=combo_name,
            tier=tier,
            signals=signals,
            kelly_size=kelly_size,
            educational_disclaimer=educational_disclaimer,
        )

    try:
        embed = _build_embed(
            symbol=symbol,
            score=score,
            conviction=conviction,
            price=price,
            combo_name=combo_name,
            tier=tier,
            signals=signals,
            kelly_size=kelly_size,
            educational_disclaimer=educational_disclaimer,
        )

        payload = {"embeds": [embed]}

        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if 200 <= response.status < 300:
                    logger.info(
                        "Async Discord alert sent for %s (score=%s, conviction=%s)",
                        symbol,
                        score,
                        conviction,
                    )
                    return True
                else:
                    body = await response.text()
                    logger.warning(
                        "Async Discord webhook returned %s for %s: %s",
                        response.status,
                        symbol,
                        body[:200],
                    )
                    return False

    except Exception:
        logger.exception("Failed to send async Discord alert for %s", symbol)
        return False
