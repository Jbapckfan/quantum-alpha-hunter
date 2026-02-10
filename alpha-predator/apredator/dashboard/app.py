"""
Alpha Predator -- Streamlit Dashboard.

Provides a unified view of watchlist signals, symbol analysis, backtest results,
regime state, alert history, and self-learning metrics.
"""
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import select, func, desc

# ---------------------------------------------------------------------------
# Page configuration (must be first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Alpha Predator",
    page_icon="AP",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Imports from apredator package (relative)
# ---------------------------------------------------------------------------
from ..db import session_scope
from ..schemas import (
    Predictions,
    PriceOHLC,
    Factors,
    Regime,
    AlertLog,
    SignalPerformance,
    ModelRegistry,
    ExplosiveSignals,
)

# ---------------------------------------------------------------------------
# Custom CSS for conviction-level color coding
# ---------------------------------------------------------------------------
CONVICTION_COLORS = {
    "EXTREME": "#00ff00",
    "HIGH": "#ffff00",
    "MODERATE": "#ff8c00",
    "LOW": "#ff0000",
}

REGIME_COLORS = {
    "CRISIS": "#ff0000",
    "EUPHORIA": "#9b59b6",
    "BULL_LOW_VOL": "#00ff00",
    "BULL_HIGH_VOL": "#7cfc00",
    "BEAR_LOW_VOL": "#ff8c00",
    "BEAR_HIGH_VOL": "#ff0000",
    "NEUTRAL": "#888888",
    "RECOVERY": "#1e90ff",
}

st.markdown(
    """
    <style>
    .conviction-extreme { color: #00ff00; font-weight: bold; }
    .conviction-high    { color: #ffff00; font-weight: bold; }
    .conviction-moderate { color: #ff8c00; font-weight: bold; }
    .conviction-low     { color: #ff0000; font-weight: bold; }
    .metric-card {
        background: #1a1a2e;
        border-radius: 8px;
        padding: 16px;
        margin: 4px 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Cached data loaders
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def load_predictions(min_score: int, asset_type: str) -> pd.DataFrame:
    """Load predictions with quantum_score >= min_score."""
    with session_scope() as session:
        stmt = (
            select(Predictions)
            .where(Predictions.quantum_score >= min_score)
            .order_by(desc(Predictions.quantum_score))
        )
        rows = session.execute(stmt).scalars().all()
        if not rows:
            return pd.DataFrame()
        data = [
            {
                "symbol": r.symbol,
                "date": r.date,
                "quantum_score": r.quantum_score,
                "conviction": r.conviction_level,
                "combo": r.combo_match,
                "tier": r.tier,
                "prob_hit_10d": r.prob_hit_10d,
                "kelly": r.kelly_fraction,
                "ensemble": r.ensemble_score,
            }
            for r in rows
        ]
    df = pd.DataFrame(data)
    if asset_type != "all":
        # Filter by joining to PriceOHLC asset_type if needed
        pass
    return df


@st.cache_data(ttl=300)
def load_price_data(symbol: str, days: int = 90) -> pd.DataFrame:
    """Load OHLC price data for a symbol."""
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    with session_scope() as session:
        stmt = (
            select(PriceOHLC)
            .where(PriceOHLC.symbol == symbol)
            .where(PriceOHLC.date >= cutoff)
            .order_by(PriceOHLC.date)
        )
        rows = session.execute(stmt).scalars().all()
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(
            [
                {
                    "date": r.date,
                    "open": r.open,
                    "high": r.high,
                    "low": r.low,
                    "close": r.close,
                    "volume": r.volume,
                }
                for r in rows
            ]
        )


@st.cache_data(ttl=300)
def load_factors(symbol: str) -> dict:
    """Load latest factors row for a symbol."""
    with session_scope() as session:
        stmt = (
            select(Factors)
            .where(Factors.symbol == symbol)
            .order_by(desc(Factors.date))
            .limit(1)
        )
        row = session.execute(stmt).scalars().first()
        if not row:
            return {}
        cols = [c.key for c in Factors.__table__.columns]
        return {c: getattr(row, c, None) for c in cols}


@st.cache_data(ttl=300)
def load_explosive_signals(symbol: str) -> dict:
    """Load latest explosive signals row for a symbol."""
    with session_scope() as session:
        stmt = (
            select(ExplosiveSignals)
            .where(ExplosiveSignals.symbol == symbol)
            .order_by(desc(ExplosiveSignals.date))
            .limit(1)
        )
        row = session.execute(stmt).scalars().first()
        if not row:
            return {}
        cols = [c.key for c in ExplosiveSignals.__table__.columns]
        return {c: getattr(row, c, None) for c in cols}


@st.cache_data(ttl=300)
def load_regime() -> pd.DataFrame:
    """Load recent regime states."""
    with session_scope() as session:
        stmt = select(Regime).order_by(desc(Regime.date)).limit(30)
        rows = session.execute(stmt).scalars().all()
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(
            [
                {
                    "date": r.date,
                    "regime_state": r.regime_state,
                    "regime_confidence": r.regime_confidence,
                    "vix_level": r.vix_level,
                    "spy_above_200ma": r.spy_above_200ma,
                    "btc_above_200ma": r.btc_above_200ma,
                    "risk_on_equities": r.risk_on_equities,
                    "risk_on_crypto": r.risk_on_crypto,
                }
                for r in rows
            ]
        )


@st.cache_data(ttl=300)
def load_alert_history(limit: int = 100) -> pd.DataFrame:
    """Load recent alert log entries."""
    with session_scope() as session:
        stmt = select(AlertLog).order_by(desc(AlertLog.timestamp)).limit(limit)
        rows = session.execute(stmt).scalars().all()
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(
            [
                {
                    "id": r.id,
                    "symbol": r.symbol,
                    "timestamp": r.timestamp,
                    "channel": r.channel,
                    "conviction": r.conviction_level,
                    "quantum_score": r.quantum_score,
                    "combo": r.combo_name,
                    "tier": r.tier,
                    "entry_price": r.entry_price,
                    "outcome_5d": r.outcome_5d,
                    "outcome_10d": r.outcome_10d,
                    "outcome_30d": r.outcome_30d,
                    "max_gain_30d": r.max_gain_30d,
                    "hit_target": r.hit_target,
                }
                for r in rows
            ]
        )


@st.cache_data(ttl=300)
def load_signal_performance() -> pd.DataFrame:
    """Load signal performance tracking data."""
    with session_scope() as session:
        stmt = select(SignalPerformance).order_by(
            desc(SignalPerformance.period_end)
        )
        rows = session.execute(stmt).scalars().all()
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(
            [
                {
                    "signal_name": r.signal_name,
                    "period_start": r.period_start,
                    "period_end": r.period_end,
                    "total_signals": r.total_signals,
                    "hits": r.hits,
                    "hit_rate": r.hit_rate,
                    "avg_return": r.avg_return,
                    "avg_max_gain": r.avg_max_gain,
                    "lift_vs_baseline": r.lift_vs_baseline,
                    "weight_adjustment": r.weight_adjustment,
                }
                for r in rows
            ]
        )


@st.cache_data(ttl=300)
def load_model_registry() -> pd.DataFrame:
    """Load model registry entries."""
    with session_scope() as session:
        stmt = select(ModelRegistry).order_by(desc(ModelRegistry.trained_at))
        rows = session.execute(stmt).scalars().all()
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(
            [
                {
                    "model_id": r.model_id,
                    "asset_type": r.asset_type,
                    "trained_at": r.trained_at,
                    "n_samples": r.n_samples,
                    "n_features": r.n_features,
                    "oos_hit_rate": r.oos_hit_rate,
                    "oos_sharpe": r.oos_sharpe,
                    "filepath": r.filepath,
                    "is_active": r.is_active,
                    "notes": r.notes,
                }
                for r in rows
            ]
        )


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("Alpha Predator")
st.sidebar.markdown("---")
min_score = st.sidebar.slider("Min Quantum Score", 0, 100, 70, step=5)
asset_type = st.sidebar.selectbox("Asset Type", ["all", "stock", "crypto"])
if st.sidebar.button("Refresh Data"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption("Alpha Predator v0.1.0")

# ---------------------------------------------------------------------------
# Main tabs
# ---------------------------------------------------------------------------
tab_watchlist, tab_analysis, tab_backtest, tab_regime, tab_alerts, tab_learning = st.tabs(
    ["Watchlist", "Symbol Analysis", "Backtest", "Regime", "Alert History", "Self-Learning"]
)


# ============================== TAB 1: Watchlist ==============================
with tab_watchlist:
    st.header("Signal Watchlist")

    preds_df = load_predictions(min_score, asset_type)

    if preds_df.empty:
        st.info("No predictions found above the minimum score threshold.")
    else:
        # Summary counts by conviction level
        col1, col2, col3, col4 = st.columns(4)
        for col, level in zip(
            [col1, col2, col3, col4], ["EXTREME", "HIGH", "MODERATE", "LOW"]
        ):
            count = len(preds_df[preds_df["conviction"] == level])
            color = CONVICTION_COLORS.get(level, "#ffffff")
            col.markdown(
                f"<div class='metric-card'>"
                f"<span style='color:{color};font-size:24px;font-weight:bold'>{count}</span><br>"
                f"<span style='color:#aaa'>{level}</span></div>",
                unsafe_allow_html=True,
            )

        st.markdown("---")

        # Color-coded dataframe
        def color_conviction(val):
            color = CONVICTION_COLORS.get(val, "#ffffff")
            return f"color: {color}; font-weight: bold"

        styled = preds_df.style.applymap(
            color_conviction, subset=["conviction"]
        )
        st.dataframe(
            preds_df,
            column_config={
                "quantum_score": st.column_config.ProgressColumn(
                    "Score", min_value=0, max_value=100, format="%d"
                ),
                "prob_hit_10d": st.column_config.NumberColumn(
                    "P(Hit 10d)", format="%.1f%%"
                ),
                "kelly": st.column_config.NumberColumn(
                    "Kelly %", format="%.1f%%"
                ),
            },
            use_container_width=True,
            hide_index=True,
        )


# ============================== TAB 2: Symbol Analysis ==============================
with tab_analysis:
    st.header("Symbol Analysis")

    symbol_input = st.text_input("Enter Symbol", value="", placeholder="e.g. AMC, BTC-USD")
    symbol = symbol_input.strip().upper()

    if symbol:
        # Price chart -- candlestick
        price_df = load_price_data(symbol, days=90)
        if price_df.empty:
            st.warning(f"No price data found for {symbol}")
        else:
            st.subheader(f"{symbol} -- Last 90 Days")
            fig = go.Figure(
                data=[
                    go.Candlestick(
                        x=price_df["date"],
                        open=price_df["open"],
                        high=price_df["high"],
                        low=price_df["low"],
                        close=price_df["close"],
                        name=symbol,
                    )
                ]
            )
            fig.update_layout(
                title=f"{symbol} Price",
                xaxis_title="Date",
                yaxis_title="Price ($)",
                template="plotly_dark",
                height=500,
                xaxis_rangeslider_visible=False,
            )
            st.plotly_chart(fig, use_container_width=True)

        # Factors
        col_left, col_right = st.columns(2)
        with col_left:
            st.subheader("Latest Factors")
            factors = load_factors(symbol)
            if factors:
                factors_display = {
                    k: (f"{v:.4f}" if isinstance(v, float) else str(v))
                    for k, v in factors.items()
                    if v is not None and k not in ("symbol", "date")
                }
                st.json(factors_display)
            else:
                st.info("No factors computed for this symbol.")

        with col_right:
            st.subheader("Explosive Signals")
            explosive = load_explosive_signals(symbol)
            if explosive:
                explosive_display = {
                    k: (f"{v:.4f}" if isinstance(v, float) else str(v))
                    for k, v in explosive.items()
                    if v is not None and k not in ("symbol", "date")
                }
                st.json(explosive_display)
            else:
                st.info("No explosive signals for this symbol.")

        # Combo matches (from explosive signals)
        if explosive and explosive.get("matched_combos"):
            st.subheader("Combo Matches")
            combos_str = explosive["matched_combos"]
            if combos_str:
                for combo in combos_str.split(","):
                    combo = combo.strip()
                    if combo:
                        st.success(f"COMBO: {combo}")
    else:
        st.info("Enter a symbol above to begin analysis.")


# ============================== TAB 3: Backtest ==============================
with tab_backtest:
    st.header("Backtest Simulation")

    col_start, col_end, col_capital, col_minscore = st.columns(4)
    with col_start:
        bt_start = st.date_input("Start Date", value=datetime.now() - timedelta(days=365))
    with col_end:
        bt_end = st.date_input("End Date", value=datetime.now())
    with col_capital:
        bt_capital = st.number_input("Initial Capital ($)", value=100000, step=10000)
    with col_minscore:
        bt_min_score = st.slider("Min Score (BT)", 0, 100, 70, step=5)

    if st.button("Run Backtest"):
        with st.spinner("Running backtest simulation..."):
            try:
                from ..backtest.simulator import simulate
                from ..backtest.metrics import calculate_performance

                trades = simulate(
                    bt_start.strftime("%Y-%m-%d"),
                    bt_end.strftime("%Y-%m-%d"),
                    initial_capital=bt_capital,
                    min_score=bt_min_score,
                )

                if trades.empty:
                    st.warning("No trades were executed in this period.")
                else:
                    metrics = calculate_performance(trades, initial_capital=bt_capital)

                    # Metrics display
                    m1, m2, m3, m4, m5, m6 = st.columns(6)
                    m1.metric("Total Trades", metrics["total_trades"])
                    m2.metric("Hit Rate", f"{metrics['hit_rate']*100:.1f}%")
                    m3.metric("Sharpe Ratio", f"{metrics['sharpe_ratio']:.2f}")
                    m4.metric("Total Return", f"{metrics['total_return_pct']*100:.1f}%")
                    m5.metric("Max Drawdown", f"{metrics['max_drawdown']*100:.1f}%")
                    m6.metric("Profit Factor", f"{metrics['profit_factor']:.2f}")

                    # Equity curve
                    if "equity_curve" in metrics:
                        eq_df = pd.DataFrame(metrics["equity_curve"])
                        fig_eq = go.Figure()
                        fig_eq.add_trace(
                            go.Scatter(
                                x=eq_df["date"],
                                y=eq_df["equity"],
                                mode="lines",
                                name="Equity",
                                line=dict(color="#00ff00", width=2),
                            )
                        )
                        fig_eq.update_layout(
                            title="Equity Curve",
                            xaxis_title="Date",
                            yaxis_title="Portfolio Value ($)",
                            template="plotly_dark",
                            height=400,
                        )
                        st.plotly_chart(fig_eq, use_container_width=True)

                    # Trades table
                    st.subheader("Trade Log")
                    st.dataframe(trades, use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"Backtest failed: {e}")
    else:
        st.info("Configure parameters and click 'Run Backtest' to start.")


# ============================== TAB 4: Regime ==============================
with tab_regime:
    st.header("Market Regime")

    regime_df = load_regime()

    if regime_df.empty:
        st.info("No regime data available. Run a scan to populate regime state.")
    else:
        latest = regime_df.iloc[0]
        regime_state = latest.get("regime_state", "UNKNOWN")
        regime_color = REGIME_COLORS.get(regime_state, "#888888")
        confidence = latest.get("regime_confidence", 0) or 0

        st.markdown(
            f"<h2 style='color:{regime_color}'>{regime_state}</h2>"
            f"<p>Confidence: {confidence*100:.1f}% | VIX: {latest.get('vix_level', 'N/A')}</p>",
            unsafe_allow_html=True,
        )

        col_eq, col_cr = st.columns(2)
        with col_eq:
            st.subheader("Equities")
            spy_ok = latest.get("spy_above_200ma", False)
            risk_eq = latest.get("risk_on_equities", False)
            st.markdown(f"SPY > 200MA: {'Yes' if spy_ok else 'No'}")
            st.markdown(f"Risk-On: {'Yes' if risk_eq else 'No'}")

        with col_cr:
            st.subheader("Crypto")
            btc_ok = latest.get("btc_above_200ma", False)
            risk_cr = latest.get("risk_on_crypto", False)
            st.markdown(f"BTC > 200MA: {'Yes' if btc_ok else 'No'}")
            st.markdown(f"Risk-On: {'Yes' if risk_cr else 'No'}")

        st.markdown("---")
        st.subheader("Regime History (Last 30 Days)")

        def style_regime(val):
            color = REGIME_COLORS.get(val, "#ffffff")
            return f"color: {color}; font-weight: bold"

        st.dataframe(
            regime_df,
            use_container_width=True,
            hide_index=True,
        )


# ============================== TAB 5: Alert History ==============================
with tab_alerts:
    st.header("Alert History")

    alerts_df = load_alert_history(limit=200)

    if alerts_df.empty:
        st.info("No alerts have been sent yet.")
    else:
        # Summary
        n_total = len(alerts_df)
        n_with_outcome = alerts_df["hit_target"].notna().sum()
        n_hit = (alerts_df["hit_target"] == True).sum()  # noqa: E712
        hit_pct = (n_hit / n_with_outcome * 100) if n_with_outcome > 0 else 0

        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Total Alerts", n_total)
        col_b.metric("Outcomes Tracked", int(n_with_outcome))
        col_c.metric("Hit Rate", f"{hit_pct:.1f}%")

        st.markdown("---")

        # Color rows where hit_target is True
        def highlight_hits(row):
            if row.get("hit_target") is True:
                return ["background-color: rgba(0, 255, 0, 0.15)"] * len(row)
            return [""] * len(row)

        styled_alerts = alerts_df.style.apply(highlight_hits, axis=1)
        st.dataframe(
            styled_alerts,
            use_container_width=True,
            hide_index=True,
        )


# ============================== TAB 6: Self-Learning ==============================
with tab_learning:
    st.header("Self-Learning & Adaptation")

    # --- Signal Performance ---
    st.subheader("Signal Performance Tracking")
    sp_df = load_signal_performance()

    if sp_df.empty:
        st.info(
            "No signal performance data yet. The system needs tracked outcomes to learn."
        )
    else:
        # Per-signal hit rates and weight adjustments
        latest_period = sp_df["period_end"].max()
        latest_sp = sp_df[sp_df["period_end"] == latest_period].sort_values(
            "hit_rate", ascending=False
        )
        st.caption(f"Latest period ending: {latest_period}")
        st.dataframe(
            latest_sp[
                [
                    "signal_name",
                    "total_signals",
                    "hits",
                    "hit_rate",
                    "avg_return",
                    "lift_vs_baseline",
                    "weight_adjustment",
                ]
            ],
            use_container_width=True,
            hide_index=True,
            column_config={
                "hit_rate": st.column_config.NumberColumn("Hit Rate", format="%.1f%%"),
                "avg_return": st.column_config.NumberColumn("Avg Return", format="%.2f%%"),
                "lift_vs_baseline": st.column_config.NumberColumn("Lift", format="%.2fx"),
                "weight_adjustment": st.column_config.NumberColumn("Weight Adj", format="%.3f"),
            },
        )

        # Rolling hit rate chart
        st.subheader("Rolling Hit Rate Over Time")
        signal_names = sp_df["signal_name"].unique()
        fig_lr = go.Figure()
        for name in signal_names:
            sig_data = sp_df[sp_df["signal_name"] == name].sort_values("period_end")
            if len(sig_data) > 1:
                fig_lr.add_trace(
                    go.Scatter(
                        x=sig_data["period_end"],
                        y=sig_data["hit_rate"],
                        mode="lines+markers",
                        name=name,
                    )
                )
        fig_lr.update_layout(
            title="Signal Hit Rates Over Time",
            xaxis_title="Period End",
            yaxis_title="Hit Rate",
            template="plotly_dark",
            height=400,
        )
        st.plotly_chart(fig_lr, use_container_width=True)

    st.markdown("---")

    # --- Model Registry ---
    st.subheader("Model Registry")
    mr_df = load_model_registry()

    if mr_df.empty:
        st.info("No models registered yet.")
    else:
        st.dataframe(
            mr_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "oos_hit_rate": st.column_config.NumberColumn(
                    "OOS Hit Rate", format="%.1f%%"
                ),
                "oos_sharpe": st.column_config.NumberColumn(
                    "OOS Sharpe", format="%.2f"
                ),
                "is_active": st.column_config.CheckboxColumn("Active"),
            },
        )
