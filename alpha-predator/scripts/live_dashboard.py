"""
Alpha Predator — Live Trading Intelligence Dashboard

A full-featured Streamlit dashboard with:
- Live symbol search with on-demand analysis
- Universe scanning with real-time results
- Interactive candlestick charts with S/R levels
- Combo detection, tier classification, Kelly sizing
- Reversal strength scoring
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from datetime import datetime, timedelta

import yfinance as yf

import requests

from apredator.adapters.yahoo import fetch_prices
from apredator.features.technical import compute_all_technical
from apredator.features.explosive import compute_all_explosive
from apredator.scoring.combo_matcher import match_combos, WINNING_COMBOS
from apredator.scoring.tier_system import classify_tier
from apredator.scoring.position_sizer import kelly_position_size
from apredator.features.intelligence import (
    compute_relative_strength, compute_weekly_confluence, detect_unfilled_gaps,
    fetch_insider_activity, detect_unusual_options, get_earnings_proximity,
    get_sector_heatmap, get_symbol_sector, SignalTracker,
)
from apredator.features.analogs import find_historical_analogs
from apredator.features.fibonacci import compute_fibonacci_levels
from apredator.features.finra import fetch_short_interest, compute_dark_pool_proxy
from apredator.features.watchlist import Watchlist
from apredator.features.divergence import compute_divergences
from apredator.features.volume_profile import compute_volume_profile
from apredator.features.max_pain import compute_max_pain_gex
from apredator.features.multi_timeframe import compute_multi_timeframe_score
from apredator.features.edgar_insider import fetch_edgar_insider
from apredator.backtest.equity_curve import simulate_equity_curve, build_equity_chart

# Signal tracker & watchlist (persistent across reruns)
_tracker = SignalTracker()
_watchlist = Watchlist()

# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Alpha Predator",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# Preset universes
# ─────────────────────────────────────────────────────────────────────────────
PRESETS = {
    "High Beta / Meme": ["AMC", "GME", "SOFI", "HOOD", "AFRM", "UPST", "DKNG", "CLOV", "RBLX", "CVNA"],
    "Crypto-Adjacent": ["RIOT", "MARA", "COIN", "BITF", "HUT", "CIFR", "MSTR", "CLSK"],
    "Biotech": ["SAVA", "SRNE", "OCGN", "VXRT", "IBRX", "APLS", "CRSP", "BEAM", "NTLA", "DNA"],
    "EV / Clean Energy": ["LCID", "RIVN", "QS", "CHPT", "BLNK", "PLUG", "FCEL", "BE", "ENPH", "RUN"],
    "Tech Growth": ["SNOW", "CRWD", "NET", "DDOG", "ZS", "MDB", "CFLT", "SHOP", "ROKU", "TTD"],
    "Chinese ADR": ["BABA", "JD", "PDD", "NIO", "XPEV", "LI", "BIDU", "FUTU", "TAL"],
    "Quantum / Space / AI": ["IONQ", "RGTI", "QBTS", "QUBT", "LUNR", "RKLB", "ASTS", "JOBY", "SMCI", "ARM"],
    "Nuclear / Energy": ["OKLO", "SMR", "NNE", "VST", "CEG"],
    "Misc Momentum": ["CVNA", "HIMS", "DJT", "RDDT", "MNDY", "CELH", "DASH", "SNAP", "PINS", "SE"],
    "Cannabis": ["TLRY", "SNDL", "ACB", "CGC"],
    "Full Market (All US Stocks)": [],  # entire US equity market via NASDAQ screener
}

# ─────────────────────────────────────────────────────────────────────────────
# Custom CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    .stApp { background-color: #0a0e17; }
    section[data-testid="stSidebar"] { background-color: #111827; }
    .stApp header { background-color: transparent; }

    /* Hide default Streamlit elements (keep header for sidebar toggle) */
    #MainMenu, footer { visibility: hidden; }
    header[data-testid="stHeader"] { background-color: rgba(10,14,23,0.8) !important; }

    .main-title {
        font-family: 'Inter', sans-serif;
        font-size: 28px; font-weight: 800; letter-spacing: -1px;
        background: linear-gradient(135deg, #06b6d4, #3b82f6, #a855f7);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        margin-bottom: 0;
    }
    .sub-title {
        font-family: 'Inter', sans-serif;
        color: #64748b; font-size: 13px; margin-top: -8px; margin-bottom: 20px;
    }

    /* Metric cards */
    .metric-card {
        background: #111827; border: 1px solid #1e293b; border-radius: 12px;
        padding: 16px 20px; position: relative; overflow: hidden;
    }
    .metric-card::before {
        content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
    }
    .metric-card.green::before { background: linear-gradient(90deg, #22c55e, transparent); }
    .metric-card.red::before { background: linear-gradient(90deg, #ef4444, transparent); }
    .metric-card.blue::before { background: linear-gradient(90deg, #3b82f6, transparent); }
    .metric-card.purple::before { background: linear-gradient(90deg, #a855f7, transparent); }
    .metric-card.amber::before { background: linear-gradient(90deg, #f59e0b, transparent); }
    .metric-card.cyan::before { background: linear-gradient(90deg, #06b6d4, transparent); }
    .metric-label {
        font-size: 10px; text-transform: uppercase; letter-spacing: 1.5px;
        color: #64748b; font-weight: 600; font-family: 'Inter', sans-serif;
    }
    .metric-value {
        font-size: 28px; font-weight: 800; font-family: 'Inter', sans-serif;
        margin-top: 4px; line-height: 1.1;
    }
    .metric-detail {
        font-size: 12px; color: #94a3b8; margin-top: 4px; font-family: 'Inter', sans-serif;
    }

    /* Signal tags */
    .signal-tag {
        display: inline-block; padding: 5px 12px; border-radius: 6px; margin: 3px;
        font-size: 12px; font-weight: 600; font-family: 'Inter', sans-serif;
    }
    .signal-tag.green { background: rgba(34,197,94,0.12); border: 1px solid rgba(34,197,94,0.3); color: #22c55e; }
    .signal-tag.red { background: rgba(239,68,68,0.12); border: 1px solid rgba(239,68,68,0.3); color: #ef4444; }
    .signal-tag.blue { background: rgba(59,130,246,0.12); border: 1px solid rgba(59,130,246,0.3); color: #3b82f6; }
    .signal-tag.amber { background: rgba(245,158,11,0.12); border: 1px solid rgba(245,158,11,0.3); color: #f59e0b; }
    .signal-tag.purple { background: rgba(168,85,247,0.12); border: 1px solid rgba(168,85,247,0.3); color: #a855f7; }

    /* Combo badge */
    .combo-badge {
        display: inline-block; padding: 6px 16px; border-radius: 20px;
        font-size: 13px; font-weight: 700; font-family: 'Inter', sans-serif;
        background: linear-gradient(135deg, rgba(34,197,94,0.15), rgba(34,197,94,0.05));
        border: 1px solid rgba(34,197,94,0.4); color: #22c55e;
    }

    /* Level items */
    .level-resistance {
        background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.2);
        border-radius: 8px; padding: 8px 14px; margin: 4px 0;
        display: flex; justify-content: space-between; align-items: center;
    }
    .level-support {
        background: rgba(34,197,94,0.08); border: 1px solid rgba(34,197,94,0.2);
        border-radius: 8px; padding: 8px 14px; margin: 4px 0;
        display: flex; justify-content: space-between; align-items: center;
    }
    .level-ma {
        background: rgba(168,85,247,0.08); border: 1px solid rgba(168,85,247,0.2);
        border-radius: 8px; padding: 8px 14px; margin: 4px 0;
        display: flex; justify-content: space-between; align-items: center;
    }

    /* Results table */
    .result-row {
        background: #111827; border: 1px solid #1e293b; border-radius: 10px;
        padding: 14px 20px; margin: 6px 0; cursor: pointer;
        transition: all 0.15s ease;
        display: grid; grid-template-columns: 80px 90px 1fr 100px 120px 80px;
        align-items: center; gap: 12px;
    }
    .result-row:hover {
        background: #1a2332; border-color: #3b82f6;
        box-shadow: 0 0 20px rgba(59,130,246,0.1);
    }
    .result-symbol {
        font-size: 16px; font-weight: 700; color: #e2e8f0;
        font-family: 'Inter', sans-serif;
    }
    .result-price {
        font-size: 14px; color: #94a3b8; font-family: 'SF Mono', 'Fira Code', monospace;
    }
    .result-combo {
        font-size: 12px; font-weight: 600; color: #22c55e;
        font-family: 'Inter', sans-serif;
    }
    .result-score {
        font-size: 20px; font-weight: 800; font-family: 'Inter', sans-serif;
    }

    /* Scrollable results */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border: none !important;
    }

    /* Table styling */
    .stDataFrame { border-radius: 12px; overflow: hidden; }

    /* Chart container */
    .chart-container {
        background: #080c14; border: 1px solid #1e293b; border-radius: 14px;
        padding: 8px; margin: 8px 0 16px 0;
        box-shadow: 0 4px 24px rgba(0,0,0,0.3);
    }

    /* Expander styling */
    div[data-testid="stExpander"] {
        border: 1px solid #1e293b !important;
        border-radius: 10px !important;
        background: rgba(17,24,39,0.5) !important;
        margin-bottom: 8px !important;
    }
    div[data-testid="stExpander"] summary {
        font-weight: 600 !important;
        font-size: 13px !important;
    }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Core analysis functions
# ─────────────────────────────────────────────────────────────────────────────

def compute_support_resistance(df, n_levels=4):
    """Find key support/resistance levels using pivot points."""
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values

    levels = []
    window = 10
    for i in range(window, len(close) - window):
        if high[i] == max(high[i - window:i + window + 1]):
            levels.append({"price": float(high[i]), "type": "resistance"})
        if low[i] == min(low[i - window:i + window + 1]):
            levels.append({"price": float(low[i]), "type": "support"})

    current_price = close[-1]
    tolerance = current_price * 0.02

    clustered = []
    used = set()
    for l in sorted(levels, key=lambda x: x["price"]):
        p = round(l["price"], 2)
        if p in used:
            continue
        cluster = [x for x in levels if abs(x["price"] - p) <= tolerance]
        avg_price = np.mean([x["price"] for x in cluster])
        for x in cluster:
            used.add(round(x["price"], 2))
        is_resistance = avg_price > current_price
        clustered.append({
            "price": round(float(avg_price), 2),
            "type": "resistance" if is_resistance else "support",
            "touches": len(cluster),
        })

    # Add MAs
    for w, name in [(20, "MA20"), (50, "MA50"), (200, "MA200")]:
        if len(close) >= w:
            ma = float(np.mean(close[-w:]))
            clustered.append({"price": round(ma, 2), "type": name, "touches": 0})

    supports = sorted([l for l in clustered if l["type"] == "support" or l["type"].startswith("MA")],
                       key=lambda l: abs(l["price"] - current_price))[:n_levels]
    resistances = sorted([l for l in clustered if l["type"] == "resistance" or l["type"].startswith("MA")],
                          key=lambda l: abs(l["price"] - current_price))[:n_levels]

    seen = set()
    final = []
    for l in supports + resistances:
        key = round(l["price"], 1)
        if key not in seen:
            seen.add(key)
            final.append(l)
    return sorted(final, key=lambda l: l["price"])


def compute_reversal_metrics(tech, explosive, df, divergence=None):
    """Compute reversal strength score and reasons."""
    close = df["close"].iloc[-1]
    close_5d = df["close"].iloc[-6] if len(df) > 5 else close
    close_20d = df["close"].iloc[-21] if len(df) > 20 else close
    ret_5d = (close - close_5d) / close_5d * 100
    ret_20d = (close - close_20d) / close_20d * 100

    rsi = tech.get("rsi_14", 50)
    drawdown = explosive.get("drawdown_60d", 0)
    vol_ratio = tech.get("volume_ratio_20d", 1.0)
    vol_zscore = explosive.get("vol_zscore", 0)

    score = 0
    reasons = []

    if drawdown >= 40:
        score += 25; reasons.append(f"Deep drawdown {drawdown:.0f}%")
    elif drawdown >= 25:
        score += 18; reasons.append(f"Drawdown {drawdown:.0f}%")
    elif drawdown >= 15:
        score += 10; reasons.append(f"Pullback {drawdown:.0f}%")

    if 30 <= rsi <= 50:
        score += 15; reasons.append(f"RSI setup {rsi:.0f}")
    elif rsi < 30:
        score += 10; reasons.append(f"RSI oversold {rsi:.0f}")

    if ret_5d > 3 and ret_20d < 0:
        score += 20; reasons.append(f"Bounce +{ret_5d:.1f}%")
    elif ret_5d > 1 and ret_20d < -5:
        score += 15; reasons.append(f"Early reversal +{ret_5d:.1f}%")

    if vol_ratio >= 2.0:
        score += 15; reasons.append(f"Vol surge {vol_ratio:.1f}x")
    elif vol_ratio >= 1.3:
        score += 8; reasons.append(f"Vol rising {vol_ratio:.1f}x")

    if vol_zscore >= 0.15:
        score += 10; reasons.append(f"Vol z={vol_zscore:.2f}")

    if explosive.get("rejection_wick", 0) >= 1.0:
        score += 8; reasons.append("Rejection wicks")
    if explosive.get("low_in_range", 0):
        score += 5; reasons.append("Low in range")
    if tech.get("bb_width_pct", 10) < 5:
        score += 8; reasons.append(f"BB squeeze {tech.get('bb_width_pct',0):.1f}%")

    # Divergence boost
    if divergence and divergence.get("has_bullish_div"):
        strength = divergence.get("divergence_strength", 0)
        if strength >= 3:
            score += 20; reasons.append(f"Strong bullish divergence ({divergence.get('divergence_type', '')})")
        elif strength >= 2:
            score += 16; reasons.append(f"Bullish divergence ({divergence.get('divergence_type', '')})")
        else:
            score += 12; reasons.append(f"Mild bullish divergence ({divergence.get('divergence_type', '')})")

    return {
        "reversal_score": score, "reasons": reasons,
        "ret_5d": ret_5d, "ret_20d": ret_20d, "rsi": rsi,
        "drawdown": drawdown, "vol_ratio": vol_ratio, "vol_zscore": vol_zscore,
    }


@st.cache_data(ttl=3600, show_spinner="Fetching full US market from NASDAQ...")
def fetch_full_market(min_mcap=0, max_mcap=0):
    """Fetch ALL US-traded stocks from NASDAQ screener API, filtered by market cap.

    Volume filtering is done downstream in analyze_batch using actual OHLCV data
    because the NASDAQ API does not return a volume field.
    """
    url = "https://api.nasdaq.com/api/screener/stocks"
    params = {"tableType": "traded", "limit": 25000, "offset": 0}
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("data", {}).get("table", {}).get("rows", [])
    except Exception as e:
        st.warning(f"NASDAQ screener unavailable ({e}). Falling back to index-based universe.")
        from apredator.universe.stocks import get_stock_universe
        return get_stock_universe()

    if not rows:
        from apredator.universe.stocks import get_stock_universe
        return get_stock_universe()

    filtered = []
    for row in rows:
        symbol = row.get("symbol", "").strip()
        if not symbol or "/" in symbol or "^" in symbol or " " in symbol:
            continue
        # Skip warrants, units, rights
        if len(symbol) >= 5 and symbol[-1] in ("W", "U", "R"):
            continue

        # Parse market cap
        mc_str = row.get("marketCap", "")
        mc = _parse_mcap(mc_str)

        # If mcap filter is active, stock must meet it (unknown mcap = excluded)
        if min_mcap > 0 and mc < min_mcap:
            continue
        if max_mcap > 0 and (mc == 0 or mc > max_mcap):
            continue

        # Skip completely empty entries
        if mc == 0 and not row.get("lastsale"):
            continue

        filtered.append(symbol)

    return filtered


def _parse_mcap(s):
    """Parse NASDAQ screener market cap string (raw number with commas)."""
    if not s or not isinstance(s, str):
        return 0
    s = s.strip().replace(",", "").replace("$", "")
    try:
        return float(s)
    except ValueError:
        return 0


@st.cache_data(ttl=600, show_spinner=False)
def fetch_fundamentals_batch(symbols):
    """Fetch market cap and avg volume for a list of symbols via yfinance."""
    result = {}
    try:
        tickers = yf.Tickers(" ".join(symbols))
        for symbol in symbols:
            try:
                info = tickers.tickers[symbol].info
                market_cap = info.get("marketCap", 0) or 0
                avg_volume = info.get("averageVolume", 0) or info.get("averageDailyVolume10Day", 0) or 0
                result[symbol] = {"market_cap": market_cap, "avg_volume": avg_volume}
            except Exception:
                result[symbol] = {"market_cap": 0, "avg_volume": 0}
    except Exception:
        for symbol in symbols:
            result[symbol] = {"market_cap": 0, "avg_volume": 0}
    return result


def format_market_cap(mc):
    """Format market cap as human-readable string."""
    if mc >= 1_000_000_000_000:
        return f"${mc / 1_000_000_000_000:.1f}T"
    if mc >= 1_000_000_000:
        return f"${mc / 1_000_000_000:.1f}B"
    if mc >= 1_000_000:
        return f"${mc / 1_000_000:.0f}M"
    if mc > 0:
        return f"${mc / 1_000:.0f}K"
    return "N/A"


def format_volume(vol):
    """Format volume as human-readable string."""
    if vol >= 1_000_000:
        return f"{vol / 1_000_000:.1f}M"
    if vol >= 1_000:
        return f"{vol / 1_000:.0f}K"
    if vol > 0:
        return str(int(vol))
    return "N/A"


@st.cache_data(ttl=300, show_spinner=False)
def analyze_symbol(symbol, period="1y"):
    """Full analysis pipeline for a single symbol."""
    df = fetch_prices([symbol], period=period)
    if df.empty or len(df) < 60:
        return None

    sym_df = df[df["symbol"] == symbol].sort_values("date").reset_index(drop=True)
    if len(sym_df) < 60:
        return None

    tech = compute_all_technical(sym_df)
    explosive = compute_all_explosive(sym_df)
    combos = match_combos(explosive)
    levels = compute_support_resistance(sym_df)

    # New computation-only features
    divergence = compute_divergences(sym_df)
    vol_profile = compute_volume_profile(sym_df)
    mtf = compute_multi_timeframe_score(sym_df)

    reversal = compute_reversal_metrics(tech, explosive, sym_df, divergence=divergence)
    weekly = compute_weekly_confluence(sym_df)
    gaps = detect_unfilled_gaps(sym_df)

    best_combo = max(combos, key=lambda c: c["hit_rate"]) if combos else None
    kelly = kelly_position_size(best_combo["hit_rate"]) * 100 if best_combo else 0

    feat_dict = {**tech, **explosive, "close": sym_df["close"].iloc[-1]}
    tier_result = classify_tier(feat_dict)

    # Fetch fundamentals for single symbol
    fundies = fetch_fundamentals_batch([symbol])
    fund = fundies.get(symbol, {"market_cap": 0, "avg_volume": 0})

    # Per-symbol intelligence (only for single-symbol view, too slow for batch)
    sector = get_symbol_sector(symbol)
    rel_strength = compute_relative_strength(sym_df, sector=sector)
    edgar_insider = fetch_edgar_insider(symbol)
    # Backward-compatible insider dict
    insider = {
        "insider_buys": edgar_insider.get("insider_buys_90d", 0),
        "insider_sells": edgar_insider.get("insider_sells_90d", 0),
        "insider_net": edgar_insider.get("insider_net_90d", 0),
        "insider_buy_value": 0,
        "last_insider_buy": None,
    }
    options = detect_unusual_options(symbol)
    earnings = get_earnings_proximity(symbol)

    # Max pain & GEX (single-symbol only, requires API call)
    max_pain = compute_max_pain_gex(symbol, float(sym_df["close"].iloc[-1]))

    # Existing features: analogs, fibonacci, short interest, dark pool
    current_features = {
        "drawdown_60d": explosive.get("drawdown_60d", 0),
        "rsi_14": tech.get("rsi_14", 50),
        "volume_ratio_20d": tech.get("volume_ratio_20d", 1.0),
        "bb_position": tech.get("bb_position", 0.5),
    }
    analogs = find_historical_analogs(sym_df, current_features)
    fib = compute_fibonacci_levels(sym_df)
    short_info = fetch_short_interest(symbol)
    dark_pool = compute_dark_pool_proxy(sym_df)

    return {
        "symbol": symbol, "df": sym_df, "tech": tech, "explosive": explosive,
        "combos": combos, "levels": levels, "reversal": reversal,
        "best_combo": best_combo, "kelly": kelly, "tier": tier_result,
        "price": float(sym_df["close"].iloc[-1]),
        "market_cap": fund["market_cap"],
        "avg_volume": fund["avg_volume"],
        "weekly": weekly, "gaps": gaps, "sector": sector,
        "rel_strength": rel_strength, "insider": insider,
        "options": options, "earnings": earnings,
        "analogs": analogs, "fibonacci": fib,
        "short_info": short_info, "dark_pool": dark_pool,
        "max_pain": max_pain, "divergence": divergence,
        "vol_profile": vol_profile, "edgar_insider": edgar_insider, "mtf": mtf,
    }


@st.cache_data(ttl=300, show_spinner="Fetching prices...")
def fetch_batch(symbols, period="1y"):
    """Fetch prices for multiple symbols."""
    return fetch_prices(symbols, period=period)


def filter_by_volume(df_all, symbols, min_vol):
    """Filter symbols by 20-day avg daily volume using downloaded OHLCV data.

    Returns the filtered symbol list.
    """
    if min_vol <= 0:
        return symbols
    if df_all.empty or "symbol" not in df_all.columns:
        return []

    valid = [s for s in symbols if s in df_all["symbol"].unique()]
    passing = []
    for sym in valid:
        sym_vol = df_all.loc[df_all["symbol"] == sym, "volume"]
        avg_vol = float(sym_vol.tail(20).mean()) if len(sym_vol) >= 20 else float(sym_vol.mean())
        if avg_vol >= min_vol:
            passing.append(sym)
    return passing


def analyze_batch(symbols, df_all, min_mcap=0, max_mcap=0):
    """Analyze symbols that have already been price-downloaded and volume-filtered."""
    if df_all.empty:
        return []

    valid_symbols = [s for s in symbols if s in df_all["symbol"].unique()]

    # ── Pre-filter by market cap (only if mcap filters are active) ──
    needs_mcap = min_mcap > 0 or max_mcap > 0
    if needs_mcap:
        fundies = fetch_fundamentals_batch(valid_symbols)
        filtered_symbols = []
        for symbol in valid_symbols:
            mc = fundies.get(symbol, {}).get("market_cap", 0)
            if min_mcap > 0 and mc < min_mcap:
                continue
            if max_mcap > 0 and (mc == 0 or mc > max_mcap):
                continue
            filtered_symbols.append(symbol)
    else:
        fundies = {}
        filtered_symbols = valid_symbols

    results = []
    progress = st.progress(0, text=f"Analyzing 0/{len(filtered_symbols)} symbols...")
    for idx, symbol in enumerate(filtered_symbols):
        sym_df = df_all[df_all["symbol"] == symbol].sort_values("date").reset_index(drop=True)
        if len(sym_df) < 60:
            progress.progress((idx + 1) / len(filtered_symbols),
                              text=f"Analyzing {idx+1}/{len(filtered_symbols)}... ({symbol} skipped)")
            continue
        try:
            tech = compute_all_technical(sym_df)
            explosive = compute_all_explosive(sym_df)
            combos = match_combos(explosive)
            levels = compute_support_resistance(sym_df)
            divergence = compute_divergences(sym_df)
            vol_profile = compute_volume_profile(sym_df)
            mtf = compute_multi_timeframe_score(sym_df)
            reversal = compute_reversal_metrics(tech, explosive, sym_df, divergence=divergence)
            weekly = compute_weekly_confluence(sym_df)
            gaps = detect_unfilled_gaps(sym_df)
            best_combo = max(combos, key=lambda c: c["hit_rate"]) if combos else None
            kelly = kelly_position_size(best_combo["hit_rate"]) * 100 if best_combo else 0
            feat_dict = {**tech, **explosive, "close": sym_df["close"].iloc[-1]}
            tier_result = classify_tier(feat_dict)

            fund = fundies.get(symbol, {})
            # Compute avg volume from actual OHLCV data (always reliable)
            sym_avg_vol = float(sym_df["volume"].tail(20).mean()) if len(sym_df) >= 20 else float(sym_df["volume"].mean())

            # Log signal to tracker
            _tracker.log_signal(
                symbol=symbol, price=float(sym_df["close"].iloc[-1]),
                reversal_score=reversal["reversal_score"],
                best_combo=best_combo["name"] if best_combo else None,
                combo_hit_rate=best_combo["hit_rate"] if best_combo else 0,
                tier=tier_result.get("tier"),
                confluence_score=weekly["confluence_score"],
                reasons=reversal["reasons"],
            )

            results.append({
                "symbol": symbol, "df": sym_df, "tech": tech, "explosive": explosive,
                "combos": combos, "levels": levels, "reversal": reversal,
                "best_combo": best_combo, "kelly": kelly, "tier": tier_result,
                "price": float(sym_df["close"].iloc[-1]),
                "market_cap": fund.get("market_cap", 0),
                "avg_volume": sym_avg_vol,
                "weekly": weekly, "gaps": gaps,
                "divergence": divergence, "vol_profile": vol_profile, "mtf": mtf,
            })
        except Exception:
            pass

        progress.progress((idx + 1) / len(filtered_symbols),
                          text=f"Analyzing {idx+1}/{len(filtered_symbols)}... ({symbol})")
    progress.empty()

    results.sort(key=lambda r: (len(r["combos"]) > 0, r["reversal"]["reversal_score"]), reverse=True)
    return results


def filter_bottomed_reversals(results):
    """Filter scan results to only bottomed reversals with real strength.

    Criteria:
    - Drawdown >= 15% from 60d high (it actually fell)
    - RSI < 55 (not already overbought / mid-rally)
    - At least ONE of:
      - 5d return > 0 while 20d return < 0 (the bounce-off-bottom pattern)
      - Volume ratio >= 1.3x (buyers showing up)
      - Vol z-score >= 0.15 (explosive volume)
    - Reversal score >= 25 (enough signal confluence)
    """
    filtered = []
    for r in results:
        rev = r["reversal"]
        dd = rev["drawdown"]
        rsi = rev["rsi"]
        ret_5d = rev["ret_5d"]
        ret_20d = rev["ret_20d"]
        vol_ratio = rev["vol_ratio"]
        vol_z = rev["vol_zscore"]
        score = rev["reversal_score"]

        # Must have meaningful drawdown
        if dd < 15:
            continue
        # Can't be overbought already
        if rsi >= 55:
            continue
        # Must have at least one confirmation signal
        has_bounce = ret_5d > 0 and ret_20d < 0
        has_volume = vol_ratio >= 1.3
        has_vol_explosion = vol_z >= 0.15
        if not (has_bounce or has_volume or has_vol_explosion):
            continue
        # Minimum reversal score
        if score < 25:
            continue

        filtered.append(r)

    # Sort by reversal score (primary), then combo count (secondary)
    filtered.sort(key=lambda r: (r["reversal"]["reversal_score"], len(r["combos"]) > 0), reverse=True)
    return filtered


# ─────────────────────────────────────────────────────────────────────────────
# Chart builders
# ─────────────────────────────────────────────────────────────────────────────

def build_price_chart(data, days=120):
    """Build a polished chart matching the Key Resistance Levels Analysis style.

    Features:
    - Close line with high-low range ribbon (gray shaded)
    - MA20 (blue dashed) and MA50 (orange dashed)
    - Color-graded resistance levels (red → orange → yellow) with R1-Rn labels
    - Green current price line with left-side label
    - 52-week high dotted line
    - Red/green volume bars
    - New feature overlays (Max Pain, VPOC, Value Area, divergence arrows)
    """
    df = data["df"].tail(days).copy()
    levels = data["levels"]
    current_price = data["price"]
    symbol = data["symbol"]

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04,
        row_heights=[0.75, 0.25],
        subplot_titles=[None, None],
    )

    # ── High-Low Range ribbon (gray shaded band) ──
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["high"], mode="lines",
        line=dict(color="rgba(180,180,180,0)", width=0),
        name="Range", showlegend=True, legendgroup="range",
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["low"], mode="lines", fill="tonexty",
        fillcolor="rgba(180,180,180,0.25)",
        line=dict(color="rgba(180,180,180,0)", width=0),
        name="Range", showlegend=False, legendgroup="range",
    ), row=1, col=1)

    # ── Close line (solid black/white) ──
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["close"], mode="lines",
        line=dict(color="#e2e8f0", width=2.2),
        name="Close",
    ), row=1, col=1)

    # ── Moving averages (dashed) ──
    ma20 = df["close"].rolling(20).mean()
    fig.add_trace(go.Scatter(
        x=df["date"], y=ma20, mode="lines",
        line=dict(color="#6366f1", width=1.5, dash="dash"), name="MA20",
    ), row=1, col=1)
    ma50 = df["close"].rolling(50).mean()
    fig.add_trace(go.Scatter(
        x=df["date"], y=ma50, mode="lines",
        line=dict(color="#f59e0b", width=1.5, dash="dash"), name="MA50",
    ), row=1, col=1)

    # ── 52-Week High (dotted magenta line) ──
    full_df = data["df"]
    high_52w = float(full_df["high"].tail(252).max()) if len(full_df) >= 20 else float(full_df["high"].max())
    fig.add_hline(
        y=high_52w, line_dash="dot", line_color="rgba(200,120,220,0.5)", line_width=1,
        row=1, col=1,
        annotation_text=f"52w High: ${high_52w:.2f}",
        annotation_position="right",
        annotation_font=dict(size=10, color="rgba(200,120,220,0.8)", family="Inter, sans-serif"),
    )

    # ── S/R levels — color-graded resistance/support with R1-Rn / S1-Sn labels ──
    # Separate resistances and supports, sort by distance from current price
    resistances = sorted(
        [l for l in levels if l["type"] == "resistance" and l["price"] > current_price],
        key=lambda l: l["price"],
    )
    supports = sorted(
        [l for l in levels if l["type"] == "support" and l["price"] <= current_price],
        key=lambda l: l["price"], reverse=True,
    )

    # De-cluster: skip levels within 1.5% of the previous kept level
    def _decluster(lvls, min_gap_pct=1.5):
        kept = []
        for lv in lvls:
            if kept and abs(lv["price"] / kept[-1]["price"] - 1) * 100 < min_gap_pct:
                continue
            kept.append(lv)
        return kept

    resistances = _decluster(resistances)
    supports = _decluster(supports)

    # Color gradient for resistances (cap at 4)
    _r_colors = [
        ("#ef4444", 2.0),   # R1 — red
        ("#f97316", 1.5),   # R2 — orange
        ("#f59e0b", 1.2),   # R3 — amber
        ("#eab308", 1.0),   # R4 — yellow
    ]
    for i, level in enumerate(resistances[:4]):
        color, width = _r_colors[i] if i < len(_r_colors) else ("#eab308", 1.0)
        pct = (level["price"] / current_price - 1) * 100
        label = f"R{i+1} ${level['price']:.2f} +{pct:.0f}%"
        fig.add_hline(
            y=level["price"], line_dash="dash", line_color=color, line_width=width,
            row=1, col=1,
            annotation_text=f"  {label}",
            annotation_position="right" if i % 2 == 0 else "left",
            annotation_font=dict(size=9, color=color, family="Inter, sans-serif"),
        )

    # Supports: green shades (cap at 2)
    _s_colors = [
        ("#22c55e", 1.5),   # S1 — green
        ("#4ade80", 1.2),   # S2
    ]
    for i, level in enumerate(supports[:2]):
        color, width = _s_colors[i] if i < len(_s_colors) else ("#86efac", 1.0)
        pct = (level["price"] / current_price - 1) * 100
        label = f"S{i+1} ${level['price']:.2f} {pct:.0f}%"
        fig.add_hline(
            y=level["price"], line_dash="dash", line_color=color, line_width=width,
            row=1, col=1,
            annotation_text=f"  {label}",
            annotation_position="right" if i % 2 == 1 else "left",
            annotation_font=dict(size=9, color=color, family="Inter, sans-serif"),
        )

    # ── Current price line (green solid, label on left) ──
    fig.add_hline(
        y=current_price, line_dash="solid", line_color="#22c55e", line_width=2,
        row=1, col=1,
        annotation_text=f"Current: ${current_price:.2f}  ",
        annotation_position="left",
        annotation_font=dict(size=11, color="#fbbf24", family="Inter, sans-serif"),
    )

    # ── Max Pain line (magenta dashed) ──
    max_pain = data.get("max_pain")
    if max_pain and max_pain.get("max_pain_price"):
        fig.add_hline(
            y=max_pain["max_pain_price"], line_dash="dash",
            line_color="rgba(236,72,153,0.7)", line_width=1.5, row=1, col=1,
            annotation_text=f"  Max Pain ${max_pain['max_pain_price']:.2f}",
            annotation_position="left",
            annotation_font=dict(size=9, color="rgba(236,72,153,0.8)", family="Inter, sans-serif"),
        )

    # ── Volume Profile: VPOC line + Value Area zone ──
    vp = data.get("vol_profile")
    if vp and vp.get("vpoc_price"):
        fig.add_hline(
            y=vp["vpoc_price"], line_dash="solid",
            line_color="rgba(255,255,255,0.45)", line_width=1.5, row=1, col=1,
            annotation_text=f"  VPOC ${vp['vpoc_price']:.2f}",
            annotation_position="left",
            annotation_font=dict(size=9, color="rgba(255,255,255,0.6)", family="Inter, sans-serif"),
        )
        if vp.get("value_area_high") and vp.get("value_area_low"):
            fig.add_hrect(
                y0=vp["value_area_low"], y1=vp["value_area_high"],
                fillcolor="rgba(59,130,246,0.06)",
                line=dict(width=0), row=1, col=1,
            )

    # ── Divergence annotations (arrows at pivots) ──
    div_data = data.get("divergence")
    if div_data and div_data.get("divergences"):
        for d in div_data["divergences"]:
            bar_idx = d.get("bar_index")
            if bar_idx is not None and 0 <= bar_idx < len(df):
                row_data = df.iloc[bar_idx]
                is_bullish = "bullish" in d.get("type", "").lower()
                fig.add_annotation(
                    x=row_data["date"],
                    y=float(row_data["low"]) * 0.995 if is_bullish else float(row_data["high"]) * 1.005,
                    text="Div",
                    showarrow=True,
                    arrowhead=2, arrowsize=1.2, arrowwidth=2,
                    arrowcolor="#22c55e" if is_bullish else "#ef4444",
                    ay=30 if is_bullish else -30,
                    font=dict(size=9, color="#22c55e" if is_bullish else "#ef4444", family="Inter"),
                    row=1, col=1,
                )

    # ── Volume bars (red/green, no MA overlay) ──
    vol_colors = [
        "#22c55e" if c >= o else "#ef4444"
        for c, o in zip(df["close"], df["open"])
    ]
    fig.add_trace(go.Bar(
        x=df["date"], y=df["volume"], marker_color=vol_colors,
        marker_line_width=0, name="Volume", showlegend=False,
    ), row=2, col=1)

    # ── Layout ──
    fig.update_layout(
        title=dict(
            text=f"{symbol} — Key Resistance Levels Analysis",
            font=dict(size=16, family="Inter, sans-serif", color="#e2e8f0"),
            x=0.5, xanchor="center",
        ),
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#080c14",
        height=640, margin=dict(l=60, r=160, t=50, b=40),
        xaxis_rangeslider_visible=False,
        legend=dict(
            font=dict(size=11, family="Inter, sans-serif", color="#94a3b8"),
            bgcolor="rgba(17,24,39,0.8)", bordercolor="rgba(30,41,59,0.5)", borderwidth=1,
            x=0.01, y=0.99, yanchor="top",
        ),
        yaxis=dict(
            title=dict(text="Price ($)", font=dict(size=12, color="#94a3b8", family="Inter")),
            gridcolor="rgba(30,41,59,0.4)", side="left", zeroline=False,
            tickfont=dict(size=10, color="#94a3b8", family="SF Mono, monospace"),
            tickprefix="$",
        ),
        yaxis2=dict(
            title=dict(text="Volume (M)", font=dict(size=11, color="#94a3b8", family="Inter")),
            gridcolor="rgba(30,41,59,0.2)", side="left", zeroline=False,
            tickfont=dict(size=9, color="#64748b", family="SF Mono, monospace"),
            showgrid=False,
        ),
        xaxis=dict(
            gridcolor="rgba(30,41,59,0.3)", zeroline=False,
            tickfont=dict(size=10, color="#64748b"),
        ),
        xaxis2=dict(
            title=dict(text="Date", font=dict(size=11, color="#94a3b8", family="Inter")),
            gridcolor="rgba(30,41,59,0.3)", zeroline=False,
            tickfont=dict(size=10, color="#64748b"),
        ),
        hoverlabel=dict(
            bgcolor="#1e293b", bordercolor="#334155",
            font=dict(size=12, family="Inter, sans-serif", color="#e2e8f0"),
        ),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# UI Components
# ─────────────────────────────────────────────────────────────────────────────

def render_metric_card(label, value, detail="", color="blue"):
    st.markdown(f"""
    <div class="metric-card {color}">
        <div class="metric-label">{label}</div>
        <div class="metric-value" style="color: var(--{'accent-' + color if color != 'white' else 'text-primary'})">{value}</div>
        <div class="metric-detail">{detail}</div>
    </div>
    """, unsafe_allow_html=True)


def render_symbol_detail(data):
    """Render the full detail view for a symbol."""
    rev = data["reversal"]
    best_combo = data["best_combo"]
    tier = data["tier"]

    # ── Metric cards row 1 ──
    cols = st.columns(4)
    with cols[0]:
        st.markdown(f"""<div class="metric-card blue">
            <div class="metric-label">Price</div>
            <div class="metric-value" style="color:#e2e8f0">${data['price']:.2f}</div>
            <div class="metric-detail" style="color:{'#22c55e' if rev['ret_5d']>=0 else '#ef4444'}">
                5d: {'+' if rev['ret_5d']>=0 else ''}{rev['ret_5d']:.1f}%
            </div>
        </div>""", unsafe_allow_html=True)

    with cols[1]:
        sc = rev["reversal_score"]
        c = "green" if sc >= 60 else ("amber" if sc >= 40 else "blue")
        st.markdown(f"""<div class="metric-card {c}">
            <div class="metric-label">Reversal Score</div>
            <div class="metric-value" style="color:{'#22c55e' if sc>=60 else '#f59e0b' if sc>=40 else '#3b82f6'}">{sc}</div>
            <div class="metric-detail">{'Strong' if sc>=70 else 'Moderate' if sc>=50 else 'Early'}</div>
        </div>""", unsafe_allow_html=True)

    with cols[2]:
        mc = data.get("market_cap", 0)
        st.markdown(f"""<div class="metric-card cyan">
            <div class="metric-label">Market Cap</div>
            <div class="metric-value" style="color:#06b6d4">{format_market_cap(mc)}</div>
            <div class="metric-detail">{'Nano' if mc < 50e6 else 'Micro' if mc < 300e6 else 'Small' if mc < 2e9 else 'Mid' if mc < 10e9 else 'Large' if mc < 200e9 else 'Mega' if mc > 0 else 'Unknown'} cap</div>
        </div>""", unsafe_allow_html=True)

    with cols[3]:
        av = data.get("avg_volume", 0)
        st.markdown(f"""<div class="metric-card purple">
            <div class="metric-label">Avg Daily Volume</div>
            <div class="metric-value" style="color:#a855f7">{format_volume(av)}</div>
            <div class="metric-detail">{'Low' if av < 500_000 else 'Moderate' if av < 5_000_000 else 'High' if av < 20_000_000 else 'Very high'} liquidity</div>
        </div>""", unsafe_allow_html=True)

    # ── Metric cards row 2 ──
    cols2 = st.columns(4)
    with cols2[0]:
        st.markdown(f"""<div class="metric-card red">
            <div class="metric-label">Drawdown</div>
            <div class="metric-value" style="color:#ef4444">{rev['drawdown']:.0f}%</div>
            <div class="metric-detail" style="color:{'#22c55e' if rev['ret_20d']>=0 else '#ef4444'}">
                20d: {'+' if rev['ret_20d']>=0 else ''}{rev['ret_20d']:.1f}%
            </div>
        </div>""", unsafe_allow_html=True)

    with cols2[1]:
        rsi_c = "red" if rev["rsi"] < 30 else ("purple" if rev["rsi"] < 50 else "blue")
        st.markdown(f"""<div class="metric-card {rsi_c}">
            <div class="metric-label">RSI</div>
            <div class="metric-value" style="color:{'#ef4444' if rev['rsi']<30 else '#a855f7' if rev['rsi']<50 else '#3b82f6'}">{rev['rsi']:.1f}</div>
            <div class="metric-detail">{'Oversold' if rev['rsi']<30 else 'Setup zone' if rev['rsi']<50 else 'Neutral'}</div>
        </div>""", unsafe_allow_html=True)

    with cols2[2]:
        st.markdown(f"""<div class="metric-card amber">
            <div class="metric-label">Volume Ratio</div>
            <div class="metric-value" style="color:#f59e0b">{rev['vol_ratio']:.1f}x</div>
            <div class="metric-detail">Vol Z: {rev['vol_zscore']:.2f}</div>
        </div>""", unsafe_allow_html=True)

    with cols2[3]:
        combo_text = f"{best_combo['name']}" if best_combo else "None"
        combo_color = "#22c55e" if best_combo else "#64748b"
        combo_detail = f"{len(data['combos'])} combo(s) | Kelly {data['kelly']:.1f}%" if best_combo else "No match"
        st.markdown(f"""<div class="metric-card {'green' if best_combo else 'blue'}">
            <div class="metric-label">Best Combo</div>
            <div class="metric-value" style="font-size:14px;color:{combo_color}">{combo_text}</div>
            <div class="metric-detail">{combo_detail}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # ── Chart ──
    fig = build_price_chart(data, days=chart_days)
    st.markdown('<div class="chart-container">', unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True, config={
        "displayModeBar": True,
        "modeBarButtonsToRemove": ["lasso2d", "select2d"],
        "displaylogo": False,
    })
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Signals and Levels ──
    col_signals, col_levels = st.columns([1, 1])

    with col_signals:
        st.markdown("##### Active Signals")
        tags_html = ""
        for reason in rev["reasons"]:
            r_lower = reason.lower()
            cls = "green" if ("bounce" in r_lower or "reversal" in r_lower) else (
                "red" if ("drawdown" in r_lower or "oversold" in r_lower) else (
                "amber" if "vol" in r_lower else "blue"
            ))
            tags_html += f'<span class="signal-tag {cls}">{reason}</span>'
        st.markdown(tags_html, unsafe_allow_html=True)

        if data["combos"]:
            st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
            st.markdown("##### Matched Combos")
            for combo in sorted(data["combos"], key=lambda c: c["hit_rate"], reverse=True):
                st.markdown(f"""
                <div style="display:flex;align-items:center;gap:10px;margin:4px 0">
                    <span class="combo-badge">{combo['name']}</span>
                    <span style="color:#94a3b8;font-size:13px">{combo['hit_rate']*100:.1f}% hit rate</span>
                </div>""", unsafe_allow_html=True)

        # Tier
        if tier.get("tier"):
            st.markdown(f"""<div style='margin-top:16px'>
                <span style="color:#64748b;font-size:10px;text-transform:uppercase;letter-spacing:1px">Tier Classification</span><br>
                <span style="font-size:20px;font-weight:800;color:#a855f7">Tier {tier['tier']}</span>
                <span style="color:#94a3b8;font-size:13px;margin-left:8px">
                    {tier['hit_rate']*100:.1f}% hit rate | {tier['avg_gain']*100:.0f}% avg gain | {tier['conviction']}
                </span>
            </div>""", unsafe_allow_html=True)

    with col_levels:
        current_price = data["price"]
        resistances = [l for l in data["levels"] if l["price"] > current_price]
        supports = [l for l in data["levels"] if l["price"] <= current_price]
        resistances.sort(key=lambda l: l["price"])
        supports.sort(key=lambda l: l["price"], reverse=True)

        st.markdown("##### Resistance Levels")
        if resistances:
            for l in resistances[:5]:
                pct = (l["price"] / current_price - 1) * 100
                cls = "level-ma" if l["type"].startswith("MA") else "level-resistance"
                label = l["type"] if l["type"].startswith("MA") else f"R ({l['touches']} touches)"
                st.markdown(f"""<div class="{cls}">
                    <span style="color:#94a3b8;font-size:12px">{label}</span>
                    <span style="font-weight:700;color:#ef4444;font-family:monospace">${l['price']:.2f}</span>
                    <span style="color:#64748b;font-size:11px">+{pct:.1f}%</span>
                </div>""", unsafe_allow_html=True)
        else:
            st.markdown('<span style="color:#64748b;font-size:12px">None nearby</span>', unsafe_allow_html=True)

        st.markdown("##### Support Levels")
        if supports:
            for l in supports[:5]:
                pct = (l["price"] / current_price - 1) * 100
                cls = "level-ma" if l["type"].startswith("MA") else "level-support"
                label = l["type"] if l["type"].startswith("MA") else f"S ({l['touches']} touches)"
                st.markdown(f"""<div class="{cls}">
                    <span style="color:#94a3b8;font-size:12px">{label}</span>
                    <span style="font-weight:700;color:#22c55e;font-family:monospace">${l['price']:.2f}</span>
                    <span style="color:#64748b;font-size:11px">{pct:.1f}%</span>
                </div>""", unsafe_allow_html=True)
        else:
            st.markdown('<span style="color:#64748b;font-size:12px">None nearby</span>', unsafe_allow_html=True)

        # Unfilled gaps
        gaps = data.get("gaps", [])
        if gaps:
            st.markdown("##### Unfilled Gaps")
            for g in gaps[:4]:
                is_sup = "support" in g["type"]
                cls = "level-support" if is_sup else "level-resistance"
                color = "#22c55e" if is_sup else "#ef4444"
                st.markdown(f"""<div class="{cls}">
                    <span style="color:#94a3b8;font-size:12px">Gap {g['gap_pct']}% ({g['date']})</span>
                    <span style="font-weight:700;color:{color};font-family:monospace">${g['bottom']:.2f}–${g['top']:.2f}</span>
                </div>""", unsafe_allow_html=True)

    # ── Intelligence Section ──
    intel = {}
    weekly = data.get("weekly", {})
    rs = data.get("rel_strength")
    insider = data.get("insider")
    options = data.get("options")
    earnings = data.get("earnings")

    has_intel = rs or insider or options or earnings
    if has_intel or weekly:
        st.markdown("---")
        st.markdown("""<div style="margin-bottom:12px">
            <span style="font-size:16px;font-weight:700;color:#e2e8f0;font-family:'Inter',sans-serif">
            Intelligence</span>
            <span style="color:#64748b;font-size:12px;margin-left:8px">Free data enhanced signals</span>
        </div>""", unsafe_allow_html=True)

        intel_cols = st.columns(4)

        # Weekly confluence
        with intel_cols[0]:
            cs = weekly.get("confluence_score", 0)
            cs_color = "#22c55e" if cs >= 2 else ("#f59e0b" if cs == 1 else "#ef4444")
            w_rsi = weekly.get("weekly_rsi", 0)
            w_macd = "Bull" if weekly.get("weekly_macd_bullish") else "Bear"
            w_trend = weekly.get("weekly_trend", "?")
            st.markdown(f"""<div class="metric-card {'green' if cs>=2 else 'amber' if cs==1 else 'red'}">
                <div class="metric-label">Weekly Confluence</div>
                <div class="metric-value" style="color:{cs_color}">{cs}/3</div>
                <div class="metric-detail">wRSI {w_rsi:.0f} | MACD {w_macd} | {w_trend}</div>
            </div>""", unsafe_allow_html=True)

        # Relative strength
        with intel_cols[1]:
            if rs:
                spy_rs = rs.get("rs_vs_spy_20d", 0)
                sec_rs = rs.get("rs_vs_sector_20d", 0)
                rank = rs.get("rs_rank", "?")
                rank_color = "#22c55e" if rank == "Strong" else ("#ef4444" if rank == "Weak" else "#f59e0b")
                st.markdown(f"""<div class="metric-card {'green' if rank=='Strong' else 'red' if rank=='Weak' else 'amber'}">
                    <div class="metric-label">Relative Strength</div>
                    <div class="metric-value" style="font-size:18px;color:{rank_color}">{rank}</div>
                    <div class="metric-detail">vs SPY {spy_rs:+.1f}% | vs Sector {sec_rs:+.1f}%</div>
                </div>""", unsafe_allow_html=True)
            else:
                st.markdown("""<div class="metric-card blue">
                    <div class="metric-label">Relative Strength</div>
                    <div class="metric-value" style="color:#64748b;font-size:14px">Scan for detail</div>
                </div>""", unsafe_allow_html=True)

        # Insider activity (EDGAR-enhanced when available)
        with intel_cols[2]:
            edgar = data.get("edgar_insider")
            if edgar and (edgar.get("insider_buys_90d", 0) > 0 or edgar.get("insider_sells_90d", 0) > 0):
                sentiment = edgar.get("insider_sentiment", "Neutral")
                net = edgar.get("insider_net_90d", 0)
                buys = edgar.get("insider_buys_90d", 0)
                sells = edgar.get("insider_sells_90d", 0)
                source = edgar.get("data_source", "EDGAR")
                if "Buy" in sentiment:
                    ins_color, card_c = "#22c55e", "green"
                elif sentiment == "Sell":
                    ins_color, card_c = "#ef4444", "red"
                else:
                    ins_color, card_c = "#f59e0b", "amber"
                st.markdown(f"""<div class="metric-card {card_c}">
                    <div class="metric-label">Insider ({source})</div>
                    <div class="metric-value" style="font-size:16px;color:{ins_color}">{sentiment}</div>
                    <div class="metric-detail">{buys} buys / {sells} sells | Net {net:+d}</div>
                </div>""", unsafe_allow_html=True)
            elif insider:
                net = insider.get("insider_net", 0)
                buys = insider.get("insider_buys", 0)
                sells = insider.get("insider_sells", 0)
                if net > 0:
                    ins_color, ins_label, card_c = "#22c55e", f"+{net} Net Buys", "green"
                elif net < 0:
                    ins_color, ins_label, card_c = "#ef4444", f"{net} Net", "red"
                else:
                    ins_color, ins_label, card_c = "#64748b", "No Activity", "blue"
                st.markdown(f"""<div class="metric-card {card_c}">
                    <div class="metric-label">Insider Activity</div>
                    <div class="metric-value" style="font-size:16px;color:{ins_color}">{ins_label}</div>
                    <div class="metric-detail">{buys} buys / {sells} sells</div>
                </div>""", unsafe_allow_html=True)
            else:
                st.markdown("""<div class="metric-card blue">
                    <div class="metric-label">Insider Activity</div>
                    <div class="metric-value" style="color:#64748b;font-size:14px">Scan for detail</div>
                </div>""", unsafe_allow_html=True)

        # Earnings proximity
        with intel_cols[3]:
            if earnings:
                days = earnings.get("days_to_earnings")
                edate = earnings.get("earnings_date", "")
                warning = earnings.get("earnings_warning", False)
                if days is not None:
                    e_color = "#ef4444" if warning else ("#f59e0b" if days and days <= 30 else "#64748b")
                    card_c = "red" if warning else ("amber" if days and days <= 30 else "blue")
                    st.markdown(f"""<div class="metric-card {card_c}">
                        <div class="metric-label">Next Earnings</div>
                        <div class="metric-value" style="font-size:18px;color:{e_color}">{days}d</div>
                        <div class="metric-detail">{edate}{'  ⚠ SOON' if warning else ''}</div>
                    </div>""", unsafe_allow_html=True)
                else:
                    st.markdown("""<div class="metric-card blue">
                        <div class="metric-label">Next Earnings</div>
                        <div class="metric-value" style="color:#64748b;font-size:14px">Unknown</div>
                    </div>""", unsafe_allow_html=True)
            else:
                st.markdown("""<div class="metric-card blue">
                    <div class="metric-label">Next Earnings</div>
                    <div class="metric-value" style="color:#64748b;font-size:14px">Scan for detail</div>
                </div>""", unsafe_allow_html=True)

        # Options flow (second row)
        if options and options.get("options_signal") != "N/A":
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            opt_cols = st.columns(4)
            with opt_cols[0]:
                pc = options.get("put_call_ratio", 0)
                sig = options.get("options_signal", "N/A")
                sig_color = "#22c55e" if sig == "Bullish" else ("#ef4444" if sig == "Bearish" else "#f59e0b")
                st.markdown(f"""<div class="metric-card {'green' if sig=='Bullish' else 'red' if sig=='Bearish' else 'amber'}">
                    <div class="metric-label">Options Flow</div>
                    <div class="metric-value" style="font-size:18px;color:{sig_color}">{sig}</div>
                    <div class="metric-detail">P/C Ratio: {pc:.2f}</div>
                </div>""", unsafe_allow_html=True)
            with opt_cols[1]:
                unusual = options.get("unusual_call_volume", False)
                st.markdown(f"""<div class="metric-card {'green' if unusual else 'blue'}">
                    <div class="metric-label">Unusual Calls</div>
                    <div class="metric-value" style="font-size:18px;color:{'#22c55e' if unusual else '#64748b'}">{'YES' if unusual else 'No'}</div>
                    <div class="metric-detail">Vol {'>' if unusual else '<'} 3x Open Interest</div>
                </div>""", unsafe_allow_html=True)
            with opt_cols[2]:
                strike = options.get("max_call_oi_strike")
                st.markdown(f"""<div class="metric-card purple">
                    <div class="metric-label">Max Call OI Strike</div>
                    <div class="metric-value" style="font-size:18px;color:#a855f7">{"$" + f"{strike:.2f}" if strike else "N/A"}</div>
                    <div class="metric-detail">Institutional target price</div>
                </div>""", unsafe_allow_html=True)
            with opt_cols[3]:
                c_oi = options.get("total_call_oi", 0)
                p_oi = options.get("total_put_oi", 0)
                st.markdown(f"""<div class="metric-card cyan">
                    <div class="metric-label">Open Interest</div>
                    <div class="metric-value" style="font-size:14px;color:#06b6d4">{c_oi:,} calls / {p_oi:,} puts</div>
                    <div class="metric-detail">Nearest expiration</div>
                </div>""", unsafe_allow_html=True)

        # ── Advanced Intelligence: Short Interest, Dark Pool, Analogs, Fib ──
        render_advanced_intel(data)

        # ── New features: Max Pain, Divergence, Volume Profile, MTF, EDGAR ──
        render_new_features(data)


def render_new_features(data):
    """Render new feature cards: Max Pain/GEX, Divergence, Volume Profile, Multi-TF Score, EDGAR insider."""
    max_pain = data.get("max_pain")
    div_data = data.get("divergence")
    vp = data.get("vol_profile")
    mtf = data.get("mtf")
    edgar = data.get("edgar_insider")

    has_any = max_pain or div_data or vp or mtf or edgar
    if not has_any:
        return

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # Row of 4 metric cards
    nf_cols = st.columns(4)

    # Max Pain / GEX
    with nf_cols[0]:
        if max_pain and max_pain.get("max_pain_price"):
            mp = max_pain["max_pain_price"]
            dist = max_pain.get("max_pain_distance_pct", 0)
            gex_sig = max_pain.get("gex_signal", "N/A")
            gex_color = "#22c55e" if gex_sig == "Mean-Reverting" else ("#ef4444" if gex_sig == "Trending" else "#64748b")
            card_c = "green" if gex_sig == "Mean-Reverting" else ("red" if gex_sig == "Trending" else "blue")
            st.markdown(f"""<div class="metric-card {card_c}">
                <div class="metric-label">Max Pain / GEX</div>
                <div class="metric-value" style="font-size:16px;color:{gex_color}">${mp:.2f}</div>
                <div class="metric-detail">{dist:+.1f}% away | GEX: {gex_sig}</div>
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown("""<div class="metric-card blue">
                <div class="metric-label">Max Pain / GEX</div>
                <div class="metric-value" style="color:#64748b;font-size:14px">N/A</div>
            </div>""", unsafe_allow_html=True)

    # Divergence
    with nf_cols[1]:
        if div_data:
            dtype = div_data.get("divergence_type", "None")
            strength = div_data.get("divergence_strength", 0)
            bars = div_data.get("divergence_bars_ago")
            has_bull = div_data.get("has_bullish_div", False)
            has_bear = div_data.get("has_bearish_div", False)
            if has_bull:
                d_color, card_c = "#22c55e", "green"
            elif has_bear:
                d_color, card_c = "#ef4444", "red"
            else:
                d_color, card_c = "#64748b", "blue"
            bars_text = f" | {bars} bars ago" if bars else ""
            st.markdown(f"""<div class="metric-card {card_c}">
                <div class="metric-label">Divergence</div>
                <div class="metric-value" style="font-size:14px;color:{d_color}">{dtype}</div>
                <div class="metric-detail">Strength: {strength}/3{bars_text}</div>
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown("""<div class="metric-card blue">
                <div class="metric-label">Divergence</div>
                <div class="metric-value" style="color:#64748b;font-size:14px">None</div>
            </div>""", unsafe_allow_html=True)

    # Volume Profile
    with nf_cols[2]:
        if vp and vp.get("vpoc_price"):
            vpoc = vp["vpoc_price"]
            pos = vp.get("price_vs_value_area", "unknown")
            dist = vp.get("vpoc_distance_pct", 0)
            pos_color = "#22c55e" if pos == "below" else ("#ef4444" if pos == "above" else "#3b82f6")
            card_c = "green" if pos == "below" else ("red" if pos == "above" else "blue")
            st.markdown(f"""<div class="metric-card {card_c}">
                <div class="metric-label">Volume Profile</div>
                <div class="metric-value" style="font-size:16px;color:{pos_color}">VPOC ${vpoc:.2f}</div>
                <div class="metric-detail">{dist:+.1f}% | Price {pos} value area</div>
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown("""<div class="metric-card blue">
                <div class="metric-label">Volume Profile</div>
                <div class="metric-value" style="color:#64748b;font-size:14px">N/A</div>
            </div>""", unsafe_allow_html=True)

    # Multi-TF Score
    with nf_cols[3]:
        if mtf:
            score = mtf.get("mtf_score", 50)
            signal = mtf.get("mtf_signal", "Neutral")
            alignment = mtf.get("tf_alignment", 0)
            sig_color = "#22c55e" if "Bull" in signal else ("#ef4444" if "Bear" in signal else "#f59e0b")
            card_c = "green" if "Bull" in signal else ("red" if "Bear" in signal else "amber")
            st.markdown(f"""<div class="metric-card {card_c}">
                <div class="metric-label">Multi-TF Score</div>
                <div class="metric-value" style="font-size:18px;color:{sig_color}">{score:.0f}</div>
                <div class="metric-detail">{signal} | {alignment}/3 aligned</div>
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown("""<div class="metric-card blue">
                <div class="metric-label">Multi-TF Score</div>
                <div class="metric-value" style="color:#64748b;font-size:14px">N/A</div>
            </div>""", unsafe_allow_html=True)

    # EDGAR Insider expander
    if edgar and (edgar.get("insider_buys_90d", 0) > 0 or edgar.get("insider_sells_90d", 0) > 0):
        sentiment = edgar.get("insider_sentiment", "Neutral")
        score = edgar.get("insider_score", 0)
        cluster = edgar.get("cluster_buying", False)
        source = edgar.get("data_source", "EDGAR")
        with st.expander(f"EDGAR Insider Transactions — {sentiment} (score: {score}, source: {source})", expanded=False):
            ecols = st.columns(4)
            with ecols[0]:
                st.markdown(f"""<div class="metric-card green" style="padding:10px 14px">
                    <div class="metric-label">Buys (90d)</div>
                    <div class="metric-value" style="font-size:20px;color:#22c55e">{edgar.get('insider_buys_90d', 0)}</div>
                </div>""", unsafe_allow_html=True)
            with ecols[1]:
                st.markdown(f"""<div class="metric-card red" style="padding:10px 14px">
                    <div class="metric-label">Sells (90d)</div>
                    <div class="metric-value" style="font-size:20px;color:#ef4444">{edgar.get('insider_sells_90d', 0)}</div>
                </div>""", unsafe_allow_html=True)
            with ecols[2]:
                net = edgar.get("insider_net_90d", 0)
                net_color = "#22c55e" if net > 0 else ("#ef4444" if net < 0 else "#64748b")
                st.markdown(f"""<div class="metric-card {'green' if net>0 else 'red' if net<0 else 'blue'}" style="padding:10px 14px">
                    <div class="metric-label">Net</div>
                    <div class="metric-value" style="font-size:20px;color:{net_color}">{net:+d}</div>
                </div>""", unsafe_allow_html=True)
            with ecols[3]:
                st.markdown(f"""<div class="metric-card {'green' if cluster else 'blue'}" style="padding:10px 14px">
                    <div class="metric-label">Cluster Buying</div>
                    <div class="metric-value" style="font-size:18px;color:{'#22c55e' if cluster else '#64748b'}">{'YES' if cluster else 'No'}</div>
                </div>""", unsafe_allow_html=True)

            filings = edgar.get("recent_filings", [])
            if filings:
                filing_rows = []
                for f in filings[:10]:
                    filing_rows.append({
                        "Date": f.get("filing_date", ""),
                        "Title": f.get("title", "")[:80],
                        "Link": f.get("link", ""),
                    })
                st.dataframe(pd.DataFrame(filing_rows), use_container_width=True, hide_index=True)

    # Volume profile detail expander
    if vp and vp.get("volume_profile"):
        with st.expander("Volume Profile Detail", expanded=False):
            vp_rows = []
            for level in vp["volume_profile"]:
                vp_rows.append({
                    "Price": f"${level['price_level']:.2f}",
                    "Volume": f"{level['volume']:,.0f}",
                })
            if vp_rows:
                st.dataframe(pd.DataFrame(vp_rows), use_container_width=True, hide_index=True)

    # MTF detail expander
    if mtf and mtf.get("daily_detail"):
        with st.expander("Multi-Timeframe Detail", expanded=False):
            mtf_rows = []
            for tf_name, detail_key in [("Daily", "daily_detail"), ("Weekly", "weekly_detail"), ("Monthly", "monthly_detail")]:
                d = mtf.get(detail_key, {})
                if d:
                    mtf_rows.append({
                        "Timeframe": tf_name,
                        "Bias": d.get("bias", "?").title(),
                        "RSI": f"{d.get('rsi', 0):.1f}",
                        "MACD Bull": "Yes" if d.get("macd_bullish") else "No",
                        "Above MA20": "Yes" if d.get("above_ma20") else "No",
                        "Higher Lows": "Yes" if d.get("higher_lows") else "No",
                        "Score": f"{d.get('score', 0)}/4",
                    })
            if mtf_rows:
                st.dataframe(pd.DataFrame(mtf_rows), use_container_width=True, hide_index=True)


def render_advanced_intel(data):
    """Render advanced intelligence: short interest, dark pool, analogs, fibonacci."""
    short_info = data.get("short_info")
    dark_pool = data.get("dark_pool")
    analogs = data.get("analogs")
    fib = data.get("fibonacci")

    has_any = short_info or dark_pool or analogs or fib
    if not has_any:
        return

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # Row: Short interest + Dark pool + Analog summary
    adv_cols = st.columns(4)

    with adv_cols[0]:
        if short_info:
            sig = short_info.get("short_signal", "Low")
            pct = short_info.get("short_pct_float", 0)
            ratio = short_info.get("short_ratio", 0)
            squeeze = short_info.get("squeeze_potential", False)
            sig_color = "#ef4444" if sig == "Squeeze Risk" else ("#f59e0b" if sig in ("High Short", "Moderate") else "#64748b")
            card_c = "red" if sig == "Squeeze Risk" else ("amber" if sig in ("High Short", "Moderate") else "blue")
            st.markdown(f"""<div class="metric-card {card_c}">
                <div class="metric-label">Short Interest</div>
                <div class="metric-value" style="font-size:16px;color:{sig_color}">{sig}</div>
                <div class="metric-detail">{pct:.1f}% float | {ratio:.1f} days to cover</div>
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown("""<div class="metric-card blue">
                <div class="metric-label">Short Interest</div>
                <div class="metric-value" style="color:#64748b;font-size:14px">N/A</div>
            </div>""", unsafe_allow_html=True)

    with adv_cols[1]:
        if dark_pool:
            dp_sig = dark_pool.get("dark_pool_signal", "Neutral")
            acc = dark_pool.get("accumulation_days", 0)
            dist = dark_pool.get("distribution_days", 0)
            obv = dark_pool.get("obv_trend", "confirming")
            dp_color = "#22c55e" if "Accumulation" in dp_sig else ("#ef4444" if dp_sig == "Distribution" else "#64748b")
            card_c = "green" if "Accumulation" in dp_sig else ("red" if dp_sig == "Distribution" else "blue")
            st.markdown(f"""<div class="metric-card {card_c}">
                <div class="metric-label">Dark Pool Proxy</div>
                <div class="metric-value" style="font-size:14px;color:{dp_color}">{dp_sig}</div>
                <div class="metric-detail">{acc} acc / {dist} dist days | OBV: {obv}</div>
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown("""<div class="metric-card blue">
                <div class="metric-label">Dark Pool Proxy</div>
                <div class="metric-value" style="color:#64748b;font-size:14px">N/A</div>
            </div>""", unsafe_allow_html=True)

    with adv_cols[2]:
        if analogs and analogs.get("stats", {}).get("count", 0) > 0:
            stats = analogs["stats"]
            cnt = stats["count"]
            wr20 = stats.get("win_rate_20d", 0)
            med20 = stats.get("median_20d", 0)
            wr_color = "#22c55e" if wr20 >= 20 else ("#f59e0b" if wr20 >= 10 else "#64748b")
            card_c = "green" if wr20 >= 20 else ("amber" if wr20 >= 10 else "blue")
            st.markdown(f"""<div class="metric-card {card_c}">
                <div class="metric-label">Historical Analogs</div>
                <div class="metric-value" style="font-size:16px;color:{wr_color}">{wr20:.0f}% win</div>
                <div class="metric-detail">{cnt} matches | Med 20d: {med20:+.1f}%</div>
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown("""<div class="metric-card blue">
                <div class="metric-label">Historical Analogs</div>
                <div class="metric-value" style="color:#64748b;font-size:14px">Insufficient data</div>
            </div>""", unsafe_allow_html=True)

    with adv_cols[3]:
        if fib and fib.get("levels"):
            trend = fib.get("trend", "?")
            # Find closest fib level to current price
            price = data.get("price", 0)
            closest = min(fib["levels"], key=lambda l: abs(l["price"] - price))
            trend_color = "#22c55e" if trend == "up" else "#ef4444"
            st.markdown(f"""<div class="metric-card {'green' if trend=='up' else 'red'}">
                <div class="metric-label">Fibonacci</div>
                <div class="metric-value" style="font-size:16px;color:{trend_color}">{'Uptrend' if trend=='up' else 'Downtrend'}</div>
                <div class="metric-detail">Near {closest['level']} (${closest['price']:.2f})</div>
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown("""<div class="metric-card blue">
                <div class="metric-label">Fibonacci</div>
                <div class="metric-value" style="color:#64748b;font-size:14px">N/A</div>
            </div>""", unsafe_allow_html=True)

    # Analogs detail expander
    if analogs and analogs.get("stats", {}).get("count", 0) > 0:
        with st.expander(f"Historical Analog Detail — {analogs['summary']}", expanded=False):
            stats = analogs["stats"]
            st.markdown(f"""
            <div style="display:flex;gap:16px;margin-bottom:12px;flex-wrap:wrap">
                <div class="metric-card blue" style="flex:1;min-width:100px">
                    <div class="metric-label">Matches</div>
                    <div class="metric-value" style="font-size:20px;color:#3b82f6">{stats['count']}</div>
                </div>
                <div class="metric-card green" style="flex:1;min-width:100px">
                    <div class="metric-label">Win 10d</div>
                    <div class="metric-value" style="font-size:20px;color:#22c55e">{stats['win_rate_10d']:.0f}%</div>
                </div>
                <div class="metric-card green" style="flex:1;min-width:100px">
                    <div class="metric-label">Win 20d</div>
                    <div class="metric-value" style="font-size:20px;color:#22c55e">{stats['win_rate_20d']:.0f}%</div>
                </div>
                <div class="metric-card amber" style="flex:1;min-width:100px">
                    <div class="metric-label">Best 20d</div>
                    <div class="metric-value" style="font-size:20px;color:#f59e0b">{stats['best_20d']:+.1f}%</div>
                </div>
                <div class="metric-card red" style="flex:1;min-width:100px">
                    <div class="metric-label">Worst 20d</div>
                    <div class="metric-value" style="font-size:20px;color:#ef4444">{stats['worst_20d']:+.1f}%</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Top 5 most similar matches
            top_matches = analogs.get("matches", [])[:5]
            if top_matches:
                st.markdown("**Top 5 Most Similar Setups:**")
                match_rows = []
                for m in top_matches:
                    match_rows.append({
                        "Date": m["date"],
                        "Similarity": f"{m['similarity']:.1%}",
                        "5d Fwd": f"{m['fwd_5d']:+.1f}%",
                        "10d Fwd": f"{m['fwd_10d']:+.1f}%",
                        "20d Fwd": f"{m['fwd_20d']:+.1f}%",
                    })
                st.dataframe(pd.DataFrame(match_rows), use_container_width=True, hide_index=True)

    # Fibonacci levels detail
    if fib and fib.get("levels"):
        with st.expander(f"Fibonacci Levels — Swing {fib['swing_high_date']} to {fib['swing_low_date']}", expanded=False):
            fib_rows = []
            for lvl in fib["levels"]:
                fib_rows.append({
                    "Level": lvl["level"],
                    "Price": f"${lvl['price']:.2f}",
                    "vs Current": f"{(lvl['price'] / data.get('price', 1) - 1) * 100:+.1f}%",
                })
            st.dataframe(pd.DataFrame(fib_rows), use_container_width=True, hide_index=True)


def render_scan_results_table(results):
    """Render the scan results as a sortable table."""
    if not results:
        st.info("No results. Run a scan to get started.")
        return None

    rows = []
    for r in results:
        rev = r["reversal"]
        wk = r.get("weekly", {})
        rows.append({
            "Symbol": r["symbol"],
            "Price": r["price"],
            "Mkt Cap": format_market_cap(r.get("market_cap", 0)),
            "Rev Score": rev["reversal_score"],
            "Wk Conf": f"{wk.get('confluence_score', 0)}/3",
            "RSI": round(rev["rsi"], 1),
            "DD%": round(rev["drawdown"], 0),
            "5d%": round(rev["ret_5d"], 1),
            "20d%": round(rev["ret_20d"], 1),
            "VolR": round(rev["vol_ratio"], 1),
            "Combos": len(r["combos"]),
            "Best Combo": r["best_combo"]["name"] if r["best_combo"] else "—",
            "Hit Rate": f"{r['best_combo']['hit_rate']*100:.1f}%" if r["best_combo"] else "—",
            "Gaps": len(r.get("gaps", [])),
            "Div": r.get("divergence", {}).get("divergence_type", "None"),
            "VPOC": r.get("vol_profile", {}).get("price_vs_value_area", "—"),
            "MTF": round(r.get("mtf", {}).get("mtf_score", 0)),
            "Signals": ", ".join(rev["reasons"][:3]),
        })

    df = pd.DataFrame(rows)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown('<div class="main-title">ALPHA PREDATOR</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Trading Intelligence Dashboard</div>', unsafe_allow_html=True)

    st.markdown("---")

    # Search
    search_input = st.text_input(
        "🔍 Symbol Search",
        placeholder="SOFI, RIOT, IONQ...",
        help="Enter one or more ticker symbols separated by commas",
    )
    search_btn = st.button("Analyze", type="primary", use_container_width=True)

    st.markdown("---")

    # Scan mode
    scan_mode = st.radio(
        "🎯 Scan Mode",
        ["All Signals", "Bottomed Reversals"],
        index=0,
        help="**All Signals**: Show all scanned symbols sorted by combo matches.\n\n"
             "**Bottomed Reversals**: Dynamically filter to stocks that have drawn down hard "
             "and are now reversing with volume confirmation. Sorted by reversal strength.",
    )

    # Universe scanner
    preset_keys = list(PRESETS.keys())
    preset_name = st.selectbox("🌐 Universe", preset_keys, index=preset_keys.index("Full Market (All US Stocks)"))

    # ── Filters (above the scan button so they take effect) ──
    with st.expander("📏 Filters", expanded=False):
        mcap_options = {
            "No filter": (0, 0),
            "Nano (<$50M)": (0, 50_000_000),
            "Micro ($50M–$300M)": (50_000_000, 300_000_000),
            "Small ($300M–$2B)": (300_000_000, 2_000_000_000),
            "$100M–$100B": (100_000_000, 100_000_000_000),
            "$200M–$250B": (200_000_000, 250_000_000_000),
            "Custom range": None,
        }
        mcap_choice = st.selectbox("Market cap", list(mcap_options.keys()), index=0)

        if mcap_choice == "Custom range":
            mcap_col1, mcap_col2 = st.columns(2)
            with mcap_col1:
                min_mcap_m = st.number_input("Min ($M)", min_value=0, value=50, step=50)
            with mcap_col2:
                max_mcap_m = st.number_input("Max ($M)", min_value=0, value=10000, step=500)
            min_mcap = int(min_mcap_m * 1_000_000)
            max_mcap = int(max_mcap_m * 1_000_000) if max_mcap_m > 0 else 0
        elif mcap_options[mcap_choice] is not None:
            min_mcap, max_mcap = mcap_options[mcap_choice]
        else:
            min_mcap, max_mcap = 0, 0

        vol_options = {
            "No filter": 0,
            ">100K": 100_000,
            ">500K": 500_000,
            ">1M": 1_000_000,
            ">5M": 5_000_000,
            ">10M": 10_000_000,
        }
        vol_choice = st.selectbox("Min avg daily volume", list(vol_options.keys()), index=0)
        min_avg_vol = vol_options[vol_choice]

        min_rev_score = st.slider("Min reversal score", 0, 80, 20)

    # ── Settings ──
    with st.expander("⚙️ Settings", expanded=False):
        chart_days = st.slider("Chart days", 30, 252, 120)
        period = st.selectbox("Data period", ["6mo", "1y", "2y"], index=1)

    scan_btn = st.button(
        "🔥 Find Reversals" if scan_mode == "Bottomed Reversals" else "Scan Universe",
        type="primary" if scan_mode == "Bottomed Reversals" else "secondary",
        use_container_width=True,
    )

    st.markdown("---")
    st.markdown(
        '<div style="color:#64748b;font-size:11px;text-align:center">'
        'Educational research tool only.<br>Not financial advice.</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main content
# ─────────────────────────────────────────────────────────────────────────────

# Initialize session state
if "scan_results" not in st.session_state:
    st.session_state.scan_results = []
if "selected_symbol" not in st.session_state:
    st.session_state.selected_symbol = None
if "search_data" not in st.session_state:
    st.session_state.search_data = None
if "scan_mode" not in st.session_state:
    st.session_state.scan_mode = "All Signals"
if "scan_performed" not in st.session_state:
    st.session_state.scan_performed = False

# Handle search
if search_btn and search_input.strip():
    symbols = [s.strip().upper() for s in search_input.split(",") if s.strip()]
    if len(symbols) == 1:
        with st.spinner(f"Analyzing {symbols[0]}..."):
            result = analyze_symbol(symbols[0], period)
            if result:
                st.session_state.search_data = result
                st.session_state.selected_symbol = symbols[0]
            else:
                st.error(f"Could not fetch data for {symbols[0]}. Check the ticker symbol.")
    else:
        with st.spinner(f"Downloading prices for {len(symbols)} symbols..."):
            df_all = fetch_batch(symbols, period)
        filtered = filter_by_volume(df_all, symbols, min_avg_vol)
        st.toast(f"Analyzing {len(filtered)} symbols" + (f" ({len(symbols) - len(filtered)} excluded by vol filter)" if min_avg_vol > 0 else ""))
        with st.spinner(f"Analyzing {len(filtered)} symbols..."):
            results = analyze_batch(filtered, df_all, min_mcap=min_mcap, max_mcap=max_mcap)
            if scan_mode == "Bottomed Reversals":
                results = filter_bottomed_reversals(results)
            st.session_state.scan_results = results
            st.session_state.scan_mode = scan_mode
            st.session_state.search_data = None
            st.session_state.scan_performed = True

# Handle preset scan
if scan_btn:
    if preset_name == "Full Market (All US Stocks)":
        symbols = fetch_full_market(min_mcap=min_mcap, max_mcap=max_mcap)
    else:
        symbols = PRESETS[preset_name]

    with st.spinner(f"Downloading prices for {len(symbols)} stocks..."):
        df_all = fetch_batch(symbols, period)

    # Volume filter — runs BEFORE analysis so the count is accurate
    filtered = filter_by_volume(df_all, symbols, min_avg_vol)
    if min_avg_vol > 0:
        st.toast(f"Volume filter: {len(symbols)} → {len(filtered)} stocks (≥{format_volume(min_avg_vol)} avg daily)")

    action = "Hunting reversals" if scan_mode == "Bottomed Reversals" else "Analyzing"
    with st.spinner(f"{action} across {len(filtered)} stocks..."):
        results = analyze_batch(filtered, df_all, min_mcap=0, max_mcap=0)
        if scan_mode == "Bottomed Reversals":
            results = filter_bottomed_reversals(results)
        st.session_state.scan_results = results
        st.session_state.scan_mode = scan_mode
        st.session_state.search_data = None
        st.session_state.scan_performed = True

# ── Render content ──

# If we have a single symbol search result
if st.session_state.search_data:
    data = st.session_state.search_data
    st.markdown(f"""
    <div style="display:flex;align-items:baseline;gap:16px;margin-bottom:20px">
        <span style="font-size:32px;font-weight:800;color:#e2e8f0;font-family:'Inter',sans-serif">{data['symbol']}</span>
        <span style="font-size:24px;color:#94a3b8;font-family:'SF Mono',monospace">${data['price']:.2f}</span>
    </div>
    """, unsafe_allow_html=True)
    render_symbol_detail(data)

# If we have scan results
elif st.session_state.scan_results:
    total_before_filters = len(st.session_state.scan_results)
    results = st.session_state.scan_results

    # ── Live post-filters (applied on every rerun so changing dropdowns works) ──
    # Volume and reversal score can always be post-filtered (data is in the results).
    # Market cap post-filter only works if market_cap was fetched — for Full Market scans
    # it's already filtered at the NASDAQ API level and not stored per-result.
    if min_avg_vol > 0:
        results = [r for r in results if r.get("avg_volume", 0) >= min_avg_vol]
    if min_rev_score > 0:
        results = [r for r in results if r["reversal"]["reversal_score"] >= min_rev_score]

    combo_confirmed = [r for r in results if len(r["combos"]) > 0]
    is_reversal_mode = st.session_state.get("scan_mode") == "Bottomed Reversals"

    # Active filters display
    active_filters = []
    if is_reversal_mode:
        active_filters.append("Bottomed Reversals")
    if min_mcap > 0:
        active_filters.append(f"MCap ≥ {format_market_cap(min_mcap)}")
    if max_mcap > 0:
        active_filters.append(f"MCap ≤ {format_market_cap(max_mcap)}")
    if min_avg_vol > 0:
        active_filters.append(f"Vol ≥ {format_volume(min_avg_vol)}")
    if min_rev_score > 0:
        active_filters.append(f"Rev ≥ {min_rev_score}")

    # Show filter effect — how many results are displayed vs total scanned
    filtered_count = len(results)
    if filtered_count < total_before_filters:
        st.markdown(
            f'<div style="margin-bottom:8px;color:#94a3b8;font-size:13px">'
            f'Showing <strong style="color:#e2e8f0">{filtered_count}</strong> of '
            f'{total_before_filters} results (filters applied)</div>',
            unsafe_allow_html=True,
        )

    if active_filters:
        filter_tags = " ".join(f'<span class="signal-tag {"green" if f == "Bottomed Reversals" else "purple"}">{f}</span>' for f in active_filters)
        st.markdown(f'<div style="margin-bottom:12px"><span style="color:#64748b;font-size:11px;margin-right:8px">ACTIVE FILTERS:</span>{filter_tags}</div>', unsafe_allow_html=True)

    # Summary stats — reversal mode shows different metrics
    if is_reversal_mode and results:
        avg_dd = sum(r["reversal"]["drawdown"] for r in results) / len(results)
        avg_rsi = sum(r["reversal"]["rsi"] for r in results) / len(results)
        top_score = max(r["reversal"]["reversal_score"] for r in results)
        st.markdown(f"""
        <div style="display:flex;gap:16px;margin-bottom:20px;flex-wrap:wrap">
            <div class="metric-card red" style="flex:1;min-width:140px">
                <div class="metric-label">Reversals Found</div>
                <div class="metric-value" style="color:#ef4444">{len(results)}</div>
                <div class="metric-detail">DD≥15% + RSI<55 + confirmation</div>
            </div>
            <div class="metric-card green" style="flex:1;min-width:140px">
                <div class="metric-label">Combo Confirmed</div>
                <div class="metric-value" style="color:#22c55e">{len(combo_confirmed)}</div>
                <div class="metric-detail">Highest conviction trades</div>
            </div>
            <div class="metric-card purple" style="flex:1;min-width:140px">
                <div class="metric-label">Top Rev Score</div>
                <div class="metric-value" style="color:#a855f7">{top_score}</div>
                <div class="metric-detail">Avg DD: {avg_dd:.0f}% | Avg RSI: {avg_rsi:.0f}</div>
            </div>
            <div class="metric-card amber" style="flex:1;min-width:140px">
                <div class="metric-label">Best Hit Rate</div>
                <div class="metric-value" style="color:#f59e0b">{max(r['best_combo']['hit_rate']*100 if r['best_combo'] else 0 for r in results):.1f}%</div>
                <div class="metric-detail">From backtested combos</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    elif results:
        st.markdown(f"""
        <div style="display:flex;gap:16px;margin-bottom:20px;flex-wrap:wrap">
            <div class="metric-card blue" style="flex:1;min-width:140px">
                <div class="metric-label">Candidates</div>
                <div class="metric-value" style="color:#3b82f6">{len(results)}</div>
            </div>
            <div class="metric-card green" style="flex:1;min-width:140px">
                <div class="metric-label">Combo Confirmed</div>
                <div class="metric-value" style="color:#22c55e">{len(combo_confirmed)}</div>
            </div>
            <div class="metric-card purple" style="flex:1;min-width:140px">
                <div class="metric-label">Avg Rev Score</div>
                <div class="metric-value" style="color:#a855f7">{sum(r['reversal']['reversal_score'] for r in results)//len(results)}</div>
            </div>
            <div class="metric-card amber" style="flex:1;min-width:140px">
                <div class="metric-label">Best Hit Rate</div>
                <div class="metric-value" style="color:#f59e0b">{max(r['best_combo']['hit_rate']*100 if r['best_combo'] else 0 for r in results):.1f}%</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # Results table
    df_table = render_scan_results_table(results)
    if df_table is not None:
        st.dataframe(
            df_table,
            use_container_width=True,
            height=min(400, 40 + len(df_table) * 35),
            column_config={
                "Price": st.column_config.NumberColumn(format="$%.2f"),
                "5d%": st.column_config.NumberColumn(format="%.1f%%"),
                "20d%": st.column_config.NumberColumn(format="%.1f%%"),
                "Rev Score": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d"),
            },
        )

    # Symbol selector for detail view
    if results:
        st.markdown("---")
        symbol_names = [r["symbol"] for r in results]
        selected = st.selectbox("Select symbol for detailed analysis", symbol_names, index=0)

        selected_data = next((r for r in results if r["symbol"] == selected), None)
    else:
        selected_data = None
    if selected_data:
        st.markdown(f"""
        <div style="display:flex;align-items:baseline;gap:16px;margin-bottom:20px">
            <span style="font-size:32px;font-weight:800;color:#e2e8f0;font-family:'Inter',sans-serif">{selected_data['symbol']}</span>
            <span style="font-size:24px;color:#94a3b8;font-family:'SF Mono',monospace">${selected_data['price']:.2f}</span>
        </div>
        """, unsafe_allow_html=True)
        render_symbol_detail(selected_data)

    # ── Sector Heatmap ──
    with st.expander("🗺️ Sector Rotation Heatmap", expanded=False):
        heatmap = get_sector_heatmap()
        if heatmap:
            hm_df = pd.DataFrame(heatmap)
            hm_df = hm_df.rename(columns={
                "sector": "Sector", "etf": "ETF",
                "ret_5d": "5d %", "ret_20d": "20d %", "ret_60d": "60d %",
            })
            st.dataframe(
                hm_df, use_container_width=True, hide_index=True,
                column_config={
                    "5d %": st.column_config.NumberColumn(format="%.1f%%"),
                    "20d %": st.column_config.NumberColumn(format="%.1f%%"),
                    "60d %": st.column_config.NumberColumn(format="%.1f%%"),
                },
            )
        else:
            st.info("Could not fetch sector data.")

    # ── Signal Performance Tracker ──
    with st.expander("📈 Signal Performance Tracker", expanded=False):
        total = _tracker.get_total_signals()
        st.markdown(f'<span style="color:#94a3b8;font-size:12px">{total} signals logged</span>', unsafe_allow_html=True)

        hit_rates = _tracker.get_hit_rates()
        if hit_rates:
            st.markdown("**Hit Rates by Combo (tracked signals)**")
            hr_df = pd.DataFrame(hit_rates)
            hr_df = hr_df.rename(columns={
                "combo": "Combo", "total": "Signals", "wins": "Wins",
                "hit_rate": "Hit Rate", "avg_return": "Avg 10d Ret %",
            })
            st.dataframe(hr_df, use_container_width=True, hide_index=True,
                         column_config={"Hit Rate": st.column_config.NumberColumn(format="%.0f%%")})

        recent = _tracker.get_recent_signals(10)
        if recent:
            st.markdown("**Recent Signals**")
            rec_df = pd.DataFrame(recent)
            st.dataframe(rec_df, use_container_width=True, hide_index=True)

        if total > 0:
            if st.button("Update forward returns (backfill)"):
                with st.spinner("Updating forward returns..."):
                    _tracker.update_forward_returns()
                st.success("Updated!")

    # ── Watchlist & Position Tracker ──
    with st.expander("📋 Watchlist & Position Tracker", expanded=False):
        wl_tab1, wl_tab2, wl_tab3 = st.tabs(["Watchlist", "Open Positions", "P&L History"])

        with wl_tab1:
            wl_items = _watchlist.get_watchlist()
            if wl_items:
                wl_df = pd.DataFrame(wl_items)
                display_cols = ["symbol", "status", "entry_price", "target_price", "stop_loss", "notes", "added_date"]
                avail_cols = [c for c in display_cols if c in wl_df.columns]
                st.dataframe(wl_df[avail_cols], use_container_width=True, hide_index=True)
            else:
                st.info("Watchlist empty. Use the 'Add to Watchlist' button in symbol detail view.")

            # Quick add
            wl_add_cols = st.columns([2, 1, 1, 1])
            with wl_add_cols[0]:
                wl_sym = st.text_input("Symbol", placeholder="SOFI", key="wl_add_sym")
            with wl_add_cols[1]:
                wl_target = st.number_input("Target $", min_value=0.0, value=0.0, step=1.0, key="wl_target")
            with wl_add_cols[2]:
                wl_stop = st.number_input("Stop $", min_value=0.0, value=0.0, step=1.0, key="wl_stop")
            with wl_add_cols[3]:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                if st.button("Add", key="wl_add_btn") and wl_sym:
                    ok = _watchlist.add_to_watchlist(
                        wl_sym.strip().upper(),
                        target=wl_target if wl_target > 0 else None,
                        stop_loss=wl_stop if wl_stop > 0 else None,
                    )
                    if ok:
                        st.success(f"Added {wl_sym.upper()} to watchlist")
                        st.rerun()
                    else:
                        st.warning(f"{wl_sym.upper()} already on watchlist")

        with wl_tab2:
            open_pos = _watchlist.get_open_positions()
            if open_pos:
                # Enrich with current prices
                pos_symbols = list({p["symbol"] for p in open_pos})
                try:
                    current_prices = {}
                    for sym in pos_symbols:
                        try:
                            t = yf.Ticker(sym)
                            cp = t.fast_info.get("lastPrice") or t.info.get("currentPrice", 0)
                            current_prices[sym] = float(cp) if cp else 0
                        except Exception:
                            current_prices[sym] = 0
                    enriched = _watchlist.update_current_prices(current_prices)
                except Exception:
                    enriched = open_pos

                pos_df = pd.DataFrame(enriched)
                display_cols = ["symbol", "entry_price", "shares", "current_price", "unrealized_pnl_pct", "entry_date"]
                avail_cols = [c for c in display_cols if c in pos_df.columns]
                st.dataframe(pos_df[avail_cols], use_container_width=True, hide_index=True)
            else:
                st.info("No open positions.")

        with wl_tab3:
            summary = _watchlist.get_pnl_summary()
            if summary["total_trades"] > 0:
                sm_cols = st.columns(4)
                with sm_cols[0]:
                    st.metric("Total Trades", summary["total_trades"])
                with sm_cols[1]:
                    st.metric("Win Rate", f"{summary['win_rate']:.0f}%")
                with sm_cols[2]:
                    st.metric("Avg P&L", f"{summary['avg_pnl']:+.1f}%")
                with sm_cols[3]:
                    st.metric("Total P&L", f"{summary['total_pnl']:+.1f}%")

                closed = _watchlist.get_closed_positions(20)
                if closed:
                    cl_df = pd.DataFrame(closed)
                    display_cols = ["symbol", "entry_price", "exit_price", "pnl_pct", "entry_date", "exit_date"]
                    avail_cols = [c for c in display_cols if c in cl_df.columns]
                    st.dataframe(cl_df[avail_cols], use_container_width=True, hide_index=True)
            else:
                st.info("No closed trades yet.")

    # ── Backtested Equity Curve ──
    with st.expander("📊 Backtested Equity Curve", expanded=False):
        st.markdown('<span style="color:#94a3b8;font-size:12px">Simulate portfolio equity from scan signals</span>', unsafe_allow_html=True)

        eq_cols = st.columns(4)
        with eq_cols[0]:
            eq_capital = st.number_input("Initial Capital $", min_value=1000, value=100000, step=10000, key="eq_cap")
        with eq_cols[1]:
            eq_pos_pct = st.slider("Position Size %", 2, 25, 10, key="eq_pos") / 100
        with eq_cols[2]:
            eq_tp = st.slider("Profit Target %", 10, 100, 50, key="eq_tp") / 100
        with eq_cols[3]:
            eq_sl = st.slider("Stop Loss %", 5, 30, 15, key="eq_sl") / 100

        if st.button("Run Backtest", key="eq_run"):
            if results:
                # Build signals DataFrame from scan results
                sig_rows = []
                for r in results:
                    sig_rows.append({
                        "symbol": r["symbol"],
                        "date": str(r["df"]["date"].iloc[-1]),
                        "close": r["price"],
                        "score": r["reversal"]["reversal_score"],
                        "combo_hit_rate": r["best_combo"]["hit_rate"] if r["best_combo"] else 0,
                    })
                sig_df = pd.DataFrame(sig_rows)

                # Build price data dict
                price_data = {}
                for r in results:
                    price_data[r["symbol"]] = r["df"]

                with st.spinner("Running equity simulation..."):
                    eq_result = simulate_equity_curve(
                        sig_df,
                        initial_capital=eq_capital,
                        position_pct=eq_pos_pct,
                        profit_target=eq_tp,
                        stop_loss=-eq_sl,
                        max_hold_days=20,
                        price_data=price_data,
                    )

                if eq_result["stats"]["total_trades"] > 0:
                    fig = build_equity_chart(eq_result)
                    st.plotly_chart(fig, use_container_width=True)

                    # Trade log
                    if eq_result["trades"]:
                        st.markdown("**Trade Log:**")
                        trades_df = pd.DataFrame(eq_result["trades"])
                        st.dataframe(trades_df, use_container_width=True, hide_index=True)
                else:
                    st.info("No trades were generated. Try different parameters or scan a larger universe.")
            else:
                st.warning("Run a scan first to generate signals for backtesting.")

elif st.session_state.get("scan_performed") and not st.session_state.scan_results:
    st.warning("No results found. Try broadening your filters (lower min reversal score, lower volume threshold, or wider market cap range).")

# Default: show instructions + quick-start actions
else:
    st.markdown("""
    <div style="text-align:center;padding:60px 20px 20px">
        <div class="main-title" style="font-size:42px;margin-bottom:8px">ALPHA PREDATOR</div>
        <div style="color:#64748b;font-size:16px;margin-bottom:40px">
            Swing Reversal Scanner — Bottomed Stocks Reversing With Strength
        </div>
        <div style="display:flex;justify-content:center;gap:40px;flex-wrap:wrap;margin-bottom:40px">
            <div style="text-align:center;max-width:220px">
                <div style="font-size:36px;margin-bottom:8px">🔍</div>
                <div style="color:#e2e8f0;font-weight:600;margin-bottom:4px">Search</div>
                <div style="color:#64748b;font-size:13px">Enter any ticker symbol to get instant analysis with charts and signals</div>
            </div>
            <div style="text-align:center;max-width:220px">
                <div style="font-size:36px;margin-bottom:8px">🌐</div>
                <div style="color:#e2e8f0;font-weight:600;margin-bottom:4px">Scan</div>
                <div style="color:#64748b;font-size:13px">Scan preset universes to find the best reversal candidates automatically</div>
            </div>
            <div style="text-align:center;max-width:220px">
                <div style="font-size:36px;margin-bottom:8px">📊</div>
                <div style="color:#e2e8f0;font-weight:600;margin-bottom:4px">Analyze</div>
                <div style="color:#64748b;font-size:13px">Interactive charts with S/R levels, combo detection, and Kelly sizing</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Quick-start: search bar right on the main page
    st.markdown("---")
    qs_cols = st.columns([1, 3, 1])
    with qs_cols[1]:
        st.markdown('<div style="text-align:center;color:#94a3b8;font-size:13px;margin-bottom:8px">Quick Search — or use the sidebar for full controls</div>', unsafe_allow_html=True)
        qs_sym = st.text_input("Enter ticker(s)", placeholder="SOFI, RIOT, IONQ...", key="qs_input", label_visibility="collapsed")
        qs_col1, qs_col2 = st.columns(2)
        with qs_col1:
            qs_analyze = st.button("Analyze Symbol", type="primary", use_container_width=True, key="qs_analyze")
        with qs_col2:
            qs_quick_scan = st.button("Quick Scan (High Beta)", use_container_width=True, key="qs_quick")

    if qs_analyze and qs_sym.strip():
        symbols = [s.strip().upper() for s in qs_sym.split(",") if s.strip()]
        if len(symbols) == 1:
            with st.spinner(f"Analyzing {symbols[0]}..."):
                result = analyze_symbol(symbols[0], "1y")
                if result:
                    st.session_state.search_data = result
                    st.session_state.selected_symbol = symbols[0]
                    st.rerun()
                else:
                    st.error(f"Could not fetch data for {symbols[0]}.")
        else:
            with st.spinner(f"Downloading prices for {len(symbols)} symbols..."):
                df_all = fetch_batch(symbols, "1y")
            with st.spinner(f"Analyzing {len(symbols)} symbols..."):
                results = analyze_batch(symbols, df_all)
                st.session_state.scan_results = results
                st.session_state.search_data = None
                st.session_state.scan_performed = True
                st.rerun()

    if qs_quick_scan:
        quick_universe = PRESETS["High Beta / Meme"]
        with st.spinner(f"Scanning {len(quick_universe)} high-beta stocks..."):
            df_all = fetch_batch(quick_universe, "1y")
            results = analyze_batch(quick_universe, df_all)
            st.session_state.scan_results = results
            st.session_state.search_data = None
            st.session_state.scan_performed = True
            st.rerun()
