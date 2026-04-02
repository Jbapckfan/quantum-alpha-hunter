# Quantum Alpha Hunter

Unified quantitative trading platform combining ML-powered stock/crypto scanning, empirically-validated pattern detection, options analysis, and risk management.

## What's Inside

### Equities Scanner (from rzlv-pattern-scanner)
- 45+ individually weighted technical signals across 12 categories
- Washout & reclaim pattern detection with stage system (EARLY/MID/LATE/EXTENDED)
- 6-method resistance level confluence scoring
- High-confidence play filtering with analyst target integration

### Empirical Combo Engine (from Hedge-Fund-explosive-scanner)
- 7 validated winning combinations (47-58% hit rates vs 27.4% baseline)
- Volume z-score as primary signal (+443% predictive lift)
- Trap signal detection (PULLBACK, RSI_OVERSOLD, LOW_IN_RANGE)
- Tier 1 filter achieving 91.7% hit rate in backtest

### Crypto Scanner
- 30+ crypto-specific signals with BTC relative strength
- Altcoin season detection
- Fear & Greed Index integration
- Social sentiment tracking

### Options Engine (from spy-options-engine)
- Polygon.io integration for real-time options chains with Greeks
- 0DTE SPY direction engine (5-component weighted scoring)
- LEAPS candidate scanner with momentum ranking
- Target-price strategy calculator (calls, puts, spreads)
- Covered call finder (3 strategies: Keep Shares, Okay to Sell, Max Income)

### ML Scoring Pipeline
- Ridge regression with isotonic calibration
- Hybrid scoring: 60% empirical combos + 40% ML quantum score
- Kelly criterion position sizing (quarter Kelly)
- Multi-target profit taking (T1/T2/T3 exits)
- Market regime adjustments (bull/bear/high-vol/low-vol)

## Quick Start

### Backend
```bash
pip install -e .
cp .env.example .env
# Edit .env with your API keys
qaht init          # Initialize database
qaht run-pipeline  # Run equities + crypto pipelines
qaht-api           # Start FastAPI server on :8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev        # Start Vite dev server on :5173
```

### API Docs
Once the server is running: http://localhost:8000/docs

## Architecture

```
qaht/
├── api/              # Unified FastAPI backend
├── scoring/          # ML pipeline + empirical combos + position sizing
├── signals/          # 45+ signal detection + crypto + resistance confluence
├── options/          # Polygon.io adapter, 0DTE, LEAPS, strategies
├── equities_options/ # Yahoo Finance adapter, technical features
├── crypto/           # CoinGecko + Binance adapters
├── backtest/         # Event labeling + validation
└── dashboard/        # Streamlit quick-analysis UI
frontend/             # React + TypeScript + Tailwind dashboard
```

## Configuration

See `qaht.cfg` for all tunable parameters.

## Data Sources
- **Yahoo Finance** (yfinance) -- Stock/crypto OHLCV
- **CoinGecko** -- Crypto market data, sentiment
- **Binance** -- Futures funding rates, open interest
- **Polygon.io** -- Options chains with Greeks (free tier)
- **Reddit/PRAW** -- Social sentiment
