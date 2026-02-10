# Quantum Alpha Hunter - Crypto Scanner Guide

## Overview

The crypto scanner is significantly more advanced than the stock scanner, offering:
- **Faster data** - CoinGecko API with no restrictions
- **Better technicals** - RSI, Bollinger Bands, multi-timeframe momentum
- **Whale detection** - Flags when volume exceeds market cap
- **Volatility regime** - Expanding, contracting, or stable
- **Interactive charts** - 1h/4h/1d candlesticks with SMAs

---

## Quick Start

### 1. Run Advanced Crypto Scanner (CLI)
```bash
cd ~/Documents/quantum-alpha-hunter
source venv/bin/activate
python crypto_advanced.py
```

**Output:**
- Scans 250 top coins by volume
- Advanced multi-timeframe analysis
- Saves results to `crypto_advanced_YYYYMMDD_HHMMSS.csv`

### 2. Dashboard (Recommended)
```bash
streamlit run dashboard_live.py
```

Then:
1. Go to **🚀 CRYPTO tab**
2. Click **"Scan Crypto Now (Advanced)"**
3. Expand any result to see:
   - Multi-column metrics (Price, Changes, Vol/MCap ratio, RSI, Trend)
   - Visual indicators (💥 Explosive, ⚡ Accelerating, 🔄 Reversal)
   - Interactive charts with timeframe selector
   - All signals that triggered

---

## Scoring System (100 points max)

### 1. Momentum (40 points)
- **Explosive** (25 pts): 1H > 5% AND 24H > 10%
- **Pumping** (20 pts): 1H > 5%
- **Moving** (10 pts): 1H > 2%
- **Moon 24H** (15 pts): 24H > 30%
- **Breakout 24H** (10 pts): 24H > 15%
- **Up 24H** (5 pts): 24H > 5%

### 2. Acceleration & Trend (25 points)
- **Accelerating** (15 pts): 1H rate > 24H avg rate > 7D avg rate
- **Strong Uptrend** (10 pts): Positive across 1H, 24H, 7D
- **Reversal** (10 pts): Up 24H but down 7D (catching the turn)

### 3. Volume (15 points)
- **Whale Volume** (15 pts): Vol/MCap > 2.0x (extreme interest)
- **Mega Vol** (10 pts): Vol/MCap > 1.0x
- **High Vol** (5 pts): Volume > $100M

### 4. Technical Setup (10 points)
- **RSI > 70** (5 pts): Momentum
- **RSI < 30** (5 pts): Oversold
- **BB Breakout** (5 pts): Price > 95% of BB range
- **BB Squeeze** (5 pts): BB width < 5% (coiling)

### 5. Volatility (10 points)
- **Expanding** (10 pts): Recent volatility > Historical by 50%+
- **Coiling** (5 pts): Volatility contracting (potential explosion)

---

## Example: SAPIEN (90/100 Score)

**Breakdown:**
```
+25 pts: EXPLOSIVE (+7.6% 1H, +112% 24H)
+15 pts: MOON_24H (+112%)
+15 pts: ACCELERATING (momentum increasing)
+10 pts: STRONG_UPTREND (positive all timeframes)
+10 pts: MEGA_VOL (0.98x MCap)
+10 pts: VOL_EXPANSION
+5  pts: MOMENTUM_RSI (>70)
───────
= 90/100
```

**Why it works:**
- 💥 **Explosive**: Moving fast RIGHT NOW
- ⚡ **Accelerating**: Speed is INCREASING (not fading)
- 🔥 **High conviction**: Hit max points on 3 major categories

---

## Key Features

### Multi-Timeframe Analysis
- Compares 1H, 24H, 7D, 14D, 30D price changes
- Detects if momentum is **accelerating** or **decelerating**
- Identifies trend strength (STRONG_UP, SHORT_TERM_UP, MIXED, STRONG_DOWN)

### Technical Indicators
- **RSI (14)**: Momentum/overbought/oversold
- **Bollinger Bands (20, 2σ)**: Volatility and breakouts
- **SMAs (20/50/200)**: On charts for trend identification

### Volume Analysis
- **Vol/MCap Ratio**: When > 1.0x, indicates whale activity
- **Volume Trend**: Increasing = accumulation, decreasing = distribution

### Volatility Regime
- **Expanding**: Volatility increasing (breakout potential)
- **Contracting**: Volatility decreasing (squeeze/coil)
- **Stable**: Normal volatility

### Pattern Detection
- **Explosive**: Fast moves happening NOW
- **Sustained**: Multi-day momentum (not a flash)
- **Reversal**: Catching the turn early (24H up, 7D down)

---

## Filters

### In Dashboard:
- **Min Score**: 0-100 (default: 30)
- **Min 24H Change**: -50% to +100% (default: 0%)

### In Code:
- **Min Volume**: $500K/day (filters noise)
- **Min Market Cap**: $5M (filters scams)
- **Score Threshold**: 25+ shown (adjustable)

---

## Chart Features

### Timeframes:
- **1h**: 2 days of data (5-day period with 1h candles)
- **4h**: 7 days of data (resampled from 1h)
- **1d**: 365 days of data

### Overlays:
- SMA 20 (orange) - Short-term trend
- SMA 50 (blue) - Medium-term trend
- SMA 200 (purple) - Long-term trend

### Candlestick Colors:
- 🟢 Green: Close > Open (bullish candle)
- 🔴 Red: Close < Open (bearish candle)

---

## Files

### Scanners:
- `crypto_advanced.py` - **Use this** (sophisticated analysis)
- `crypto_scanner.py` - Basic version (simpler, faster)

### Dashboard:
- `dashboard_live.py` - Main Streamlit app with both stocks and crypto

### Output:
- `crypto_advanced_*.csv` - Full results with all metrics
- `crypto_scan_*.csv` - Basic scanner results

---

## Tips

### Finding the Best Opportunities:

1. **Look for 💥⚡ together**
   - Explosive + Accelerating = Strong conviction

2. **Check Vol/MCap ratio**
   - > 2.0x = Whales are active
   - > 1.0x = Significant interest

3. **Use charts to confirm**
   - Price above SMA 20/50 = Uptrend
   - Price breaking out of consolidation = Momentum starting

4. **Watch for reversals** 🔄
   - 24H up but 7D down = Catching the turn
   - High risk but high reward

5. **Combine signals**
   - ACCELERATING + WHALE_VOLUME = Whales buying into momentum
   - COILING + OVERSOLD_RSI = Spring loaded for bounce

### Risk Management:
- Higher scores = Higher confidence
- But crypto is volatile - use stop losses
- Vol/MCap > 2x = Could pump OR dump fast
- Reversals are riskier than sustained trends

---

## Advanced: Running Hourly

To track momentum changes over time:

```bash
# Add to crontab
0 * * * * cd ~/Documents/quantum-alpha-hunter && source venv/bin/activate && python crypto_advanced.py >> logs/crypto_scan.log 2>&1
```

Then compare results hour-over-hour to see:
- Which coins are gaining momentum
- Which are losing steam
- New entries (sudden volume/price spike)

---

## Comparison: Crypto vs Stocks

| Feature | Crypto Scanner | Stock Scanner |
|---------|---------------|---------------|
| Speed | Instant | Slow (Yahoo Finance) |
| Data Quality | Excellent | Good (some missing) |
| Technicals | RSI, BB, Multi-TF | Basic |
| Volume Analysis | Vol/MCap ratio | Vol ratio only |
| Volatility | Regime detection | Not analyzed |
| Charts | 1h/4h/1d | 1h/4h/1d |
| Social | Not yet | Reddit/WSB |
| Universe | 250 top coins | 250+ stocks |

**Winner:** Crypto scanner is more sophisticated and faster.

---

## Troubleshooting

### No results found:
- Lower min score to 20
- Check crypto_advanced_*.csv was created
- Market might be consolidating (normal)

### Charts not loading:
- CoinGecko API might be rate-limited
- Try selecting different timeframe
- Check internet connection

### Old data showing:
- Dashboard caches results
- Click "Scan Crypto Now" to refresh
- Check timestamp in CSV filename

### Dashboard not loading:
```bash
pkill -f streamlit
streamlit run dashboard_live.py --server.headless false
```

---

## Next Steps

1. **Run a scan** and explore the results
2. **Compare top picks** across multiple scans
3. **Use charts** to visually confirm momentum
4. **Track favorites** by running scans hourly
5. **Paper trade** to validate the signals

The crypto scanner is designed to find explosive opportunities BEFORE they moon. Use it wisely! 🚀
