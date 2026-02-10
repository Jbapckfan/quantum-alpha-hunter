"""
Performance metrics calculator for backtesting results.
Provides comprehensive trading statistics and risk metrics.
Adapted from QAHT backtest/metrics.py for the Alpha Predator system.
"""
import logging
from typing import Dict, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("apredator.backtest.metrics")


def calculate_performance(
    trades_df: pd.DataFrame,
    initial_capital: float = 100_000,
    risk_free_rate: float = 0.02,
) -> Dict:
    """
    Calculate comprehensive performance metrics from a trades DataFrame.

    Args:
        trades_df: DataFrame produced by :func:`apredator.backtest.simulator.simulate`.
        initial_capital: Starting capital for return calculations.
        risk_free_rate: Annualised risk-free rate (default 2 %).

    Returns:
        Dictionary containing:
            - Basic: total_trades, winning_trades, losing_trades, hit_rate
            - Returns: avg_return, median_return, std_return, avg_winner, avg_loser
            - P&L: total_pnl, final_capital, total_return_pct, gross_profit, gross_loss
            - Risk: sharpe_ratio, sortino_ratio, max_drawdown, max_drawdown_duration_days
            - Trading: avg_hold_days, win_loss_ratio, profit_factor, expectancy
            - by_conviction: dict per conviction level
            - best/worst trade info
    """
    if trades_df.empty:
        logger.warning("No trades to analyse")
        return {
            "total_trades": 0,
            "hit_rate": 0.0,
            "avg_return": 0.0,
            "total_pnl": 0.0,
            "final_capital": initial_capital,
            "total_return_pct": 0.0,
        }

    logger.info(f"Calculating performance metrics for {len(trades_df)} trades")

    # ------------------------------------------------------------------
    # Basic counts
    # ------------------------------------------------------------------
    total_trades = len(trades_df)
    winning_trades = int((trades_df["return_pct"] > 0).sum())
    losing_trades = int((trades_df["return_pct"] <= 0).sum())
    hit_rate = winning_trades / total_trades if total_trades > 0 else 0.0

    # ------------------------------------------------------------------
    # Return metrics
    # ------------------------------------------------------------------
    avg_return = float(trades_df["return_pct"].mean())
    median_return = float(trades_df["return_pct"].median())
    std_return = float(trades_df["return_pct"].std()) if total_trades > 1 else 0.0

    winners = trades_df[trades_df["return_pct"] > 0]
    losers = trades_df[trades_df["return_pct"] <= 0]

    avg_winner = float(winners["return_pct"].mean()) if len(winners) > 0 else 0.0
    avg_loser = float(losers["return_pct"].mean()) if len(losers) > 0 else 0.0

    # ------------------------------------------------------------------
    # P&L metrics
    # ------------------------------------------------------------------
    total_pnl = float(trades_df["pnl"].sum())
    final_capital = initial_capital + total_pnl
    total_return_pct = (final_capital - initial_capital) / initial_capital

    gross_profit = float(trades_df.loc[trades_df["pnl"] > 0, "pnl"].sum())
    gross_loss = float(abs(trades_df.loc[trades_df["pnl"] <= 0, "pnl"].sum()))

    # ------------------------------------------------------------------
    # Risk metrics
    # ------------------------------------------------------------------
    sharpe_ratio = _calculate_sharpe_ratio(trades_df["return_pct"], risk_free_rate)
    sortino_ratio = _calculate_sortino_ratio(trades_df["return_pct"], risk_free_rate)
    max_drawdown, max_dd_duration = _calculate_max_drawdown(trades_df, initial_capital)

    # ------------------------------------------------------------------
    # Trading metrics
    # ------------------------------------------------------------------
    avg_hold_days = float(trades_df["hold_days"].mean()) if "hold_days" in trades_df.columns else 0.0

    win_loss_ratio = abs(avg_winner / avg_loser) if avg_loser != 0 else float("inf")

    profit_factor = gross_profit / gross_loss if gross_loss != 0 else float("inf")

    expectancy = (hit_rate * avg_winner) + ((1 - hit_rate) * avg_loser)

    # ------------------------------------------------------------------
    # By conviction level
    # ------------------------------------------------------------------
    conviction_metrics: Dict[str, Dict] = {}
    if "conviction_level" in trades_df.columns:
        for level in ["MAX", "HIGH", "MED", "LOW"]:
            level_trades = trades_df[trades_df["conviction_level"] == level]
            if len(level_trades) > 0:
                level_winners = (level_trades["return_pct"] > 0).sum()
                conviction_metrics[level] = {
                    "count": int(len(level_trades)),
                    "hit_rate": float(level_winners / len(level_trades)),
                    "avg_return": float(level_trades["return_pct"].mean()),
                    "total_pnl": float(level_trades["pnl"].sum()),
                }

    # ------------------------------------------------------------------
    # Best / worst trade
    # ------------------------------------------------------------------
    best_trade = trades_df.nlargest(1, "return_pct").iloc[0]
    worst_trade = trades_df.nsmallest(1, "return_pct").iloc[0]

    metrics = {
        # Basic
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "hit_rate": hit_rate,
        # Returns
        "avg_return": avg_return,
        "median_return": median_return,
        "std_return": std_return,
        "avg_winner": avg_winner,
        "avg_loser": avg_loser,
        # P&L
        "total_pnl": total_pnl,
        "final_capital": final_capital,
        "total_return_pct": total_return_pct,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        # Risk
        "sharpe_ratio": sharpe_ratio,
        "sortino_ratio": sortino_ratio,
        "max_drawdown": max_drawdown,
        "max_drawdown_duration_days": max_dd_duration,
        # Trading
        "avg_hold_days": avg_hold_days,
        "win_loss_ratio": win_loss_ratio,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        # Best / worst
        "best_trade_symbol": best_trade["symbol"],
        "best_trade_return": float(best_trade["return_pct"]),
        "best_trade_date": best_trade.get("entry_date"),
        "worst_trade_symbol": worst_trade["symbol"],
        "worst_trade_return": float(worst_trade["return_pct"]),
        "worst_trade_date": worst_trade.get("entry_date"),
        # By conviction
        "by_conviction": conviction_metrics,
    }

    _log_performance_summary(metrics)

    return metrics


# ---------------------------------------------------------------------------
# Risk-adjusted return helpers
# ---------------------------------------------------------------------------


def _calculate_sharpe_ratio(
    returns: pd.Series, risk_free_rate: float = 0.02
) -> float:
    """
    Annualised Sharpe ratio.

    Assumes approximately 25 trades per year with an average hold of ~10 days.

    Args:
        returns: Series of per-trade returns.
        risk_free_rate: Annualised risk-free rate.

    Returns:
        Annualised Sharpe ratio.
    """
    if len(returns) < 2 or returns.std() == 0:
        return 0.0

    # Per-trade risk-free rate (assume ~10 day hold)
    avg_trade_duration_years = 10 / 365
    rf_per_trade = (1 + risk_free_rate) ** avg_trade_duration_years - 1

    excess_returns = returns - rf_per_trade
    sharpe = excess_returns.mean() / returns.std()

    # Annualise assuming ~25 trades / year
    sharpe_annualized = sharpe * np.sqrt(25)

    return float(sharpe_annualized)


def _calculate_sortino_ratio(
    returns: pd.Series, risk_free_rate: float = 0.02
) -> float:
    """
    Annualised Sortino ratio (penalises only downside volatility).

    Args:
        returns: Series of per-trade returns.
        risk_free_rate: Annualised risk-free rate.

    Returns:
        Annualised Sortino ratio.
    """
    if len(returns) < 2:
        return 0.0

    negative_returns = returns[returns < 0]
    if len(negative_returns) == 0:
        return float("inf")

    downside_std = negative_returns.std()
    if downside_std == 0:
        return 0.0

    avg_trade_duration_years = 10 / 365
    rf_per_trade = (1 + risk_free_rate) ** avg_trade_duration_years - 1

    excess_returns = returns - rf_per_trade
    sortino = excess_returns.mean() / downside_std

    # Annualise
    sortino_annualized = sortino * np.sqrt(25)

    return float(sortino_annualized)


def _calculate_max_drawdown(
    trades_df: pd.DataFrame, initial_capital: float
) -> Tuple[float, int]:
    """
    Compute maximum drawdown and its duration (in number of trades).

    Args:
        trades_df: DataFrame of closed trades.
        initial_capital: Starting capital.

    Returns:
        ``(max_drawdown_pct, max_drawdown_duration_days)``
    """
    if trades_df.empty:
        return 0.0, 0

    trades_sorted = trades_df.sort_values("exit_date")

    equity = [initial_capital]
    for pnl in trades_sorted["pnl"]:
        equity.append(equity[-1] + pnl)

    equity = np.array(equity)

    running_max = np.maximum.accumulate(equity)
    drawdowns = (equity - running_max) / running_max

    max_dd = float(abs(drawdowns.min()))

    # Duration: longest consecutive stretch of drawdown
    max_dd_duration = 0
    current_dd_duration = 0

    for dd in drawdowns:
        if dd < 0:
            current_dd_duration += 1
            max_dd_duration = max(max_dd_duration, current_dd_duration)
        else:
            current_dd_duration = 0

    return max_dd, max_dd_duration


# ---------------------------------------------------------------------------
# Monthly returns
# ---------------------------------------------------------------------------


def calculate_monthly_returns(trades_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate trade results by exit month.

    Args:
        trades_df: DataFrame of closed trades.

    Returns:
        DataFrame indexed by month with ``pnl``, ``return_pct``, and
        ``trade_count`` columns.
    """
    if trades_df.empty:
        return pd.DataFrame()

    trades_df = trades_df.copy()
    trades_df["exit_month"] = pd.to_datetime(trades_df["exit_date"]).dt.to_period("M")

    monthly = trades_df.groupby("exit_month").agg(
        pnl=("pnl", "sum"),
        avg_return=("return_pct", "mean"),
        trade_count=("symbol", "count"),
    )

    return monthly


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def _log_performance_summary(metrics: Dict) -> None:
    """Log a formatted human-readable performance summary."""
    logger.info("=" * 60)
    logger.info("BACKTEST PERFORMANCE SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total Trades: {metrics['total_trades']}")
    logger.info(f"Hit Rate: {metrics['hit_rate'] * 100:.1f}%")
    logger.info(f"Average Return: {metrics['avg_return'] * 100:.2f}%")
    logger.info(f"Win/Loss Ratio: {metrics['win_loss_ratio']:.2f}")
    logger.info("-" * 60)
    logger.info(f"Total P&L: ${metrics['total_pnl']:,.2f}")
    logger.info(f"Final Capital: ${metrics['final_capital']:,.2f}")
    logger.info(f"Total Return: {metrics['total_return_pct'] * 100:.1f}%")
    logger.info("-" * 60)
    logger.info(f"Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
    logger.info(f"Sortino Ratio: {metrics['sortino_ratio']:.2f}")
    logger.info(f"Max Drawdown: {metrics['max_drawdown'] * 100:.1f}%")
    logger.info(f"Profit Factor: {metrics['profit_factor']:.2f}")
    logger.info("-" * 60)
    logger.info(f"Avg Hold: {metrics['avg_hold_days']:.1f} days")
    logger.info(f"Expectancy: {metrics['expectancy'] * 100:.2f}%")
    logger.info("=" * 60)

    if metrics["by_conviction"]:
        logger.info("")
        logger.info("Performance by Conviction Level:")
        for level, stats in metrics["by_conviction"].items():
            logger.info(
                f"  {level:4s}: {stats['count']:3d} trades | "
                f"Hit Rate: {stats['hit_rate'] * 100:5.1f}% | "
                f"Avg Return: {stats['avg_return'] * 100:6.2f}% | "
                f"P&L: ${stats['total_pnl']:9,.2f}"
            )
