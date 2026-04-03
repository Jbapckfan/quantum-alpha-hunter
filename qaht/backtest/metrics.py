"""Backtest performance metrics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List

import numpy as np
import pandas as pd


@dataclass
class MetricResult:
    """Serializable backtest metric payload."""

    total_return: float
    cagr: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    max_drawdown_duration: int
    win_rate: float
    average_winner: float
    average_loser: float
    profit_factor: float
    expectancy_per_trade: float
    combo_breakdown: Dict[str, Dict[str, Any]]
    monthly_returns: List[Dict[str, Any]]
    trade_count: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to plain dict."""
        return asdict(self)


class BacktestMetrics:
    """Compute common portfolio and trade statistics."""

    @staticmethod
    def compute(
        equity_curve: List[Dict[str, Any]],
        trades: List[Dict[str, Any]],
        risk_free_rate: float = 0.045,
    ) -> MetricResult:
        if not equity_curve:
            return MetricResult(
                total_return=0.0,
                cagr=0.0,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                max_drawdown_pct=0.0,
                max_drawdown_duration=0,
                win_rate=0.0,
                average_winner=0.0,
                average_loser=0.0,
                profit_factor=0.0,
                expectancy_per_trade=0.0,
                combo_breakdown={},
                monthly_returns=[],
                trade_count=len(trades),
            )

        curve = pd.DataFrame(equity_curve).copy()
        curve["date"] = pd.to_datetime(curve["date"])
        curve = curve.sort_values("date")
        curve["daily_return"] = curve["equity"].pct_change().fillna(0.0)

        start_equity = float(curve["equity"].iloc[0])
        end_equity = float(curve["equity"].iloc[-1])
        total_return = (end_equity / start_equity - 1.0) if start_equity else 0.0

        elapsed_days = max(1, int((curve["date"].iloc[-1] - curve["date"].iloc[0]).days))
        cagr = (end_equity / start_equity) ** (365.25 / elapsed_days) - 1.0 if start_equity > 0 else 0.0

        rf_daily = risk_free_rate / 252.0
        excess = curve["daily_return"] - rf_daily
        std = float(excess.std(ddof=0))
        sharpe = float(excess.mean() / std * np.sqrt(252)) if std > 0 else 0.0

        downside = curve.loc[curve["daily_return"] < 0, "daily_return"]
        downside_std = float(downside.std(ddof=0)) if not downside.empty else 0.0
        sortino = float(excess.mean() / downside_std * np.sqrt(252)) if downside_std > 0 else 0.0

        running_peak = curve["equity"].cummax()
        drawdown = curve["equity"] / running_peak - 1.0
        max_drawdown_pct = float(drawdown.min()) if not drawdown.empty else 0.0
        max_drawdown_duration = BacktestMetrics._drawdown_duration(drawdown.tolist())

        returns = [float(trade.get("return_pct", 0.0)) for trade in trades]
        winners = [value for value in returns if value > 0]
        losers = [value for value in returns if value <= 0]
        win_rate = (len(winners) / len(returns)) if returns else 0.0
        average_winner = float(np.mean(winners)) if winners else 0.0
        average_loser = float(np.mean(losers)) if losers else 0.0
        gross_wins = float(sum(winners))
        gross_losses = float(abs(sum(losers)))
        profit_factor = (gross_wins / gross_losses) if gross_losses > 0 else 0.0
        expectancy = float(np.mean(returns)) if returns else 0.0

        combo_breakdown: Dict[str, Dict[str, Any]] = {}
        for trade in trades:
            combo = trade.get("combo_used") or "NONE"
            row = combo_breakdown.setdefault(combo, {"count": 0, "returns": [], "wins": 0})
            row["count"] += 1
            trade_return = float(trade.get("return_pct", 0.0))
            row["returns"].append(trade_return)
            if trade_return > 0:
                row["wins"] += 1

        for combo, row in combo_breakdown.items():
            count = max(1, row["count"])
            returns_list = row.pop("returns")
            row["avg_return"] = round(float(np.mean(returns_list)), 4) if returns_list else 0.0
            row["hit_rate"] = round(row["wins"] / count, 4)

        monthly = curve.set_index("date")["equity"].resample("M").last().pct_change().dropna()
        monthly_returns = [
            {"month": idx.strftime("%Y-%m"), "return_pct": round(float(value), 4)}
            for idx, value in monthly.items()
        ]

        return MetricResult(
            total_return=round(float(total_return), 4),
            cagr=round(float(cagr), 4),
            sharpe_ratio=round(float(sharpe), 4),
            sortino_ratio=round(float(sortino), 4),
            max_drawdown_pct=round(float(max_drawdown_pct), 4),
            max_drawdown_duration=int(max_drawdown_duration),
            win_rate=round(float(win_rate), 4),
            average_winner=round(float(average_winner), 4),
            average_loser=round(float(average_loser), 4),
            profit_factor=round(float(profit_factor), 4),
            expectancy_per_trade=round(float(expectancy), 4),
            combo_breakdown=combo_breakdown,
            monthly_returns=monthly_returns,
            trade_count=len(trades),
        )

    @staticmethod
    def _drawdown_duration(drawdowns: List[float]) -> int:
        longest = 0
        current = 0
        for value in drawdowns:
            if value < 0:
                current += 1
                longest = max(longest, current)
            else:
                current = 0
        return longest
