# ⚡ Quantum Alpha Hunter - Quickstart

**Get running in 10 minutes**

## 1. Prerequisites

- Python 3.11+ installed
- Git installed
- Terminal/Command Prompt access

## 2. Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/quantum-alpha-hunter.git
cd quantum-alpha-hunter

# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate  # Mac/Linux
venv\Scripts\activate     # Windows

# Install dependencies
pip install -e ".[dev]"
```

## 3. Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your Reddit API credentials
# Get free credentials at: https://www.reddit.com/prefs/apps
nano .env  # or use any text editor
```

Required in `.env`:
```
REDDIT_CLIENT_ID=your_id_here
REDDIT_CLIENT_SECRET=your_secret_here
REDDIT_USER_AGENT=QuantumAlphaHunter/1.0
```

## 4. Initialize Database

```bash
# Create database and tables
qaht init

# Validate setup
python scripts/validate_setup.py
```

You should see: `🎉 All tests passed! System is ready.`

## 5. Test Run

```bash
# The system will fetch data for symbols in data/universe/initial_universe.csv
# This includes: AAPL, TSLA, NVDA, BTC-USD, ETH-USD, etc.

# For now, test the CLI commands (full pipeline coming in Phase 2):
qaht validate        # Check system health
qaht init            # Re-initialize if needed
```

## 6. Development Workflow

**Phase 1 (Current):** Foundation is ready
- ✅ Database schemas
- ✅ Configuration management
- ✅ Core utilities (retry, parallel processing)
- ✅ CLI framework
- ✅ Feature registry

**Phase 2 (Weeks 1-4):** Build the pipelines
```bash
# You'll create data adapters in:
qaht/equities_options/adapters/prices_yahoo.py
qaht/crypto/adapters/spot_coingecko.py

# Then wire them into:
qaht/equities_options/pipeline/daily_job.py
```

**Phase 3 (Weeks 5-8):** Feature engineering & scoring
```bash
# Implement features in:
qaht/equities_options/features/tech.py
qaht/scoring/ridge_model.py
```

**Phase 4 (Weeks 9-12):** Dashboard & polish
```bash
qaht dashboard  # Will launch Streamlit UI
```

## 7. First Development Task

Create your first data fetching script:

```python
# scripts/test_fetch.py
import yfinance as yf
from qaht.db import session_scope
from qaht.schemas import PriceOHLC

symbol = "AAPL"
ticker = yf.Ticker(symbol)
hist = ticker.history(period="1mo")

with session_scope() as session:
    for date, row in hist.iterrows():
        price = PriceOHLC(
            symbol=symbol,
            date=date.strftime("%Y-%m-%d"),
            open=float(row['Open']),
            high=float(row['High']),
            low=float(row['Low']),
            close=float(row['Close']),
            volume=float(row['Volume']),
            asset_type='stock'
        )
        session.add(price)

print(f"✅ Saved {len(hist)} days of {symbol} data")
```

Run it:
```bash
python scripts/test_fetch.py
```

## 8. Next Steps

1. Read `GETTING_STARTED.md` for the complete learning path
2. Follow the week-by-week plan
3. Build incrementally - don't try to do everything at once!

## 🆘 Troubleshooting

**Virtual environment not activating?**
```bash
# Mac/Linux
chmod +x venv/bin/activate
source venv/bin/activate

# Windows - run as Administrator
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
venv\Scripts\activate
```

**Import errors?**
```bash
# Make sure you're in the virtual environment (should see (venv) in prompt)
# Re-install
pip install -e ".[dev]"
```

**Database errors?**
```bash
# Reset database
rm -rf data/qaht.db*
qaht init
```

## 📚 Documentation

- `README.md` - System overview & architecture
- `GETTING_STARTED.md` - Complete learning guide for non-coders
- `qaht.cfg` - Configuration file (edit this)
- `.env` - API credentials (create from .env.example)

## 🎯 Goals

By the end of your first session, you should:
- ✅ Have the environment installed
- ✅ Database initialized
- ✅ Validation tests passing
- ✅ First data fetch script working

**You're ready to build! 🚀**
