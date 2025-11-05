# 🚀 Quantum Alpha Hunter

**AI-Powered Multi-Bagger Detection System**

A self-learning market intelligence system that detects pre-explosive setups in equities, options, and crypto assets **before the crowd sees them**, using only free, publicly available data.

## 🎯 Core Philosophy

> **"Buy the spring before it uncoils"**

Focus on technical, social, and structural compression — moments when volatility, sentiment, and liquidity tighten just before an asymmetric breakout.

---

## ✨ Key Features

- **Pre-Breakout Detection**: Identify explosive moves 3-14 days before they happen
- **Cross-Asset Intelligence**: Unified scoring for stocks, options, and crypto
- **Self-Optimizing**: Automatically adjusts feature weights monthly based on historical accuracy
- **100% Free Data**: No paid APIs required (Yahoo Finance, CoinGecko, Binance, Reddit, SEC EDGAR)
- **Explainable Signals**: Every prediction shows the top 3 contributing factors

---

## 📊 System Architecture

```
quantum-alpha-hunter/
├── qaht/                          # Core library
│   ├── config.py                  # Configuration management
│   ├── db.py                      # Database layer with SQLite optimizations
│   ├── schemas.py                 # SQLAlchemy models
│   ├── utils/                     # Utilities (retry, parallel processing)
│   ├── scoring/                   # ML models and feature registry
│   ├── backtest/                  # Historical validation
│   ├── dashboard/                 # Streamlit UI
│   ├── equities_options/          # Stock/options vertical
│   │   ├── adapters/              # Data fetching
│   │   ├── features/              # Feature engineering
│   │   └── pipeline/              # ETL orchestration
│   └── crypto/                    # Crypto vertical
│       ├── adapters/
│       ├── features/
│       └── pipeline/
├── data/                          # Data storage (gitignored)
├── logs/                          # Application logs
├── scripts/                       # Standalone scripts
├── pyproject.toml                 # Dependencies
└── qaht.cfg                       # Configuration file
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- SQLite (included with Python) or PostgreSQL
- Reddit API credentials (free, get from [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps))

### Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd quantum-alpha-hunter

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Copy environment template
cp .env.example .env
# Edit .env with your Reddit API credentials (required for social signals)

# Initialize database
qaht init
```

### First Run

```bash
# Run the pipeline on the initial universe
qaht run-pipeline

# Launch the dashboard
qaht dashboard
```

---

## 📖 Core Concepts

### 1. **Compression Detection**

The system identifies "coiled spring" setups where:
- Moving averages compress (20/50/200 MA within 5%)
- Volatility drops (Bollinger Band width < 20th percentile)
- Volume shows quiet accumulation
- Price is near key technical levels

### 2. **Social Delta Tracking**

Monitors **rate of change** in social attention:
- 7-day vs 30-day mention volume comparison
- Author diversity (new voices = organic interest)
- Engagement quality (comments/posts ratio)
- Sustained attention (≥3 days above baseline)

### 3. **Quantum Score (0-100)**

Adaptive composite score combining:
- 30% Technical Setup (compression + momentum)
- 25% Social Momentum (delta + quality)
- 20% Catalyst Strength (SEC filings, news)
- 15% Volume/Flow Pressure
- 10% Attention Delta (Google Trends, Wikipedia)

**Conviction Levels:**
- 90+: **MAXIMUM** - Explosion Imminent
- 80-89: **HIGH** - Strong Breakout Potential
- 70-79: **MEDIUM** - Setup Forming
- <70: **LOW** - Weak Signal

### 4. **Self-Optimization**

Monthly feedback loop:
1. Backtest all predictions vs actual returns
2. Calculate factor correlations with outcomes
3. Adjust feature weights toward strongest predictors
4. Recalibrate probability estimates

---

## 🔧 Configuration

Edit `qaht.cfg` to customize:

```ini
[pipeline]
lookback_days = 400        # Historical data window
max_concurrent = 5         # Parallel data fetching threads

[features]
bb_window = 20             # Bollinger Band period
ma_windows = 20,50,200     # Moving average periods
social_delta_window = 7    # Social attention lookback

[backtest]
initial_capital = 100000
risk_per_trade = 0.02      # 2% risk per position
explosion_threshold_equity = 0.50   # 50% return for stocks
explosion_threshold_crypto = 0.30   # 30% return for crypto
```

---

## 📡 Data Sources (All Free)

### Equities/Options
- **Prices**: Yahoo Finance (yfinance)
- **Options**: Yahoo Finance options chains
- **SEC Filings**: EDGAR (8-K, 13D/G, Form 4)
- **Short Interest**: FINRA daily short volume
- **Social**: Reddit (PRAW), Twitter (snscrape)
- **Attention**: Google Trends, Wikipedia pageviews

### Crypto
- **Prices**: CoinGecko, Binance public API
- **Derivatives**: Binance futures (funding rate, open interest)
- **Social**: Reddit crypto subs, Crypto Twitter
- **Dev Activity**: GitHub (stars, commits)

---

## 🎯 Usage Examples

### Daily Watchlist Generation

```bash
# Run full pipeline (data fetch + feature compute + scoring)
qaht run-pipeline

# View top signals in dashboard
qaht dashboard
```

### Historical Backtesting

```python
from qaht.backtest.simulator import simulate
from qaht.backtest.metrics import calculate_performance

# Backtest 2022-2024
results = simulate(
    symbols=['GME', 'AMC', 'TSLA'],
    start_date='2022-01-01',
    end_date='2024-01-01'
)

metrics = calculate_performance(results)
print(f"Hit Rate: {metrics['hit_rate']:.2%}")
print(f"Sharpe Ratio: {metrics['sharpe']:.2f}")
```

### Custom Universe

Create a CSV file with your symbols:

```csv
# data/universe/my_universe.csv
AAPL
TSLA
BTC-USD
ETH-USD
```

Run pipeline:

```bash
qaht run-pipeline --universe data/universe/my_universe.csv
```

---

## 📈 Performance Targets (MVP Phase)

| Metric | Target |
|--------|--------|
| Hit Rate (High Conviction 80+ score) | ≥70% accuracy |
| Lead Time | 3-14 days before move |
| Multi-bagger Capture Rate | 3-5 explosive moves (5x+) per year |
| Max Portfolio Drawdown | <8% |
| False Positive Reduction | -50% vs naive TA scanners |

---

## 🛠️ Development Roadmap

### Phase 1: Foundation (Weeks 1-4) ✅
- [x] Core data pipelines
- [x] Database architecture
- [x] Basic feature engineering
- [x] Configuration management

### Phase 2: Intelligence Engine (Weeks 5-8)
- [ ] Complete technical indicators
- [ ] Social sentiment ingestion
- [ ] Ridge regression scoring model
- [ ] Historical pattern matching

### Phase 3: Validation (Weeks 9-12)
- [ ] Backtesting framework
- [ ] Performance metrics
- [ ] Calibration curves
- [ ] Monthly weight optimization

### Phase 4: Production (Weeks 13-16)
- [ ] Streamlit dashboard
- [ ] Real-time alerts
- [ ] API deployment
- [ ] Documentation

---

## 🔒 Risk Management

**Built-in Safeguards:**
- Position sizing: 1-5% per idea (Kelly-inspired)
- Max sector exposure: 20%
- Daily loss limit: 2% of portfolio
- Hard stop: 8% total drawdown = pause trading
- Time stops: Exit if no move in expected timeframe

---

## 🤝 Contributing

This is a personal project but improvements are welcome!

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-signal`)
3. Commit changes (`git commit -m 'Add new catalyst detector'`)
4. Push to branch (`git push origin feature/amazing-signal`)
5. Open a Pull Request

---

## 📝 License

MIT License - feel free to use for personal trading, learning, or building your own systems.

---

## ⚠️ Disclaimer

**This software is for educational and research purposes only.**

- Not financial advice
- Past performance does not guarantee future results
- Trading involves risk of loss
- Always do your own research
- Start with paper trading

---

## 🙏 Acknowledgments

Inspired by:
- GME, AMC, SHIB, DOGE - the multi-baggers that showed retail can win
- Quantitative finance community for open-source tools
- Reddit communities for democratizing market intelligence

---

## 📬 Support

- Issues: [GitHub Issues](your-repo/issues)
- Discussions: [GitHub Discussions](your-repo/discussions)

---

**Built with ❤️ for finding asymmetric opportunities before they're obvious.**

*"The best trades feel uncomfortable when you enter them."*
