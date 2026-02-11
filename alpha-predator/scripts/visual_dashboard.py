"""Generate a modern visual dashboard for swing trade reversal candidates."""
import sys
import json
import webbrowser
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
from apredator.logging_conf import setup_logging
from apredator.adapters.yahoo import fetch_prices
from apredator.features.technical import compute_all_technical
from apredator.features.explosive import compute_all_explosive
from apredator.scoring.combo_matcher import match_combos
from apredator.scoring.position_sizer import kelly_position_size

TOP_SYMBOLS = [
    "HOOD", "DDOG", "MNDY", "MARA", "SNAP", "RDDT", "QS", "HIMS",
    "SOFI", "RBLX", "SHOP", "FUTU", "SE", "SNOW", "ZS", "CVNA",
    "MSTR", "DASH", "TLRY", "RIVN", "OPEN",
]


def compute_support_resistance(df, n_levels=3):
    """Find key support/resistance levels using pivot points and volume clusters."""
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    volume = df["volume"].values

    levels = []

    # 1. Pivot-based S/R: local highs and lows (swing points)
    window = 10
    for i in range(window, len(close) - window):
        # Local high (resistance)
        if high[i] == max(high[i - window:i + window + 1]):
            levels.append({"price": float(high[i]), "type": "resistance", "strength": 0})
        # Local low (support)
        if low[i] == min(low[i - window:i + window + 1]):
            levels.append({"price": float(low[i]), "type": "support", "strength": 0})

    # 2. Cluster nearby levels and weight by touch count
    if not levels:
        return []

    prices = sorted(set(round(l["price"], 2) for l in levels))
    current_price = close[-1]
    tolerance = current_price * 0.02  # 2% clustering

    clustered = []
    used = set()
    for p in prices:
        if p in used:
            continue
        cluster = [l for l in levels if abs(l["price"] - p) <= tolerance]
        if cluster:
            avg_price = np.mean([l["price"] for l in cluster])
            n_touches = len(cluster)
            is_resistance = avg_price > current_price
            for l in cluster:
                used.add(round(l["price"], 2))
            clustered.append({
                "price": round(float(avg_price), 2),
                "type": "resistance" if is_resistance else "support",
                "touches": n_touches,
                "strength": min(n_touches / 5, 1.0),
            })

    # 3. Add key moving averages as dynamic S/R
    if len(close) >= 200:
        ma200 = float(np.mean(close[-200:]))
        clustered.append({"price": round(ma200, 2), "type": "ma200", "touches": 0, "strength": 0.8})
    if len(close) >= 50:
        ma50 = float(np.mean(close[-50:]))
        clustered.append({"price": round(ma50, 2), "type": "ma50", "touches": 0, "strength": 0.6})
    if len(close) >= 20:
        ma20 = float(np.mean(close[-20:]))
        clustered.append({"price": round(ma20, 2), "type": "ma20", "touches": 0, "strength": 0.4})

    # Sort by distance from current price, take closest n_levels of each type
    supports = sorted(
        [l for l in clustered if l["type"] == "support" or l["type"].startswith("ma")],
        key=lambda l: abs(l["price"] - current_price)
    )[:n_levels + 2]
    resistances = sorted(
        [l for l in clustered if l["type"] == "resistance" or l["type"].startswith("ma")],
        key=lambda l: abs(l["price"] - current_price)
    )[:n_levels + 2]

    # Deduplicate
    seen = set()
    final = []
    for l in supports + resistances:
        key = round(l["price"], 1)
        if key not in seen:
            seen.add(key)
            final.append(l)

    return sorted(final, key=lambda l: l["price"])


def build_html(symbols_data):
    """Generate a self-contained HTML dashboard."""

    # Build chart data for each symbol
    charts_json = []
    for sd in symbols_data:
        df = sd["df"]
        dates = df["date"].astype(str).tolist()
        ohlc = {
            "dates": dates,
            "open": df["open"].round(2).tolist(),
            "high": df["high"].round(2).tolist(),
            "low": df["low"].round(2).tolist(),
            "close": df["close"].round(2).tolist(),
            "volume": df["volume"].tolist(),
        }

        # Compute BB bands for chart
        close_series = df["close"]
        ma20 = close_series.rolling(20).mean()
        std20 = close_series.rolling(20).std()
        bb_upper = (ma20 + 2 * std20).round(2).tolist()
        bb_lower = (ma20 - 2 * std20).round(2).tolist()
        ma20_vals = ma20.round(2).tolist()
        ma50_vals = close_series.rolling(50).mean().round(2).tolist()

        # Volume MA
        vol_ma = df["volume"].rolling(20).mean().tolist()

        charts_json.append({
            "symbol": sd["symbol"],
            "price": sd["price"],
            "ohlc": ohlc,
            "bb_upper": bb_upper,
            "bb_lower": bb_lower,
            "ma20": ma20_vals,
            "ma50": ma50_vals,
            "vol_ma": vol_ma,
            "levels": sd["levels"],
            "combo": sd["combo"],
            "combo_hit": sd["combo_hit"],
            "n_combos": sd["n_combos"],
            "kelly": sd["kelly"],
            "rsi": sd["rsi"],
            "drawdown": sd["drawdown"],
            "ret_5d": sd["ret_5d"],
            "ret_20d": sd["ret_20d"],
            "vol_zscore": sd["vol_zscore"],
            "vol_ratio": sd["vol_ratio"],
            "reversal_score": sd["reversal_score"],
            "reasons": sd["reasons"],
        })

    data_json = json.dumps(charts_json)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Alpha Predator — Swing Reversal Dashboard</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  :root {{
    --bg-primary: #0a0e17;
    --bg-card: #111827;
    --bg-card-hover: #1a2332;
    --border: #1e293b;
    --text-primary: #e2e8f0;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --accent-green: #22c55e;
    --accent-red: #ef4444;
    --accent-blue: #3b82f6;
    --accent-purple: #a855f7;
    --accent-amber: #f59e0b;
    --accent-cyan: #06b6d4;
    --glow-green: rgba(34, 197, 94, 0.15);
    --glow-blue: rgba(59, 130, 246, 0.15);
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Inter', sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    min-height: 100vh;
    overflow-x: hidden;
  }}

  /* Header */
  .header {{
    background: linear-gradient(135deg, rgba(17,24,39,0.95), rgba(10,14,23,0.98));
    border-bottom: 1px solid var(--border);
    padding: 20px 40px;
    display: flex; align-items: center; justify-content: space-between;
    backdrop-filter: blur(20px);
    position: sticky; top: 0; z-index: 100;
  }}
  .header h1 {{
    font-size: 22px; font-weight: 700; letter-spacing: -0.5px;
    background: linear-gradient(135deg, var(--accent-cyan), var(--accent-blue), var(--accent-purple));
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }}
  .header .subtitle {{ color: var(--text-muted); font-size: 13px; margin-top: 2px; }}
  .header .timestamp {{ color: var(--text-muted); font-size: 12px; }}

  /* Summary bar */
  .summary-bar {{
    display: flex; gap: 16px; padding: 16px 40px;
    background: var(--bg-card); border-bottom: 1px solid var(--border);
    overflow-x: auto;
  }}
  .stat-pill {{
    display: flex; flex-direction: column; align-items: center;
    background: rgba(30,41,59,0.5); border: 1px solid var(--border);
    border-radius: 12px; padding: 12px 20px; min-width: 130px;
  }}
  .stat-pill .label {{ font-size: 10px; text-transform: uppercase; letter-spacing: 1px; color: var(--text-muted); }}
  .stat-pill .value {{ font-size: 22px; font-weight: 700; margin-top: 4px; }}
  .stat-pill .value.green {{ color: var(--accent-green); }}
  .stat-pill .value.blue {{ color: var(--accent-blue); }}
  .stat-pill .value.purple {{ color: var(--accent-purple); }}
  .stat-pill .value.amber {{ color: var(--accent-amber); }}

  /* Symbol selector */
  .symbol-nav {{
    display: flex; gap: 8px; padding: 16px 40px; flex-wrap: wrap;
    border-bottom: 1px solid var(--border);
  }}
  .sym-btn {{
    padding: 8px 16px; border-radius: 8px; cursor: pointer;
    border: 1px solid var(--border); background: var(--bg-card);
    color: var(--text-secondary); font-size: 13px; font-weight: 600;
    transition: all 0.2s;
  }}
  .sym-btn:hover {{ background: var(--bg-card-hover); color: var(--text-primary); }}
  .sym-btn.active {{
    background: linear-gradient(135deg, rgba(59,130,246,0.2), rgba(168,85,247,0.2));
    border-color: var(--accent-blue); color: var(--text-primary);
    box-shadow: 0 0 15px var(--glow-blue);
  }}
  .sym-btn .combo-dot {{
    display: inline-block; width: 6px; height: 6px; border-radius: 50%;
    margin-left: 6px; vertical-align: middle;
  }}
  .sym-btn .combo-dot.green {{ background: var(--accent-green); box-shadow: 0 0 6px var(--accent-green); }}
  .sym-btn .combo-dot.amber {{ background: var(--accent-amber); box-shadow: 0 0 6px var(--accent-amber); }}

  /* Main content */
  .main {{ padding: 24px 40px; }}

  /* Info cards row */
  .info-row {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 12px; margin-bottom: 20px;
  }}
  .info-card {{
    background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px;
    padding: 16px; position: relative; overflow: hidden;
  }}
  .info-card::before {{
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
  }}
  .info-card.green::before {{ background: linear-gradient(90deg, var(--accent-green), transparent); }}
  .info-card.red::before {{ background: linear-gradient(90deg, var(--accent-red), transparent); }}
  .info-card.blue::before {{ background: linear-gradient(90deg, var(--accent-blue), transparent); }}
  .info-card.purple::before {{ background: linear-gradient(90deg, var(--accent-purple), transparent); }}
  .info-card.amber::before {{ background: linear-gradient(90deg, var(--accent-amber), transparent); }}
  .info-card .card-label {{ font-size: 10px; text-transform: uppercase; letter-spacing: 1px; color: var(--text-muted); }}
  .info-card .card-value {{ font-size: 24px; font-weight: 700; margin-top: 6px; }}
  .info-card .card-detail {{ font-size: 12px; color: var(--text-secondary); margin-top: 4px; }}

  /* Chart container */
  .chart-container {{
    background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px;
    padding: 8px; margin-bottom: 20px;
  }}

  /* Signals list */
  .signals-card {{
    background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px;
    padding: 20px;
  }}
  .signals-card h3 {{ font-size: 14px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px; }}
  .signal-tag {{
    display: inline-block; padding: 6px 12px; border-radius: 6px; margin: 3px;
    font-size: 12px; font-weight: 600;
    background: rgba(59,130,246,0.1); border: 1px solid rgba(59,130,246,0.3); color: var(--accent-blue);
  }}
  .signal-tag.green {{ background: rgba(34,197,94,0.1); border-color: rgba(34,197,94,0.3); color: var(--accent-green); }}
  .signal-tag.red {{ background: rgba(239,68,68,0.1); border-color: rgba(239,68,68,0.3); color: var(--accent-red); }}
  .signal-tag.amber {{ background: rgba(245,158,11,0.1); border-color: rgba(245,158,11,0.3); color: var(--accent-amber); }}

  /* Resistance/Support levels table */
  .levels-grid {{
    display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 20px;
  }}
  .level-item {{
    display: flex; align-items: center; justify-content: space-between;
    padding: 10px 14px; border-radius: 8px; font-size: 13px;
  }}
  .level-item.resistance {{
    background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.2);
  }}
  .level-item.support {{
    background: rgba(34,197,94,0.08); border: 1px solid rgba(34,197,94,0.2);
  }}
  .level-item.ma {{
    background: rgba(168,85,247,0.08); border: 1px solid rgba(168,85,247,0.2);
  }}
  .level-item .level-label {{ color: var(--text-secondary); }}
  .level-item .level-price {{ font-weight: 700; font-family: 'SF Mono', monospace; }}
  .level-item.resistance .level-price {{ color: var(--accent-red); }}
  .level-item.support .level-price {{ color: var(--accent-green); }}
  .level-item.ma .level-price {{ color: var(--accent-purple); }}

  /* Disclaimer */
  .disclaimer {{
    text-align: center; padding: 20px 40px; color: var(--text-muted);
    font-size: 11px; border-top: 1px solid var(--border); margin-top: 40px;
  }}

  .combo-badge {{
    display: inline-block; padding: 4px 12px; border-radius: 20px;
    font-size: 12px; font-weight: 700;
    background: linear-gradient(135deg, rgba(34,197,94,0.2), rgba(34,197,94,0.05));
    border: 1px solid rgba(34,197,94,0.4); color: var(--accent-green);
  }}

  @media (max-width: 768px) {{
    .header, .summary-bar, .symbol-nav, .main {{ padding-left: 16px; padding-right: 16px; }}
    .info-row {{ grid-template-columns: repeat(2, 1fr); }}
    .levels-grid {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>ALPHA PREDATOR</h1>
    <div class="subtitle">Swing Reversal Scanner — Bottomed Stocks Reversing With Strength</div>
  </div>
  <div class="timestamp">{datetime.now().strftime('%B %d, %Y %I:%M %p')}</div>
</div>

<div class="summary-bar" id="summaryBar"></div>
<div class="symbol-nav" id="symbolNav"></div>
<div class="main" id="mainContent"></div>

<div class="disclaimer">
  Alpha Predator is an educational research tool. Past performance does not guarantee future results.
  All signals are generated algorithmically and should not be considered financial advice. Do your own research.
</div>

<script>
const DATA = {data_json};

let activeSymbol = 0;

function init() {{
  buildSummary();
  buildNav();
  renderSymbol(0);
}}

function buildSummary() {{
  const bar = document.getElementById('summaryBar');
  const comboConfirmed = DATA.filter(d => d.n_combos > 0).length;
  const avgRev = Math.round(DATA.reduce((s,d) => s + d.reversal_score, 0) / DATA.length);
  const topHit = Math.max(...DATA.map(d => d.combo_hit)) * 100;
  const deepDD = DATA.filter(d => d.drawdown >= 30).length;

  bar.innerHTML = `
    <div class="stat-pill"><span class="label">Candidates</span><span class="value blue">${{DATA.length}}</span></div>
    <div class="stat-pill"><span class="label">Combo Confirmed</span><span class="value green">${{comboConfirmed}}</span></div>
    <div class="stat-pill"><span class="label">Avg Rev Score</span><span class="value purple">${{avgRev}}</span></div>
    <div class="stat-pill"><span class="label">Best Hit Rate</span><span class="value green">${{topHit.toFixed(1)}}%</span></div>
    <div class="stat-pill"><span class="label">Deep Drawdown</span><span class="value amber">${{deepDD}}</span></div>
  `;
}}

function buildNav() {{
  const nav = document.getElementById('symbolNav');
  nav.innerHTML = DATA.map((d, i) => {{
    const dotClass = d.n_combos >= 5 ? 'green' : d.n_combos > 0 ? 'amber' : '';
    const dot = dotClass ? `<span class="combo-dot ${{dotClass}}"></span>` : '';
    return `<button class="sym-btn ${{i === 0 ? 'active' : ''}}" onclick="selectSymbol(${{i}})" id="btn-${{i}}">
      ${{d.symbol}} ${{dot}}
    </button>`;
  }}).join('');
}}

function selectSymbol(idx) {{
  document.querySelectorAll('.sym-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('btn-' + idx).classList.add('active');
  activeSymbol = idx;
  renderSymbol(idx);
}}

function renderSymbol(idx) {{
  const d = DATA[idx];
  const main = document.getElementById('mainContent');

  const comboHtml = d.combo
    ? `<span class="combo-badge">${{d.combo}} (${{(d.combo_hit*100).toFixed(1)}}%)</span>`
    : '<span style="color:var(--text-muted)">No combo match</span>';

  const retColor5d = d.ret_5d >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
  const retColor20d = d.ret_20d >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';

  // Levels HTML
  const currentPrice = d.price;
  const resistances = d.levels.filter(l => l.price > currentPrice).sort((a,b) => a.price - b.price);
  const supports = d.levels.filter(l => l.price <= currentPrice).sort((a,b) => b.price - a.price);

  const levelsHtml = `
    <div class="levels-grid">
      <div>
        <h3 style="font-size:12px;color:var(--accent-red);margin-bottom:8px;">RESISTANCE</h3>
        ${{resistances.length ? resistances.map(l => `
          <div class="level-item ${{l.type.startsWith('ma') ? 'ma' : 'resistance'}}">
            <span class="level-label">${{l.type.startsWith('ma') ? l.type.toUpperCase() : 'R' + (l.touches||'')}}</span>
            <span class="level-price">$${{l.price.toFixed(2)}}</span>
            <span style="color:var(--text-muted);font-size:11px">${{((l.price/currentPrice-1)*100).toFixed(1)}}%</span>
          </div>`).join('') : '<div style="color:var(--text-muted);font-size:12px;padding:8px">None nearby</div>'}}
      </div>
      <div>
        <h3 style="font-size:12px;color:var(--accent-green);margin-bottom:8px;">SUPPORT</h3>
        ${{supports.length ? supports.map(l => `
          <div class="level-item ${{l.type.startsWith('ma') ? 'ma' : 'support'}}">
            <span class="level-label">${{l.type.startsWith('ma') ? l.type.toUpperCase() : 'S' + (l.touches||'')}}</span>
            <span class="level-price">$${{l.price.toFixed(2)}}</span>
            <span style="color:var(--text-muted);font-size:11px">${{((l.price/currentPrice-1)*100).toFixed(1)}}%</span>
          </div>`).join('') : '<div style="color:var(--text-muted);font-size:12px;padding:8px">None nearby</div>'}}
      </div>
    </div>`;

  const signalTags = d.reasons.map(r => {{
    let cls = 'blue';
    if (r.toLowerCase().includes('drawdown') || r.toLowerCase().includes('oversold')) cls = 'red';
    if (r.toLowerCase().includes('bounce') || r.toLowerCase().includes('reversal')) cls = 'green';
    if (r.toLowerCase().includes('vol')) cls = 'amber';
    return `<span class="signal-tag ${{cls}}">${{r}}</span>`;
  }}).join('');

  main.innerHTML = `
    <div class="info-row">
      <div class="info-card blue">
        <div class="card-label">Price</div>
        <div class="card-value">$${{d.price.toFixed(2)}}</div>
        <div class="card-detail" style="color:${{retColor5d}}">5d: ${{d.ret_5d >= 0 ? '+' : ''}}${{d.ret_5d.toFixed(1)}}%</div>
      </div>
      <div class="info-card ${{d.reversal_score >= 60 ? 'green' : d.reversal_score >= 40 ? 'amber' : 'blue'}}">
        <div class="card-label">Reversal Score</div>
        <div class="card-value">${{d.reversal_score}}</div>
        <div class="card-detail">${{d.reversal_score >= 70 ? 'Strong' : d.reversal_score >= 50 ? 'Moderate' : 'Early'}}</div>
      </div>
      <div class="info-card red">
        <div class="card-label">Drawdown</div>
        <div class="card-value" style="color:var(--accent-red)">${{d.drawdown.toFixed(0)}}%</div>
        <div class="card-detail" style="color:${{retColor20d}}">20d: ${{d.ret_20d >= 0 ? '+' : ''}}${{d.ret_20d.toFixed(1)}}%</div>
      </div>
      <div class="info-card purple">
        <div class="card-label">RSI</div>
        <div class="card-value">${{d.rsi.toFixed(1)}}</div>
        <div class="card-detail">${{d.rsi < 30 ? 'Oversold' : d.rsi < 50 ? 'Setup zone' : 'Neutral'}}</div>
      </div>
      <div class="info-card amber">
        <div class="card-label">Volume</div>
        <div class="card-value">${{d.vol_ratio.toFixed(1)}}x</div>
        <div class="card-detail">Vol Z: ${{d.vol_zscore.toFixed(2)}}</div>
      </div>
      <div class="info-card green">
        <div class="card-label">Best Combo</div>
        <div class="card-value" style="font-size:16px">${{comboHtml}}</div>
        <div class="card-detail">${{d.n_combos}} combo(s) | Kelly ${{d.kelly.toFixed(1)}}%</div>
      </div>
    </div>

    <div class="chart-container"><div id="priceChart"></div></div>
    <div class="chart-container"><div id="volumeChart"></div></div>

    <div class="signals-card">
      <h3>Active Signals</h3>
      <div style="margin-bottom:16px">${{signalTags}}</div>
      ${{levelsHtml}}
    </div>
  `;

  renderCharts(d);
}}

function renderCharts(d) {{
  const dates = d.ohlc.dates.slice(-120);
  const oOpen = d.ohlc.open.slice(-120);
  const oHigh = d.ohlc.high.slice(-120);
  const oLow = d.ohlc.low.slice(-120);
  const oClose = d.ohlc.close.slice(-120);
  const vol = d.ohlc.volume.slice(-120);
  const bbUp = d.bb_upper.slice(-120);
  const bbLow = d.bb_lower.slice(-120);
  const ma20 = d.ma20.slice(-120);
  const ma50 = d.ma50.slice(-120);
  const volMA = d.vol_ma.slice(-120);
  const currentPrice = d.price;

  // S/R level shapes
  const shapes = d.levels.map(l => ({{
    type: 'line', xref: 'paper', x0: 0, x1: 1, y0: l.price, y1: l.price,
    line: {{
      color: l.type === 'resistance' ? 'rgba(239,68,68,0.5)'
           : l.type.startsWith('ma') ? 'rgba(168,85,247,0.4)'
           : 'rgba(34,197,94,0.5)',
      width: l.type.startsWith('ma') ? 1 : 1.5,
      dash: l.type.startsWith('ma') ? 'dot' : 'dash',
    }}
  }}));

  // S/R annotations
  const annotations = d.levels.map(l => ({{
    x: dates[dates.length - 1], y: l.price, xanchor: 'left',
    text: ` ${{l.type.startsWith('ma') ? l.type.toUpperCase() : (l.price > currentPrice ? 'R' : 'S')}} $${{l.price.toFixed(2)}}`,
    showarrow: false,
    font: {{
      size: 10,
      color: l.type === 'resistance' ? '#ef4444' : l.type.startsWith('ma') ? '#a855f7' : '#22c55e',
    }},
    bgcolor: 'rgba(10,14,23,0.8)', borderpad: 2,
  }}));

  // Candlestick chart
  const candlestick = {{
    x: dates, open: oOpen, high: oHigh, low: oLow, close: oClose,
    type: 'candlestick', name: d.symbol,
    increasing: {{ line: {{ color: '#22c55e' }}, fillcolor: '#22c55e' }},
    decreasing: {{ line: {{ color: '#ef4444' }}, fillcolor: '#ef4444' }},
  }};

  const bbUpperTrace = {{
    x: dates, y: bbUp, type: 'scatter', mode: 'lines', name: 'BB Upper',
    line: {{ color: 'rgba(59,130,246,0.3)', width: 1 }}, showlegend: false,
  }};
  const bbLowerTrace = {{
    x: dates, y: bbLow, type: 'scatter', mode: 'lines', name: 'BB Lower',
    fill: 'tonexty', fillcolor: 'rgba(59,130,246,0.05)',
    line: {{ color: 'rgba(59,130,246,0.3)', width: 1 }}, showlegend: false,
  }};
  const ma20Trace = {{
    x: dates, y: ma20, type: 'scatter', mode: 'lines', name: 'MA20',
    line: {{ color: 'rgba(245,158,11,0.6)', width: 1.5, dash: 'dot' }},
  }};
  const ma50Trace = {{
    x: dates, y: ma50, type: 'scatter', mode: 'lines', name: 'MA50',
    line: {{ color: 'rgba(168,85,247,0.6)', width: 1.5, dash: 'dot' }},
  }};

  Plotly.newPlot('priceChart',
    [bbLowerTrace, bbUpperTrace, candlestick, ma20Trace, ma50Trace],
    {{
      title: {{ text: `${{d.symbol}} — Price Action & S/R Levels`, font: {{ color: '#e2e8f0', size: 14 }} }},
      paper_bgcolor: '#111827', plot_bgcolor: '#0a0e17',
      xaxis: {{ color: '#64748b', gridcolor: '#1e293b', rangeslider: {{ visible: false }},
        type: 'date' }},
      yaxis: {{ color: '#64748b', gridcolor: '#1e293b', side: 'right' }},
      shapes: shapes, annotations: annotations,
      margin: {{ l: 10, r: 80, t: 40, b: 30 }},
      height: 450,
      legend: {{ font: {{ color: '#94a3b8', size: 10 }}, bgcolor: 'rgba(0,0,0,0)', x: 0, y: 1 }},
    }},
    {{ responsive: true }}
  );

  // Volume chart
  const volColors = oClose.map((c, i) => c >= (oOpen[i]||c) ? 'rgba(34,197,94,0.6)' : 'rgba(239,68,68,0.6)');
  const volBar = {{
    x: dates, y: vol, type: 'bar', name: 'Volume',
    marker: {{ color: volColors }},
  }};
  const volMATrace = {{
    x: dates, y: volMA, type: 'scatter', mode: 'lines', name: '20d Avg',
    line: {{ color: 'rgba(245,158,11,0.7)', width: 2 }},
  }};

  Plotly.newPlot('volumeChart',
    [volBar, volMATrace],
    {{
      title: {{ text: 'Volume Profile', font: {{ color: '#e2e8f0', size: 14 }} }},
      paper_bgcolor: '#111827', plot_bgcolor: '#0a0e17',
      xaxis: {{ color: '#64748b', gridcolor: '#1e293b', type: 'date' }},
      yaxis: {{ color: '#64748b', gridcolor: '#1e293b', side: 'right' }},
      margin: {{ l: 10, r: 80, t: 40, b: 30 }},
      height: 200,
      bargap: 0.3,
      showlegend: false,
    }},
    {{ responsive: true }}
  );
}}

window.addEventListener('load', init);
</script>
</body>
</html>"""
    return html


def main():
    setup_logging(log_level="WARNING", name="apredator")
    print("Fetching data for top reversal candidates...")

    df_all = fetch_prices(TOP_SYMBOLS, period="1y")
    if df_all.empty:
        print("Failed to fetch prices.")
        return

    print(f"Got data for {df_all['symbol'].nunique()} symbols")

    symbols_data = []
    for symbol in TOP_SYMBOLS:
        sym_df = df_all[df_all["symbol"] == symbol].sort_values("date").reset_index(drop=True)
        if len(sym_df) < 60:
            continue

        tech = compute_all_technical(sym_df)
        explosive = compute_all_explosive(sym_df)
        combos = match_combos(explosive)
        levels = compute_support_resistance(sym_df)
        best_combo = max(combos, key=lambda c: c["hit_rate"]) if combos else None

        close = sym_df["close"].iloc[-1]
        close_5d = sym_df["close"].iloc[-6] if len(sym_df) > 5 else close
        close_20d = sym_df["close"].iloc[-21] if len(sym_df) > 20 else close
        ret_5d = (close - close_5d) / close_5d * 100
        ret_20d = (close - close_20d) / close_20d * 100
        drawdown = explosive.get("drawdown_60d", 0)
        rsi = tech.get("rsi_14", 50)
        vol_ratio = tech.get("volume_ratio_20d", 1.0)
        vol_zscore = explosive.get("vol_zscore", 0)

        rev_score = 0
        reasons = []
        if drawdown >= 40:
            rev_score += 25; reasons.append(f"Deep drawdown {drawdown:.0f}%")
        elif drawdown >= 25:
            rev_score += 18; reasons.append(f"Drawdown {drawdown:.0f}%")
        elif drawdown >= 15:
            rev_score += 10; reasons.append(f"Pullback {drawdown:.0f}%")
        if 30 <= rsi <= 50:
            rev_score += 15; reasons.append(f"RSI setup {rsi:.0f}")
        elif rsi < 30:
            rev_score += 10; reasons.append(f"RSI oversold {rsi:.0f}")
        if ret_5d > 3 and ret_20d < 0:
            rev_score += 20; reasons.append(f"Bounce +{ret_5d:.1f}%")
        elif ret_5d > 1 and ret_20d < -5:
            rev_score += 15; reasons.append(f"Early reversal +{ret_5d:.1f}%")
        if vol_ratio >= 2.0:
            rev_score += 15; reasons.append(f"Vol surge {vol_ratio:.1f}x")
        elif vol_ratio >= 1.3:
            rev_score += 8; reasons.append(f"Vol rising {vol_ratio:.1f}x")
        if vol_zscore >= 0.15:
            rev_score += 10; reasons.append(f"Vol z={vol_zscore:.2f}")
        if explosive.get("rejection_wick", 0) >= 1.0:
            rev_score += 8; reasons.append("Rejection wicks")
        if explosive.get("low_in_range", 0):
            rev_score += 5; reasons.append("Low in range")
        bb_width = tech.get("bb_width_pct", 10)
        if bb_width < 5:
            rev_score += 8; reasons.append(f"BB squeeze {bb_width:.1f}%")

        kelly = kelly_position_size(best_combo["hit_rate"]) * 100 if best_combo else 0

        symbols_data.append({
            "symbol": symbol,
            "price": round(float(close), 2),
            "df": sym_df,
            "levels": levels,
            "combo": best_combo["name"] if best_combo else None,
            "combo_hit": best_combo["hit_rate"] if best_combo else 0,
            "n_combos": len(combos),
            "kelly": kelly,
            "rsi": round(float(rsi), 1),
            "drawdown": round(float(drawdown), 1),
            "ret_5d": round(float(ret_5d), 1),
            "ret_20d": round(float(ret_20d), 1),
            "vol_zscore": round(float(vol_zscore), 2),
            "vol_ratio": round(float(vol_ratio), 1),
            "reversal_score": rev_score,
            "reasons": reasons,
        })

    # Sort: combo-confirmed first, then by reversal score
    symbols_data.sort(key=lambda d: (d["n_combos"] > 0, d["reversal_score"]), reverse=True)

    print(f"Building dashboard for {len(symbols_data)} symbols...")
    html = build_html(symbols_data)

    out_path = Path(__file__).parent.parent / "dashboard_output.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"Dashboard saved to {out_path}")

    webbrowser.open(f"file://{out_path.resolve()}")
    print("Opened in browser.")


if __name__ == "__main__":
    main()
