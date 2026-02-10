"""
Full daily pipeline orchestrating all Alpha Predator modules.

This is the main entry point for a complete scan cycle: universe selection,
data ingestion, feature computation, ML scoring, combo matching, position
sizing, alert delivery, and self-learning outcome tracking.
"""
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from ..adapters import fetch_and_upsert, fetch_reddit_mentions
from ..alerts import send_discord_alert, AlertMonitor
from ..backtest import label_explosions
from ..config import get_config
from ..db import session_scope
from ..features import (
    compute_all_explosive,
    compute_all_technical,
    compute_crypto_features,
    compute_order_flow,
    compute_smart_money,
    compute_social_features,
    detect_regime,
    GammaSqueezeDetector,
    ShortSqueezeDetector,
)
from ..schemas import Factors, PriceOHLC, Predictions
from ..scoring import (
    classify_tier,
    combine_scores,
    kelly_position_size,
    match_combos,
    score_symbols,
    train_model,
)
from ..universe import get_crypto_universe, get_stock_universe
from ..utils.parallel import process_concurrently

logger = logging.getLogger("apredator.pipeline.daily_scan")


# ---------------------------------------------------------------------------
# Step timing tracker
# ---------------------------------------------------------------------------

class PipelineMonitor:
    """Tracks wall-clock duration of each pipeline step."""

    def __init__(self):
        self._starts: Dict[str, float] = {}
        self._durations: Dict[str, float] = {}

    def start_step(self, name: str) -> None:
        self._starts[name] = time.time()
        logger.info("Step [%s] started", name)

    def end_step(self, name: str) -> None:
        start = self._starts.pop(name, None)
        if start is not None:
            elapsed = time.time() - start
            self._durations[name] = round(elapsed, 2)
            logger.info("Step [%s] completed in %.2fs", name, elapsed)

    def get_summary(self) -> Dict[str, float]:
        """Return mapping of step name -> elapsed seconds."""
        return dict(self._durations)


# ---------------------------------------------------------------------------
# Per-symbol feature computation helper
# ---------------------------------------------------------------------------

def _compute_features_for_symbol(symbol: str, asset_type: str) -> Optional[dict]:
    """Fetch price data from the DB and compute all features for *symbol*.

    Returns a dict of feature name -> value, or ``None`` on failure.
    """
    try:
        with session_scope() as session:
            rows = (
                session.query(PriceOHLC)
                .filter(PriceOHLC.symbol == symbol)
                .order_by(PriceOHLC.date)
                .all()
            )

        if not rows or len(rows) < 60:
            logger.debug("Insufficient price data for %s (%d rows)", symbol, len(rows) if rows else 0)
            return None

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
        ])
        df = df.sort_values("date").reset_index(drop=True)

        # Technical indicators
        features = compute_all_technical(df)

        # Explosive signals (stocks and crypto)
        explosive = compute_all_explosive(df)
        features.update(explosive)

        # Institutional features (stocks only -- requires options chain)
        if asset_type == "stock":
            try:
                order_flow = compute_order_flow(df)
                features.update(order_flow)
            except Exception:
                logger.debug("Order flow unavailable for %s", symbol)
            try:
                smart_money = compute_smart_money(df)
                features.update(smart_money)
            except Exception:
                logger.debug("Smart money detection unavailable for %s", symbol)
            try:
                gamma = GammaSqueezeDetector().detect(symbol)
                features["call_oi_ratio"] = gamma.get("call_oi_ratio", 0.0)
            except Exception:
                logger.debug("Gamma squeeze detection unavailable for %s", symbol)
            try:
                short_sq = ShortSqueezeDetector().detect(symbol)
                features["short_pct_float"] = short_sq.get("short_pct_float", 0.0)
            except Exception:
                logger.debug("Short squeeze detection unavailable for %s", symbol)

        # Crypto-specific features
        if asset_type == "crypto":
            crypto_feats = compute_crypto_features(symbol, df)
            features.update(crypto_feats)

        features["symbol"] = symbol
        features["date"] = df["date"].iloc[-1]
        features["asset_type"] = asset_type

        # Upsert into Factors table
        _upsert_factors(symbol, features)

        return features

    except Exception:
        logger.exception("Feature computation failed for %s", symbol)
        return None


def _upsert_factors(symbol: str, features: dict) -> None:
    """Persist feature values to the Factors table."""
    try:
        with session_scope() as session:
            date = features.get("date", datetime.utcnow().strftime("%Y-%m-%d"))
            existing = (
                session.query(Factors)
                .filter(Factors.symbol == symbol, Factors.date == date)
                .first()
            )
            if existing:
                for key, value in features.items():
                    if hasattr(existing, key) and key not in ("symbol", "date"):
                        setattr(existing, key, value)
            else:
                factor_kwargs = {"symbol": symbol, "date": date}
                for key, value in features.items():
                    if hasattr(Factors, key) and key not in ("symbol", "date", "asset_type"):
                        factor_kwargs[key] = value
                session.add(Factors(**factor_kwargs))
    except Exception:
        logger.exception("Failed to upsert factors for %s", symbol)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_daily_scan(
    asset_types: Optional[List[str]] = None,
    symbols: Optional[List[str]] = None,
    send_alerts: bool = True,
) -> dict:
    """Execute the full daily Alpha Predator scan pipeline.

    Parameters
    ----------
    asset_types : list[str], optional
        Asset classes to scan. Defaults to ``["stock", "crypto"]``.
    symbols : list[str], optional
        Explicit symbol list.  If provided, *asset_types* is ignored for
        universe building but still used for feature routing.
    send_alerts : bool
        Whether to deliver Discord alerts for tier 1-2 signals.

    Returns
    -------
    dict
        Summary containing ``n_symbols``, ``n_signals``, ``top_signals``,
        ``regime``, and ``timing``.
    """
    config = get_config()
    monitor = PipelineMonitor()
    alert_monitor = AlertMonitor(config=config)

    if asset_types is None:
        asset_types = ["stock", "crypto"]

    all_features: List[dict] = []
    scored_signals: List[dict] = []
    regime_state: Optional[str] = None

    # -------------------------------------------------------------------------
    # 1. Build universe
    # -------------------------------------------------------------------------
    monitor.start_step("build_universe")
    stock_symbols: List[str] = []
    crypto_symbols: List[str] = []

    if symbols:
        # Caller provided explicit list -- split by convention (crypto symbols
        # typically contain "/" or "-USDT" etc.; a simple heuristic suffices).
        for s in symbols:
            if any(tag in s.upper() for tag in ("/", "-USDT", "-USD", "BUSD", "BTC", "ETH", "SOL")):
                crypto_symbols.append(s)
            else:
                stock_symbols.append(s)
    else:
        if "stock" in asset_types:
            stock_symbols = get_stock_universe()
        if "crypto" in asset_types:
            crypto_symbols = get_crypto_universe()

    all_symbols = stock_symbols + crypto_symbols
    logger.info(
        "Universe built: %d stocks, %d crypto, %d total",
        len(stock_symbols), len(crypto_symbols), len(all_symbols),
    )
    monitor.end_step("build_universe")

    if not all_symbols:
        logger.warning("Empty universe -- aborting scan")
        return {
            "n_symbols": 0,
            "n_signals": 0,
            "top_signals": [],
            "regime": None,
            "timing": monitor.get_summary(),
        }

    # -------------------------------------------------------------------------
    # 2. Fetch prices
    # -------------------------------------------------------------------------
    monitor.start_step("fetch_prices")
    if stock_symbols:
        try:
            fetch_and_upsert(stock_symbols)
        except Exception:
            logger.exception("Stock price fetch failed")

    if crypto_symbols:
        try:
            # Crypto adapter: fetch_and_upsert supports asset_type param
            fetch_and_upsert(crypto_symbols)
        except Exception:
            logger.exception("Crypto price fetch failed")
    monitor.end_step("fetch_prices")

    # -------------------------------------------------------------------------
    # 3. Fetch social data
    # -------------------------------------------------------------------------
    monitor.start_step("fetch_social")
    try:
        fetch_reddit_mentions(all_symbols)
    except Exception:
        logger.exception("Social data fetch failed")
    monitor.end_step("fetch_social")

    # -------------------------------------------------------------------------
    # 4. Detect market regime
    # -------------------------------------------------------------------------
    monitor.start_step("detect_regime")
    try:
        regime_result = detect_regime()
        regime_state = regime_result.get("regime_state") if isinstance(regime_result, dict) else str(regime_result)
        logger.info("Market regime: %s", regime_state)
    except Exception:
        logger.exception("Regime detection failed")
    monitor.end_step("detect_regime")

    # -------------------------------------------------------------------------
    # 5 & 6 & 7. Compute features (technical + explosive + institutional + crypto)
    # -------------------------------------------------------------------------
    monitor.start_step("compute_features")

    def _compute_stock(symbol: str) -> Optional[dict]:
        return _compute_features_for_symbol(symbol, "stock")

    def _compute_crypto(symbol: str) -> Optional[dict]:
        return _compute_features_for_symbol(symbol, "crypto")

    max_workers = config.pipeline.max_concurrent

    if stock_symbols:
        stock_results = process_concurrently(
            stock_symbols, _compute_stock,
            max_workers=max_workers, description="Stock features",
        )
        all_features.extend([r for r in stock_results if r is not None])

    if crypto_symbols:
        crypto_results = process_concurrently(
            crypto_symbols, _compute_crypto,
            max_workers=max_workers, description="Crypto features",
        )
        all_features.extend([r for r in crypto_results if r is not None])

    monitor.end_step("compute_features")

    # -------------------------------------------------------------------------
    # 8. Compute social features
    # -------------------------------------------------------------------------
    monitor.start_step("social_features")
    for feat_dict in all_features:
        try:
            symbol = feat_dict["symbol"]
            social = compute_social_features(symbol)
            feat_dict.update(social)
        except Exception:
            logger.debug("Social features unavailable for %s", feat_dict.get("symbol"))
    monitor.end_step("social_features")

    # -------------------------------------------------------------------------
    # 9. Label explosions (for training data)
    # -------------------------------------------------------------------------
    monitor.start_step("label_explosions")
    try:
        for symbol in all_symbols:
            try:
                label_explosions(symbol)
            except Exception:
                logger.debug("Labelling skipped for %s", symbol)
    except Exception:
        logger.exception("Explosion labelling failed")
    monitor.end_step("label_explosions")

    # -------------------------------------------------------------------------
    # 10. Match combos and classify tiers
    # -------------------------------------------------------------------------
    monitor.start_step("match_combos")
    for feat_dict in all_features:
        try:
            combos = match_combos(feat_dict)
            feat_dict["combos"] = combos
            if combos:
                best = max(combos, key=lambda c: c["hit_rate"])
                feat_dict["best_combo"] = best["name"]
                tier_result = classify_tier(feat_dict)
                feat_dict["tier"] = tier_result.get("tier") or 5
                feat_dict["tier_hit_rate"] = tier_result.get("hit_rate", 0.0)
                feat_dict["tier_conviction"] = tier_result.get("conviction", "NONE")
            else:
                feat_dict["best_combo"] = None
                feat_dict["tier"] = 5
        except Exception:
            logger.debug("Combo matching failed for %s", feat_dict.get("symbol"))
            feat_dict["combos"] = []
            feat_dict["best_combo"] = None
            feat_dict["tier"] = 5
    monitor.end_step("match_combos")

    # -------------------------------------------------------------------------
    # 11. ML scoring
    # -------------------------------------------------------------------------
    monitor.start_step("ml_scoring")
    try:
        for asset_type in asset_types:
            type_symbols = stock_symbols if asset_type == "stock" else crypto_symbols
            if type_symbols:
                model_dict = train_model(type_symbols, asset_type)
                if model_dict is not None:
                    scored_df = score_symbols(type_symbols, model_dict, asset_type)
                    if scored_df is not None and not scored_df.empty:
                        # Merge ML scores into all_features
                        ml_scores = {
                            row["symbol"]: {
                                "quantum_score": row["quantum_score"],
                                "prob_hit_10d": row["prob_hit_10d"],
                                "conviction_level": row["conviction_level"],
                            }
                            for _, row in scored_df.iterrows()
                        }
                        for feat_dict in all_features:
                            ml_result = ml_scores.get(feat_dict.get("symbol"))
                            if ml_result:
                                feat_dict.update(ml_result)
    except Exception:
        logger.exception("ML training/scoring failed")
    monitor.end_step("ml_scoring")

    # -------------------------------------------------------------------------
    # 12. Ensemble scoring
    # -------------------------------------------------------------------------
    monitor.start_step("ensemble")
    for feat_dict in all_features:
        try:
            ensemble = combine_scores(feat_dict)
            feat_dict.update(ensemble)
        except Exception:
            logger.debug("Ensemble scoring failed for %s", feat_dict.get("symbol"))
    monitor.end_step("ensemble")

    # -------------------------------------------------------------------------
    # 13. Position sizing (Kelly) for high-conviction signals
    # -------------------------------------------------------------------------
    monitor.start_step("position_sizing")
    for feat_dict in all_features:
        try:
            tier = feat_dict.get("tier", 5)
            if isinstance(tier, dict):
                tier = tier.get("tier", 5)
            if tier is not None and tier <= 3:
                prob = feat_dict.get("prob_hit_10d", feat_dict.get("ensemble_prob", 0.5))
                kelly = kelly_position_size(probability=prob)
                feat_dict["kelly_fraction"] = kelly
            else:
                feat_dict["kelly_fraction"] = 0.0
        except Exception:
            feat_dict["kelly_fraction"] = 0.0
    monitor.end_step("position_sizing")

    # -------------------------------------------------------------------------
    # 14. Store predictions
    # -------------------------------------------------------------------------
    monitor.start_step("store_predictions")
    try:
        with session_scope() as session:
            for feat_dict in all_features:
                _upsert_prediction(session, feat_dict)
    except Exception:
        logger.exception("Prediction storage failed")
    monitor.end_step("store_predictions")

    # -------------------------------------------------------------------------
    # 15. Send alerts for tier 1-2 signals
    # -------------------------------------------------------------------------
    monitor.start_step("send_alerts")
    webhook_url = config.discord_webhook_url

    for feat_dict in all_features:
        tier = feat_dict.get("tier", 5)
        if tier > 2:
            continue

        symbol = feat_dict["symbol"]
        score = feat_dict.get("quantum_score", feat_dict.get("ensemble_score", 0))
        conviction = feat_dict.get("conviction_level", "MODERATE")
        price = feat_dict.get("close", feat_dict.get("price", 0.0))

        scored_signals.append({
            "symbol": symbol,
            "score": score,
            "conviction": conviction,
            "tier": tier,
            "combo": feat_dict.get("best_combo"),
            "price": price,
        })

        if send_alerts and webhook_url and alert_monitor.should_alert(symbol, conviction, score):
            sent = send_discord_alert(
                webhook_url=webhook_url,
                symbol=symbol,
                score=int(score),
                conviction=conviction,
                price=price,
                combo_name=feat_dict.get("best_combo"),
                tier=tier,
                signals=list(feat_dict.get("combos", [{}])[0].get("matched_signals", []))
                if feat_dict.get("combos") else None,
                kelly_size=feat_dict.get("kelly_fraction"),
                educational_disclaimer=config.alerts.educational_disclaimer,
            )
            if sent:
                alert_monitor.record_alert(symbol, conviction, int(score), price)

    monitor.end_step("send_alerts")

    # -------------------------------------------------------------------------
    # 16. Self-learning: fill past alert outcomes
    # -------------------------------------------------------------------------
    monitor.start_step("self_learning")
    try:
        alert_monitor.fill_outcomes()
    except Exception:
        logger.exception("Self-learning outcome fill failed")
    monitor.end_step("self_learning")

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    timing = monitor.get_summary()
    total_time = sum(timing.values())

    # Sort scored signals by score descending
    scored_signals.sort(key=lambda s: s.get("score", 0), reverse=True)
    top_signals = scored_signals[:10]

    summary = {
        "n_symbols": len(all_symbols),
        "n_signals": len(scored_signals),
        "top_signals": top_signals,
        "regime": regime_state,
        "timing": timing,
    }

    logger.info(
        "Daily scan complete: %d symbols, %d signals, regime=%s, total=%.1fs",
        summary["n_symbols"],
        summary["n_signals"],
        regime_state,
        total_time,
    )

    for sig in top_signals[:5]:
        logger.info(
            "  TOP: %s  score=%s  conviction=%s  tier=%s  combo=%s",
            sig["symbol"], sig["score"], sig["conviction"],
            sig["tier"], sig.get("combo"),
        )

    return summary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _upsert_prediction(session, feat_dict: dict) -> None:
    """Persist a single prediction row to the Predictions table."""
    symbol = feat_dict.get("symbol")
    date = feat_dict.get("date", datetime.utcnow().strftime("%Y-%m-%d"))

    try:
        existing = (
            session.query(Predictions)
            .filter(Predictions.symbol == symbol, Predictions.date == date)
            .first()
        )

        pred_data = {
            "quantum_score": int(feat_dict.get("quantum_score", feat_dict.get("ensemble_score", 0))),
            "prob_hit_10d": feat_dict.get("prob_hit_10d"),
            "conviction_level": feat_dict.get("conviction_level"),
            "combo_match": feat_dict.get("best_combo"),
            "tier": feat_dict.get("tier"),
            "kelly_fraction": feat_dict.get("kelly_fraction"),
            "ensemble_score": feat_dict.get("ensemble_score"),
        }

        if existing:
            for key, value in pred_data.items():
                if hasattr(existing, key) and value is not None:
                    setattr(existing, key, value)
        else:
            session.add(Predictions(symbol=symbol, date=date, **pred_data))

    except Exception:
        logger.exception("Failed to upsert prediction for %s", symbol)
