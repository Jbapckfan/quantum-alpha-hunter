"""
Performance metrics calculator for backtesting results
Provides comprehensive trading statistics and risk metrics
"""
import logging
import pandas as pd
import numpy as np
from typing import Dict, Optional

logger = logging.getLogger("qaht.backtest.metrics")


def calculate_performance(
    trades_df: pd.DataFrame,
    initial_capital: float = 100000,
    risk_free_rate: float = 0.02
) -> Dict:
    """
    Calculate comprehensive performance metrics from trades DataFrame

    Args:
        trades_df: DataFrame from simulate() containing trade history
        initial_capital: Starting capital for performance calculations
        risk_free_rate: Annual risk-free rate for Sharpe/Sortino (default 2%)

    Returns:
        Dictionary of performance metrics
    """
    if trades_df.empty:
        logger.warning("No trades to analyze")
        return {
            'total_trades': 0,
            'hit_rate': 0.0,
            'avg_return': 0.0,
            'total_pnl': 0.0,
            'final_capital': initial_capital,
            'total_return_pct': 0.0
        }

    logger.info(f"Calculating performance metrics for {len(trades_df)} trades")

    # Basic metrics
    total_trades = len(trades_df)
    winning_trades = len(trades_df[trades_df['return_pct'] > 0])
    losing_trades = len(trades_df[trades_df['return_pct'] <= 0])

    hit_rate = winning_trades / total_trades if total_trades > 0 else 0.0

    # Return metrics
    avg_return = trades_df['return_pct'].mean()
    median_return = trades_df['return_pct'].median()
    std_return = trades_df['return_pct'].std()

    avg_winner = trades_df[trades_df['return_pct'] > 0]['return_pct'].mean() if winning_trades > 0 else 0.0
    avg_loser = trades_df[trades_df['return_pct'] <= 0]['return_pct'].mean() if losing_trades > 0 else 0.0

    # P&L metrics
    total_pnl = trades_df['pnl'].sum()
    final_capital = initial_capital + total_pnl
    total_return_pct = (final_capital - initial_capital) / initial_capital

    # Risk metrics
    sharpe_ratio = _calculate_sharpe_ratio(trades_df['return_pct'], risk_free_rate)
    sortino_ratio = _calculate_sortino_ratio(trades_df['return_pct'], risk_free_rate)
    max_drawdown, max_dd_duration = _calculate_max_drawdown(trades_df, initial_capital)

    # Trade duration
    avg_hold_days = trades_df['hold_days'].mean()
    median_hold_days = trades_df['hold_days'].median()

    # Win/loss ratio
    win_loss_ratio = abs(avg_winner / avg_loser) if avg_loser != 0 else float('inf')

    # Profit factor (gross profit / gross loss)
    gross_profit = trades_df[trades_df['pnl'] > 0]['pnl'].sum()
    gross_loss = abs(trades_df[trades_df['pnl'] <= 0]['pnl'].sum())
    profit_factor = gross_profit / gross_loss if gross_loss != 0 else float('inf')

    # Expectancy (expected value per trade)
    expectancy = (hit_rate * avg_winner) + ((1 - hit_rate) * avg_loser)

    # By conviction level
    conviction_metrics = {}
    if 'conviction_level' in trades_df.columns:
        for level in ['MAX', 'HIGH', 'MED', 'LOW']:
            level_trades = trades_df[trades_df['conviction_level'] == level]
            if len(level_trades) > 0:
                conviction_metrics[level] = {
                    'count': len(level_trades),
                    'hit_rate': (level_trades['return_pct'] > 0).sum() / len(level_trades),
                    'avg_return': level_trades['return_pct'].mean(),
                    'total_pnl': level_trades['pnl'].sum()
                }

    # Best and worst trades
    best_trade = trades_df.nlargest(1, 'return_pct').iloc[0] if len(trades_df) > 0 else None
    worst_trade = trades_df.nsmallest(1, 'return_pct').iloc[0] if len(trades_df) > 0 else None

    metrics = {
        # Basic counts
        'total_trades': total_trades,
        'winning_trades': winning_trades,
        'losing_trades': losing_trades,
        'hit_rate': hit_rate,

        # Return metrics
        'avg_return': avg_return,
        'median_return': median_return,
        'std_return': std_return,
        'avg_winner': avg_winner,
        'avg_loser': avg_loser,

        # P&L metrics
        'total_pnl': total_pnl,
        'final_capital': final_capital,
        'total_return_pct': total_return_pct,
        'gross_profit': gross_profit,
        'gross_loss': gross_loss,

        # Risk metrics
        'sharpe_ratio': sharpe_ratio,
        'sortino_ratio': sortino_ratio,
        'max_drawdown': max_drawdown,
        'max_drawdown_duration_days': max_dd_duration,

        # Trading metrics
        'avg_hold_days': avg_hold_days,
        'median_hold_days': median_hold_days,
        'win_loss_ratio': win_loss_ratio,
        'profit_factor': profit_factor,
        'expectancy': expectancy,

        # Best/worst
        'best_trade_symbol': best_trade['symbol'] if best_trade is not None else None,
        'best_trade_return': best_trade['return_pct'] if best_trade is not None else None,
        'worst_trade_symbol': worst_trade['symbol'] if worst_trade is not None else None,
        'worst_trade_return': worst_trade['return_pct'] if worst_trade is not None else None,

        # By conviction
        'by_conviction': conviction_metrics
    }

    _log_performance_summary(metrics)

    return metrics


def _calculate_sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.02) -> float:
    """
    Calculate Sharpe ratio (risk-adjusted return)

    Args:
        returns: Series of trade returns
        risk_free_rate: Annual risk-free rate

    Returns:
        Sharpe ratio (higher is better, >1 is good, >2 is excellent)
    """
    if len(returns) < 2 or returns.std() == 0:
        return 0.0

    # Convert annual risk-free rate to per-trade
    avg_trade_duration_years = 10 / 365  # Assume ~10 day average hold
    rf_per_trade = (1 + risk_free_rate) ** avg_trade_duration_years - 1

    excess_returns = returns - rf_per_trade
    sharpe = excess_returns.mean() / returns.std()

    # Annualize (assuming ~25 trades per year for typical multi-bagger strategy)
    sharpe_annualized = sharpe * np.sqrt(25)

    return sharpe_annualized


def _calculate_sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.02) -> float:
    """
    Calculate Sortino ratio (only penalizes downside volatility)

    Args:
        returns: Series of trade returns
        risk_free_rate: Annual risk-free rate

    Returns:
        Sortino ratio (higher is better)
    """
    if len(returns) < 2:
        return 0.0

    # Only consider downside deviation
    negative_returns = returns[returns < 0]
    if len(negative_returns) == 0:
        return float('inf')

    downside_std = negative_returns.std()
    if downside_std == 0:
        return 0.0

    avg_trade_duration_years = 10 / 365
    rf_per_trade = (1 + risk_free_rate) ** avg_trade_duration_years - 1

    excess_returns = returns - rf_per_trade
    sortino = excess_returns.mean() / downside_std

    # Annualize
    sortino_annualized = sortino * np.sqrt(25)

    return sortino_annualized


def _calculate_max_drawdown(trades_df: pd.DataFrame, initial_capital: float) -> tuple:
    """
    Calculate maximum drawdown and duration

    Args:
        trades_df: DataFrame of trades
        initial_capital: Starting capital

    Returns:
        (max_drawdown_pct, max_duration_days)
    """
    if trades_df.empty:
        return 0.0, 0

    # Build equity curve
    trades_sorted = trades_df.sort_values('exit_date')
    equity = [initial_capital]
    for pnl in trades_sorted['pnl']:
        equity.append(equity[-1] + pnl)

    equity = np.array(equity)

    # Calculate drawdowns
    running_max = np.maximum.accumulate(equity)
    drawdowns = (equity - running_max) / running_max

    max_dd = abs(drawdowns.min())

    # Calculate drawdown duration
    max_dd_duration = 0
    current_dd_duration = 0

    for dd in drawdowns:
        if dd < 0:
            current_dd_duration += 1
            max_dd_duration = max(max_dd_duration, current_dd_duration)
        else:
            current_dd_duration = 0

    return max_dd, max_dd_duration


def calculate_monthly_returns(trades_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate monthly return summary

    Args:
        trades_df: DataFrame of trades

    Returns:
        DataFrame with monthly aggregated returns
    """
    if trades_df.empty:
        return pd.DataFrame()

    trades_df = trades_df.copy()
    trades_df['exit_month'] = pd.to_datetime(trades_df['exit_date']).dt.to_period('M')

    monthly = trades_df.groupby('exit_month').agg({
        'pnl': 'sum',
        'return_pct': 'mean',
        'symbol': 'count'
    }).rename(columns={'symbol': 'trade_count'})

    return monthly


def calculate_score_bucket_performance(trades_df: pd.DataFrame) -> pd.DataFrame:
    """
    Analyze performance by quantum score bucket

    Args:
        trades_df: DataFrame of trades

    Returns:
        DataFrame with performance by score range
    """
    if trades_df.empty:
        return pd.DataFrame()

    trades_df = trades_df.copy()

    # Create score buckets
    bins = [0, 70, 80, 90, 100]
    labels = ['70-79', '80-89', '90-99', '100']
    trades_df['score_bucket'] = pd.cut(
        trades_df['quantum_score'],
        bins=bins,
        labels=labels,
        include_lowest=True
    )

    # Aggregate by bucket
    bucket_perf = trades_df.groupby('score_bucket').agg({
        'return_pct': ['count', 'mean', 'std'],
        'pnl': 'sum'
    })

    bucket_perf.columns = ['_'.join(col).strip() for col in bucket_perf.columns.values]
    bucket_perf['hit_rate'] = trades_df.groupby('score_bucket')['return_pct'].apply(
        lambda x: (x > 0).sum() / len(x) if len(x) > 0 else 0
    )

    return bucket_perf


def _log_performance_summary(metrics: Dict):
    """Log human-readable performance summary"""
    logger.info("=" * 60)
    logger.info("BACKTEST PERFORMANCE SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total Trades: {metrics['total_trades']}")
    logger.info(f"Hit Rate: {metrics['hit_rate']*100:.1f}%")
    logger.info(f"Average Return: {metrics['avg_return']*100:.2f}%")
    logger.info(f"Win/Loss Ratio: {metrics['win_loss_ratio']:.2f}")
    logger.info(f"-" * 60)
    logger.info(f"Total P&L: ${metrics['total_pnl']:,.2f}")
    logger.info(f"Final Capital: ${metrics['final_capital']:,.2f}")
    logger.info(f"Total Return: {metrics['total_return_pct']*100:.1f}%")
    logger.info(f"-" * 60)
    logger.info(f"Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
    logger.info(f"Sortino Ratio: {metrics['sortino_ratio']:.2f}")
    logger.info(f"Max Drawdown: {metrics['max_drawdown']*100:.1f}%")
    logger.info(f"Profit Factor: {metrics['profit_factor']:.2f}")
    logger.info(f"-" * 60)
    logger.info(f"Avg Hold: {metrics['avg_hold_days']:.1f} days")
    logger.info(f"Expectancy: {metrics['expectancy']*100:.2f}%")
    logger.info("=" * 60)

    if metrics['by_conviction']:
        logger.info("\nPerformance by Conviction Level:")
        for level, stats in metrics['by_conviction'].items():
            logger.info(
                f"  {level:4s}: {stats['count']:3d} trades | "
                f"Hit Rate: {stats['hit_rate']*100:5.1f}% | "
                f"Avg Return: {stats['avg_return']*100:6.2f}% | "
                f"P&L: ${stats['total_pnl']:9,.2f}"
            )
