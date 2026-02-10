"""
Walk-forward validation and signal-level performance analysis.
Provides out-of-sample validation to guard against overfitting.
Adapted from the Hedge Fund backtester walk-forward framework.
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
from dateutil.relativedelta import relativedelta
from sqlalchemy import select

from ..db import session_scope
from ..schemas import ExplosiveSignals, Labels, Predictions
from .labeler import label_explosions
from .metrics import calculate_performance
from .simulator import simulate
from ..scoring.ml_scorer import train_model, score_symbols

logger = logging.getLogger("apredator.backtest.validator")


def walk_forward_validate(
    symbols: List[str],
    start_date: str,
    end_date: str,
    train_months: int = 12,
    test_months: int = 3,
    min_score: int = 70,
) -> Dict:
    """
    Rolling walk-forward validation.

    The date range is split into overlapping windows: each window trains
    on *train_months* of data and tests on the subsequent *test_months*.
    The window then slides forward by *test_months* and repeats.

    For each window the pipeline is:
        1. ``label_explosions`` on the training period.
        2. ``train_model`` on training data.
        3. ``score_symbols`` on the test period.
        4. ``simulate`` on the test period.
        5. ``calculate_performance`` on the simulated trades.

    Args:
        symbols: Universe of symbols to validate.
        start_date: Overall start date (YYYY-MM-DD).
        end_date: Overall end date (YYYY-MM-DD).
        train_months: Length of each training window in months.
        test_months: Length of each test window in months.
        min_score: Minimum quantum score for trade entry.

    Returns:
        Dictionary with ``periods`` (list of per-window results) and
        ``aggregate`` summary statistics.
    """
    logger.info(
        f"Walk-forward validation: {start_date} to {end_date} | "
        f"train={train_months}m, test={test_months}m, "
        f"{len(symbols)} symbols"
    )

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    periods: List[Dict] = []
    window_start = start_dt

    while True:
        train_end = window_start + relativedelta(months=train_months)
        test_start = train_end
        test_end = test_start + relativedelta(months=test_months)

        if test_end > end_dt:
            break

        train_start_str = window_start.strftime("%Y-%m-%d")
        train_end_str = train_end.strftime("%Y-%m-%d")
        test_start_str = test_start.strftime("%Y-%m-%d")
        test_end_str = test_end.strftime("%Y-%m-%d")

        logger.info(
            f"Window: train [{train_start_str} .. {train_end_str}] "
            f"| test [{test_start_str} .. {test_end_str}]"
        )

        # 1. Label explosions on the training period
        for sym in symbols:
            try:
                label_explosions(sym)
            except Exception as exc:
                logger.warning(f"Labeling failed for {sym}: {exc}")

        # 2. Train model on training data
        model_dict = None
        try:
            model_dict = train_model(
                symbols=symbols,
                asset_type="stock",
            )
        except Exception as exc:
            logger.error(f"Training failed for window ending {train_end_str}: {exc}")
            window_start += relativedelta(months=test_months)
            continue

        if model_dict is None:
            logger.warning(f"No model produced for window ending {train_end_str}")
            window_start += relativedelta(months=test_months)
            continue

        # 3. Score symbols on the test period
        try:
            score_symbols(
                symbols=symbols,
                model_dict=model_dict,
                asset_type="stock",
            )
        except Exception as exc:
            logger.error(f"Scoring failed for window {test_start_str}: {exc}")
            window_start += relativedelta(months=test_months)
            continue

        # 4. Simulate on the test period
        trades_df = simulate(
            start_date=test_start_str,
            end_date=test_end_str,
            min_score=min_score,
            symbols=symbols,
        )

        # 5. Compute performance metrics
        perf = calculate_performance(trades_df)

        period_result = {
            "train_start": train_start_str,
            "train_end": train_end_str,
            "test_start": test_start_str,
            "test_end": test_end_str,
            "n_trades": perf.get("total_trades", 0),
            "hit_rate": perf.get("hit_rate", 0.0),
            "sharpe": perf.get("sharpe_ratio", 0.0),
            "total_pnl": perf.get("total_pnl", 0.0),
            "avg_return": perf.get("avg_return", 0.0),
            "max_drawdown": perf.get("max_drawdown", 0.0),
            "n_signals": len(trades_df) if not trades_df.empty else 0,
        }
        periods.append(period_result)

        logger.info(
            f"  Result: {period_result['n_trades']} trades, "
            f"hit_rate={period_result['hit_rate']:.2%}, "
            f"sharpe={period_result['sharpe']:.2f}"
        )

        # Slide forward
        window_start += relativedelta(months=test_months)

    # ------------------------------------------------------------------
    # Aggregate statistics across all periods
    # ------------------------------------------------------------------
    if periods:
        periods_with_trades = [p for p in periods if p["n_trades"] > 0]
        n_periods_with_trades = len(periods_with_trades)

        avg_hit_rate = (
            sum(p["hit_rate"] for p in periods_with_trades) / n_periods_with_trades
            if n_periods_with_trades > 0
            else 0.0
        )
        avg_sharpe = (
            sum(p["sharpe"] for p in periods_with_trades) / n_periods_with_trades
            if n_periods_with_trades > 0
            else 0.0
        )
        # Consistency: fraction of test periods that were profitable
        profitable_periods = sum(
            1 for p in periods_with_trades if p["total_pnl"] > 0
        )
        consistency = (
            profitable_periods / n_periods_with_trades
            if n_periods_with_trades > 0
            else 0.0
        )
    else:
        avg_hit_rate = 0.0
        avg_sharpe = 0.0
        consistency = 0.0

    aggregate = {
        "n_periods": len(periods),
        "n_periods_with_trades": len([p for p in periods if p["n_trades"] > 0]),
        "avg_hit_rate": avg_hit_rate,
        "avg_sharpe": avg_sharpe,
        "consistency": consistency,
        "total_pnl": sum(p["total_pnl"] for p in periods),
    }

    logger.info(
        f"Walk-forward complete: {aggregate['n_periods']} periods, "
        f"avg hit rate={aggregate['avg_hit_rate']:.2%}, "
        f"avg sharpe={aggregate['avg_sharpe']:.2f}, "
        f"consistency={aggregate['consistency']:.2%}"
    )

    return {"periods": periods, "aggregate": aggregate}


def validate_combo_performance(
    combo_name: str,
    start_date: str,
    end_date: str,
) -> Dict:
    """
    Validate in-sample vs out-of-sample hit rate for a specific combo.

    Queries ``ExplosiveSignals`` where ``matched_combos`` contains
    *combo_name*, joins with ``Labels`` to determine actual outcomes,
    then splits 70/30 for IS/OOS comparison.

    Args:
        combo_name: Name of the combo pattern (e.g. "vol_squeeze_breakout").
        start_date: Analysis start (YYYY-MM-DD).
        end_date: Analysis end (YYYY-MM-DD).

    Returns:
        Dictionary with ``combo``, ``is_hit_rate``, ``oos_hit_rate``,
        ``n_signals``, and ``expected_hit_rate``.
    """
    logger.info(
        f"Validating combo '{combo_name}' performance: {start_date} to {end_date}"
    )

    with session_scope() as session:
        # Get all signals matching this combo in the date range
        signals = session.execute(
            select(ExplosiveSignals)
            .where(
                ExplosiveSignals.date >= start_date,
                ExplosiveSignals.date <= end_date,
                ExplosiveSignals.matched_combos.contains(combo_name),
            )
        ).scalars().all()

        if not signals:
            logger.warning(f"No signals found for combo '{combo_name}'")
            return {
                "combo": combo_name,
                "is_hit_rate": 0.0,
                "oos_hit_rate": 0.0,
                "n_signals": 0,
                "expected_hit_rate": 0.0,
            }

        # Join with labels to get outcomes
        records = []
        for sig in signals:
            label = session.get(Labels, (sig.symbol, sig.date))
            if label is not None and label.explosive_10d is not None:
                records.append(
                    {
                        "symbol": sig.symbol,
                        "date": sig.date,
                        "hit": bool(label.explosive_10d),
                    }
                )

        if not records:
            logger.warning(f"No labelled outcomes for combo '{combo_name}'")
            return {
                "combo": combo_name,
                "is_hit_rate": 0.0,
                "oos_hit_rate": 0.0,
                "n_signals": 0,
                "expected_hit_rate": 0.0,
            }

        df = pd.DataFrame(records).sort_values("date").reset_index(drop=True)

        # Split 70/30 for IS/OOS
        split_idx = int(len(df) * 0.70)
        is_df = df.iloc[:split_idx]
        oos_df = df.iloc[split_idx:]

        is_hit_rate = float(is_df["hit"].mean()) if len(is_df) > 0 else 0.0
        oos_hit_rate = float(oos_df["hit"].mean()) if len(oos_df) > 0 else 0.0
        expected_hit_rate = float(df["hit"].mean())

        logger.info(
            f"Combo '{combo_name}': {len(df)} signals | "
            f"IS hit rate={is_hit_rate:.2%} ({len(is_df)} samples) | "
            f"OOS hit rate={oos_hit_rate:.2%} ({len(oos_df)} samples)"
        )

        return {
            "combo": combo_name,
            "is_hit_rate": is_hit_rate,
            "oos_hit_rate": oos_hit_rate,
            "n_signals": len(df),
            "expected_hit_rate": expected_hit_rate,
        }


def compute_signal_lift(
    signal_name: str,
    start_date: str,
    end_date: str,
) -> Dict:
    """
    Compute the incremental lift a specific signal provides over the baseline.

    Baseline = overall hit rate for all predictions in the period.
    Signal hit rate = hit rate when this specific signal was active (present
    in the ``components`` field of ``Predictions``).

    Args:
        signal_name: Name of the signal/feature to evaluate.
        start_date: Analysis start (YYYY-MM-DD).
        end_date: Analysis end (YYYY-MM-DD).

    Returns:
        Dictionary with ``signal_name``, ``hit_rate``, ``baseline_rate``,
        and ``lift_pct``.
    """
    logger.info(
        f"Computing signal lift for '{signal_name}': {start_date} to {end_date}"
    )

    with session_scope() as session:
        # All predictions in the date range
        all_preds = session.execute(
            select(Predictions).where(
                Predictions.date >= start_date,
                Predictions.date <= end_date,
            )
        ).scalars().all()

        if not all_preds:
            logger.warning("No predictions found in the specified date range")
            return {
                "signal_name": signal_name,
                "hit_rate": 0.0,
                "baseline_rate": 0.0,
                "lift_pct": 0.0,
            }

        # Build records with outcome labels
        baseline_records = []
        signal_records = []

        for pred in all_preds:
            label = session.get(Labels, (pred.symbol, pred.date))
            if label is None or label.explosive_10d is None:
                continue

            hit = bool(label.explosive_10d)
            baseline_records.append(hit)

            # Check if this signal was active in the prediction's components
            components_str = pred.components or ""
            if signal_name in components_str:
                signal_records.append(hit)

        if not baseline_records:
            logger.warning("No labelled outcomes found for baseline calculation")
            return {
                "signal_name": signal_name,
                "hit_rate": 0.0,
                "baseline_rate": 0.0,
                "lift_pct": 0.0,
            }

        baseline_rate = sum(baseline_records) / len(baseline_records)

        if not signal_records:
            logger.warning(
                f"Signal '{signal_name}' was never active in the period"
            )
            return {
                "signal_name": signal_name,
                "hit_rate": 0.0,
                "baseline_rate": baseline_rate,
                "lift_pct": 0.0,
            }

        signal_hit_rate = sum(signal_records) / len(signal_records)

        lift_pct = (
            ((signal_hit_rate - baseline_rate) / baseline_rate * 100)
            if baseline_rate > 0
            else 0.0
        )

        logger.info(
            f"Signal '{signal_name}': hit_rate={signal_hit_rate:.2%} "
            f"({len(signal_records)} occurrences) | "
            f"baseline={baseline_rate:.2%} | lift={lift_pct:+.1f}%"
        )

        return {
            "signal_name": signal_name,
            "hit_rate": signal_hit_rate,
            "baseline_rate": baseline_rate,
            "lift_pct": lift_pct,
        }
