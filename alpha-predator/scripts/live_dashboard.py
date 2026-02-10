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
    "High Beta / Meme": ["AMC", "GME", "SOFI", "HOOD", "AFRM", "UPST", "DKNG", "PLTR", "CLOV", "RBLX"],
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

    /* Hide default Streamlit elements */
    #MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; }

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


def compute_reversal_metrics(tech, explosive, df):
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

    return {
        "reversal_score": score, "reasons": reasons,
        "ret_5d": ret_5d, "ret_20d": ret_20d, "rsi": rsi,
        "drawdown": drawdown, "vol_ratio": vol_ratio, "vol_zscore": vol_zscore,
    }


@st.cache_data(ttl=3600, show_spinner="Fetching full US market from NASDAQ...")
def fetch_full_market(min_mcap=0, max_mcap=0, min_vol=0):
    """Fetch ALL US-traded stocks from NASDAQ screener API and pre-filter.

    Returns a list of symbol strings that pass the market cap filter.
    Volume filtering is done downstream via yfinance since NASDAQ screener
    doesn't provide avg volume.

    Covers NYSE + NASDAQ + AMEX — the entire US equity market (~7000+ stocks).
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

        # Parse market cap — comes as raw number string like "4,594,401,000,000"
        mc_str = row.get("marketCap", "")
        mc = _parse_mcap(mc_str)

        # Apply market cap filters (0 = no filter; unknown/0 mcap passes)
        if min_mcap > 0 and mc > 0 and mc < min_mcap:
            continue
        if max_mcap > 0 and mc > 0 and mc > max_mcap:
            continue

        # Skip completely empty entries (no market cap at all = likely shell/dead)
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
    reversal = compute_reversal_metrics(tech, explosive, sym_df)
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
    insider = fetch_insider_activity(symbol)
    options = detect_unusual_options(symbol)
    earnings = get_earnings_proximity(symbol)

    # New features: analogs, fibonacci, short interest, dark pool
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
    }


@st.cache_data(ttl=300, show_spinner="Fetching prices...")
def fetch_batch(symbols, period="1y"):
    """Fetch prices for multiple symbols."""
    return fetch_prices(symbols, period=period)


def analyze_batch(symbols, period="1y", min_mcap=0, max_mcap=0, min_vol=0):
    """Analyze multiple symbols efficiently with market cap and volume filtering."""
    df_all = fetch_batch(symbols, period)
    if df_all.empty:
        return []

    # Fetch fundamentals for all symbols at once
    valid_symbols = [s for s in symbols if s in df_all["symbol"].unique()]
    fundies = fetch_fundamentals_batch(valid_symbols)

    # Pre-filter by market cap and volume before heavy computation
    filtered_symbols = []
    for symbol in valid_symbols:
        fund = fundies.get(symbol, {"market_cap": 0, "avg_volume": 0})
        mc = fund["market_cap"]
        av = fund["avg_volume"]

        # Apply filters (0 = no filter / unknown passes)
        if min_mcap > 0 and mc > 0 and mc < min_mcap:
            continue
        if max_mcap > 0 and mc > 0 and mc > max_mcap:
            continue
        if min_vol > 0 and av > 0 and av < min_vol:
            continue
        filtered_symbols.append(symbol)

    results = []
    for symbol in filtered_symbols:
        sym_df = df_all[df_all["symbol"] == symbol].sort_values("date").reset_index(drop=True)
        if len(sym_df) < 60:
            continue
        try:
            tech = compute_all_technical(sym_df)
            explosive = compute_all_explosive(sym_df)
            combos = match_combos(explosive)
            levels = compute_support_resistance(sym_df)
            reversal = compute_reversal_metrics(tech, explosive, sym_df)
            weekly = compute_weekly_confluence(sym_df)
            gaps = detect_unfilled_gaps(sym_df)
            best_combo = max(combos, key=lambda c: c["hit_rate"]) if combos else None
            kelly = kelly_position_size(best_combo["hit_rate"]) * 100 if best_combo else 0
            feat_dict = {**tech, **explosive, "close": sym_df["close"].iloc[-1]}
            tier_result = classify_tier(feat_dict)

            fund = fundies.get(symbol, {"market_cap": 0, "avg_volume": 0})

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
                "market_cap": fund["market_cap"],
                "avg_volume": fund["avg_volume"],
                "weekly": weekly, "gaps": gaps,
            })
        except Exception:
            pass

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
    """Build a polished interactive candlestick chart with S/R levels, VWAP, and overlays."""
    df = data["df"].tail(days).copy()
    levels = data["levels"]
    current_price = data["price"]
    symbol = data["symbol"]

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.02,
        row_heights=[0.78, 0.22],
    )

    # ── Candlestick ──
    fig.add_trace(go.Candlestick(
        x=df["date"], open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        increasing_line_color="#22c55e", decreasing_line_color="#ef4444",
        increasing_fillcolor="rgba(34,197,94,0.85)", decreasing_fillcolor="rgba(239,68,68,0.85)",
        increasing_line_width=1, decreasing_line_width=1,
        name=symbol, showlegend=False,
    ), row=1, col=1)

    # ── Bollinger Bands (shaded ribbon) ──
    ma20 = df["close"].rolling(20).mean()
    std20 = df["close"].rolling(20).std()
    bb_upper = ma20 + 2 * std20
    bb_lower = ma20 - 2 * std20
    fig.add_trace(go.Scatter(
        x=df["date"], y=bb_upper, mode="lines",
        line=dict(color="rgba(59,130,246,0.2)", width=1), name="BB Upper", showlegend=False,
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=df["date"], y=bb_lower, mode="lines", fill="tonexty",
        fillcolor="rgba(59,130,246,0.04)",
        line=dict(color="rgba(59,130,246,0.2)", width=1), name="BB Lower", showlegend=False,
    ), row=1, col=1)

    # ── Moving averages ──
    fig.add_trace(go.Scatter(
        x=df["date"], y=ma20, mode="lines",
        line=dict(color="#f59e0b", width=1.5), name="MA 20",
    ), row=1, col=1)
    ma50 = df["close"].rolling(50).mean()
    fig.add_trace(go.Scatter(
        x=df["date"], y=ma50, mode="lines",
        line=dict(color="#a855f7", width=1.5), name="MA 50",
    ), row=1, col=1)
    if len(df) >= 200:
        ma200 = df["close"].rolling(200).mean()
        fig.add_trace(go.Scatter(
            x=df["date"], y=ma200, mode="lines",
            line=dict(color="#06b6d4", width=1.5), name="MA 200",
        ), row=1, col=1)

    # ── VWAP ──
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    cumvol = df["volume"].cumsum()
    cumtp = (typical_price * df["volume"]).cumsum()
    vwap = cumtp / cumvol.replace(0, np.nan)
    fig.add_trace(go.Scatter(
        x=df["date"], y=vwap, mode="lines",
        line=dict(color="rgba(236,72,153,0.6)", width=1.5, dash="dot"), name="VWAP",
    ), row=1, col=1)

    # ── S/R levels (pivot-based and MA-based) ──
    for level in levels:
        is_ma = level["type"].startswith("MA")
        is_resistance = level["type"] == "resistance"

        if is_ma:
            color = "rgba(168,85,247,0.45)"
            dash = "dot"
            width = 1
            label = level["type"]
        elif is_resistance:
            color = "rgba(239,68,68,0.55)"
            dash = "dash"
            width = 1.5
            touches = level.get("touches", 0)
            label = f"R ${level['price']:.2f}" + (f" ({touches}x)" if touches > 1 else "")
        else:
            color = "rgba(34,197,94,0.55)"
            dash = "dash"
            width = 1.5
            touches = level.get("touches", 0)
            label = f"S ${level['price']:.2f}" + (f" ({touches}x)" if touches > 1 else "")

        fig.add_hline(
            y=level["price"], line_dash=dash, line_color=color, line_width=width,
            row=1, col=1,
            annotation_text=f"  {label}",
            annotation_position="right",
            annotation_font=dict(size=10, color=color, family="Inter, sans-serif"),
        )

    # ── Fibonacci retracement levels ──
    fib = data.get("fibonacci")
    if fib and fib.get("levels"):
        fib_colors = {
            "23.6%": "rgba(255,215,0,0.4)",
            "38.2%": "rgba(255,165,0,0.45)",
            "50%": "rgba(0,191,255,0.45)",
            "61.8%": "rgba(255,165,0,0.45)",
            "78.6%": "rgba(255,215,0,0.4)",
        }
        for lvl in fib.get("levels", []):
            label = lvl["level"]
            if label in ("0%", "100%"):
                continue  # skip swing high/low lines (already shown as S/R)
            color = fib_colors.get(label, "rgba(255,215,0,0.35)")
            fig.add_hline(
                y=lvl["price"], line_dash="dot", line_color=color, line_width=1,
                row=1, col=1,
                annotation_text=f"  Fib {label}",
                annotation_position="left",
                annotation_font=dict(size=9, color=color, family="Inter, sans-serif"),
            )

    # ── Unfilled gaps (shaded zones) ──
    for gap in data.get("gaps", []):
        is_support = "support" in gap["type"]
        fig.add_hrect(
            y0=gap["bottom"], y1=gap["top"],
            fillcolor="rgba(34,197,94,0.08)" if is_support else "rgba(239,68,68,0.08)",
            line=dict(width=0),
            row=1, col=1,
            annotation_text=f"  Gap {gap['gap_pct']}%",
            annotation_position="top right" if not is_support else "bottom right",
            annotation_font=dict(
                size=9, family="Inter, sans-serif",
                color="rgba(34,197,94,0.6)" if is_support else "rgba(239,68,68,0.6)",
            ),
        )

    # ── Current price line ──
    fig.add_hline(
        y=current_price, line_dash="solid", line_color="rgba(255,255,255,0.35)",
        line_width=1, row=1, col=1,
        annotation_text=f"  ${current_price:.2f}",
        annotation_position="right",
        annotation_font=dict(size=11, color="#e2e8f0", family="SF Mono, Fira Code, monospace"),
    )

    # ── Volume bars (color-coded) ──
    vol_colors = [
        "rgba(34,197,94,0.5)" if c >= o else "rgba(239,68,68,0.5)"
        for c, o in zip(df["close"], df["open"])
    ]
    fig.add_trace(go.Bar(
        x=df["date"], y=df["volume"], marker_color=vol_colors,
        name="Volume", showlegend=False,
    ), row=2, col=1)
    vol_ma = df["volume"].rolling(20).mean()
    fig.add_trace(go.Scatter(
        x=df["date"], y=vol_ma, mode="lines",
        line=dict(color="#f59e0b", width=1.5), name="Vol MA20", showlegend=False,
    ), row=2, col=1)

    # ── Layout ──
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#080c14",
        height=600, margin=dict(l=0, r=90, t=30, b=10),
        xaxis_rangeslider_visible=False,
        legend=dict(
            font=dict(size=11, family="Inter, sans-serif", color="#94a3b8"),
            bgcolor="rgba(0,0,0,0)", x=0.01, y=0.99,
            orientation="h", yanchor="top",
        ),
        yaxis=dict(
            gridcolor="rgba(30,41,59,0.5)", side="right", zeroline=False,
            tickfont=dict(size=10, color="#64748b", family="SF Mono, monospace"),
        ),
        yaxis2=dict(
            gridcolor="rgba(30,41,59,0.3)", side="right", zeroline=False,
            tickfont=dict(size=9, color="#475569", family="SF Mono, monospace"),
            showgrid=False,
        ),
        xaxis=dict(
            gridcolor="rgba(30,41,59,0.3)", zeroline=False,
            tickfont=dict(size=10, color="#475569"),
        ),
        xaxis2=dict(
            gridcolor="rgba(30,41,59,0.3)", zeroline=False,
            tickfont=dict(size=9, color="#475569"),
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

        # Insider activity
        with intel_cols[2]:
            if insider:
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
        placeholder="AAPL, TSLA, NVDA...",
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
    scan_btn = st.button(
        "🔥 Find Reversals" if scan_mode == "Bottomed Reversals" else "Scan Universe",
        type="primary" if scan_mode == "Bottomed Reversals" else "secondary",
        use_container_width=True,
    )

    st.markdown("---")

    # ── Collapsible Filters ──
    with st.expander("📏 Filters", expanded=False):
        mcap_options = {
            "No filter": (0, 0),
            "Below $200B": (0, 200_000_000_000),
            "Nano (<$50M)": (0, 50_000_000),
            "Micro ($50M–$300M)": (50_000_000, 300_000_000),
            "Small ($300M–$2B)": (300_000_000, 2_000_000_000),
            "Mid ($2B–$10B)": (2_000_000_000, 10_000_000_000),
            "Large ($10B–$200B)": (10_000_000_000, 200_000_000_000),
            "Mega (>$200B)": (200_000_000_000, 0),
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

    # ── Collapsible Settings ──
    with st.expander("⚙️ Settings", expanded=False):
        chart_days = st.slider("Chart days", 30, 252, 120)
        period = st.selectbox("Data period", ["6mo", "1y", "2y"], index=1)

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
        with st.spinner(f"Scanning {len(symbols)} symbols..."):
            results = analyze_batch(symbols, period, min_mcap=min_mcap, max_mcap=max_mcap, min_vol=min_avg_vol)
            if scan_mode == "Bottomed Reversals":
                results = filter_bottomed_reversals(results)
            st.session_state.scan_results = results
            st.session_state.scan_mode = scan_mode
            st.session_state.search_data = None

# Handle preset scan
if scan_btn:
    if preset_name == "Full Market (All US Stocks)":
        # Fetch the ENTIRE US equity market, pre-filtered by mcap at screener level
        symbols = fetch_full_market(min_mcap=min_mcap, max_mcap=max_mcap, min_vol=0)
        st.toast(f"Universe: {len(symbols)} stocks pass market cap filter")
    else:
        symbols = PRESETS[preset_name]

    spinner_msg = (f"Hunting bottomed reversals across {len(symbols)} stocks..."
                   if scan_mode == "Bottomed Reversals"
                   else f"Scanning {len(symbols)} symbols from '{preset_name}'...")

    with st.spinner(spinner_msg):
        # For Full Market, mcap already filtered at screener level — only pass volume filter
        if preset_name == "Full Market (All US Stocks)":
            results = analyze_batch(symbols, period, min_mcap=0, max_mcap=0, min_vol=min_avg_vol)
        else:
            results = analyze_batch(symbols, period, min_mcap=min_mcap, max_mcap=max_mcap, min_vol=min_avg_vol)
        results = [r for r in results if r["reversal"]["reversal_score"] >= min_rev_score]
        if scan_mode == "Bottomed Reversals":
            results = filter_bottomed_reversals(results)
        st.session_state.scan_results = results
        st.session_state.scan_mode = scan_mode
        st.session_state.search_data = None

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
    results = st.session_state.scan_results
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
    st.markdown("---")
    symbol_names = [r["symbol"] for r in results]
    selected = st.selectbox("Select symbol for detailed analysis", symbol_names, index=0)

    selected_data = next((r for r in results if r["symbol"] == selected), None)
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
                wl_sym = st.text_input("Symbol", placeholder="AAPL", key="wl_add_sym")
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

# Default: show instructions
else:
    st.markdown("""
    <div style="text-align:center;padding:80px 20px">
        <div class="main-title" style="font-size:42px;margin-bottom:8px">ALPHA PREDATOR</div>
        <div style="color:#64748b;font-size:16px;margin-bottom:40px">
            Swing Reversal Scanner — Bottomed Stocks Reversing With Strength
        </div>
        <div style="display:flex;justify-content:center;gap:40px;flex-wrap:wrap">
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
