# 🍎 MacBook Setup Guide - Quantum Alpha Hunter

Complete guide to get Quantum Alpha Hunter running on your MacBook.

---

## 📋 Prerequisites

Before you start, you'll need:
- macOS (any recent version)
- Terminal app
- 15 minutes

---

## 🚀 Step-by-Step Setup

### Step 1: Install Homebrew (if not already installed)

Open Terminal and run:

```bash
# Check if Homebrew is installed
which brew

# If not found, install it:
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### Step 2: Install Python 3.11+

```bash
# Install Python 3.11
brew install python@3.11

# Verify installation
python3.11 --version
# Should show: Python 3.11.x
```

### Step 3: Clone Your Repository

```bash
# Navigate to where you want the project
cd ~/Documents  # or anywhere you prefer

# Clone your repository
git clone https://github.com/Jbapckfan/quantum-alpha-hunter.git

# Enter the directory
cd quantum-alpha-hunter

# Switch to the latest branch
git checkout claude/continue-work-011CUqPUodcG9qemRz7AqzfB
```

### Step 4: Create Virtual Environment

```bash
# Create virtual environment
python3.11 -m venv venv

# Activate it
source venv/bin/activate

# You should see (venv) in your prompt now
```

### Step 5: Install Dependencies

```bash
# Upgrade pip first
pip install --upgrade pip setuptools wheel

# Install core dependencies (without talib-binary which causes issues)
pip install pandas numpy scikit-learn yfinance praw SQLAlchemy \
    python-dotenv tqdm requests plotly streamlit click beautifulsoup4 lxml

# Install additional packages
pip install ta pydantic structlog

# Verify installation
python -c "import pandas, yfinance, praw, sqlalchemy; print('✅ All core packages installed!')"
```

**Note**: If you get errors with `talib-binary`, that's OK - the system uses pandas fallbacks.

### Step 6: Get Reddit API Credentials (Free)

1. **Go to Reddit Apps**: https://www.reddit.com/prefs/apps
2. **Scroll to bottom**, click "create another app..."
3. **Fill out the form**:
   - Name: `QuantumAlphaHunter`
   - Type: Select "script"
   - Description: `Personal trading signals`
   - About URL: (leave blank)
   - Redirect URI: `http://localhost:8080`
4. **Click "create app"**
5. **Copy your credentials**:
   - Client ID: The string under "personal use script" (14 characters)
   - Client Secret: The "secret" field

### Step 7: Configure Environment

```bash
# Copy the example environment file
cp .env.example .env

# Edit the file
nano .env
# Or use any text editor you prefer:
# open -e .env  # Opens in TextEdit
```

Add your Reddit credentials:

```bash
# Reddit API (required for social signals)
REDDIT_CLIENT_ID=your_14_char_client_id_here
REDDIT_CLIENT_SECRET=your_secret_here
REDDIT_USER_AGENT=QuantumAlphaHunter/1.0

# Optional: Email alerts
# SMTP_SERVER=smtp.gmail.com
# SMTP_PORT=587
# SMTP_USER=your_email@gmail.com
# SMTP_PASSWORD=your_app_password
```

**Save and close** (In nano: Ctrl+X, then Y, then Enter)

### Step 8: Initialize Database

```bash
# Create database structure
python -c "
import sys
sys.path.insert(0, '.')
from qaht.db import init_db
from qaht.config import load_config
config = load_config()
init_db(config)
print('✅ Database initialized!')
"
```

This creates a SQLite database at `data/qaht.db`.

### Step 9: Run the Demo

```bash
# See the system in action (no real data needed)
python scripts/demo.py
```

You should see the full demonstration output!

### Step 10: First Real Data Fetch (Optional)

If you want to fetch real data:

```bash
# Create a small test universe
mkdir -p data/universe
echo "AAPL
TSLA
NVDA
BTC-USD
ETH-USD" > data/universe/test.csv

# Run a test fetch (this will take 2-3 minutes)
python scripts/quick_test.py
```

---

## 🎯 Daily Usage

### Morning Routine

```bash
# 1. Activate virtual environment (if not already active)
cd ~/Documents/quantum-alpha-hunter  # or wherever you put it
source venv/bin/activate

# 2. Run the pipeline (fetches data, computes features, generates scores)
python -c "
import sys
sys.path.insert(0, '.')
from qaht.equities_options.pipeline.daily_job import run_equities_pipeline
from qaht.crypto.pipeline.daily_job import run_crypto_pipeline

print('Running equities pipeline...')
run_equities_pipeline()

print('Running crypto pipeline...')
run_crypto_pipeline()

print('✅ Pipeline complete!')
"

# 3. Generate alerts
python scripts/daily_score_and_alert.py --min-score 80

# 4. Launch dashboard (opens in browser)
streamlit run qaht/dashboard/app.py
```

### Set Up Automation (Optional)

Use macOS's built-in `launchd` for scheduling:

```bash
# Create launch agent directory if needed
mkdir -p ~/Library/LaunchAgents

# Create a plist file for daily pipeline
cat > ~/Library/LaunchAgents/com.quantumalpha.daily.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.quantumalpha.daily</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOUR_USERNAME/Documents/quantum-alpha-hunter/venv/bin/python</string>
        <string>/Users/YOUR_USERNAME/Documents/quantum-alpha-hunter/scripts/run_full_pipeline.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>6</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/YOUR_USERNAME/Documents/quantum-alpha-hunter/logs/daily.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOUR_USERNAME/Documents/quantum-alpha-hunter/logs/daily.error.log</string>
</dict>
</plist>
EOF

# Replace YOUR_USERNAME with your actual username
# Then load it:
# launchctl load ~/Library/LaunchAgents/com.quantumalpha.daily.plist
```

---

## 📊 Running Backtests

```bash
# Activate environment
source venv/bin/activate

# Run backtest
python -c "
import sys
sys.path.insert(0, '.')
from qaht.backtest import simulate, calculate_performance
import pandas as pd

# Note: This requires historical data in the database
# For demo, we'll show the structure

print('To run a real backtest:')
print('1. Fetch historical data with the pipeline')
print('2. Run: python -c \"from qaht.backtest import simulate; ...')
print('3. Or use: python scripts/monthly_retrain.py --skip-retrain')
"

# When you have data, actual backtest:
# python -c "
# from qaht.backtest import simulate, calculate_performance
# trades = simulate('2023-01-01', '2024-01-01', min_score=80)
# metrics = calculate_performance(trades)
# print(metrics)
# "
```

---

## 🔧 Troubleshooting

### Issue: "command not found: python3.11"

**Solution**: Install Python 3.11 via Homebrew:
```bash
brew install python@3.11
# Then use python3.11 instead of python3
```

### Issue: "No module named 'qaht'"

**Solution**: Make sure you're in the project directory and virtual environment is active:
```bash
cd quantum-alpha-hunter
source venv/bin/activate
# Set Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### Issue: "Permission denied" when installing

**Solution**: Never use `sudo` with pip in a virtual environment. If you see permission errors:
```bash
# Deactivate and recreate venv
deactivate
rm -rf venv
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
# Try installation again
```

### Issue: SQLAlchemy or pandas install fails

**Solution**: Install Xcode Command Line Tools:
```bash
xcode-select --install
# Then try pip install again
```

### Issue: "rate limit" errors from APIs

**Solution**: The system has retry logic, but you can:
- Wait a few minutes between runs
- Reduce universe size for testing
- APIs used are all free tier - just be patient

### Issue: Dashboard won't open

**Solution**:
```bash
# Make sure streamlit is installed
pip install streamlit

# Run with explicit command
streamlit run qaht/dashboard/app.py --server.port 8501

# Then open browser to: http://localhost:8501
```

---

## 🎨 VS Code Setup (Optional but Recommended)

If you use VS Code:

```bash
# Install VS Code command line tools
# In VS Code: Cmd+Shift+P → "Shell Command: Install 'code' command in PATH"

# Open project in VS Code
code .

# Install recommended extensions:
# - Python (Microsoft)
# - Pylance
# - Python Debugger
```

Create `.vscode/settings.json`:
```json
{
    "python.defaultInterpreterPath": "${workspaceFolder}/venv/bin/python",
    "python.terminal.activateEnvironment": true,
    "python.linting.enabled": true,
    "python.formatting.provider": "black"
}
```

---

## 📱 Slack Notifications (Optional)

To get alerts on your phone:

1. **Create Slack Workspace** (free): https://slack.com/create
2. **Add Incoming Webhooks**:
   - Go to https://YOUR_WORKSPACE.slack.com/apps
   - Search "Incoming Webhooks"
   - Click "Add to Slack"
   - Choose channel (e.g., #trading-signals)
   - Copy webhook URL

3. **Use it**:
```bash
python scripts/daily_score_and_alert.py \
  --min-score 80 \
  --slack-webhook https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

4. **Get Slack mobile app** → Receive push notifications!

---

## 🔄 Updating Your Code

When there are updates to the project:

```bash
# Make sure you're in the project directory
cd ~/Documents/quantum-alpha-hunter

# Activate environment
source venv/bin/activate

# Pull latest changes
git pull origin claude/continue-work-011CUqPUodcG9qemRz7AqzfB

# Update dependencies if needed
pip install --upgrade -r requirements.txt  # if we add this file

# Restart your workflows
```

---

## 📁 Recommended Folder Structure on Mac

```
~/Documents/
└── quantum-alpha-hunter/          # Your project
    ├── venv/                      # Virtual environment (created by you)
    ├── data/                      # Data storage (created automatically)
    │   ├── qaht.db               # SQLite database
    │   ├── alerts/               # Daily alert history
    │   └── universe/             # Your symbol lists
    ├── logs/                      # Application logs
    ├── models/                    # Trained models
    ├── qaht/                      # Core library
    ├── scripts/                   # Operational scripts
    └── .env                       # Your API credentials (YOU CREATE THIS)
```

---

## 🎯 Quick Reference Commands

```bash
# Activate environment (do this first, every time)
cd ~/Documents/quantum-alpha-hunter
source venv/bin/activate

# Run demo (no API needed)
python scripts/demo.py

# Fetch real data (needs Reddit API)
python scripts/run_full_pipeline.py

# Generate alerts
python scripts/daily_score_and_alert.py --min-score 80

# Dashboard
streamlit run qaht/dashboard/app.py

# Monthly maintenance
python scripts/monthly_retrain.py

# Deactivate environment when done
deactivate
```

---

## 🚦 Start Simple

**Day 1**: Setup + Demo
```bash
source venv/bin/activate
python scripts/demo.py
```

**Day 2**: Configure Reddit API
```bash
nano .env  # Add your credentials
python scripts/quick_test.py
```

**Day 3**: First real pipeline
```bash
python scripts/run_full_pipeline.py
python scripts/daily_score_and_alert.py --min-score 80
```

**Day 4**: Explore dashboard
```bash
streamlit run qaht/dashboard/app.py
```

**Week 2**: Set up automation, refine universe, track results

---

## ✅ Verification Checklist

- [ ] Python 3.11+ installed (`python3.11 --version`)
- [ ] Virtual environment created and activated (`which python` shows venv path)
- [ ] Dependencies installed (`python -c "import pandas, yfinance, praw"`)
- [ ] Reddit API credentials in `.env` file
- [ ] Database initialized (file exists at `data/qaht.db`)
- [ ] Demo runs successfully (`python scripts/demo.py`)
- [ ] Ready to fetch real data!

---

## 🆘 Getting Help

If you get stuck:

1. **Check logs**: `tail -f logs/qaht.log`
2. **Test imports**: `python -c "import qaht; print('OK')"`
3. **Verify credentials**: Check `.env` file has correct Reddit API keys
4. **Review documentation**:
   - `README.md` - Overview
   - `PRODUCTION_USAGE.md` - Detailed usage
   - `PROJECT_SUMMARY.md` - Architecture

---

## 🎉 You're Ready!

Once setup is complete, you have a fully-functional multi-bagger detection system running on your MacBook!

**Next**: See `PRODUCTION_USAGE.md` for daily workflows, backtesting, and advanced features.

**Remember**: Start with paper trading, validate the signals yourself, and never risk more than you can afford to lose.

---

*Built with ❤️ for Mac users finding asymmetric opportunities.*
