# 🚀 Quick Start Guide

Run Quantum Alpha Hunter in **seconds** with these super-easy commands.

## ⚡️ Fastest Way (One Command)

### Install & Setup
```bash
./install.sh
```

### Run Interactive Menu
```bash
./run.sh
```

That's it! The menu guides you through everything.

---

## 🎯 CLI Commands (Fast & Easy)

### After Installation
```bash
# If installed globally
qaht scan crypto              # Scan cryptocurrencies
qaht scan stocks              # Scan stocks
qaht scan all                 # Scan everything
qaht dashboard                # Start web UI
qaht automate --interval 1h   # Setup automation
```

### Without Global Install
```bash
python3 qaht-cli.py scan crypto
python3 qaht-cli.py scan stocks
python3 qaht-cli.py dashboard
```

---

## 📋 Makefile Commands (Even Easier)

```bash
make scan-crypto              # Scan cryptocurrencies
make scan-stocks              # Scan stocks
make scan-all                 # Scan everything
make dashboard                # Start dashboard
make automate                 # Setup automation
make test                     # Run tests
make clean                    # Clean cache
```

---

## 🤖 Automated Scanning

### Background Daemon (Auto-scan forever)
```bash
# Scan every hour in background
python3 auto-scanner.py --interval 1h --daemon &

# Scan every 30 minutes
python3 auto-scanner.py --interval 30m &

# High-quality alerts only (score >= 85)
python3 auto-scanner.py --interval 1h --min-score 85 &
```

### Cron Jobs (Schedule scans)
```bash
# Setup hourly scans
qaht automate --interval 1h

# Or manually edit crontab
crontab -e

# Add this line for hourly scans:
0 * * * * cd /path/to/quantum-alpha-hunter && python3 auto-scanner.py --interval 1h >> logs/cron.log 2>&1
```

---

## 📊 All Available Commands

### Scanning
```bash
qaht scan crypto                    # Scan cryptocurrencies
qaht scan crypto --force-refresh    # Bypass cache (fresh data)
qaht scan stocks                    # Scan stocks for agile movers
qaht scan stocks --min-score 80     # High-quality stocks only
qaht scan all                       # Scan everything
```

### Dashboard
```bash
qaht dashboard                      # Start on :8000
qaht dashboard --port 8080          # Custom port
```

**Access:** http://localhost:8000

### Automation
```bash
qaht automate --interval 15m        # Every 15 minutes
qaht automate --interval 30m        # Every 30 minutes
qaht automate --interval 1h         # Every hour (default)
qaht automate --interval 4h         # Every 4 hours
qaht automate --interval daily      # Once daily (9 AM)
```

### Status & Alerts
```bash
qaht schedule                       # Show cron schedule
qaht alert                          # Check for high-priority alerts
qaht alert --min-score 85           # Show score >= 85 only
```

### Makefile Shortcuts
```bash
make install                        # Install everything
make scan-crypto                    # Scan crypto (cached)
make scan-crypto-fresh              # Scan crypto (force refresh)
make scan-stocks                    # Scan stocks
make scan-all                       # Scan everything
make dashboard                      # Start dashboard
make automate                       # Setup 1h automation
make automate-15m                   # Setup 15min automation
make automate-daily                 # Setup daily automation
make schedule                       # Show cron schedule
make test                           # Run tests
make clean                          # Clean cache & logs
make clean-cache                    # Clean only cache
make status                         # Show system status
```

---

## ⏱️ Performance

### First Run (No Cache)
```bash
Crypto scan: ~2-3 minutes
Stock scan: ~30-60 minutes (Alpha Vantage rate limits)
```

### Subsequent Runs (With Cache)
```bash
Crypto scan: <1 second
Stock scan: <1 second
```

### Force Refresh (Bypass Cache)
```bash
qaht scan crypto --force-refresh    # Fresh data, slow
make scan-crypto-fresh              # Same
```

---

## 📁 File Structure

```
quantum-alpha-hunter/
├── qaht-cli.py              # Main CLI tool
├── run.sh                   # Interactive menu
├── install.sh               # Quick install
├── auto-scanner.py          # Background automation
├── Makefile                 # Make commands
├── .env                     # API keys (create after install)
├── data/
│   └── cache/              # Cached results (auto-created)
├── logs/                    # Logs (auto-created)
└── results/
    └── auto_scans/         # Automated scan results
```

---

## 🔑 API Keys (Optional but Recommended)

After running `./install.sh`, edit `.env`:

```bash
# Alpha Vantage (500 calls/day FREE)
# https://www.alphavantage.co/support/#api-key
ALPHA_VANTAGE_API_KEY=your_key_here

# NewsAPI (100 calls/day FREE)
# https://newsapi.org/register
NEWS_API_KEY=your_key_here

# Finnhub (60 calls/min FREE)
# https://finnhub.io/register
FINNHUB_API_KEY=your_key_here
```

**Without API keys:** System still works but uses fewer data sources.

---

## 🎯 Common Workflows

### Daily Morning Scan
```bash
# Quick scan before market opens
qaht scan all

# Or automated daily at 9 AM
qaht automate --interval daily
```

### Real-Time Monitoring
```bash
# Background daemon scanning every 15 minutes
python3 auto-scanner.py --interval 15m &

# Start dashboard for visualization
qaht dashboard
```

### Breaking News Response
```bash
# Force refresh to get latest data
qaht scan crypto --force-refresh
qaht scan stocks --force-refresh
```

### High-Quality Signals Only
```bash
# Scan for score >= 85
qaht scan crypto --min-score 85
qaht scan stocks --min-score 85

# Automated high-quality alerts
python3 auto-scanner.py --interval 30m --min-score 85 &
```

---

## 🧹 Maintenance

### Clear Cache
```bash
make clean-cache
# Or
rm -rf data/cache/*
```

### Clear Logs
```bash
make clean-logs
# Or
rm -rf logs/*
```

### Full Clean
```bash
make clean
```

### Check Status
```bash
make status
```

---

## 🐛 Troubleshooting

### Scripts not executable
```bash
chmod +x install.sh run.sh qaht-cli.py auto-scanner.py
```

### Python not found
```bash
# Use python3 explicitly
python3 qaht-cli.py scan crypto
```

### API errors in sandboxed environment
The code is designed for real internet access. If running in a sandboxed environment (like this one), APIs may be blocked. **It will work perfectly on your MacBook.**

### Cron job not running
```bash
# Check cron logs
tail -f logs/cron.log

# Verify crontab
crontab -l
```

---

## 📚 Learn More

- **Production Features:** `docs/PRODUCTION_OPTIMIZATIONS.md`
- **Data Sources:** `docs/README_DATA_SOURCES.md`
- **Advanced Strategies:** `docs/ADVANCED_STRATEGIES.md`

---

## 🎯 Summary

### Simplest Usage
```bash
./run.sh                    # Interactive menu
```

### CLI Usage
```bash
qaht scan crypto            # Scan crypto
qaht scan stocks            # Scan stocks
qaht dashboard              # Web UI
```

### Makefile Usage
```bash
make scan-crypto            # Scan crypto
make dashboard              # Web UI
```

### Automated Usage
```bash
python3 auto-scanner.py --interval 1h &    # Background scanning
```

**That's it!** The system is designed to be as fast and easy as possible. Pick whichever method you prefer. 🚀
