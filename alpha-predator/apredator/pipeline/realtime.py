"""
Real-time monitoring loop for Alpha Predator.

Runs a continuous scan cycle at a configurable interval, detecting conviction
upgrades and delivering alerts in near real-time.  Uses an abbreviated
"quick scan" path that skips model retraining and focuses on explosive signal
detection and combo matching for speed.
"""
import logging
import time
from typing import Dict, List, Optional

import pandas as pd

from .daily_scan import PipelineMonitor
from ..alerts import send_discord_alert, AlertMonitor
from ..config import get_config
from ..db import session_scope
from ..features import compute_all_explosive, compute_all_technical
from ..schemas import PriceOHLC
from ..scoring import combine_scores, match_combos, classify_tier, score_symbols
from ..scoring.ml_scorer import load_model

logger = logging.getLogger("apredator.pipeline.realtime")


# ---------------------------------------------------------------------------
# Quick scan (fast path -- no retraining)
# ---------------------------------------------------------------------------

def _quick_scan(
    symbols: List[str],
    model_path: Optional[str] = None,
) -> List[dict]:
    """Run a fast scoring pass over *symbols* without retraining.

    Steps
    -----
    1. Load existing ML model (or skip ML if unavailable).
    2. Fetch latest prices from the DB.
    3. Compute explosive signals and combo matching.
    4. Return scored symbols sorted by score descending.

    Parameters
    ----------
    symbols : list[str]
        Symbols to scan.
    model_path : str, optional
        Path to a serialised model.  If ``None``, the system will attempt to
        load the active model from the registry; ML scoring is skipped when
        no model is available.

    Returns
    -------
    list[dict]
        Each element has keys ``symbol``, ``score``, ``conviction``, ``combos``,
        ``tier``, and ``price``.
    """
    results: List[dict] = []

    # Attempt to load ML model
    model = None
    try:
        model = load_model(model_path)
    except Exception:
        logger.debug("No ML model loaded -- scoring will rely on signal-only heuristics")

    for symbol in symbols:
        try:
            # Fetch price data
            with session_scope() as session:
                rows = (
                    session.query(PriceOHLC)
                    .filter(PriceOHLC.symbol == symbol)
                    .order_by(PriceOHLC.date)
                    .all()
                )

            if not rows or len(rows) < 60:
                continue

            df = pd.DataFrame([
                {
                    "date": r.date,
                    "open": r.open,
                    "high": r.high,
                    "low": r.low,
                    "close": r.close,
                    "volume": r.volume,
                }
                for r in rows
            ]).sort_values("date").reset_index(drop=True)

            # Compute features (fast path: technical + explosive only)
            features = compute_all_technical(df)
            explosive = compute_all_explosive(df)
            features.update(explosive)
            features["symbol"] = symbol
            features["close"] = df["close"].iloc[-1]

            # Combo matching
            combos = match_combos(features)
            features["combos"] = combos

            best_combo = None
            tier = 5
            if combos:
                best = max(combos, key=lambda c: c["hit_rate"])
                best_combo = best["name"]
                try:
                    tier_result = classify_tier(features)
                    tier = tier_result.get("tier") or 5
                except Exception:
                    tier = 3 if len(combos) >= 2 else 4

            features["best_combo"] = best_combo
            features["tier"] = tier

            # Ensemble / ML scoring
            try:
                ensemble = combine_scores(features)
                features.update(ensemble)
            except Exception:
                pass

            score = features.get("quantum_score", features.get("ensemble_score", 0))
            conviction = features.get("conviction_level", "MODERATE")

            results.append({
                "symbol": symbol,
                "score": score,
                "conviction": conviction,
                "combos": combos,
                "tier": tier,
                "price": features["close"],
                "best_combo": best_combo,
                "kelly_fraction": features.get("kelly_fraction", 0.0),
                "_features": features,
            })

        except Exception:
            logger.exception("Quick scan failed for %s", symbol)

    # Sort by score descending
    results.sort(key=lambda r: r.get("score", 0), reverse=True)
    return results


# ---------------------------------------------------------------------------
# Continuous monitoring loop
# ---------------------------------------------------------------------------

def run_realtime_monitor(
    interval_minutes: int = 60,
    asset_types: Optional[List[str]] = None,
    webhook_url: Optional[str] = None,
) -> None:
    """Run a continuous real-time monitoring loop.

    Scans the universe at the specified interval, detects conviction upgrades,
    and delivers Discord alerts.  Runs forever until interrupted with
    ``KeyboardInterrupt``.

    Parameters
    ----------
    interval_minutes : int
        Sleep duration between scan cycles (default 60).
    asset_types : list[str], optional
        Asset classes to monitor.  Defaults to ``["stock", "crypto"]``.
    webhook_url : str, optional
        Discord webhook URL override.  If ``None``, uses the value from config.
    """
    config = get_config()
    alert_monitor = AlertMonitor(config=config)

    if asset_types is None:
        asset_types = ["stock", "crypto"]

    if webhook_url is None:
        webhook_url = config.discord_webhook_url

    # Build symbol list once at startup
    from ..universe import get_stock_universe, get_crypto_universe

    all_symbols: List[str] = []
    if "stock" in asset_types:
        try:
            all_symbols.extend(get_stock_universe())
        except Exception:
            logger.exception("Failed to load stock universe")
    if "crypto" in asset_types:
        try:
            all_symbols.extend(get_crypto_universe())
        except Exception:
            logger.exception("Failed to load crypto universe")

    if not all_symbols:
        logger.error("Empty universe -- nothing to monitor")
        return

    logger.info(
        "Real-time monitor starting: %d symbols, interval=%d min, webhook=%s",
        len(all_symbols),
        interval_minutes,
        "configured" if webhook_url else "none",
    )

    cycle = 0

    try:
        while True:
            cycle += 1
            cycle_start = time.time()
            logger.info("Starting scan cycle #%d", cycle)

            step_monitor = PipelineMonitor()

            # ----- Quick scan -----
            step_monitor.start_step("quick_scan")
            try:
                scan_results = _quick_scan(all_symbols)
            except Exception:
                logger.exception("Quick scan failed in cycle #%d", cycle)
                scan_results = []
            step_monitor.end_step("quick_scan")

            # ----- Conviction changes -----
            step_monitor.start_step("conviction_changes")
            current_signals = [
                {"symbol": r["symbol"], "conviction": r["conviction"]}
                for r in scan_results
            ]
            changes = alert_monitor.get_conviction_changes(current_signals)
            step_monitor.end_step("conviction_changes")

            # ----- Alerts for upgrades -----
            step_monitor.start_step("send_alerts")
            alerts_sent = 0

            for change in changes:
                if change["direction"] not in ("upgrade", "new"):
                    continue

                symbol = change["symbol"]

                # Find full result for this symbol
                result = next(
                    (r for r in scan_results if r["symbol"] == symbol), None
                )
                if result is None:
                    continue

                score = result.get("score", 0)
                conviction = result["conviction"]
                price = result.get("price", 0.0)

                if not alert_monitor.should_alert(symbol, conviction, score):
                    continue

                if webhook_url:
                    sent = send_discord_alert(
                        webhook_url=webhook_url,
                        symbol=symbol,
                        score=int(score),
                        conviction=conviction,
                        price=price,
                        combo_name=result.get("best_combo"),
                        tier=result.get("tier"),
                        signals=(
                            result["combos"][0].get("matched_signals", [])
                            if result.get("combos") else None
                        ),
                        kelly_size=result.get("kelly_fraction"),
                        educational_disclaimer=config.alerts.educational_disclaimer,
                    )
                    if sent:
                        alert_monitor.record_alert(symbol, conviction, int(score), price)
                        alerts_sent += 1
                else:
                    # No webhook -- just record
                    alert_monitor.record_alert(symbol, conviction, int(score), price)
                    alerts_sent += 1

            step_monitor.end_step("send_alerts")

            # ----- Self-learning outcome fill -----
            step_monitor.start_step("fill_outcomes")
            try:
                alert_monitor.fill_outcomes()
            except Exception:
                logger.exception("Outcome fill failed in cycle #%d", cycle)
            step_monitor.end_step("fill_outcomes")

            # ----- Cycle summary -----
            cycle_time = time.time() - cycle_start
            n_signals = sum(1 for r in scan_results if r.get("tier", 5) <= 3)
            logger.info(
                "Cycle #%d complete: %d symbols scanned, %d signals, "
                "%d alerts sent, %.1fs elapsed",
                cycle,
                len(scan_results),
                n_signals,
                alerts_sent,
                cycle_time,
            )

            if scan_results:
                top = scan_results[0]
                logger.info(
                    "  Top signal: %s score=%s conviction=%s tier=%s",
                    top["symbol"], top["score"], top["conviction"], top.get("tier"),
                )

            # ----- Sleep -----
            sleep_seconds = interval_minutes * 60
            logger.info("Sleeping %d minutes until next cycle...", interval_minutes)
            time.sleep(sleep_seconds)

    except KeyboardInterrupt:
        logger.info("Real-time monitoring stopped by user (cycle #%d)", cycle)

    except Exception:
        logger.exception(
            "Unexpected error in monitoring loop (cycle #%d) -- restarting after delay",
            cycle,
        )
        # Brief pause to avoid tight error loops, then the outer caller can
        # decide whether to restart.
        time.sleep(30)
