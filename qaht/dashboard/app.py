"""
Quantum Alpha Hunter - Streamlit Dashboard
Real-time watchlist and signal analysis
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import json

from ..db import session_scope
from ..schemas import Predictions, Factors, Labels, PriceOHLC
from sqlalchemy import select, desc

# Page config
st.set_page_config(
    page_title="Quantum Alpha Hunter",
    page_icon="🚀",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    .big-score {
        font-size: 48px;
        font-weight: bold;
        text-align: center;
    }
    .conviction-max {
        color: #00ff00;
    }
    .conviction-high {
        color: #ffff00;
    }
    .conviction-med {
        color: #ffa500;
    }
    .conviction-low {
        color: #ff0000;
    }
</style>
""", unsafe_allow_html=True)


def load_watchlist(min_score: int = 70):
    """Load latest predictions"""
    with session_scope() as session:
        predictions = session.execute(
            select(Predictions)
            .where(Predictions.quantum_score >= min_score)
            .order_by(desc(Predictions.quantum_score), desc(Predictions.date))
        ).scalars().all()

        if not predictions:
            return pd.DataFrame()

        data = []
        for p in predictions:
            # Parse components
            try:
                components = json.loads(p.components) if p.components else {}
            except:
                components = {}

            # Get top 3 features
            top_features = sorted(components.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
            top_features_str = ", ".join([f"{k}" for k, v in top_features])

            data.append({
                'Symbol': p.symbol,
                'Date': p.date,
                'Score': p.quantum_score,
                'Conviction': p.conviction_level,
                'Probability': f"{p.prob_hit_10d:.1%}",
                'Top Signals': top_features_str
            })

        return pd.DataFrame(data)


def load_symbol_details(symbol: str):
    """Load detailed info for a symbol"""
    with session_scope() as session:
        # Latest prediction
        pred = session.execute(
            select(Predictions)
            .where(Predictions.symbol == symbol)
            .order_by(desc(Predictions.date))
            .limit(1)
        ).scalar_one_or_none()

        # Latest factors
        factors = session.execute(
            select(Factors)
            .where(Factors.symbol == symbol)
            .order_by(desc(Factors.date))
            .limit(1)
        ).scalar_one_or_none()

        # Price history
        prices = session.execute(
            select(PriceOHLC)
            .where(PriceOHLC.symbol == symbol)
            .order_by(PriceOHLC.date)
            .limit(252)
        ).scalars().all()

        return pred, factors, prices


# Sidebar
st.sidebar.title("🚀 Quantum Alpha Hunter")
st.sidebar.markdown("---")

page = st.sidebar.radio("Navigation", ["Watchlist", "Symbol Analysis", "Performance"])

min_score = st.sidebar.slider("Minimum Score", 0, 100, 70, 5)

# Main content
if page == "Watchlist":
    st.title("🎯 Pre-Breakout Watchlist")
    st.markdown("Symbols showing compression + attention explosion")

    # Load data
    df = load_watchlist(min_score)

    if df.empty:
        st.warning("No signals found. Run pipeline first: `qaht run-pipeline`")
    else:
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True
        )

        # Stats
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Signals", len(df))

        with col2:
            max_signals = len(df[df['Conviction'] == 'MAX'])
            st.metric("MAX Conviction", max_signals)

        with col3:
            high_signals = len(df[df['Conviction'] == 'HIGH'])
            st.metric("HIGH Conviction", high_signals)

        with col4:
            avg_score = df['Score'].mean()
            st.metric("Avg Score", f"{avg_score:.0f}")

elif page == "Symbol Analysis":
    st.title("🔍 Symbol Deep Dive")

    # Symbol selector
    with session_scope() as session:
        symbols = session.execute(
            select(Predictions.symbol).distinct()
        ).scalars().all()

    if not symbols:
        st.warning("No symbols found. Run pipeline first.")
    else:
        symbol = st.selectbox("Select Symbol", sorted(symbols))

        if symbol:
            pred, factors, prices = load_symbol_details(symbol)

            if pred:
                # Header
                col1, col2, col3 = st.columns([1, 2, 1])

                with col1:
                    st.markdown(f"<div class='big-score conviction-{pred.conviction_level.lower()}'>{pred.quantum_score}</div>", unsafe_allow_html=True)
                    st.markdown(f"<p style='text-align:center'>{pred.conviction_level} CONVICTION</p>", unsafe_allow_html=True)

                with col2:
                    st.metric("Explosion Probability", f"{pred.prob_hit_10d:.1%}")
                    st.metric("Last Updated", pred.date)

                st.markdown("---")

                # Price chart
                if prices:
                    df_prices = pd.DataFrame([{
                        'date': p.date,
                        'close': p.close,
                        'volume': p.volume
                    } for p in prices])

                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=df_prices['date'],
                        y=df_prices['close'],
                        mode='lines',
                        name='Price'
                    ))
                    fig.update_layout(
                        title=f"{symbol} Price History",
                        xaxis_title="Date",
                        yaxis_title="Price",
                        height=400
                    )
                    st.plotly_chart(fig, use_container_width=True)

                # Feature breakdown
                if factors:
                    st.subheader("📊 Feature Breakdown")

                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown("**Technical Compression**")
                        st.metric("BB Width %", f"{factors.bb_width_pct:.3f}" if factors.bb_width_pct else "N/A")
                        st.metric("MA Spread %", f"{factors.ma_spread_pct:.3f}" if factors.ma_spread_pct else "N/A")
                        st.metric("ATR %", f"{factors.atr_pct:.3f}" if factors.atr_pct else "N/A")

                    with col2:
                        st.markdown("**Social & Momentum**")
                        st.metric("Social Delta", f"{factors.social_delta_7d:.2f}x" if factors.social_delta_7d else "N/A")
                        st.metric("Volume Ratio", f"{factors.volume_ratio_20d:.2f}x" if factors.volume_ratio_20d else "N/A")
                        st.metric("RSI", f"{factors.rsi_14:.0f}" if factors.rsi_14 else "N/A")

            else:
                st.warning(f"No prediction found for {symbol}")

elif page == "Performance":
    st.title("📈 System Performance")

    with session_scope() as session:
        # Get predictions with labels
        query = """
            SELECT
                p.symbol,
                p.date,
                p.quantum_score,
                p.conviction_level,
                l.fwd_ret_10d,
                l.explosive_10d
            FROM predictions p
            JOIN labels l ON p.symbol = l.symbol AND p.date = l.date
            WHERE l.fwd_ret_10d IS NOT NULL
        """

        df = pd.read_sql(query, session.bind)

    if df.empty:
        st.warning("No performance data available yet")
    else:
        # Calculate hit rate by conviction
        conviction_perf = df.groupby('conviction_level').agg({
            'explosive_10d': ['count', 'sum', 'mean']
        }).round(3)

        st.subheader("Hit Rate by Conviction Level")
        st.dataframe(conviction_perf)

        # Score distribution
        fig = px.histogram(df, x='quantum_score', nbins=20, title="Score Distribution")
        st.plotly_chart(fig, use_container_width=True)

        # Returns by score bucket
        df['score_bucket'] = pd.cut(df['quantum_score'], bins=[0, 70, 80, 90, 100], labels=['70-79', '80-89', '90-99', '100'])
        bucket_perf = df.groupby('score_bucket')['fwd_ret_10d'].agg(['count', 'mean', 'std']).round(3)

        st.subheader("Returns by Score Bucket")
        st.dataframe(bucket_perf)

# Footer
st.sidebar.markdown("---")
st.sidebar.markdown("Built with Quantum Alpha Hunter")
st.sidebar.markdown("Buy the spring before it uncoils 🚀")
