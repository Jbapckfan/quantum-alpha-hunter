# 🚀 Production Usage Guide

Complete guide for running Quantum Alpha Hunter in production mode with daily signals, backtesting, and automated maintenance.

---

## 📅 Daily Workflow

### 1. Run the Data Pipeline

Fetch latest data and generate scores:

```bash
# Run full pipeline (morning, before market open)
qaht run-pipeline

# Or run for specific asset types
qaht run-pipeline --asset-type stock
qaht run-pipeline --asset-type crypto
```

This will:
- Fetch latest prices (Yahoo Finance, CoinGecko, Binance)
- Fetch social sentiment (Reddit mentions)
- Compute technical features
- Compute social deltas
- Label recent explosions
- Train/update scoring models
- Generate quantum scores for all symbols

### 2. Generate Alerts

Get high-conviction signals immediately:

```bash
# Console output only
python scripts/daily_score_and_alert.py --min-score 80

# Send email alert
python scripts/daily_score_and_alert.py --min-score 80 --email your@email.com

# Send to Slack
python scripts/daily_score_and_alert.py --min-score 80 --slack-webhook https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Send to Telegram
python scripts/daily_score_and_alert.py --min-score 80 \
  --telegram-bot-token YOUR_BOT_TOKEN \
  --telegram-chat-id YOUR_CHAT_ID

# Save to file for later review
python scripts/daily_score_and_alert.py --min-score 80 --save-file
```

**Alert Output Example:**
```
🎯 QUANTUM ALPHA HUNTER - Daily Signals
📅 Date: 2024-11-05 09:30
🔥 Found 5 high-conviction opportunities

🚀 MAX CONVICTION (2)
--------------------------------------------------
  TSLA     | Score:  95 | Prob: 78.5%
  BTC-USD  | Score:  92 | Prob: 74.2%

⭐ HIGH CONVICTION (3)
--------------------------------------------------
  NVDA     | Score:  87 | Prob: 68.3%
  ETH-USD  | Score:  84 | Prob: 65.1%
  AMD      | Score:  81 | Prob: 61.7%
```

### 3. Review Dashboard

Launch the interactive dashboard to analyze signals:

```bash
qaht dashboard
```

The dashboard provides:
- **Watchlist**: Filter by score, view top signals
- **Symbol Analysis**: Deep dive into individual symbols with charts
- **Performance**: Hit rates by conviction level, score distribution

---

## 📊 Backtesting

### Run Historical Backtest

Test your strategy on historical data to validate performance:

```bash
# Basic backtest
qaht backtest --start 2023-01-01 --end 2024-01-01

# Custom parameters
qaht backtest \
  --start 2023-01-01 \
  --end 2024-01-01 \
  --min-score 85 \
  --max-positions 5 \
  --position-size 0.15 \
  --profit-target 0.40 \
  --stop-loss -0.12
```

**Parameters:**
- `--start`: Start date (YYYY-MM-DD)
- `--end`: End date (YYYY-MM-DD)
- `--min-score`: Minimum quantum score to enter (default: 70)
- `--max-positions`: Max concurrent positions (default: 10)
- `--position-size`: Position size as % of capital (default: 0.10 = 10%)
- `--profit-target`: Take profit at this return (default: 0.50 = 50%)
- `--stop-loss`: Stop loss threshold (default: -0.15 = -15%)
- `--max-hold-days`: Maximum hold time (default: 14 days)

**Example Output:**
```
============================================================
BACKTEST PERFORMANCE SUMMARY
============================================================
Total Trades: 47
Hit Rate: 68.1%
Average Return: 12.34%
Win/Loss Ratio: 2.87
------------------------------------------------------------
Total P&L: $34,567.00
Final Capital: $134,567.00
Total Return: 34.6%
------------------------------------------------------------
Sharpe Ratio: 1.87
Sortino Ratio: 2.34
Max Drawdown: 7.2%
Profit Factor: 3.21
------------------------------------------------------------
Avg Hold: 8.4 days
Expectancy: 8.23%
============================================================

Performance by Conviction Level:
  MAX :  12 trades | Hit Rate:  83.3% | Avg Return: +18.45% | P&L: $18,234.00
  HIGH:  23 trades | Hit Rate:  69.6% | Avg Return: +10.23% | P&L: $12,456.00
  MED :  12 trades | Hit Rate:  50.0% | Avg Return:  +5.67% | P&L:  $3,877.00
```

### Python Backtesting API

For custom backtesting logic:

```python
from qaht.backtest import simulate, calculate_performance

# Run simulation
trades_df = simulate(
    start_date='2023-01-01',
    end_date='2024-01-01',
    initial_capital=100000,
    min_score=80,
    max_positions=10,
    position_size_pct=0.10,
    profit_target=0.50,
    stop_loss=-0.15,
    symbols=['TSLA', 'NVDA', 'BTC-USD']  # Optional filter
)

# Calculate metrics
metrics = calculate_performance(trades_df, initial_capital=100000)

print(f"Hit Rate: {metrics['hit_rate']:.2%}")
print(f"Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
print(f"Max Drawdown: {metrics['max_drawdown']:.2%}")

# Analyze by score bucket
from qaht.backtest import calculate_score_bucket_performance
bucket_perf = calculate_score_bucket_performance(trades_df)
print(bucket_perf)
```

---

## 🔄 Monthly Maintenance

### Automated Retraining

Run monthly to keep models fresh:

```bash
# Full analysis and retraining
python scripts/monthly_retrain.py

# Custom lookback period
python scripts/monthly_retrain.py --lookback-months 6 --min-samples 200

# Generate report only (skip retraining)
python scripts/monthly_retrain.py --skip-retrain --report-file reports/monthly_$(date +%Y%m).txt
```

This script:
1. Analyzes recent prediction performance
2. Calculates hit rates by conviction level
3. Checks model calibration
4. Identifies top/bottom performing features
5. Retrains models with latest data
6. Backs up old models with timestamp
7. Generates detailed performance report

**Example Output:**
```
============================================================
MONTHLY PERFORMANCE REPORT
============================================================

Analysis Period: Last 3 months
Total Predictions: 156

Performance by Conviction Level:
------------------------------------------------------------
MAX :   28 predictions | Hit Rate:  82.1% | Avg Return: +16.34%
HIGH:   54 predictions | Hit Rate:  70.4% | Avg Return: +11.23%
MED :   47 predictions | Hit Rate:  57.4% | Avg Return:  +6.78%
LOW :   27 predictions | Hit Rate:  44.4% | Avg Return:  +2.34%

Calibration Error: 0.0423
(Lower is better, <0.05 is well-calibrated)

Performance by Score Bucket:
------------------------------------------------------------
70-79 :  42 predictions | Hit Rate:  54.8% | Avg Return:  +5.67%
80-89 :  68 predictions | Hit Rate:  69.1% | Avg Return: +10.89%
90-99 :  38 predictions | Hit Rate:  81.6% | Avg Return: +15.23%
100   :   8 predictions | Hit Rate:  87.5% | Avg Return: +19.45%

============================================================
FEATURE IMPORTANCE ANALYSIS
============================================================

STOCK Features:
------------------------------------------------------------
bb_width_pct             : Corr=+0.423 | Explosive Avg=+0.082 | Normal Avg=+0.156
social_delta_7d          : Corr=+0.389 | Explosive Avg=+2.340 | Normal Avg=+0.234
ma_spread_pct            : Corr=+0.367 | Explosive Avg=+0.023 | Normal Avg=+0.089
volume_ratio_20d         : Corr=+0.312 | Explosive Avg=+1.890 | Normal Avg=+1.120
rsi_14                   : Corr=-0.287 | Explosive Avg=+42.30 | Normal Avg=+54.60
```

### Cron Schedule Recommendations

Add to your crontab for automation:

```bash
# Edit crontab
crontab -e

# Add these lines:

# Daily pipeline - run at 6 AM (before market open)
0 6 * * 1-5 cd /path/to/quantum-alpha-hunter && /path/to/venv/bin/python -m qaht run-pipeline

# Daily alerts - run at 6:30 AM
30 6 * * 1-5 cd /path/to/quantum-alpha-hunter && /path/to/venv/bin/python scripts/daily_score_and_alert.py --min-score 80 --email your@email.com --save-file

# Monthly retraining - run on 1st of month at 2 AM
0 2 1 * * cd /path/to/quantum-alpha-hunter && /path/to/venv/bin/python scripts/monthly_retrain.py --report-file reports/monthly_$(date +\%Y\%m).txt
```

---

## 🔧 Configuration

### Email Alerts

Set environment variables for email:

```bash
export SMTP_SERVER=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USER=your_email@gmail.com
export SMTP_PASSWORD=your_app_password  # Use app password for Gmail
```

### Slack Alerts

Create a Slack webhook:
1. Go to https://api.slack.com/apps
2. Create new app → Incoming Webhooks
3. Add to workspace and get webhook URL
4. Use in alert script: `--slack-webhook <URL>`

### Telegram Alerts

Setup Telegram bot:
1. Talk to @BotFather on Telegram
2. Create new bot with `/newbot`
3. Get bot token
4. Get your chat ID from @userinfobot
5. Use: `--telegram-bot-token <TOKEN> --telegram-chat-id <CHAT_ID>`

---

## 📈 Performance Targets

Track these KPIs monthly:

| Metric | MVP Target | Production Goal |
|--------|------------|-----------------|
| Hit Rate (Score 80+) | ≥70% | ≥75% |
| Sharpe Ratio | ≥1.5 | ≥2.0 |
| Max Drawdown | <8% | <6% |
| Profit Factor | ≥2.0 | ≥2.5 |
| Calibration Error | <0.08 | <0.05 |
| Multi-baggers/year (5x+) | 3-5 | 5-10 |

---

## 🛡️ Risk Management

### Built-in Safeguards

The backtest simulator includes:
- **Position Sizing**: 10% per position (configurable)
- **Max Positions**: 10 concurrent (prevents over-concentration)
- **Profit Targets**: Auto-exit at 50% gain (adjustable)
- **Stop Losses**: -15% hard stop (adjustable)
- **Time Stops**: Exit after 14 days max hold
- **Portfolio Limits**: Prevent over-exposure

### Recommended Manual Checks

Before acting on signals:
1. **Review Dashboard**: Understand WHY the score is high (which features)
2. **Check News**: Any catalyst or earnings coming?
3. **Verify Liquidity**: Can you actually enter/exit the position?
4. **Sector Exposure**: Don't load up all tech or all crypto
5. **Market Regime**: Bull/bear/choppy? Adjust position sizes accordingly

### Paper Trading First

Before going live:
1. Run 3-month backtest on recent data
2. Verify hit rates meet targets
3. Paper trade for 1 month minimum
4. Compare paper results to backtest
5. Only then start with small real positions

---

## 🐛 Troubleshooting

### Pipeline Failures

```bash
# Check logs
tail -f logs/qaht.log

# Validate configuration
qaht validate

# Test individual components
python scripts/quick_test.py
```

### No Signals Generated

Possible causes:
- No data in database (run pipeline first)
- Scores below threshold (try `--min-score 60`)
- Recent training data insufficient
- Check: `qaht analyze <symbol>` to see raw scores

### Alert Delivery Issues

**Email not sending:**
- Verify SMTP credentials
- Check firewall/port 587 access
- For Gmail, enable "Less secure app access" or use App Password

**Slack webhook failing:**
- Verify webhook URL is correct
- Check workspace permissions
- Test with curl: `curl -X POST -H 'Content-type: application/json' --data '{"text":"Test"}' WEBHOOK_URL`

### Model Performance Degrading

If hit rates drop below targets:
1. Run `monthly_retrain.py` immediately
2. Check if market regime changed
3. Review feature importance - some features may have stopped working
4. Consider expanding training data window
5. Add new features if available

---

## 📚 Advanced Usage

### Custom Universe

Create a CSV with symbols to track:

```csv
AAPL
TSLA
NVDA
AMD
BTC-USD
ETH-USD
```

Run pipeline:
```bash
qaht run-pipeline --universe data/universe/my_watchlist.csv
```

### API Integration

The system is designed for easy integration:

```python
from qaht.db import session_scope
from qaht.schemas import Predictions
from sqlalchemy import select, desc

# Get today's top signal programmatically
with session_scope() as session:
    top_signal = session.execute(
        select(Predictions)
        .where(Predictions.date == '2024-11-05')
        .order_by(desc(Predictions.quantum_score))
        .limit(1)
    ).scalar_one_or_none()

    if top_signal:
        print(f"Top signal: {top_signal.symbol}")
        print(f"Score: {top_signal.quantum_score}")
        print(f"Probability: {top_signal.prob_hit_10d:.2%}")
```

### Database Queries

Access all data via SQLAlchemy:

```python
from qaht.db import session_scope
from qaht.schemas import PriceOHLC, Factors, Labels, Predictions
from sqlalchemy import select, func

# Get best performing symbols over last month
with session_scope() as session:
    results = session.execute(
        select(
            Labels.symbol,
            func.count(Labels.explosive_10d).label('explosions'),
            func.avg(Labels.fwd_ret_10d).label('avg_return')
        )
        .where(
            Labels.date >= '2024-10-01',
            Labels.explosive_10d == True
        )
        .group_by(Labels.symbol)
        .order_by(desc('explosions'))
        .limit(10)
    ).all()

    for symbol, count, avg_ret in results:
        print(f"{symbol}: {count} explosions, {avg_ret:.2%} avg return")
```

---

## 🎯 Next Steps

1. **Validate Setup**: Run `qaht validate` to check configuration
2. **Initial Backtest**: Test on 2023 data to establish baseline
3. **Paper Trade**: Run daily for 1 month without real money
4. **Go Live**: Start with small positions (1-2% each)
5. **Monitor**: Track monthly performance vs targets
6. **Optimize**: Adjust parameters based on results

**Remember:** This is a tool to find opportunities, not a guarantee. Always do your own research, manage risk carefully, and never invest more than you can afford to lose.

---

**Built with ❤️ for finding asymmetric opportunities before they're obvious.**
