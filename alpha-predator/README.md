# Alpha Predator -- Unified Trading Intelligence System

<!-- Badges -->
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Status: Active Development](https://img.shields.io/badge/status-active%20development-orange)

Alpha Predator combines proven explosive-move detection (backtested to 80%+ out-of-sample hit rates), ML scoring (Ridge regression with isotonic calibration), institutional signal analysis, and real-time alerting into a single production-grade system. It unifies the best techniques from three predecessor systems -- QAHT (Quantum Alpha Hunter), Hedge Fund Explosive Scanner, and Destroyer -- into one cohesive, self-learning pipeline that works across both equities and crypto.

---

## Quick Start

```bash
# Install (editable mode recommended for development)
pip install -e .

# Initialize the database
apredator init

# Run a full scan (equities + crypto)
apredator scan

# Run scan for a specific asset type
apredator scan --asset-type stock
apredator scan --asset-type crypto

# Analyze a single symbol in depth
apredator analyze AMC

# Launch the Streamlit dashboard
apredator dashboard

# Run a backtest
apredator backtest --start 2024-01-01 --end 2024-12-31

# Start real-time monitoring loop
apredator monitor --interval 60

# Validate feature registry and database integrity
apredator validate
```

---

## Architecture

```
apredator/
  adapters/        Data adapters (Yahoo Finance, CoinGecko, Binance, Reddit, SEC)
  alerts/          Alert delivery (Discord webhooks with educational disclaimers)
  backtest/        Backtesting simulator, labeler, and performance metrics
  dashboard/       Streamlit web dashboard with 6 analysis tabs
  features/        Feature computation (technical, explosive, social, institutional, crypto, regime)
  pipeline/        Orchestration (daily scan, real-time monitoring loop)
  scoring/         ML scoring, combo matching, tier classification, ensemble, position sizing
  universe/        Universe selection and filtering
  utils/           Shared utilities
  cli.py           Click CLI entry point
  config.py        Configuration management (apredator.cfg + .env)
  db.py            Database connection manager (SQLAlchemy, SQLite/Postgres)
  logging_conf.py  Structured logging setup
  schemas.py       All database table definitions (ORM models)
```

### Module Descriptions

- **adapters**: Fetch price data (Yahoo Finance), crypto metrics (CoinGecko, Binance), social sentiment (Reddit), and regulatory filings (SEC EDGAR). Each adapter handles rate limiting and error recovery.
- **features**: Computes ~40 features organized into technical (Bollinger Bands, RSI, MACD, ATR, moving average alignment), explosive (volume z-score, gap-ups, vol acceleration, range, rejection wicks, selling pressure), social (mention deltas, author entropy, engagement ratios), institutional (options flow, short interest, order flow scoring), and crypto-specific (funding rate, OI, BTC decoupling).
- **scoring**: The ML scorer trains a Ridge classifier with isotonic calibration. The combo matcher checks for 7 validated winning signal combinations. The tier system classifies setups into 4 conviction tiers. The ensemble combines all scores with regime adjustments. The position sizer applies Kelly criterion.
- **backtest**: Simulates trades using historical predictions with configurable capital, position limits, profit targets, and stop losses. Calculates Sharpe ratio, drawdown, profit factor, and hit rates.
- **alerts**: Sends Discord webhook alerts for high-conviction signals with educational disclaimers. Tracks alert outcomes for self-learning feedback.
- **pipeline**: Orchestrates the full scan flow -- universe selection, price fetching, feature computation, scoring, regime detection, and alert dispatch.
- **dashboard**: Six-tab Streamlit application covering watchlist, symbol analysis, backtesting, regime state, alert history, and self-learning metrics.

---

## Key Features

| Feature | Detail |
|---|---|
| 11 Explosive Signals | Volume z-score, gap-up, vol spike count, vol acceleration, 20-day range, rejection wick, selling pressure, low-in-range, RSI, momentum, drawdown |
| 7 Validated Winning Combos | Backtested combinations with top hit rate of 58.3% (OOS) |
| 4-Tier Classification | Tier 1: 91.7% hit rate, Tier 2: 78.3%, Tier 3: 67.7%, Tier 4: 60.6% |
| Kelly Position Sizing | Optimal bet sizing based on combo/tier hit rates and payoff ratios |
| 8-State Regime Detection | CRISIS, EUPHORIA, BULL_LOW_VOL, BULL_HIGH_VOL, BEAR_LOW_VOL, BEAR_HIGH_VOL, NEUTRAL, RECOVERY |
| Self-Learning Thresholds | Adaptive signal weights and thresholds based on rolling performance |
| Discord Alerts | Real-time alerts with conviction levels and educational disclaimers |
| Streamlit Dashboard | Interactive 6-tab dashboard with watchlist, analysis, backtest, regime, alerts, and learning views |
| Multi-Asset Support | Equities and crypto with asset-specific features and thresholds |
| ML Ensemble Scoring | Ridge + isotonic calibration combined with rule-based signals and regime state |
| Production Database | SQLAlchemy ORM with SQLite (dev) or PostgreSQL (prod), WAL mode, connection pooling |

---

## Configuration

### apredator.cfg

The main configuration file uses INI format with sections for each subsystem:

```ini
[pipeline]
lookback_days = 400
scan_interval_minutes = 60
max_concurrent = 5

[features]
bb_window = 20
ma_windows = 20,50,200
atr_window = 14

[backtest]
initial_capital = 100000
risk_per_trade = 0.02
max_positions = 10
profit_target = 0.50
stop_loss = -0.15

[scoring]
min_samples = 200
cv_folds = 5
calibration_method = isotonic

[alerts]
cooldown_hours = 4
min_confidence = 0.7
educational_disclaimer = true

[universe]
max_price = 50.0
min_volume_20d = 100000

[learning]
enabled = true
retrain_interval_days = 30
weight_update_method = bayesian
```

### .env

Sensitive credentials are loaded from a `.env` file:

```
APREDATOR_DB_URL=sqlite:///data/apredator.db
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
LOG_LEVEL=INFO
```

---

## Signal Hierarchy

The system uses a strict hierarchy when evaluating signals:

1. **combo_probability** -- If a validated winning combo is matched, its historically backtested hit rate takes priority. Combos represent the strongest, most validated edge.
2. **tier_probability** -- The multi-factor tier classification (1-4) provides the next level of conviction. Tier 1 setups have a 91.7% historical hit rate.
3. **ml_probability** -- The Ridge + isotonic calibration model provides a calibrated probability estimate from the full feature set.
4. **individual signals** -- Raw signal values (volume z-score, gap percentage, etc.) serve as inputs to the above layers but are not used directly for trading decisions.

The ensemble scorer (`scoring/ensemble.py`) combines these layers with regime-based adjustments. In CRISIS or BEAR_HIGH_VOL regimes, position sizes are reduced and score thresholds are raised.

---

## Self-Learning

Alpha Predator includes a closed-loop self-learning system that tracks every alert and adjusts behavior based on outcomes:

1. **Alert Tracking**: Every sent alert is logged with entry price, conviction level, combo name, and tier.
2. **Outcome Measurement**: A background process checks 5-day, 10-day, and 30-day returns for each alert, recording whether the profit target was hit.
3. **Signal Performance**: Rolling hit rates, average returns, and lift-vs-baseline are computed per signal and combo over configurable windows.
4. **Weight Adjustment**: Signals that consistently outperform receive higher weights in the ensemble; underperforming signals are down-weighted using Bayesian updating.
5. **Threshold Adaptation**: If the false positive rate for a signal exceeds the configured threshold (default 40%), its trigger threshold is automatically tightened.
6. **Model Retraining**: The ML model is retrained on a configurable schedule (default: every 30 days) using the latest labeled data. New models are registered in the model registry and only activated if they outperform the current model on OOS metrics.

The learning loop is conservative by design -- it requires a minimum number of outcome samples before making any adjustments, and uses exponential decay with a configurable half-life to weight recent observations more heavily.

---

## Disclaimer

This software is provided for **educational and research purposes only**. It is not financial advice. The authors make no guarantees about the accuracy of predictions or the profitability of any trading strategy derived from this system. Trading stocks and cryptocurrency involves substantial risk of loss. Past performance, including backtested results, does not guarantee future results. Always do your own research and consult a qualified financial advisor before making investment decisions.
