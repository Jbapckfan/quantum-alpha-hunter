"""
Backtesting simulator - test historical performance of Quantum Alpha Hunter
Simulates trading based on quantum scores with realistic constraints
"""
import pandas as pd
import numpy as np
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import logging

from ..db import session_scope
from ..schemas import Predictions, PriceOHLC, Labels
from ..config import get_config
from sqlalchemy import select, and_

logger = logging.getLogger("qaht.backtest.simulator")
config = get_config()


class Trade:
    """Represents a single trade"""
    def __init__(self, symbol: str, entry_date: str, entry_price: float,
                 quantum_score: int, position_size: float, conviction: str):
        self.symbol = symbol
        self.entry_date = entry_date
        self.entry_price = entry_price
        self.quantum_score = quantum_score
        self.position_size = position_size  # Dollar amount
        self.conviction = conviction
        self.exit_date: Optional[str] = None
        self.exit_price: Optional[float] = None
        self.return_pct: Optional[float] = None
        self.pnl: Optional[float] = None
        self.days_held: Optional[int] = None
        self.exit_reason: Optional[str] = None

    def close(self, exit_date: str, exit_price: float, reason: str = "time_stop"):
        """Close the trade"""
        self.exit_date = exit_date
        self.exit_price = exit_price
        self.exit_reason = reason
        self.return_pct = (exit_price / self.entry_price) - 1
        self.pnl = self.position_size * self.return_pct

        # Calculate days held
        entry = datetime.strptime(self.entry_date, '%Y-%m-%d')
        exit = datetime.strptime(self.exit_date, '%Y-%m-%d')
        self.days_held = (exit - entry).days

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'symbol': self.symbol,
            'entry_date': self.entry_date,
            'entry_price': self.entry_price,
            'exit_date': self.exit_date,
            'exit_price': self.exit_price,
            'quantum_score': self.quantum_score,
            'conviction': self.conviction,
            'position_size': self.position_size,
            'return_pct': self.return_pct,
            'pnl': self.pnl,
            'days_held': self.days_held,
            'exit_reason': self.exit_reason
        }


class PortfolioSimulator:
    """Simulates portfolio management and trading"""

    def __init__(self, initial_capital: float = 100000,
                 max_positions: int = 10,
                 min_score: int = 70,
                 risk_per_trade: float = 0.02,
                 holding_period: int = 14,
                 profit_target: float = 0.50,
                 stop_loss: float = -0.08):
        """
        Initialize simulator

        Args:
            initial_capital: Starting capital
            max_positions: Maximum concurrent positions
            min_score: Minimum quantum score to trade
            risk_per_trade: Max risk per position (fraction of capital)
            holding_period: Max days to hold (time stop)
            profit_target: Take profit at this return (e.g., 0.50 = 50%)
            stop_loss: Stop loss at this return (e.g., -0.08 = -8%)
        """
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.max_positions = max_positions
        self.min_score = min_score
        self.risk_per_trade = risk_per_trade
        self.holding_period = holding_period
        self.profit_target = profit_target
        self.stop_loss = stop_loss

        self.open_trades: List[Trade] = []
        self.closed_trades: List[Trade] = []
        self.equity_curve: List[Dict] = []

    def get_position_size(self, conviction: str) -> float:
        """
        Calculate position size based on conviction level

        Args:
            conviction: MAX, HIGH, MED, or LOW

        Returns:
            Position size as fraction of capital
        """
        # Kelly-inspired sizing based on conviction
        conviction_weights = {
            'MAX': 0.05,   # 5% of capital
            'HIGH': 0.03,  # 3% of capital
            'MED': 0.02,   # 2% of capital
            'LOW': 0.01    # 1% of capital
        }
        return self.capital * conviction_weights.get(conviction, 0.01)

    def can_enter_trade(self) -> bool:
        """Check if we can enter a new position"""
        return len(self.open_trades) < self.max_positions

    def enter_trade(self, symbol: str, date: str, price: float,
                   quantum_score: int, conviction: str) -> Optional[Trade]:
        """
        Enter a new trade

        Args:
            symbol: Ticker
            date: Entry date
            price: Entry price
            quantum_score: Quantum score
            conviction: Conviction level

        Returns:
            Trade object or None if can't enter
        """
        if not self.can_enter_trade():
            return None

        position_size = self.get_position_size(conviction)

        # Create trade
        trade = Trade(
            symbol=symbol,
            entry_date=date,
            entry_price=price,
            quantum_score=quantum_score,
            position_size=position_size,
            conviction=conviction
        )

        self.open_trades.append(trade)
        self.capital -= position_size  # Allocate capital

        logger.info(f"Entered {symbol} @ ${price:.2f}, size=${position_size:.0f}, "
                   f"score={quantum_score}, conviction={conviction}")

        return trade

    def check_exits(self, date: str, prices: Dict[str, float]):
        """
        Check if any open positions should be closed

        Args:
            date: Current date
            prices: Dict of {symbol: current_price}
        """
        trades_to_close = []

        for trade in self.open_trades:
            if trade.symbol not in prices:
                continue

            current_price = prices[trade.symbol]
            current_return = (current_price / trade.entry_price) - 1

            # Entry date
            entry_dt = datetime.strptime(trade.entry_date, '%Y-%m-%d')
            current_dt = datetime.strptime(date, '%Y-%m-%d')
            days_held = (current_dt - entry_dt).days

            # Check exit conditions
            reason = None

            # Profit target hit
            if current_return >= self.profit_target:
                reason = "profit_target"

            # Stop loss hit
            elif current_return <= self.stop_loss:
                reason = "stop_loss"

            # Time stop
            elif days_held >= self.holding_period:
                reason = "time_stop"

            if reason:
                trade.close(date, current_price, reason)
                trades_to_close.append(trade)

                # Return capital plus P&L
                self.capital += trade.position_size + trade.pnl

                logger.info(f"Closed {trade.symbol} @ ${current_price:.2f}, "
                           f"return={trade.return_pct:.2%}, days={days_held}, "
                           f"reason={reason}")

        # Remove closed trades from open positions
        for trade in trades_to_close:
            self.open_trades.remove(trade)
            self.closed_trades.append(trade)

    def record_equity(self, date: str, prices: Dict[str, float]):
        """Record current equity for equity curve"""
        # Calculate mark-to-market value of open positions
        mtm_value = 0
        for trade in self.open_trades:
            if trade.symbol in prices:
                current_value = trade.position_size * (prices[trade.symbol] / trade.entry_price)
                mtm_value += current_value
            else:
                mtm_value += trade.position_size  # Use cost basis if no price

        total_equity = self.capital + mtm_value

        self.equity_curve.append({
            'date': date,
            'equity': total_equity,
            'cash': self.capital,
            'positions_value': mtm_value,
            'num_positions': len(self.open_trades)
        })


def simulate(symbols: Optional[List[str]] = None,
            start_date: str = '2023-01-01',
            end_date: str = '2024-01-01',
            initial_capital: float = 100000,
            min_score: int = 70) -> Dict:
    """
    Run historical backtest simulation

    Args:
        symbols: List of symbols to test (None = all)
        start_date: Start date for backtest
        end_date: End date for backtest
        initial_capital: Starting capital
        min_score: Minimum quantum score to trade

    Returns:
        Dict with simulation results
    """
    logger.info(f"Starting backtest: {start_date} to {end_date}")

    # Initialize simulator
    sim = PortfolioSimulator(
        initial_capital=initial_capital,
        max_positions=config.backtest.max_positions,
        min_score=min_score,
        risk_per_trade=config.backtest.risk_per_trade,
        holding_period=config.backtest.horizon_days,
        profit_target=config.backtest.explosion_threshold_equity,
        stop_loss=-0.08  # 8% max loss per position
    )

    # Get all trading dates
    with session_scope() as session:
        # Get unique dates in range
        dates_query = select(PriceOHLC.date).distinct().where(
            and_(
                PriceOHLC.date >= start_date,
                PriceOHLC.date <= end_date
            )
        ).order_by(PriceOHLC.date)

        trading_dates = [d[0] for d in session.execute(dates_query).all()]

    if not trading_dates:
        logger.warning("No trading dates found in backtest period")
        return {'error': 'No data in date range'}

    logger.info(f"Backtesting over {len(trading_dates)} trading days")

    # Simulate day by day
    for date in trading_dates:
        with session_scope() as session:
            # Get prices for this date
            prices_query = select(PriceOHLC).where(PriceOHLC.date == date)
            if symbols:
                prices_query = prices_query.where(PriceOHLC.symbol.in_(symbols))

            prices_data = session.execute(prices_query).scalars().all()
            prices = {p.symbol: p.close for p in prices_data}

            # Check exits for existing positions
            sim.check_exits(date, prices)

            # Get trading signals for this date
            signals_query = select(Predictions).where(
                and_(
                    Predictions.date == date,
                    Predictions.quantum_score >= min_score
                )
            ).order_by(Predictions.quantum_score.desc())

            if symbols:
                signals_query = signals_query.where(Predictions.symbol.in_(symbols))

            signals = session.execute(signals_query).scalars().all()

            # Try to enter new positions
            for signal in signals:
                if not sim.can_enter_trade():
                    break

                if signal.symbol in prices:
                    sim.enter_trade(
                        symbol=signal.symbol,
                        date=date,
                        price=prices[signal.symbol],
                        quantum_score=signal.quantum_score,
                        conviction=signal.conviction_level
                    )

            # Record equity
            sim.record_equity(date, prices)

    # Close any remaining open positions at end date
    if sim.open_trades:
        with session_scope() as session:
            end_prices_query = select(PriceOHLC).where(PriceOHLC.date == trading_dates[-1])
            end_prices_data = session.execute(end_prices_query).scalars().all()
            end_prices = {p.symbol: p.close for p in end_prices_data}

            for trade in list(sim.open_trades):
                if trade.symbol in end_prices:
                    trade.close(trading_dates[-1], end_prices[trade.symbol], "end_of_period")
                    sim.capital += trade.position_size + (trade.pnl or 0)
                    sim.closed_trades.append(trade)

            sim.open_trades = []

    logger.info(f"Backtest complete: {len(sim.closed_trades)} trades")

    return {
        'trades': [t.to_dict() for t in sim.closed_trades],
        'equity_curve': sim.equity_curve,
        'initial_capital': initial_capital,
        'final_capital': sim.equity_curve[-1]['equity'] if sim.equity_curve else initial_capital,
        'num_trades': len(sim.closed_trades),
        'start_date': start_date,
        'end_date': end_date
    }
