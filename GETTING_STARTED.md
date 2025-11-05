# 🎓 Getting Started with Quantum Alpha Hunter
## A Complete Guide for Non-Programmers

This guide assumes you have **minimal or no coding experience** but strong financial knowledge. We'll walk through everything step-by-step.

---

## 📚 Table of Contents

1. [Understanding What You're Building](#understanding)
2. [Setting Up Your Computer](#setup)
3. [Week 1: Your First Data Pipeline](#week1)
4. [Week 2-3: Adding Features](#week2-3)
5. [Week 4-8: Building the Intelligence](#week4-8)
6. [Common Errors and How to Fix Them](#errors)
7. [Learning Resources](#resources)

---

## <a name="understanding"></a>🎯 Understanding What You're Building

### The Big Picture

You're building a system that:
1. **Fetches data** from free sources (Yahoo, Reddit, etc.)
2. **Calculates indicators** (moving averages, social sentiment)
3. **Scores assets** (0-100 based on compression + attention)
4. **Displays results** in a web dashboard
5. **Learns over time** (adjusts weights based on what works)

### Key Terminology

| Term | What It Means |
|------|---------------|
| **Pipeline** | Automated sequence: fetch data → calculate features → generate scores |
| **Feature** | A single data point (e.g., "BB width" or "social delta") |
| **Quantum Score** | Your system's 0-100 rating of explosion potential |
| **Backtest** | Testing your system on historical data |
| **Schema** | Database table structure (columns and their types) |

---

## <a name="setup"></a>💻 Setting Up Your Computer

### Step 1: Install Python

**Mac:**
```bash
# Open Terminal (Cmd+Space, type "Terminal")
# Check if Python 3.11+ is installed
python3 --version

# If not installed or version < 3.11, install via Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python@3.11
```

**Windows:**
1. Download Python 3.11 from [python.org](https://www.python.org/downloads/)
2. Run installer, **check "Add Python to PATH"**
3. Open Command Prompt, verify: `python --version`

### Step 2: Install Visual Studio Code (Your Code Editor)

1. Download from [code.visualstudio.com](https://code.visualstudio.com/)
2. Install Python extension (open VS Code → Extensions icon → search "Python" → Install)

### Step 3: Set Up the Project

```bash
# Navigate to where you want the project
cd ~/Documents  # Mac
cd C:\Users\YourName\Documents  # Windows

# Clone or download the project
# (Assuming you have the quantum-alpha-hunter folder)
cd quantum-alpha-hunter

# Create a virtual environment (isolated Python installation for this project)
python3 -m venv venv

# Activate it
source venv/bin/activate  # Mac/Linux
venv\Scripts\activate     # Windows

# You'll see (venv) in your terminal prompt now

# Install all required packages
pip install -e ".[dev]"
```

**What just happened?**
- `venv`: Isolated environment (won't mess with other Python projects)
- `pip install -e .`: Installs all dependencies listed in `pyproject.toml`

### Step 4: Get Reddit API Credentials (Free)

Social sentiment is critical to this system. You need Reddit API access:

1. Go to [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)
2. Scroll to bottom, click "create another app..."
3. Fill out:
   - **name**: QuantumAlphaHunter
   - **type**: script
   - **redirect uri**: http://localhost:8080
4. Click "create app"
5. Copy the **client ID** (under app name) and **secret**

Now create your `.env` file:

```bash
# Copy the template
cp .env.example .env

# Edit .env (use VS Code or any text editor)
code .env
```

Add your credentials:

```
REDDIT_CLIENT_ID=your_client_id_here
REDDIT_CLIENT_SECRET=your_secret_here
REDDIT_USER_AGENT=QuantumAlphaHunter/1.0
```

### Step 5: Initialize the Database

```bash
# This creates the SQLite database and all tables
qaht init
```

You should see: `Database initialized`

---

## <a name="week1"></a>📅 Week 1: Your First Data Pipeline

### Goal: Fetch prices for 5 stocks and calculate 3 basic indicators

### Day 1-2: Understanding the Code Structure

Open the project in VS Code:

```bash
code .
```

Key files to know:
- `qaht/config.py`: Settings (lookback days, features to calculate)
- `qaht/schemas.py`: Database tables (like Excel sheets, but in SQL)
- `qaht/db.py`: Database connection management
- `qaht.cfg`: Configuration file (edit this, not the Python files initially)

### Day 3: Your First Script

Create a new file: `scripts/test_basic_pipeline.py`

```python
"""
Your first pipeline test - fetches prices and calculates 3 features
"""
import yfinance as yf
import pandas as pd
from qaht.db import session_scope
from qaht.schemas import PriceOHLC, Factors

# Step 1: Fetch data for one symbol
symbol = "AAPL"
print(f"Fetching data for {symbol}...")

ticker = yf.Ticker(symbol)
hist = ticker.history(period="1y")

print(f"Got {len(hist)} days of data")
print(hist.tail())  # Show last 5 rows

# Step 2: Save to database
with session_scope() as session:
    for date, row in hist.iterrows():
        # Check if already exists
        exists = session.query(PriceOHLC).filter_by(
            symbol=symbol,
            date=date.strftime("%Y-%m-%d")
        ).first()

        if not exists:
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

    print(f"Saved {symbol} prices to database")

# Step 3: Calculate a simple feature (20-day moving average)
hist['MA20'] = hist['Close'].rolling(window=20).mean()

# Calculate Bollinger Band width
hist['MA20_std'] = hist['Close'].rolling(window=20).std()
hist['BB_upper'] = hist['MA20'] + (2 * hist['MA20_std'])
hist['BB_lower'] = hist['MA20'] - (2 * hist['MA20_std'])
hist['BB_width_pct'] = (hist['BB_upper'] - hist['BB_lower']) / hist['Close']

# Save latest feature
latest = hist.iloc[-1]
with session_scope() as session:
    factor = Factors(
        symbol=symbol,
        date=hist.index[-1].strftime("%Y-%m-%d"),
        bb_width_pct=float(latest['BB_width_pct']),
        ma_spread_pct=None,  # We'll add this later
        social_delta_7d=0.0  # Placeholder
    )
    session.add(factor)
    print(f"Saved features for {symbol}")

print("\n✅ SUCCESS! You just:")
print("1. Fetched price data from Yahoo Finance")
print("2. Saved it to your database")
print("3. Calculated Bollinger Band width")
print("4. Saved the feature")
```

**Run it:**

```bash
python scripts/test_basic_pipeline.py
```

**What to expect:**
- You'll see data being fetched
- Messages about saving to database
- No errors = success!

### Day 4-5: Expand to Multiple Symbols

Modify the script to loop over symbols:

```python
symbols = ["AAPL", "TSLA", "NVDA", "AMD", "GME"]

for symbol in symbols:
    print(f"\n{'='*50}")
    print(f"Processing {symbol}")
    print(f"{'='*50}")

    # ... (your existing code, indented inside this loop)
```

### Day 6-7: Add Error Handling

Wrap in try/except so one failure doesn't kill everything:

```python
for symbol in symbols:
    try:
        # ... your code ...
    except Exception as e:
        print(f"❌ Error processing {symbol}: {e}")
        continue  # Skip to next symbol
```

**Deliverable Week 1:**
- Working script that fetches 5+ symbols
- Data saved to database
- Basic feature (BB width) calculated
- You understand how data flows: API → DataFrame → Database

---

## <a name="week2-3"></a>📊 Week 2-3: Adding Social Signals & More Features

### Week 2 Goal: Reddit mention tracking

Create `scripts/test_reddit.py`:

```python
"""
Fetch Reddit mentions for symbols
"""
import praw
import os
from datetime import datetime, timedelta
from qaht.db import session_scope
from qaht.schemas import SocialMentions

# Initialize Reddit API
reddit = praw.Reddit(
    client_id=os.getenv("REDDIT_CLIENT_ID"),
    client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
    user_agent=os.getenv("REDDIT_USER_AGENT")
)

# Test connection
print(f"Reddit API initialized: {reddit.read_only}")

# Track mentions for a symbol
symbol = "GME"
subreddits = ["wallstreetbets", "stocks", "investing"]
mention_count = 0

for sub_name in subreddits:
    subreddit = reddit.subreddit(sub_name)

    # Search for mentions in last 24 hours
    for submission in subreddit.search(symbol, time_filter="day", limit=100):
        mention_count += 1

print(f"Found {mention_count} mentions of ${symbol} in past day")

# Save to database
with session_scope() as session:
    today = datetime.now().strftime("%Y-%m-%d")

    social = SocialMentions(
        symbol=symbol,
        date=today,
        reddit_count=mention_count,
        twitter_count=0,  # We'll add Twitter later
        author_entropy=None,
        engagement_ratio=None
    )
    session.add(social)

print(f"✅ Saved social data for {symbol}")
```

### Week 3 Goal: Calculate social delta

Once you have 7+ days of social data, calculate rate of change:

```python
"""
Calculate social delta (7-day vs 30-day average)
"""
import pandas as pd
from qaht.db import session_scope
from qaht.schemas import SocialMentions, Factors

symbol = "GME"

with session_scope() as session:
    # Get all social data for symbol
    mentions = session.query(SocialMentions).filter_by(symbol=symbol).all()

    # Convert to DataFrame
    data = pd.DataFrame([{
        'date': m.date,
        'reddit_count': m.reddit_count,
        'twitter_count': m.twitter_count
    } for m in mentions])

    data['date'] = pd.to_datetime(data['date'])
    data = data.sort_values('date')

    # Calculate rolling averages
    data['mentions_7d'] = data['reddit_count'].rolling(7).mean()
    data['mentions_30d'] = data['reddit_count'].rolling(30).mean()

    # Calculate delta
    data['social_delta_7d'] = (
        (data['mentions_7d'] - data['mentions_30d']) / data['mentions_30d']
    ).fillna(0)

    # Save latest delta to Factors table
    latest = data.iloc[-1]

    factor = session.query(Factors).filter_by(
        symbol=symbol,
        date=latest['date'].strftime("%Y-%m-%d")
    ).first()

    if factor:
        factor.social_delta_7d = float(latest['social_delta_7d'])
    else:
        factor = Factors(
            symbol=symbol,
            date=latest['date'].strftime("%Y-%m-%d"),
            social_delta_7d=float(latest['social_delta_7d'])
        )
        session.add(factor)

    print(f"✅ Social delta for {symbol}: {latest['social_delta_7d']:.2f}")
```

---

## <a name="week4-8"></a>🧠 Week 4-8: Building the Scoring Model

By now you have:
- Price data with technical features
- Social mention data with deltas
- Both saved in the database

### Week 4-5: Labeling (What to Predict)

Create "labels" = did the stock explode in next 10 days?

```python
"""
Label explosions - did stock move 50%+ in next 10 days?
"""
import pandas as pd
from qaht.db import session_scope
from qaht.schemas import PriceOHLC, Labels

symbol = "GME"

with session_scope() as session:
    # Get all prices
    prices = session.query(PriceOHLC).filter_by(symbol=symbol).all()

    df = pd.DataFrame([{
        'date': p.date,
        'close': p.close
    } for p in prices])

    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')

    # Calculate forward returns
    df['fwd_ret_10d'] = (df['close'].shift(-10) / df['close']) - 1

    # Mark explosions (50%+ return)
    df['explosive_10d'] = df['fwd_ret_10d'] >= 0.50

    # Save labels
    for _, row in df.iterrows():
        if pd.notna(row['fwd_ret_10d']):
            label = Labels(
                symbol=symbol,
                date=row['date'].strftime("%Y-%m-%d"),
                fwd_ret_10d=float(row['fwd_ret_10d']),
                explosive_10d=bool(row['explosive_10d'])
            )
            session.add(label)

    explosions = df['explosive_10d'].sum()
    print(f"✅ Found {explosions} explosive moves for {symbol}")
```

### Week 6-7: Training a Model

Use scikit-learn to predict explosions:

```python
"""
Train a simple model to predict explosions
"""
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.model_selection import train_test_split
from qaht.db import session_scope
from sqlalchemy import text

# Load all data
with session_scope() as session:
    query = text("""
        SELECT
            f.symbol, f.date,
            f.bb_width_pct, f.ma_spread_pct, f.social_delta_7d,
            l.explosive_10d
        FROM factors f
        JOIN labels l ON f.symbol = l.symbol AND f.date = l.date
        WHERE f.bb_width_pct IS NOT NULL
          AND f.social_delta_7d IS NOT NULL
    """)

    data = pd.read_sql(query, session.bind)

print(f"Loaded {len(data)} rows")

# Prepare features and target
features = ['bb_width_pct', 'ma_spread_pct', 'social_delta_7d']
X = data[features].fillna(0)
y = data['explosive_10d'].astype(int)

# Split train/test
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.3, random_state=42
)

# Train model
model = Ridge(alpha=1.0)
model.fit(X_train, y_train)

# Evaluate
train_score = model.score(X_train, y_train)
test_score = model.score(X_test, y_test)

print(f"Train R²: {train_score:.3f}")
print(f"Test R²: {test_score:.3f}")

# Show feature importance
for feature, coef in zip(features, model.coef_):
    print(f"{feature}: {coef:.4f}")
```

---

## <a name="errors"></a>❌ Common Errors and Fixes

### 1. `ModuleNotFoundError: No module named 'qaht'`

**Fix:** Activate your virtual environment
```bash
source venv/bin/activate  # Mac
venv\Scripts\activate     # Windows
```

### 2. `OperationalError: no such table: price_ohlc`

**Fix:** Initialize the database
```bash
qaht init
```

### 3. `KeyError: 'bb_width_pct'`

**Fix:** The feature doesn't exist in your DataFrame
```python
# Check what columns you have
print(df.columns.tolist())

# Only use features that exist
available = [f for f in ['bb_width_pct', 'social_delta_7d'] if f in df.columns]
X = df[available]
```

### 4. Reddit API errors

**Fix:** Check your .env file has correct credentials
```bash
# Test connection
python -c "import praw; import os; r = praw.Reddit(client_id=os.getenv('REDDIT_CLIENT_ID'), client_secret=os.getenv('REDDIT_CLIENT_SECRET'), user_agent='test'); print(r.read_only)"
```

---

## <a name="resources"></a>📚 Learning Resources

### Python Basics (When You Need It)
- **Corey Schafer YouTube**: [Python Tutorials](https://www.youtube.com/playlist?list=PL-osiE80TeTt2d9bfVyTiXJA-UTHn6WwU)
- **Real Python**: [Python Basics](https://realpython.com/)

### Pandas (Data Manipulation)
- **Pandas Docs**: [10 Minutes to Pandas](https://pandas.pydata.org/docs/user_guide/10min.html)
- **YouTube**: Search "Pandas tutorial for beginners"

### Machine Learning Basics
- **StatQuest YouTube**: [Machine Learning](https://www.youtube.com/c/joshstarmer) - best visual explanations
- **Scikit-learn Docs**: [Supervised Learning](https://scikit-learn.org/stable/supervised_learning.html)

### Trading/Quant Finance
- **QuantConnect**: [Tutorials](https://www.quantconnect.com/tutorials)
- **Investopedia**: For financial concepts

---

## 🎓 Learning Philosophy

**Don't try to learn everything upfront.**

Instead:
1. Get something working (even if ugly)
2. Hit an error or limitation
3. Google/Claude that specific thing
4. Learn just enough to fix it
5. Move forward

Example:
- Don't study "all of pandas" - just learn `df.rolling()` when you need moving averages
- Don't study "all of scikit-learn" - just learn `Ridge()` when you're ready to train

**You're building knowledge through doing, not through courses.**

---

## 💬 Getting Help

When stuck:

1. **Read the error message carefully** - it usually tells you what's wrong
2. **Google the error** - someone has hit it before
3. **Ask Claude/ChatGPT** with context:
   ```
   "I'm trying to fetch stock data with yfinance but getting this error:
   [paste error]

   Here's my code:
   [paste code]

   How do I fix it?"
   ```
4. **Check GitHub Issues** for this project

---

## 🎯 Week 8+ Checkpoint

By Week 8, you should have:
- ✅ Data pipeline running daily (prices + social)
- ✅ 10+ features calculated and stored
- ✅ Labels (explosions) identified
- ✅ Basic Ridge model trained
- ✅ Ability to score new assets

**You're 70% of the way there!**

Next steps are polish:
- Better UI (Streamlit dashboard)
- More features
- Backtesting framework
- Monthly retraining

---

**Remember: Every expert was once a beginner. The only difference is they didn't quit.**

You've got this! 🚀
