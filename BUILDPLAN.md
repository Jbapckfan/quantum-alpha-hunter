# Quantum Alpha Hunter v2.1 — Build Plan

## Feature 1: Live Alert Pipeline (ntfy.sh)

### Files to create/modify:
- **NEW** `qaht/alerts/__init__.py`
- **NEW** `qaht/alerts/ntfy.py` — ntfy.sh push notification client
- **NEW** `qaht/alerts/scheduler.py` — APScheduler loop (30-min interval)
- **NEW** `qaht/alerts/alert_types.py` — Alert dataclasses (ComboAlert, TrapClearedAlert, Tier1Alert, NewHighConfAlert)
- **MODIFY** `qaht/api/main.py` — Add /api/alerts endpoints (GET status, POST start/stop, GET history)
- **MODIFY** `docker-compose.yml` — Add NTFY_TOPIC env var

### Implementation details:
- `NtfyClient` class: POST to `https://ntfy.sh/{topic}` with title, body, priority, tags, click URL
- Topic: configurable via `NTFY_TOPIC` env var, default `james-qah-alerts`
- `AlertScheduler` class using APScheduler `BackgroundScheduler`:
  - Every 30 min: run `StockSignalDetector.scan_universe()` on the default universe
  - Compare results to previous scan (stored in memory/SQLite `alert_history` table)
  - Fire alert when: new combo activates, score crosses 70+ threshold, trap clears (was unmitigated, now mitigated by volume), Tier 1 eligible stock appears
  - Rate limit: max 10 alerts per hour, deduplicate by ticker+alert_type within 4 hours
- Alert format: `"{ticker}: {combo_name} combo active — {hit_rate}% hit rate — Entry ${price}, Stop ${stop}, T1 ${t1}"`
- Priority mapping: Tier1 = urgent (5), Combo = high (4), HighConf = default (3)
- Store alert history in new `alert_history` SQLite table (ticker, alert_type, timestamp, data JSON)
- API endpoints: GET /api/alerts/status (running/paused, last_scan, next_scan, alert_count), POST /api/alerts/start, POST /api/alerts/stop, GET /api/alerts/history?limit=50

---

## Feature 2: Outcome Tracking + Self-Tuning Weights

### Files to create/modify:
- **NEW** `qaht/tracking/__init__.py`
- **NEW** `qaht/tracking/outcome_tracker.py` — Track signal outcomes over 30 days
- **NEW** `qaht/tracking/weight_tuner.py` — Auto-adjust signal weights from outcomes
- **MODIFY** `qaht/schemas.py` — Add `signal_events` and `signal_outcomes` tables
- **MODIFY** `qaht/api/main.py` — Add /api/tracking endpoints

### Implementation details:
- `signal_events` table: id, ticker, signal_name, fired_date, entry_price, score_at_fire, combo_matched (nullable)
- `signal_outcomes` table: id, event_id FK, check_date, price_at_check, return_pct, hit_t1 bool, hit_t2 bool, hit_t3 bool, hit_stop bool, days_elapsed
- `OutcomeTracker` class:
  - `record_signals(scan_results)` — When scanner runs, log every signal that fires with entry price
  - `check_outcomes()` — Daily job: for all open events older than 5 days, fetch current price, compute return, check if T1/T2/T3/stop hit
  - `mark_completed(event_id)` — After 30 days or stop hit, mark event as final
  - `get_signal_stats(lookback_days=90)` — Return per-signal hit rates, avg return, win rate
- `WeightTuner` class:
  - `compute_adjusted_weights(lookback_days=90)` — For each signal:
    - Count how many times it fired in lookback period
    - Compute: hit_rate = (times T1 hit) / (times fired)
    - Compute: avg_return = mean return after 30 days
    - New weight = base_weight * (1 + (hit_rate - 0.5) * 2) — signals above 50% hit rate get boosted, below get penalized
    - Floor: 0.25 * base_weight, Ceiling: 2.0 * base_weight
  - `apply_tuned_weights()` — Save adjusted weights to the weights JSON file
  - `get_weight_drift_report()` — Show which signals improved/degraded vs baseline
- Integrate with alert scheduler: after each scan, call `record_signals()`; daily at midnight, call `check_outcomes()`
- API: GET /api/tracking/stats (per-signal hit rates), GET /api/tracking/drift (weight changes), POST /api/tracking/tune (apply tuned weights)

---

## Feature 3: Walk-Forward Backtester with Equity Curves

### Files to create/modify:
- **NEW** `qaht/backtest/simulator.py` — Walk-forward backtesting engine
- **NEW** `qaht/backtest/metrics.py` — Performance metrics (Sharpe, Sortino, max DD, etc.)
- **MODIFY** `qaht/api/main.py` — Add /api/backtest endpoints

### Implementation details:
- `BacktestSimulator` class:
  - `run(tickers, start_date, end_date, initial_capital=100000)`:
    - Fetch historical OHLCV for all tickers across date range
    - Walk forward day by day:
      1. Run signal detector on data available up to current day (no lookahead)
      2. Score each ticker, check for combo matches
      3. If combo fires + score > threshold → enter position (Kelly-sized)
      4. For open positions: check if price hit stop, T1, T2, or T3 → execute exit rules
      5. Track: cash, positions, daily portfolio value
    - Output: list of trades (entry, exit, return, days held, combo used), daily equity curve
  - Position management: respect Kelly sizing, max 30% allocation, max 3 per sector
  - No lookahead bias: only use data available on each simulation day
- `BacktestMetrics` class:
  - `compute(equity_curve, trades)` → returns:
    - Total return, CAGR
    - Sharpe ratio (risk-free rate = 4.5%)
    - Sortino ratio
    - Max drawdown (% and duration)
    - Win rate (T1+ hit / total trades)
    - Average winner vs average loser
    - Profit factor (gross wins / gross losses)
    - Expectancy per trade
    - By-combo breakdown: hit rate, avg return, count for each of the 7 combos
    - Monthly returns heatmap data
  - `to_dict()` — Serializable output for API/frontend
- API: POST /api/backtest/run (body: tickers, start, end, capital) → returns metrics + equity curve + trades
- Store backtest results in `backtest_runs` table for comparison

---

## Feature 4: Options Flow Anomaly Detection

### Files to create/modify:
- **NEW** `qaht/options/flow_detector.py` — Unusual options activity scanner
- **MODIFY** `qaht/api/main.py` — Add /api/options/flow endpoints

### Implementation details:
- `FlowDetector` class (uses PolygonAdapter):
  - `scan_unusual_activity(tickers, min_score=3)`:
    - For each ticker, fetch options chain via Polygon
    - For each contract, compute:
      - `vol_oi_ratio` = volume / open_interest (>5 = unusual)
      - `dollar_volume` = volume * mid_price * 100 (>$500K = large)
      - `iv_percentile` = current IV vs 30-day IV range (>80th = elevated)
      - `otm_pct` = how far OTM the strike is (>10% OTM with high volume = speculative)
    - Score each contract: vol_oi_ratio > 5 (+3), dollar_volume > 1M (+2), dollar_volume > 500K (+1), iv_percentile > 80 (+2), otm_pct > 15% (+2), otm_pct > 10% (+1), near-term expiry < 14 DTE (+1)
    - Aggregate per ticker: sum top 3 contract scores, note dominant direction (calls vs puts by dollar volume)
  - `detect_iv_skew_anomaly(ticker)`:
    - Compare 25-delta put IV to 25-delta call IV
    - If skew changes by >5% in one day → flag
  - `detect_block_trades(ticker)`:
    - Any single contract with volume > 10x avg daily volume → flag as block trade
- Output: `FlowAlert` dataclass with ticker, direction (bullish/bearish), score, top_contracts (list), total_dollar_volume, dominant_expiry
- API: GET /api/options/flow?min_score=3 — returns ranked list of tickers with unusual flow
- Integrate with alert scheduler: if flow_score > 6 AND technical score > 100 → fire "Dark Flow + Technical Confluence" alert

---

## Feature 5: AI Trade Thesis Generator

### Files to create/modify:
- **NEW** `qaht/ai/__init__.py`
- **NEW** `qaht/ai/thesis_generator.py` — LLM-powered trade thesis

### Implementation details:
- `ThesisGenerator` class:
  - `__init__(provider="openrouter", model="meta-llama/llama-3.3-70b-instruct:free")` — uses OPENROUTER_API_KEY env var
  - `generate(scan_result, resistance_levels, combo_result=None)`:
    - Build prompt with structured data:
      ```
      Ticker: {ticker}, Price: ${price}, Score: {score}, Stage: {stage}
      Signals: {top 5 signals with weights}
      Resistance: {top 3 levels with strength and methods}
      Combo: {combo name and hit rate if active}
      Trap warnings: {any traps}
      Exit plan: Stop ${stop}, T1 ${t1}, T2 ${t2}, T3 ${t3}
      ```
    - System prompt: "You are a concise technical analyst. Write a 3-sentence trade thesis. Sentence 1: the setup (what happened). Sentence 2: the catalyst (what's changing). Sentence 3: the trade (entry, target, risk). No disclaimers."
    - POST to OpenRouter API (OpenAI-compatible endpoint)
    - Return: thesis string (3 sentences)
  - `batch_generate(high_confidence_results)` — Generate thesis for top 5 plays
- Use httpx with 15-second timeout, retry once on failure
- Cache thesis for 4 hours per ticker (avoid re-generating on every scan)
- API: GET /api/thesis/{ticker} — returns thesis + scan data + resistance
- Integrate with alerts: include thesis in ntfy notification body for high-conviction plays

---

## Feature 6: Multi-Timeframe Confluence

### Files to create/modify:
- **NEW** `qaht/signals/multiframe.py` — Multi-timeframe analysis
- **MODIFY** `qaht/signals/detector.py` — Add timeframe parameter support

### Implementation details:
- `MultiFrameAnalyzer` class:
  - `analyze(ticker)`:
    - Fetch 3 timeframes from yfinance:
      - Weekly: `yf.download(ticker, period="2y", interval="1wk")`
      - Daily: `yf.download(ticker, period="1y", interval="1d")` (existing)
      - 4-hour: `yf.download(ticker, period="60d", interval="1h")` then resample to 4H
    - Run signal detection on each timeframe independently
    - Compute alignment score:
      - For each signal category (MA, RSI, MACD, volume, momentum):
        - If bullish on all 3 timeframes: +3 (strong alignment)
        - If bullish on 2 of 3: +1 (partial alignment)
        - If conflicting (bullish daily, bearish weekly): -1 (divergence)
      - Total alignment score: sum across categories (-15 to +15)
    - Confluence multiplier:
      - Alignment >= 10: 2.0x score multiplier (strong multi-TF confluence)
      - Alignment >= 6: 1.5x
      - Alignment >= 3: 1.2x
      - Alignment < 0: 0.7x (conflicting timeframes = danger)
  - `get_timeframe_breakdown(ticker)` — Detailed per-TF signal matrix
- Apply multiplier to the final scan score in `StockSignalDetector.scan()`
- API: GET /api/analyze/{ticker}/multiframe — returns per-TF signals + alignment score
- Flag in scan results: "MTF_ALIGNED" when alignment >= 6

---

## Feature 7: Earnings Catalyst Integration

### Files to create/modify:
- **NEW** `qaht/signals/earnings.py` — Earnings calendar + pre-earnings plays
- **MODIFY** `qaht/signals/detector.py` — Add earnings proximity signals
- **MODIFY** `qaht/api/main.py` — Add /api/earnings endpoints

### Implementation details:
- `EarningsAnalyzer` class:
  - `get_upcoming_earnings(tickers, days_ahead=14)`:
    - Use yfinance `Ticker.calendar` to get next earnings date
    - Return list of (ticker, earnings_date, days_until) sorted by date
  - `compute_earnings_context(ticker)`:
    - Days until earnings
    - Historical earnings moves: last 4 quarters avg absolute move %
    - Current IV vs historical pre-earnings IV (IV expansion check)
    - Pre-earnings drift: avg return in 10 days before earnings over last 4 quarters
    - Post-earnings drift: avg return in 5 days after earnings
  - `flag_earnings_plays(scan_results)`:
    - For each scanned ticker, check if earnings within 5-14 days
    - If yes AND technical score > 100 AND stage is EARLY/MID:
      - Add `earnings_catalyst` signal (+15 points)
      - Add earnings context to result metadata
    - If earnings within 0-2 days:
      - Add `earnings_imminent_warning` flag (-5 points for stock plays, +5 for straddles)
  - `estimate_iv_crush(ticker)`:
    - Compare current ATM IV to historical realized move
    - If IV implies 10% move but historical avg is 5% → IV is rich, avoid long options
    - If IV implies 5% but historical avg is 10% → IV is cheap, buy straddles
- API: GET /api/earnings/upcoming?days=14 — upcoming earnings with context
- API: GET /api/earnings/{ticker} — detailed earnings analysis for one ticker
- Integrate with scanner: earnings_catalyst signal fires automatically during scans

---

## Build Order:
1. Alerts (ntfy) — immediate user value
2. Outcome tracking — feeds into everything else
3. Backtester — proves the edge with data
4. Options flow — unique alpha source
5. AI thesis — polish, uses OpenRouter free models
6. Multi-timeframe — quality multiplier
7. Earnings catalyst — seasonal edge
