"""
Backtesting simulator for Alpha Predator.
Simulates trading based on historical predictions and quantum scores.
Adapted from QAHT backtest/simulator.py.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import select

from ..db import session_scope
from ..schemas import Predictions, PriceOHLC

logger = logging.getLogger("apredator.backtest.simulator")


class Trade:
    """Represents a single simulated trade with full lifecycle tracking."""

    def __init__(
        self,
        symbol: str,
        entry_date: str,
        entry_price: float,
        position_size: float,
        quantum_score: int,
        conviction_level: str,
    ):
        self.symbol = symbol
        self.entry_date = entry_date
        self.entry_price = entry_price
        self.position_size = position_size
        self.quantum_score = quantum_score
        self.conviction_level = conviction_level

        self.exit_date: Optional[str] = None
        self.exit_price: Optional[float] = None
        self.pnl: Optional[float] = None
        self.return_pct: Optional[float] = None
        self.hold_days: Optional[int] = None
        self.exit_reason: Optional[str] = None

    def close(self, exit_date: str, exit_price: float, exit_reason: str) -> None:
        """Close the trade and compute P&L fields."""
        self.exit_date = exit_date
        self.exit_price = exit_price
        self.exit_reason = exit_reason

        self.return_pct = (exit_price - self.entry_price) / self.entry_price
        self.pnl = self.position_size * self.return_pct

        entry_dt = datetime.strptime(self.entry_date, "%Y-%m-%d")
        exit_dt = datetime.strptime(self.exit_date, "%Y-%m-%d")
        self.hold_days = (exit_dt - entry_dt).days

    def to_dict(self) -> Dict:
        """Serialise all fields to a plain dictionary."""
        return {
            "symbol": self.symbol,
            "entry_date": self.entry_date,
            "entry_price": self.entry_price,
            "position_size": self.position_size,
            "quantum_score": self.quantum_score,
            "conviction_level": self.conviction_level,
            "exit_date": self.exit_date,
            "exit_price": self.exit_price,
            "pnl": self.pnl,
            "return_pct": self.return_pct,
            "hold_days": self.hold_days,
            "exit_reason": self.exit_reason,
        }


# ---------------------------------------------------------------------------
# Main simulation entry point
# ---------------------------------------------------------------------------


def simulate(
    start_date: str,
    end_date: str,
    initial_capital: float = 100_000,
    min_score: int = 70,
    max_positions: int = 10,
    position_size_pct: float = 0.10,
    max_hold_days: int = 14,
    profit_target: float = 0.50,
    stop_loss: float = -0.15,
    symbols: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Simulate trading over a historical period using stored Predictions.

    Walk through each date in chronological order.  On every date the
    simulator first evaluates open positions for exits (profit-target,
    stop-loss, or time-stop), then considers new entries from the
    highest-scoring predictions that day.

    Entry price = next trading day's open (falling back to signal-day
    close when the next day is unavailable).  Exit price = close on the
    exit day.

    Any positions still open at *end_date* are forcibly closed.

    Args:
        start_date: Backtest start (YYYY-MM-DD).
        end_date:   Backtest end   (YYYY-MM-DD).
        initial_capital: Starting capital in dollars.
        min_score: Minimum quantum_score to consider for entry.
        max_positions: Maximum concurrent open positions.
        position_size_pct: Fraction of current capital per position (0-1).
        max_hold_days: Close position after this many calendar days.
        profit_target: Take-profit threshold (e.g. 0.50 = +50 %).
        stop_loss: Stop-loss threshold (e.g. -0.15 = -15 %).
        symbols: Restrict simulation to these symbols (None = all).

    Returns:
        DataFrame of closed trades (one row per trade).
    """
    logger.info(
        f"Starting backtest simulation: {start_date} to {end_date}"
    )
    logger.info(
        f"Min score: {min_score}, Max positions: {max_positions}, "
        f"Position size: {position_size_pct * 100:.0f}%"
    )

    with session_scope() as session:
        # ------------------------------------------------------------------
        # Load predictions in the date window
        # ------------------------------------------------------------------
        query = (
            select(Predictions)
            .where(
                Predictions.date >= start_date,
                Predictions.date <= end_date,
                Predictions.quantum_score >= min_score,
            )
            .order_by(Predictions.date, Predictions.quantum_score.desc())
        )

        if symbols:
            query = query.where(Predictions.symbol.in_(symbols))

        predictions = session.execute(query).scalars().all()
        logger.info(
            f"Found {len(predictions)} predictions with score >= {min_score}"
        )

        # Organise predictions by date
        predictions_by_date: Dict[str, List] = {}
        for pred in predictions:
            predictions_by_date.setdefault(pred.date, []).append(pred)

        # ------------------------------------------------------------------
        # Simulation state
        # ------------------------------------------------------------------
        capital = initial_capital
        open_trades: List[Trade] = []
        closed_trades: List[Trade] = []

        dates = sorted(predictions_by_date.keys())

        for date in dates:
            # ---------- Check exits first ----------
            trades_to_close: List[Trade] = []

            for trade in open_trades:
                exit_price, exit_reason = _check_exit_conditions(
                    session, trade, date, max_hold_days, profit_target, stop_loss
                )
                if exit_price is not None:
                    trade.close(date, exit_price, exit_reason)
                    capital += trade.position_size + trade.pnl
                    closed_trades.append(trade)
                    trades_to_close.append(trade)
                    logger.debug(
                        f"Closed {trade.symbol} | "
                        f"Entry: {trade.entry_date} @ ${trade.entry_price:.2f} | "
                        f"Exit: {date} @ ${exit_price:.2f} | "
                        f"P&L: ${trade.pnl:.2f} ({trade.return_pct * 100:.1f}%) | "
                        f"Reason: {exit_reason}"
                    )

            for trade in trades_to_close:
                open_trades.remove(trade)

            # ---------- Check entries ----------
            if len(open_trades) < max_positions:
                day_predictions = predictions_by_date[date]
                # Best scores first (already ordered, but re-sort to be safe)
                day_predictions.sort(
                    key=lambda p: p.quantum_score, reverse=True
                )

                for pred in day_predictions:
                    if len(open_trades) >= max_positions:
                        break

                    # Skip if already holding this symbol
                    if any(t.symbol == pred.symbol for t in open_trades):
                        continue

                    # Determine entry price
                    entry_price = _get_entry_price(session, pred.symbol, date)
                    if entry_price is None:
                        continue

                    position_value = capital * position_size_pct

                    trade = Trade(
                        symbol=pred.symbol,
                        entry_date=date,
                        entry_price=entry_price,
                        position_size=position_value,
                        quantum_score=pred.quantum_score,
                        conviction_level=pred.conviction_level or "UNKNOWN",
                    )
                    open_trades.append(trade)
                    capital -= position_value

                    logger.debug(
                        f"Opened {trade.symbol} | Date: {date} "
                        f"@ ${entry_price:.2f} | Score: {trade.quantum_score} | "
                        f"Conviction: {trade.conviction_level} | "
                        f"Size: ${position_value:.2f}"
                    )

        # ------------------------------------------------------------------
        # Force-close remaining open trades at end_date
        # ------------------------------------------------------------------
        for trade in open_trades:
            exit_price = _get_exit_price(session, trade.symbol, end_date)
            if exit_price is not None:
                trade.close(end_date, exit_price, "end_of_backtest")
                capital += trade.position_size + trade.pnl
                closed_trades.append(trade)

        # ------------------------------------------------------------------
        # Return results
        # ------------------------------------------------------------------
        if closed_trades:
            df = pd.DataFrame([t.to_dict() for t in closed_trades])
            logger.info(
                f"Backtest complete: {len(closed_trades)} trades, "
                f"Final capital: ${capital:,.2f}"
            )
            return df

        logger.warning("No trades executed during backtest period")
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_exit_conditions(
    session,
    trade: Trade,
    current_date: str,
    max_hold_days: int,
    profit_target: float,
    stop_loss: float,
) -> Tuple[Optional[float], Optional[str]]:
    """
    Evaluate whether an open trade should be exited on *current_date*.

    Returns:
        ``(exit_price, reason)`` if the trade should be closed, otherwise
        ``(None, None)``.
    """
    current_price = _get_exit_price(session, trade.symbol, current_date)
    if current_price is None:
        return None, None

    current_return = (current_price - trade.entry_price) / trade.entry_price

    # Profit target
    if profit_target is not None and current_return >= profit_target:
        return current_price, "profit_target"

    # Stop loss
    if stop_loss is not None and current_return <= stop_loss:
        return current_price, "stop_loss"

    # Time stop
    entry_dt = datetime.strptime(trade.entry_date, "%Y-%m-%d")
    current_dt = datetime.strptime(current_date, "%Y-%m-%d")
    hold_days = (current_dt - entry_dt).days

    if hold_days >= max_hold_days:
        return current_price, "time_stop"

    return None, None


def _get_entry_price(
    session, symbol: str, signal_date: str
) -> Optional[float]:
    """
    Get entry price for a signal.

    Tries next trading day's open first; falls back to signal-day close.
    """
    signal_dt = datetime.strptime(signal_date, "%Y-%m-%d")
    next_day = (signal_dt + timedelta(days=1)).strftime("%Y-%m-%d")

    # Attempt: next day's open
    result = session.execute(
        select(PriceOHLC.open).where(
            PriceOHLC.symbol == symbol, PriceOHLC.date == next_day
        )
    ).scalar_one_or_none()

    if result is not None:
        return float(result)

    # Fallback: signal day close
    result = session.execute(
        select(PriceOHLC.close).where(
            PriceOHLC.symbol == symbol, PriceOHLC.date == signal_date
        )
    ).scalar_one_or_none()

    return float(result) if result is not None else None


def _get_exit_price(
    session, symbol: str, date: str
) -> Optional[float]:
    """Return the closing price on *date* for *symbol*."""
    result = session.execute(
        select(PriceOHLC.close).where(
            PriceOHLC.symbol == symbol, PriceOHLC.date == date
        )
    ).scalar_one_or_none()

    return float(result) if result is not None else None
