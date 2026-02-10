"""
Backtested equity curve simulation for Alpha Predator.

Simulates portfolio equity growth from historical signal DataFrames,
producing day-by-day equity tracking, per-trade records, and standard
performance statistics.  Includes a Plotly chart builder for the
dashboard.
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

logger = logging.getLogger("apredator.backtest.equity_curve")


# ---------------------------------------------------------------------------
# Price data helper
# ---------------------------------------------------------------------------

def _fetch_prices(symbol: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """Fetch OHLC data for *symbol* between *start* and *end* via yfinance.

    Returns a DataFrame with columns [date, open, high, low, close, volume]
    indexed by integer, or ``None`` on failure.
    """
    try:
        import yfinance as yf

        # Add buffer days so we can get the next-day open after the last signal
        end_dt = datetime.strptime(end, "%Y-%m-%d") + timedelta(days=40)
        start_dt = datetime.strptime(start, "%Y-%m-%d") - timedelta(days=5)

        ticker = yf.Ticker(symbol)
        hist = ticker.history(
            start=start_dt.strftime("%Y-%m-%d"),
            end=end_dt.strftime("%Y-%m-%d"),
            auto_adjust=True,
        )

        if hist.empty:
            return None

        hist = hist.reset_index()
        hist.columns = [c.lower() for c in hist.columns]

        # Normalise the date column
        if "date" in hist.columns:
            hist["date"] = pd.to_datetime(hist["date"]).dt.strftime("%Y-%m-%d")
        elif "datetime" in hist.columns:
            hist["date"] = pd.to_datetime(hist["datetime"]).dt.strftime("%Y-%m-%d")
            hist = hist.drop(columns=["datetime"])

        return hist[["date", "open", "high", "low", "close", "volume"]]

    except Exception:
        logger.debug("yfinance fetch failed for %s", symbol)
        return None


# ---------------------------------------------------------------------------
# Core simulation
# ---------------------------------------------------------------------------

def simulate_equity_curve(
    signals_df: pd.DataFrame,
    initial_capital: float = 100_000,
    position_pct: float = 0.10,
    profit_target: float = 0.50,
    stop_loss: float = -0.15,
    max_hold_days: int = 20,
    price_data: Optional[Dict[str, pd.DataFrame]] = None,
) -> Dict[str, Any]:
    """Simulate portfolio equity growth from a DataFrame of historical signals.

    Parameters
    ----------
    signals_df : pd.DataFrame
        Must contain columns: ``symbol``, ``date``, ``close``.
        Optional columns: ``score`` (or ``reversal_score``), ``combo_hit_rate``.
        Each row represents a buy signal on that date.
    initial_capital : float
        Starting portfolio value in dollars.
    position_pct : float
        Fraction of current equity allocated to each new position (0-1).
    profit_target : float
        Take-profit threshold as a return fraction (e.g. 0.50 = +50%).
    stop_loss : float
        Stop-loss threshold as a negative return fraction (e.g. -0.15 = -15%).
    max_hold_days : int
        Maximum calendar days to hold before a time-stop exit.
    price_data : dict[str, pd.DataFrame], optional
        Pre-fetched price data keyed by symbol.  Each DataFrame must have
        columns ``[date, open, high, low, close, volume]``.  If ``None``,
        prices are fetched via yfinance on the fly.

    Returns
    -------
    dict
        ``equity_curve`` : list of {date, equity, drawdown_pct}
        ``trades``       : list of per-trade dicts
        ``stats``        : dict of aggregate performance statistics
    """
    if signals_df.empty:
        logger.warning("Empty signals DataFrame -- nothing to simulate")
        return _empty_result(initial_capital)

    signals_df = signals_df.copy()

    # Normalise column names -------------------------------------------------
    if "reversal_score" in signals_df.columns and "score" not in signals_df.columns:
        signals_df["score"] = signals_df["reversal_score"]
    if "score" not in signals_df.columns:
        signals_df["score"] = 50  # default neutral score
    if "combo_hit_rate" not in signals_df.columns:
        signals_df["combo_hit_rate"] = 0.0

    signals_df["date"] = pd.to_datetime(signals_df["date"]).dt.strftime("%Y-%m-%d")
    signals_df = signals_df.sort_values("date").reset_index(drop=True)

    # Determine date range ---------------------------------------------------
    date_min = signals_df["date"].min()
    date_max = signals_df["date"].max()

    # Collect unique symbols and pre-fetch prices ----------------------------
    symbols = signals_df["symbol"].unique().tolist()

    if price_data is None:
        price_data = {}

    prices_cache: Dict[str, pd.DataFrame] = {}
    for sym in symbols:
        if sym in price_data:
            pdf = price_data[sym].copy()
            pdf["date"] = pd.to_datetime(pdf["date"]).dt.strftime("%Y-%m-%d")
            prices_cache[sym] = pdf
        else:
            pdf = _fetch_prices(sym, date_min, date_max)
            if pdf is not None:
                prices_cache[sym] = pdf

    if not prices_cache:
        logger.warning("No price data available for any symbol")
        return _empty_result(initial_capital)

    # Build a master calendar of trading days --------------------------------
    all_dates = set()
    for pdf in prices_cache.values():
        all_dates.update(pdf["date"].tolist())
    all_dates = sorted(all_dates)

    if not all_dates:
        return _empty_result(initial_capital)

    # Group signals by date --------------------------------------------------
    signals_by_date: Dict[str, List[dict]] = {}
    for _, row in signals_df.iterrows():
        d = row["date"]
        signals_by_date.setdefault(d, []).append(row.to_dict())

    # -----------------------------------------------------------------------
    # Simulation loop
    # -----------------------------------------------------------------------
    capital = initial_capital
    open_positions: List[dict] = []   # {symbol, entry_date, entry_price, shares, size}
    closed_trades: List[dict] = []

    equity_records: List[dict] = []   # {date, equity, drawdown_pct}
    peak_equity = initial_capital

    for date in all_dates:
        # --- 1. Check exits for open positions ---
        positions_to_close = []
        for pos in open_positions:
            sym = pos["symbol"]
            pdf = prices_cache.get(sym)
            if pdf is None:
                continue

            day_row = pdf[pdf["date"] == date]
            if day_row.empty:
                continue

            current_close = float(day_row["close"].iloc[0])
            current_high = float(day_row["high"].iloc[0])
            current_low = float(day_row["low"].iloc[0])

            entry_price = pos["entry_price"]
            ret_close = (current_close - entry_price) / entry_price
            ret_high = (current_high - entry_price) / entry_price
            ret_low = (current_low - entry_price) / entry_price

            entry_dt = datetime.strptime(pos["entry_date"], "%Y-%m-%d")
            current_dt = datetime.strptime(date, "%Y-%m-%d")
            hold_days = (current_dt - entry_dt).days

            exit_price = None
            exit_reason = None

            # Check intraday stop-loss (assume worst case: low hit first)
            if ret_low <= stop_loss:
                exit_price = entry_price * (1 + stop_loss)
                exit_reason = "stop_loss"
            # Check intraday profit-target
            elif ret_high >= profit_target:
                exit_price = entry_price * (1 + profit_target)
                exit_reason = "profit_target"
            # Check time stop
            elif hold_days >= max_hold_days:
                exit_price = current_close
                exit_reason = "time_stop"

            if exit_price is not None:
                ret_pct = (exit_price - entry_price) / entry_price
                pnl = pos["size"] * ret_pct
                capital += pos["size"] + pnl

                closed_trades.append({
                    "symbol": sym,
                    "entry_date": pos["entry_date"],
                    "exit_date": date,
                    "entry_price": round(entry_price, 4),
                    "exit_price": round(exit_price, 4),
                    "return_pct": round(ret_pct, 6),
                    "pnl": round(pnl, 2),
                    "exit_reason": exit_reason,
                })
                positions_to_close.append(pos)

        for pos in positions_to_close:
            open_positions.remove(pos)

        # --- 2. Check entries for new signals ---
        if date in signals_by_date:
            day_signals = sorted(
                signals_by_date[date],
                key=lambda s: s.get("score", 0),
                reverse=True,
            )

            for sig in day_signals:
                sym = sig["symbol"]

                # Skip if already holding
                if any(p["symbol"] == sym for p in open_positions):
                    continue

                pdf = prices_cache.get(sym)
                if pdf is None:
                    continue

                # Entry at next day's open
                date_idx = pdf[pdf["date"] == date].index
                if date_idx.empty:
                    continue
                idx = date_idx[0]
                if idx + 1 >= len(pdf):
                    continue

                next_row = pdf.iloc[idx + 1]
                entry_price = float(next_row["open"])
                entry_date = next_row["date"]

                if entry_price <= 0:
                    continue

                position_size = capital * position_pct
                if position_size <= 0:
                    continue

                shares = position_size / entry_price
                capital -= position_size

                open_positions.append({
                    "symbol": sym,
                    "entry_date": entry_date,
                    "entry_price": entry_price,
                    "shares": shares,
                    "size": position_size,
                })

        # --- 3. Mark-to-market for equity curve ---
        open_value = 0.0
        for pos in open_positions:
            pdf = prices_cache.get(pos["symbol"])
            if pdf is None:
                continue
            day_row = pdf[pdf["date"] == date]
            if day_row.empty:
                # Use entry price as fallback
                open_value += pos["size"]
            else:
                current_close = float(day_row["close"].iloc[0])
                open_value += pos["shares"] * current_close

        total_equity = capital + open_value
        peak_equity = max(peak_equity, total_equity)
        drawdown_pct = (total_equity - peak_equity) / peak_equity if peak_equity > 0 else 0.0

        equity_records.append({
            "date": date,
            "equity": round(total_equity, 2),
            "drawdown_pct": round(drawdown_pct, 6),
        })

    # --- Force-close remaining open positions at the last available price ---
    if open_positions and all_dates:
        last_date = all_dates[-1]
        for pos in open_positions:
            pdf = prices_cache.get(pos["symbol"])
            if pdf is None:
                continue
            day_row = pdf[pdf["date"] == last_date]
            if day_row.empty:
                # Try the last available row
                day_row = pdf.iloc[[-1]]

            exit_price = float(day_row["close"].iloc[0])
            ret_pct = (exit_price - pos["entry_price"]) / pos["entry_price"]
            pnl = pos["size"] * ret_pct

            closed_trades.append({
                "symbol": pos["symbol"],
                "entry_date": pos["entry_date"],
                "exit_date": last_date,
                "entry_price": round(pos["entry_price"], 4),
                "exit_price": round(exit_price, 4),
                "return_pct": round(ret_pct, 6),
                "pnl": round(pnl, 2),
                "exit_reason": "end_of_backtest",
            })

    # -----------------------------------------------------------------------
    # Compute aggregate statistics
    # -----------------------------------------------------------------------
    stats = _compute_stats(closed_trades, equity_records, initial_capital)

    logger.info(
        "Equity curve simulation complete: %d trades, total_return=%.1f%%, "
        "sharpe=%.2f, max_dd=%.1f%%",
        stats["total_trades"],
        stats["total_return"] * 100,
        stats["sharpe"],
        stats["max_drawdown"] * 100,
    )

    return {
        "equity_curve": equity_records,
        "trades": closed_trades,
        "stats": stats,
    }


# ---------------------------------------------------------------------------
# Statistics computation
# ---------------------------------------------------------------------------

def _compute_stats(
    trades: List[dict],
    equity_records: List[dict],
    initial_capital: float,
) -> Dict[str, Any]:
    """Compute aggregate performance statistics from trade and equity data."""
    if not trades:
        return {
            "total_return": 0.0,
            "cagr": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "profit_factor": 0.0,
            "total_trades": 0,
        }

    returns = np.array([t["return_pct"] for t in trades])
    pnls = np.array([t["pnl"] for t in trades])

    total_trades = len(trades)
    winners = returns[returns > 0]
    losers = returns[returns <= 0]

    win_rate = len(winners) / total_trades if total_trades > 0 else 0.0
    avg_win = float(winners.mean()) if len(winners) > 0 else 0.0
    avg_loss = float(losers.mean()) if len(losers) > 0 else 0.0

    gross_profit = float(pnls[pnls > 0].sum()) if len(pnls[pnls > 0]) > 0 else 0.0
    gross_loss = float(abs(pnls[pnls < 0].sum())) if len(pnls[pnls < 0]) > 0 else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Total return from equity curve
    if equity_records:
        final_equity = equity_records[-1]["equity"]
    else:
        final_equity = initial_capital + float(pnls.sum())

    total_return = (final_equity - initial_capital) / initial_capital

    # CAGR
    if equity_records and len(equity_records) > 1:
        first_date = datetime.strptime(equity_records[0]["date"], "%Y-%m-%d")
        last_date = datetime.strptime(equity_records[-1]["date"], "%Y-%m-%d")
        years = (last_date - first_date).days / 365.25
        if years > 0 and final_equity > 0:
            cagr = (final_equity / initial_capital) ** (1.0 / years) - 1.0
        else:
            cagr = 0.0
    else:
        cagr = 0.0

    # Max drawdown from equity curve
    if equity_records:
        dd_values = [r["drawdown_pct"] for r in equity_records]
        max_drawdown = abs(min(dd_values)) if dd_values else 0.0
    else:
        max_drawdown = 0.0

    # Annualised Sharpe ratio (daily returns from equity curve)
    sharpe = _compute_sharpe(equity_records)

    return {
        "total_return": round(total_return, 6),
        "cagr": round(cagr, 6),
        "sharpe": round(sharpe, 4),
        "max_drawdown": round(max_drawdown, 6),
        "win_rate": round(win_rate, 4),
        "avg_win": round(avg_win, 6),
        "avg_loss": round(avg_loss, 6),
        "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else 999.99,
        "total_trades": total_trades,
    }


def _compute_sharpe(
    equity_records: List[dict],
    risk_free_rate: float = 0.02,
) -> float:
    """Compute annualised Sharpe ratio from daily equity records."""
    if len(equity_records) < 2:
        return 0.0

    equities = np.array([r["equity"] for r in equity_records], dtype=np.float64)
    daily_returns = np.diff(equities) / equities[:-1]

    if len(daily_returns) < 2 or np.std(daily_returns) == 0:
        return 0.0

    daily_rf = (1 + risk_free_rate) ** (1 / 252) - 1
    excess_returns = daily_returns - daily_rf

    sharpe = (np.mean(excess_returns) / np.std(excess_returns)) * np.sqrt(252)
    return float(sharpe)


def _empty_result(initial_capital: float) -> Dict[str, Any]:
    """Return an empty result structure."""
    return {
        "equity_curve": [],
        "trades": [],
        "stats": {
            "total_return": 0.0,
            "cagr": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "profit_factor": 0.0,
            "total_trades": 0,
        },
    }


# ---------------------------------------------------------------------------
# Plotly equity curve chart
# ---------------------------------------------------------------------------

def build_equity_chart(equity_data: Dict[str, Any]) -> go.Figure:
    """Build a Plotly figure showing the equity curve with drawdown shading.

    Parameters
    ----------
    equity_data : dict
        Output from :func:`simulate_equity_curve`.  Must contain keys
        ``equity_curve`` and ``stats``.

    Returns
    -------
    plotly.graph_objects.Figure
    """
    curve = equity_data.get("equity_curve", [])
    stats = equity_data.get("stats", {})

    if not curve:
        fig = go.Figure()
        fig.update_layout(
            title="Equity Curve (No Data)",
            template="plotly_dark",
        )
        return fig

    dates = [r["date"] for r in curve]
    equities = [r["equity"] for r in curve]
    drawdowns = [r["drawdown_pct"] * 100 for r in curve]  # as percentage

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.7, 0.3],
        subplot_titles=("Portfolio Equity", "Drawdown (%)"),
    )

    # --- Equity line ---
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=equities,
            mode="lines",
            name="Equity",
            line=dict(color="#00d4aa", width=2),
            hovertemplate="Date: %{x}<br>Equity: $%{y:,.0f}<extra></extra>",
        ),
        row=1, col=1,
    )

    # --- New high markers ---
    peak = 0
    new_high_dates = []
    new_high_vals = []
    for i, eq in enumerate(equities):
        if eq > peak:
            peak = eq
            new_high_dates.append(dates[i])
            new_high_vals.append(eq)

    if new_high_dates:
        fig.add_trace(
            go.Scatter(
                x=new_high_dates,
                y=new_high_vals,
                mode="markers",
                name="New High",
                marker=dict(color="#00ff88", size=4, symbol="triangle-up"),
                hovertemplate="New High: $%{y:,.0f}<extra></extra>",
            ),
            row=1, col=1,
        )

    # --- Drawdown area (red shaded) ---
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=drawdowns,
            fill="tozeroy",
            mode="lines",
            name="Drawdown",
            line=dict(color="#ff4444", width=1),
            fillcolor="rgba(255, 68, 68, 0.3)",
            hovertemplate="Date: %{x}<br>Drawdown: %{y:.1f}%<extra></extra>",
        ),
        row=2, col=1,
    )

    # --- Annotation: max drawdown point ---
    if drawdowns:
        min_dd_idx = int(np.argmin(drawdowns))
        max_dd_val = drawdowns[min_dd_idx]
        max_dd_date = dates[min_dd_idx]

        fig.add_annotation(
            x=max_dd_date,
            y=max_dd_val,
            text=f"Max DD: {max_dd_val:.1f}%",
            showarrow=True,
            arrowhead=2,
            arrowcolor="#ff4444",
            font=dict(color="#ff4444", size=10),
            row=2, col=1,
        )

    # --- Annotation: final equity ---
    if equities:
        fig.add_annotation(
            x=dates[-1],
            y=equities[-1],
            text=f"${equities[-1]:,.0f}",
            showarrow=True,
            arrowhead=2,
            arrowcolor="#00d4aa",
            font=dict(color="#00d4aa", size=11),
            row=1, col=1,
        )

    # --- Stats annotation box ---
    total_return = stats.get("total_return", 0) * 100
    cagr = stats.get("cagr", 0) * 100
    sharpe = stats.get("sharpe", 0)
    win_rate = stats.get("win_rate", 0) * 100
    total_trades = stats.get("total_trades", 0)
    max_dd = stats.get("max_drawdown", 0) * 100
    pf = stats.get("profit_factor", 0)

    stats_text = (
        f"Return: {total_return:+.1f}%  |  CAGR: {cagr:.1f}%  |  "
        f"Sharpe: {sharpe:.2f}  |  Win Rate: {win_rate:.0f}%  |  "
        f"Max DD: {max_dd:.1f}%  |  PF: {pf:.2f}  |  "
        f"Trades: {total_trades}"
    )

    # --- Layout ---
    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text="Alpha Predator Backtested Equity Curve",
            font=dict(size=16),
        ),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=10),
        ),
        height=600,
        margin=dict(l=60, r=30, t=80, b=60),
        annotations=[
            dict(
                text=stats_text,
                xref="paper", yref="paper",
                x=0.5, y=-0.12,
                showarrow=False,
                font=dict(size=10, color="#aaaaaa"),
                xanchor="center",
            ),
        ] + list(fig.layout.annotations),
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
    )

    fig.update_xaxes(
        gridcolor="rgba(128,128,128,0.1)",
        showgrid=True,
    )
    fig.update_yaxes(
        gridcolor="rgba(128,128,128,0.1)",
        showgrid=True,
        tickprefix="$",
        row=1, col=1,
    )
    fig.update_yaxes(
        gridcolor="rgba(128,128,128,0.1)",
        showgrid=True,
        ticksuffix="%",
        row=2, col=1,
    )

    return fig
