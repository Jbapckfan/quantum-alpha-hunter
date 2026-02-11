"""
Alpha Predator — Intelligence Module
Enhanced signal detection using free data sources.

Features:
1. Relative Strength vs Sector & SPY
2. Multi-Timeframe (Weekly) Confluence
3. Unfilled Gap Detection (S/R)
4. Insider Activity (yfinance)
5. Unusual Options Activity (yfinance)
6. Earnings Proximity (yfinance)
7. Sector Rotation Heatmap
8. Signal Performance Tracker (SQLite)
"""
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger("apredator.intelligence")

# ─────────────────────────────────────────────────────────────────────────────
# Sector ETF Mapping (yfinance sector names → ETF tickers)
# ─────────────────────────────────────────────────────────────────────────────
SECTOR_ETFS = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financial Services": "XLF",
    "Energy": "XLE",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Industrials": "XLI",
    "Basic Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
    "Communication Services": "XLC",
}

ALL_SECTOR_TICKERS = list(SECTOR_ETFS.values()) + ["SPY"]

_sector_cache = {}


def fetch_sector_benchmark_data(period="1y"):
    """Fetch and cache price data for all sector ETFs + SPY."""
    if period in _sector_cache:
        return _sector_cache[period]

    try:
        data = yf.download(ALL_SECTOR_TICKERS, period=period, progress=False)
        if data.empty:
            return {}

        result = {}
        for ticker in ALL_SECTOR_TICKERS:
            try:
                if isinstance(data.columns, pd.MultiIndex):
                    close = data["Close"][ticker].dropna()
                else:
                    close = data["Close"].dropna()
                result[ticker] = close
            except Exception:
                pass

        _sector_cache[period] = result
        return result
    except Exception:
        return {}


def get_symbol_sector(symbol):
    """Get the sector for a stock symbol via yfinance."""
    try:
        return yf.Ticker(symbol).info.get("sector", "Unknown")
    except Exception:
        return "Unknown"


def get_sector_from_info(info):
    """Extract sector from a pre-fetched ``ticker.info`` dict."""
    if not info:
        return "Unknown"
    return info.get("sector", "Unknown")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Relative Strength vs Sector & SPY
# ─────────────────────────────────────────────────────────────────────────────

def compute_relative_strength(df, sector=None, period="1y"):
    """Compute relative strength of a stock vs its sector ETF and SPY.

    Returns:
        rs_vs_spy_20d: 20d outperformance vs SPY (%)
        rs_vs_sector_20d: 20d outperformance vs sector ETF (%)
        rs_rank: "Strong" / "Neutral" / "Weak"
    """
    benchmarks = fetch_sector_benchmark_data(period)
    default = {"rs_vs_spy_20d": 0, "rs_vs_sector_20d": 0, "rs_rank": "Unknown"}

    if not benchmarks or len(df) < 21:
        return default

    close = df["close"]
    stock_ret_20d = (close.iloc[-1] / close.iloc[-21] - 1) * 100

    # vs SPY
    spy_close = benchmarks.get("SPY")
    if spy_close is not None and len(spy_close) >= 21:
        spy_ret_20d = (spy_close.iloc[-1] / spy_close.iloc[-21] - 1) * 100
    else:
        spy_ret_20d = 0
    rs_vs_spy = stock_ret_20d - spy_ret_20d

    # vs Sector
    rs_vs_sector = 0.0
    if sector and sector in SECTOR_ETFS:
        etf_close = benchmarks.get(SECTOR_ETFS[sector])
        if etf_close is not None and len(etf_close) >= 21:
            etf_ret_20d = (etf_close.iloc[-1] / etf_close.iloc[-21] - 1) * 100
            rs_vs_sector = stock_ret_20d - etf_ret_20d

    # Rank
    if rs_vs_spy > 5 and rs_vs_sector > 3:
        rank = "Strong"
    elif rs_vs_spy < -5 and rs_vs_sector < -3:
        rank = "Weak"
    else:
        rank = "Neutral"

    return {
        "rs_vs_spy_20d": round(rs_vs_spy, 1),
        "rs_vs_sector_20d": round(rs_vs_sector, 1),
        "rs_rank": rank,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. Multi-Timeframe (Weekly) Confluence
# ─────────────────────────────────────────────────────────────────────────────

def compute_weekly_confluence(df):
    """Compute weekly timeframe signals for multi-TF confirmation.

    Returns:
        weekly_rsi: RSI on weekly bars
        weekly_macd_bullish: True if MACD > signal on weekly
        weekly_trend: "up" / "down" / "sideways"
        confluence_score: 0-3 (weekly signals confirming daily setup)
    """
    default = {
        "weekly_rsi": 50.0, "weekly_macd_bullish": False,
        "weekly_trend": "unknown", "confluence_score": 0,
    }
    if len(df) < 50:
        return default

    # Resample to weekly
    wdf = df.copy()
    wdf["date"] = pd.to_datetime(wdf["date"])
    wdf = wdf.set_index("date").resample("W").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna()

    if len(wdf) < 14:
        return default

    close = wdf["close"]

    # Weekly RSI-14
    delta = close.diff()
    avg_gain = delta.clip(lower=0).rolling(14).mean()
    avg_loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    weekly_rsi = float((100 - 100 / (1 + rs)).iloc[-1])

    # Weekly MACD
    macd = close.ewm(span=12).mean() - close.ewm(span=26).mean()
    signal = macd.ewm(span=9).mean()
    weekly_macd_bullish = bool(macd.iloc[-1] > signal.iloc[-1])

    # Weekly trend (slope of 10-week MA)
    ma10w = close.rolling(10).mean().dropna()
    if len(ma10w) >= 4:
        slope = (ma10w.iloc[-1] - ma10w.iloc[-4]) / ma10w.iloc[-4]
        weekly_trend = "up" if slope > 0.02 else ("down" if slope < -0.02 else "sideways")
    else:
        weekly_trend = "unknown"

    # Confluence score
    score = 0
    if 30 <= weekly_rsi <= 55:
        score += 1
    if weekly_macd_bullish:
        score += 1
    if weekly_trend != "down":
        score += 1

    return {
        "weekly_rsi": round(weekly_rsi, 1),
        "weekly_macd_bullish": weekly_macd_bullish,
        "weekly_trend": weekly_trend,
        "confluence_score": score,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. Unfilled Gap Detection
# ─────────────────────────────────────────────────────────────────────────────

def detect_unfilled_gaps(df, min_gap_pct=1.0):
    """Find unfilled price gaps that act as S/R levels.

    A gap up: today's low > yesterday's high.
    A gap down: today's high < yesterday's low.
    Unfilled: price has not returned into the gap zone since.
    """
    gaps = []
    if len(df) < 10:
        return gaps

    high = df["high"].values
    low = df["low"].values
    dates = df["date"].values
    current_price = df["close"].values[-1]

    for i in range(1, len(df)):
        # Gap up
        if low[i] > high[i - 1]:
            gap_pct = (low[i] - high[i - 1]) / high[i - 1] * 100
            if gap_pct >= min_gap_pct:
                gap_top = float(low[i])
                gap_bottom = float(high[i - 1])
                filled = any(low[j] <= gap_top for j in range(i + 1, len(df)))
                if not filled:
                    gaps.append({
                        "price": round((gap_top + gap_bottom) / 2, 2),
                        "top": round(gap_top, 2),
                        "bottom": round(gap_bottom, 2),
                        "type": "gap_support" if gap_top < current_price else "gap_resistance",
                        "date": str(dates[i])[:10],
                        "gap_pct": round(gap_pct, 1),
                    })

        # Gap down
        if high[i] < low[i - 1]:
            gap_pct = (low[i - 1] - high[i]) / low[i - 1] * 100
            if gap_pct >= min_gap_pct:
                gap_top = float(low[i - 1])
                gap_bottom = float(high[i])
                filled = any(high[j] >= gap_bottom for j in range(i + 1, len(df)))
                if not filled:
                    gaps.append({
                        "price": round((gap_top + gap_bottom) / 2, 2),
                        "top": round(gap_top, 2),
                        "bottom": round(gap_bottom, 2),
                        "type": "gap_resistance" if gap_bottom > current_price else "gap_support",
                        "date": str(dates[i])[:10],
                        "gap_pct": round(gap_pct, 1),
                    })

    gaps.sort(key=lambda g: abs(g["price"] - current_price))
    return gaps[:6]


# ─────────────────────────────────────────────────────────────────────────────
# 4. Insider Activity
# ─────────────────────────────────────────────────────────────────────────────

def fetch_insider_activity(symbol):
    """Fetch insider buying/selling activity from yfinance.

    Returns:
        insider_buys / insider_sells: transaction counts
        insider_net: buys - sells (positive = bullish)
        insider_buy_value: total $ of purchases
        last_insider_buy: date string of most recent purchase
    """
    empty = {
        "insider_buys": 0, "insider_sells": 0, "insider_net": 0,
        "insider_buy_value": 0, "last_insider_buy": None,
    }
    try:
        ticker = yf.Ticker(symbol)
        txns = ticker.insider_transactions
        if txns is None or (hasattr(txns, "empty") and txns.empty):
            return empty

        txns.columns = [c.lower().replace(" ", "_") for c in txns.columns]

        buys = 0
        sells = 0
        buy_value = 0
        last_buy_date = None

        for _, row in txns.iterrows():
            text = str(row.get("text", "") or row.get("transaction", "")).lower()
            value = abs(float(row.get("value", 0) or 0))

            if any(kw in text for kw in ("purchase", "buy", "acquisition")):
                buys += 1
                buy_value += value
                if last_buy_date is None:
                    d = row.get("start_date", row.get("date", None))
                    if d is not None:
                        last_buy_date = str(d)[:10]
            elif any(kw in text for kw in ("sale", "sell", "disposition")):
                sells += 1

        return {
            "insider_buys": buys,
            "insider_sells": sells,
            "insider_net": buys - sells,
            "insider_buy_value": buy_value,
            "last_insider_buy": last_buy_date,
        }
    except Exception:
        return empty


# ─────────────────────────────────────────────────────────────────────────────
# 5. Unusual Options Activity
# ─────────────────────────────────────────────────────────────────────────────

def detect_unusual_options(symbol):
    """Detect unusual options activity using yfinance options data.

    Returns:
        put_call_ratio: put OI / call OI (< 0.7 bullish, > 1.3 bearish)
        unusual_call_volume: True if any strike has vol > 3x OI
        max_call_oi_strike: strike price with highest call OI
        options_signal: "Bullish" / "Bearish" / "Neutral" / "N/A"
    """
    empty = {
        "put_call_ratio": 0, "unusual_call_volume": False,
        "max_call_oi_strike": None, "total_call_oi": 0,
        "total_put_oi": 0, "options_signal": "N/A",
    }
    try:
        ticker = yf.Ticker(symbol)
        exp_dates = ticker.options
        if not exp_dates:
            return empty

        chain = ticker.option_chain(exp_dates[0])
        return detect_unusual_options_from_chain(chain.calls, chain.puts)
    except Exception:
        return empty


def detect_unusual_options_from_chain(calls, puts):
    """Detect unusual options activity from pre-fetched call/put DataFrames.

    Parameters
    ----------
    calls : pd.DataFrame
        Calls DataFrame from ``ticker.option_chain().calls``.
    puts : pd.DataFrame
        Puts DataFrame from ``ticker.option_chain().puts``.

    Returns same dict as ``detect_unusual_options()``.
    """
    empty = {
        "put_call_ratio": 0, "unusual_call_volume": False,
        "max_call_oi_strike": None, "total_call_oi": 0,
        "total_put_oi": 0, "options_signal": "N/A",
    }
    try:
        if (calls is None or calls.empty) and (puts is None or puts.empty):
            return empty

        if calls is None:
            calls = pd.DataFrame()
        if puts is None:
            puts = pd.DataFrame()

        call_oi = int(calls["openInterest"].sum()) if "openInterest" in calls.columns else 0
        put_oi = int(puts["openInterest"].sum()) if "openInterest" in puts.columns else 0
        pc_ratio = put_oi / max(call_oi, 1)

        # Unusual call volume
        unusual = False
        if "volume" in calls.columns and "openInterest" in calls.columns:
            active = calls[calls["openInterest"] > 10]
            if not active.empty:
                unusual = bool((active["volume"].fillna(0) > 3 * active["openInterest"]).any())

        # Max call OI strike
        max_strike = None
        if "openInterest" in calls.columns and not calls.empty:
            max_strike = float(calls.loc[calls["openInterest"].idxmax(), "strike"])

        # Signal
        if pc_ratio < 0.5 or unusual:
            sig = "Bullish"
        elif pc_ratio > 1.5:
            sig = "Bearish"
        else:
            sig = "Neutral"

        return {
            "put_call_ratio": round(pc_ratio, 2),
            "unusual_call_volume": unusual,
            "max_call_oi_strike": max_strike,
            "total_call_oi": call_oi,
            "total_put_oi": put_oi,
            "options_signal": sig,
        }
    except Exception:
        return empty


# ─────────────────────────────────────────────────────────────────────────────
# 6. Earnings Proximity
# ─────────────────────────────────────────────────────────────────────────────

def get_earnings_proximity(symbol):
    """Get days until next earnings report.

    Returns:
        days_to_earnings: int or None
        earnings_date: date string or None
        earnings_warning: True if within 14 days
    """
    empty = {"days_to_earnings": None, "earnings_date": None, "earnings_warning": False}
    try:
        ticker = yf.Ticker(symbol)
        cal = ticker.calendar
        return get_earnings_from_calendar(cal)
    except Exception:
        return empty


def get_earnings_from_calendar(cal):
    """Extract earnings proximity from a pre-fetched ``ticker.calendar`` object.

    Parameters
    ----------
    cal : dict | pd.DataFrame | None
        The calendar object from ``yf.Ticker(symbol).calendar``.

    Returns same dict as ``get_earnings_proximity()``.
    """
    empty = {"days_to_earnings": None, "earnings_date": None, "earnings_warning": False}
    try:
        if cal is None:
            return empty

        # yfinance returns dict in newer versions, DataFrame in older
        if isinstance(cal, dict):
            ed = cal.get("Earnings Date", cal.get("earnings_date", []))
            if not ed:
                return empty
            next_date = pd.Timestamp(ed[0] if isinstance(ed, list) else ed)
        elif isinstance(cal, pd.DataFrame):
            if cal.empty:
                return empty
            for key in ("Earnings Date", "earnings_date"):
                if key in cal.index:
                    val = cal.loc[key]
                    next_date = pd.Timestamp(val.iloc[0] if hasattr(val, "iloc") else val)
                    break
            else:
                return empty
        else:
            return empty

        days = (next_date - pd.Timestamp.now()).days
        return {
            "days_to_earnings": days,
            "earnings_date": next_date.strftime("%Y-%m-%d"),
            "earnings_warning": 0 < days <= 14,
        }
    except Exception:
        return empty


# ─────────────────────────────────────────────────────────────────────────────
# 7. Sector Rotation Heatmap
# ─────────────────────────────────────────────────────────────────────────────

def get_sector_heatmap():
    """Get sector ETF performance data for heatmap display.

    Returns list of dicts: sector, etf, ret_5d, ret_20d, ret_60d.
    """
    benchmarks = fetch_sector_benchmark_data("1y")
    if not benchmarks:
        return []

    result = []
    for sector_name, etf in SECTOR_ETFS.items():
        close = benchmarks.get(etf)
        if close is None or len(close) < 61:
            continue

        ret_5d = (close.iloc[-1] / close.iloc[-6] - 1) * 100 if len(close) > 5 else 0
        ret_20d = (close.iloc[-1] / close.iloc[-21] - 1) * 100 if len(close) > 20 else 0
        ret_60d = (close.iloc[-1] / close.iloc[-61] - 1) * 100 if len(close) > 60 else 0

        result.append({
            "sector": sector_name, "etf": etf,
            "ret_5d": round(ret_5d, 1),
            "ret_20d": round(ret_20d, 1),
            "ret_60d": round(ret_60d, 1),
        })

    result.sort(key=lambda x: x["ret_20d"], reverse=True)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 8. Signal Performance Tracker
# ─────────────────────────────────────────────────────────────────────────────

class SignalTracker:
    """Track signal performance over time using SQLite."""

    def __init__(self, db_path=None):
        if db_path is None:
            db_path = Path(__file__).parent.parent.parent / "data" / "signal_tracker.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(db_path)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    scan_date TEXT NOT NULL,
                    price_at_signal REAL,
                    reversal_score INTEGER,
                    best_combo TEXT,
                    combo_hit_rate REAL,
                    tier INTEGER,
                    confluence_score INTEGER,
                    reasons TEXT,
                    fwd_ret_5d REAL,
                    fwd_ret_10d REAL,
                    fwd_ret_20d REAL,
                    outcome TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_symbol_date
                ON signals(symbol, scan_date)
            """)

    def log_signal(self, symbol, price, reversal_score, best_combo=None,
                   combo_hit_rate=0, tier=None, confluence_score=0, reasons=None):
        """Log a signal. Skips duplicates (same symbol + same day)."""
        today = datetime.now().strftime("%Y-%m-%d")
        with sqlite3.connect(self.db_path) as conn:
            existing = conn.execute(
                "SELECT id FROM signals WHERE symbol=? AND scan_date=?",
                (symbol, today),
            ).fetchone()
            if existing:
                return

            conn.execute("""
                INSERT INTO signals
                    (symbol, scan_date, price_at_signal, reversal_score,
                     best_combo, combo_hit_rate, tier, confluence_score, reasons)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (symbol, today, price, reversal_score, best_combo,
                  combo_hit_rate, tier, confluence_score, json.dumps(reasons or [])))

    def update_forward_returns(self):
        """Backfill forward returns for old signals."""
        with sqlite3.connect(self.db_path) as conn:
            pending = conn.execute("""
                SELECT id, symbol, scan_date, price_at_signal
                FROM signals
                WHERE fwd_ret_20d IS NULL
                  AND scan_date < date('now', '-20 days')
                LIMIT 50
            """).fetchall()

            for sig_id, symbol, scan_date, entry_price in pending:
                try:
                    hist = yf.Ticker(symbol).history(start=scan_date, period="30d")
                    if len(hist) >= 20 and entry_price > 0:
                        c = hist["Close"]
                        r5 = (c.iloc[5] / entry_price - 1) * 100 if len(c) > 5 else None
                        r10 = (c.iloc[10] / entry_price - 1) * 100 if len(c) > 10 else None
                        r20 = (c.iloc[20] / entry_price - 1) * 100 if len(c) > 20 else None
                        outcome = "win" if (r10 or 0) > 5 else ("loss" if (r10 or 0) < -5 else "flat")
                        conn.execute("""
                            UPDATE signals
                            SET fwd_ret_5d=?, fwd_ret_10d=?, fwd_ret_20d=?, outcome=?
                            WHERE id=?
                        """, (r5, r10, r20, outcome, sig_id))
                except Exception:
                    pass

    def get_hit_rates(self):
        """Get signal hit rates grouped by combo type."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT best_combo,
                       COUNT(*) as total,
                       SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END) as wins,
                       AVG(fwd_ret_10d) as avg_ret
                FROM signals WHERE outcome IS NOT NULL
                GROUP BY best_combo
                ORDER BY total DESC
            """).fetchall()
            return [{
                "combo": r[0] or "No Combo", "total": r[1], "wins": r[2],
                "hit_rate": r[2] / r[1] if r[1] > 0 else 0,
                "avg_return": round(r[3] or 0, 1),
            } for r in rows]

    def get_recent_signals(self, limit=20):
        """Get most recent logged signals."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT symbol, scan_date, price_at_signal, reversal_score,
                       best_combo, fwd_ret_5d, fwd_ret_10d, fwd_ret_20d, outcome
                FROM signals
                ORDER BY scan_date DESC, reversal_score DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [{
                "symbol": r[0], "date": r[1], "price": r[2], "score": r[3],
                "combo": r[4], "ret_5d": r[5], "ret_10d": r[6],
                "ret_20d": r[7], "outcome": r[8],
            } for r in rows]

    def get_total_signals(self):
        """Get total number of logged signals."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM signals").fetchone()
            return row[0] if row else 0
