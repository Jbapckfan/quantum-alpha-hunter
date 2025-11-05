"""
Backtesting simulator for Quantum Alpha Hunter
Simulates trading based on historical predictions and scores
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
from sqlalchemy import select

from ..db import session_scope
from ..schemas import Predictions, PriceOHLC, Labels
from ..config import load_config

logger = logging.getLogger("qaht.backtest.simulator")


class Trade:
    """Represents a single trade"""
    def __init__(
        self,
        symbol: str,
        entry_date: str,
        entry_price: float,
        position_size: float,
        quantum_score: int,
        conviction_level: str
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

    def close(self, exit_date: str, exit_price: float, exit_reason: str):
        """Close the trade"""
        self.exit_date = exit_date
        self.exit_price = exit_price
        self.exit_reason = exit_reason

        # Calculate P&L
        self.return_pct = (exit_price - self.entry_price) / self.entry_price
        self.pnl = self.position_size * self.return_pct

        # Calculate hold time
        entry_dt = datetime.strptime(self.entry_date, "%Y-%m-%d")
        exit_dt = datetime.strptime(self.exit_date, "%Y-%m-%d")
        self.hold_days = (exit_dt - entry_dt).days

    def to_dict(self) -> Dict:
        """Convert to dictionary for DataFrame creation"""
        return {
            'symbol': self.symbol,
            'entry_date': self.entry_date,
            'entry_price': self.entry_price,
            'position_size': self.position_size,
            'quantum_score': self.quantum_score,
            'conviction_level': self.conviction_level,
            'exit_date': self.exit_date,
            'exit_price': self.exit_price,
            'pnl': self.pnl,
            'return_pct': self.return_pct,
            'hold_days': self.hold_days,
            'exit_reason': self.exit_reason
        }


def simulate(
    start_date: str,
    end_date: str,
    initial_capital: float = 100000,
    min_score: int = 70,
    max_positions: int = 10,
    position_size_pct: float = 0.10,
    max_hold_days: int = 14,
    profit_target: Optional[float] = 0.50,
    stop_loss: Optional[float] = -0.15,
    symbols: Optional[List[str]] = None
) -> pd.DataFrame:
    """
    Simulate trading based on historical predictions

    Args:
        start_date: Start date for backtest (YYYY-MM-DD)
        end_date: End date for backtest (YYYY-MM-DD)
        initial_capital: Starting capital ($)
        min_score: Minimum quantum score to enter trade (0-100)
        max_positions: Maximum concurrent positions
        position_size_pct: Position size as % of capital (0.0-1.0)
        max_hold_days: Maximum days to hold position
        profit_target: Take profit at this return (e.g., 0.50 = 50%)
        stop_loss: Stop loss at this return (e.g., -0.15 = -15%)
        symbols: List of symbols to backtest (None = all)

    Returns:
        DataFrame of trades with P&L
    """
    logger.info(f"Starting backtest simulation: {start_date} to {end_date}")
    logger.info(f"Min score: {min_score}, Max positions: {max_positions}, Position size: {position_size_pct*100}%")

    with session_scope() as session:
        # Get all predictions in date range
        query = select(Predictions).where(
            Predictions.date >= start_date,
            Predictions.date <= end_date,
            Predictions.quantum_score >= min_score
        ).order_by(Predictions.date, Predictions.quantum_score.desc())

        if symbols:
            query = query.where(Predictions.symbol.in_(symbols))

        predictions = session.execute(query).scalars().all()

        logger.info(f"Found {len(predictions)} predictions with score >= {min_score}")

        # Organize predictions by date
        predictions_by_date = {}
        for pred in predictions:
            if pred.date not in predictions_by_date:
                predictions_by_date[pred.date] = []
            predictions_by_date[pred.date].append(pred)

        # Simulation state
        capital = initial_capital
        open_trades: List[Trade] = []
        closed_trades: List[Trade] = []

        # Walk through each date
        dates = sorted(predictions_by_date.keys())
        for date in dates:
            # Check exits first (evaluate open positions)
            trades_to_close = []
            for trade in open_trades:
                exit_price, exit_reason = _check_exit_conditions(
                    session, trade, date, max_hold_days, profit_target, stop_loss
                )
                if exit_price:
                    trade.close(date, exit_price, exit_reason)
                    capital += trade.position_size + trade.pnl
                    closed_trades.append(trade)
                    trades_to_close.append(trade)
                    logger.debug(
                        f"Closed {trade.symbol} | Entry: {trade.entry_date} @ ${trade.entry_price:.2f} "
                        f"| Exit: {date} @ ${exit_price:.2f} | P&L: ${trade.pnl:.2f} ({trade.return_pct*100:.1f}%) "
                        f"| Reason: {exit_reason}"
                    )

            # Remove closed trades
            for trade in trades_to_close:
                open_trades.remove(trade)

            # Check entries (new signals)
            if len(open_trades) < max_positions:
                day_predictions = predictions_by_date[date]
                # Sort by score descending (best signals first)
                day_predictions.sort(key=lambda p: p.quantum_score, reverse=True)

                for pred in day_predictions:
                    if len(open_trades) >= max_positions:
                        break

                    # Check if already in this symbol
                    if any(t.symbol == pred.symbol for t in open_trades):
                        continue

                    # Get entry price (use next day's open)
                    entry_price = _get_entry_price(session, pred.symbol, date)
                    if not entry_price:
                        continue

                    # Calculate position size
                    position_value = capital * position_size_pct

                    # Create trade
                    trade = Trade(
                        symbol=pred.symbol,
                        entry_date=date,
                        entry_price=entry_price,
                        position_size=position_value,
                        quantum_score=pred.quantum_score,
                        conviction_level=pred.conviction_level or "UNKNOWN"
                    )
                    open_trades.append(trade)
                    capital -= position_value

                    logger.debug(
                        f"Opened {trade.symbol} | Date: {date} @ ${entry_price:.2f} "
                        f"| Score: {trade.quantum_score} | Conviction: {trade.conviction_level} "
                        f"| Size: ${position_value:.2f}"
                    )

        # Close any remaining open trades at end date
        for trade in open_trades:
            exit_price = _get_exit_price(session, trade.symbol, end_date)
            if exit_price:
                trade.close(end_date, exit_price, "end_of_backtest")
                capital += trade.position_size + trade.pnl
                closed_trades.append(trade)

        # Convert to DataFrame
        if closed_trades:
            df = pd.DataFrame([t.to_dict() for t in closed_trades])
            logger.info(f"Backtest complete: {len(closed_trades)} trades, Final capital: ${capital:,.2f}")
            return df
        else:
            logger.warning("No trades executed during backtest period")
            return pd.DataFrame()


def _check_exit_conditions(
    session,
    trade: Trade,
    current_date: str,
    max_hold_days: int,
    profit_target: Optional[float],
    stop_loss: Optional[float]
) -> Tuple[Optional[float], Optional[str]]:
    """
    Check if trade should be exited

    Returns:
        (exit_price, exit_reason) if should exit, else (None, None)
    """
    # Get current price
    current_price = _get_exit_price(session, trade.symbol, current_date)
    if not current_price:
        return None, None

    # Calculate current return
    current_return = (current_price - trade.entry_price) / trade.entry_price

    # Check profit target
    if profit_target and current_return >= profit_target:
        return current_price, "profit_target"

    # Check stop loss
    if stop_loss and current_return <= stop_loss:
        return current_price, "stop_loss"

    # Check max hold time
    entry_dt = datetime.strptime(trade.entry_date, "%Y-%m-%d")
    current_dt = datetime.strptime(current_date, "%Y-%m-%d")
    hold_days = (current_dt - entry_dt).days

    if hold_days >= max_hold_days:
        return current_price, "time_stop"

    return None, None


def _get_entry_price(session, symbol: str, signal_date: str) -> Optional[float]:
    """
    Get entry price (next day's open after signal)
    If next day not available, use signal day close
    """
    signal_dt = datetime.strptime(signal_date, "%Y-%m-%d")
    next_day = (signal_dt + timedelta(days=1)).strftime("%Y-%m-%d")

    # Try to get next day's open
    result = session.execute(
        select(PriceOHLC.open)
        .where(PriceOHLC.symbol == symbol, PriceOHLC.date == next_day)
    ).scalar_one_or_none()

    if result:
        return float(result)

    # Fallback to signal day close
    result = session.execute(
        select(PriceOHLC.close)
        .where(PriceOHLC.symbol == symbol, PriceOHLC.date == signal_date)
    ).scalar_one_or_none()

    return float(result) if result else None


def _get_exit_price(session, symbol: str, exit_date: str) -> Optional[float]:
    """Get exit price (close on exit date)"""
    result = session.execute(
        select(PriceOHLC.close)
        .where(PriceOHLC.symbol == symbol, PriceOHLC.date == exit_date)
    ).scalar_one_or_none()

    return float(result) if result else None
