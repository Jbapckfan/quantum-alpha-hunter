"""
Performance metrics calculation for backtest results
Calculate hit rate, Sharpe, drawdown, and other key metrics
"""
import pandas as pd
import numpy as np
from typing import Dict, List
import logging

logger = logging.getLogger("qaht.backtest.metrics")


def calculate_performance(results: Dict) -> Dict:
    """
    Calculate comprehensive performance metrics from backtest results

    Args:
        results: Output from simulate() function

    Returns:
        Dict with performance metrics
    """
    trades = results.get('trades', [])
    equity_curve = results.get('equity_curve', [])
    initial_capital = results.get('initial_capital', 100000)
    final_capital = results.get('final_capital', initial_capital)

    if not trades:
        return {
            'error': 'No trades to analyze',
            'total_trades': 0
        }

    # Convert to DataFrames
    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame(equity_curve)

    metrics = {}

    # ========================================================================
    # BASIC METRICS
    # ========================================================================

    metrics['total_trades'] = len(trades_df)
    metrics['initial_capital'] = initial_capital
    metrics['final_capital'] = final_capital
    metrics['total_return'] = (final_capital / initial_capital) - 1
    metrics['total_pnl'] = final_capital - initial_capital

    # ========================================================================
    # WIN/LOSS ANALYSIS
    # ========================================================================

    winning_trades = trades_df[trades_df['return_pct'] > 0]
    losing_trades = trades_df[trades_df['return_pct'] <= 0]

    metrics['winning_trades'] = len(winning_trades)
    metrics['losing_trades'] = len(losing_trades)
    metrics['hit_rate'] = len(winning_trades) / len(trades_df) if len(trades_df) > 0 else 0

    # Average returns
    metrics['avg_win'] = winning_trades['return_pct'].mean() if len(winning_trades) > 0 else 0
    metrics['avg_loss'] = losing_trades['return_pct'].mean() if len(losing_trades) > 0 else 0
    metrics['avg_trade'] = trades_df['return_pct'].mean()

    # Largest wins/losses
    metrics['largest_win'] = trades_df['return_pct'].max()
    metrics['largest_loss'] = trades_df['return_pct'].min()

    # Win/loss ratio
    if metrics['avg_loss'] != 0:
        metrics['win_loss_ratio'] = abs(metrics['avg_win'] / metrics['avg_loss'])
    else:
        metrics['win_loss_ratio'] = float('inf') if metrics['avg_win'] > 0 else 0

    # ========================================================================
    # DRAWDOWN ANALYSIS
    # ========================================================================

    if not equity_df.empty:
        # Calculate running maximum
        equity_df['cummax'] = equity_df['equity'].cummax()
        equity_df['drawdown'] = (equity_df['equity'] - equity_df['cummax']) / equity_df['cummax']

        metrics['max_drawdown'] = equity_df['drawdown'].min()
        metrics['avg_drawdown'] = equity_df[equity_df['drawdown'] < 0]['drawdown'].mean() if (equity_df['drawdown'] < 0).any() else 0

        # Drawdown duration
        in_drawdown = equity_df['drawdown'] < 0
        if in_drawdown.any():
            drawdown_periods = []
            current_period = 0
            for dd in in_drawdown:
                if dd:
                    current_period += 1
                else:
                    if current_period > 0:
                        drawdown_periods.append(current_period)
                    current_period = 0
            metrics['max_drawdown_days'] = max(drawdown_periods) if drawdown_periods else 0
        else:
            metrics['max_drawdown_days'] = 0
    else:
        metrics['max_drawdown'] = 0
        metrics['avg_drawdown'] = 0
        metrics['max_drawdown_days'] = 0

    # ========================================================================
    # RISK-ADJUSTED RETURNS
    # ========================================================================

    if not trades_df.empty:
        # Sharpe Ratio (annualized, assuming ~250 trading days)
        returns_std = trades_df['return_pct'].std()
        if returns_std > 0:
            # Annualize assuming average holding period
            avg_holding_days = trades_df['days_held'].mean()
            periods_per_year = 250 / avg_holding_days if avg_holding_days > 0 else 1

            annualized_return = (1 + metrics['avg_trade']) ** periods_per_year - 1
            annualized_std = returns_std * np.sqrt(periods_per_year)

            metrics['sharpe_ratio'] = annualized_return / annualized_std if annualized_std > 0 else 0
        else:
            metrics['sharpe_ratio'] = 0

        # Sortino Ratio (only penalize downside volatility)
        downside_returns = trades_df[trades_df['return_pct'] < 0]['return_pct']
        if len(downside_returns) > 0:
            downside_std = downside_returns.std()
            if downside_std > 0:
                avg_holding_days = trades_df['days_held'].mean()
                periods_per_year = 250 / avg_holding_days if avg_holding_days > 0 else 1
                annualized_return = (1 + metrics['avg_trade']) ** periods_per_year - 1
                annualized_downside_std = downside_std * np.sqrt(periods_per_year)
                metrics['sortino_ratio'] = annualized_return / annualized_downside_std
            else:
                metrics['sortino_ratio'] = float('inf') if annualized_return > 0 else 0
        else:
            metrics['sortino_ratio'] = float('inf') if metrics['avg_trade'] > 0 else 0

        # Calmar Ratio (return / max drawdown)
        if metrics['max_drawdown'] < 0:
            metrics['calmar_ratio'] = abs(metrics['total_return'] / metrics['max_drawdown'])
        else:
            metrics['calmar_ratio'] = float('inf') if metrics['total_return'] > 0 else 0

    # ========================================================================
    # TRADE CHARACTERISTICS
    # ========================================================================

    metrics['avg_holding_days'] = trades_df['days_held'].mean()
    metrics['median_holding_days'] = trades_df['days_held'].median()

    # Exit reason breakdown
    exit_reasons = trades_df['exit_reason'].value_counts().to_dict()
    metrics['exit_reasons'] = exit_reasons

    # ========================================================================
    # CONVICTION LEVEL ANALYSIS
    # ========================================================================

    conviction_performance = {}
    for conviction in ['MAX', 'HIGH', 'MED', 'LOW']:
        conv_trades = trades_df[trades_df['conviction'] == conviction]
        if len(conv_trades) > 0:
            conviction_performance[conviction] = {
                'count': len(conv_trades),
                'hit_rate': (conv_trades['return_pct'] > 0).mean(),
                'avg_return': conv_trades['return_pct'].mean(),
                'total_pnl': conv_trades['pnl'].sum()
            }

    metrics['conviction_performance'] = conviction_performance

    # ========================================================================
    # EXPLOSION CAPTURE
    # ========================================================================

    # Trades that hit 50%+ (multi-baggers)
    multi_baggers = trades_df[trades_df['return_pct'] >= 0.50]
    metrics['multi_bagger_count'] = len(multi_baggers)
    metrics['multi_bagger_capture_rate'] = len(multi_baggers) / len(trades_df) if len(trades_df) > 0 else 0

    # Trades that hit profit target
    profit_targets = trades_df[trades_df['exit_reason'] == 'profit_target']
    metrics['profit_target_hits'] = len(profit_targets)
    metrics['profit_target_rate'] = len(profit_targets) / len(trades_df) if len(trades_df) > 0 else 0

    # Stop loss hits
    stop_losses = trades_df[trades_df['exit_reason'] == 'stop_loss']
    metrics['stop_loss_hits'] = len(stop_losses)
    metrics['stop_loss_rate'] = len(stop_losses) / len(trades_df) if len(trades_df) > 0 else 0

    # ========================================================================
    # CONSISTENCY METRICS
    # ========================================================================

    # Consecutive wins/losses
    trades_df = trades_df.sort_values('entry_date')
    trades_df['is_winner'] = trades_df['return_pct'] > 0

    max_consecutive_wins = 0
    max_consecutive_losses = 0
    current_wins = 0
    current_losses = 0

    for is_winner in trades_df['is_winner']:
        if is_winner:
            current_wins += 1
            max_consecutive_wins = max(max_consecutive_wins, current_wins)
            current_losses = 0
        else:
            current_losses += 1
            max_consecutive_losses = max(max_consecutive_losses, current_losses)
            current_wins = 0

    metrics['max_consecutive_wins'] = max_consecutive_wins
    metrics['max_consecutive_losses'] = max_consecutive_losses

    # ========================================================================
    # EXPECTANCY
    # ========================================================================

    # Expected value per trade
    metrics['expectancy'] = (
        metrics['hit_rate'] * metrics['avg_win'] +
        (1 - metrics['hit_rate']) * metrics['avg_loss']
    )

    # Profit factor
    total_wins = winning_trades['pnl'].sum() if len(winning_trades) > 0 else 0
    total_losses = abs(losing_trades['pnl'].sum()) if len(losing_trades) > 0 else 0

    if total_losses > 0:
        metrics['profit_factor'] = total_wins / total_losses
    else:
        metrics['profit_factor'] = float('inf') if total_wins > 0 else 0

    logger.info(f"Performance calculated: {metrics['total_trades']} trades, "
               f"{metrics['hit_rate']:.1%} hit rate, "
               f"{metrics['total_return']:.2%} return")

    return metrics


def print_performance_report(metrics: Dict):
    """
    Print formatted performance report

    Args:
        metrics: Output from calculate_performance()
    """
    if 'error' in metrics:
        print(f"❌ {metrics['error']}")
        return

    print("=" * 80)
    print("📊 BACKTEST PERFORMANCE REPORT")
    print("=" * 80)

    print("\n📈 OVERALL PERFORMANCE")
    print(f"  Initial Capital:        ${metrics['initial_capital']:,.2f}")
    print(f"  Final Capital:          ${metrics['final_capital']:,.2f}")
    print(f"  Total Return:           {metrics['total_return']:.2%}")
    print(f"  Total P&L:              ${metrics['total_pnl']:,.2f}")

    print("\n🎯 TRADE STATISTICS")
    print(f"  Total Trades:           {metrics['total_trades']}")
    print(f"  Winning Trades:         {metrics['winning_trades']} ({metrics['hit_rate']:.1%})")
    print(f"  Losing Trades:          {metrics['losing_trades']}")
    print(f"  Average Win:            {metrics['avg_win']:.2%}")
    print(f"  Average Loss:           {metrics['avg_loss']:.2%}")
    print(f"  Win/Loss Ratio:         {metrics['win_loss_ratio']:.2f}x")
    print(f"  Largest Win:            {metrics['largest_win']:.2%}")
    print(f"  Largest Loss:           {metrics['largest_loss']:.2%}")

    print("\n💰 RISK-ADJUSTED METRICS")
    print(f"  Sharpe Ratio:           {metrics['sharpe_ratio']:.2f}")
    print(f"  Sortino Ratio:          {metrics['sortino_ratio']:.2f}")
    print(f"  Calmar Ratio:           {metrics['calmar_ratio']:.2f}")
    print(f"  Max Drawdown:           {metrics['max_drawdown']:.2%}")
    print(f"  Avg Drawdown:           {metrics['avg_drawdown']:.2%}")
    print(f"  Max DD Duration:        {metrics['max_drawdown_days']:.0f} days")

    print("\n🚀 EXPLOSION CAPTURE")
    print(f"  Multi-Baggers (50%+):   {metrics['multi_bagger_count']} ({metrics['multi_bagger_capture_rate']:.1%})")
    print(f"  Profit Target Hits:     {metrics['profit_target_hits']} ({metrics['profit_target_rate']:.1%})")
    print(f"  Stop Loss Hits:         {metrics['stop_loss_hits']} ({metrics['stop_loss_rate']:.1%})")

    print("\n⏱️  TRADE DURATION")
    print(f"  Avg Holding Period:     {metrics['avg_holding_days']:.1f} days")
    print(f"  Median Holding Period:  {metrics['median_holding_days']:.1f} days")

    print("\n🎲 EXPECTANCY")
    print(f"  Expectancy:             {metrics['expectancy']:.2%}")
    print(f"  Profit Factor:          {metrics['profit_factor']:.2f}x")

    print("\n🏆 CONVICTION LEVEL PERFORMANCE")
    for conviction, perf in metrics['conviction_performance'].items():
        print(f"  {conviction:4s}: {perf['count']:3d} trades, "
              f"{perf['hit_rate']:.1%} hit rate, "
              f"{perf['avg_return']:+.2%} avg return")

    print("\n🔄 EXIT REASONS")
    for reason, count in metrics['exit_reasons'].items():
        pct = count / metrics['total_trades'] * 100
        print(f"  {reason:15s}: {count:3d} ({pct:.1f}%)")

    print("\n" + "=" * 80)
