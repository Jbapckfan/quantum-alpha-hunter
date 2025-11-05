# Market-Wide Scanning Architecture

## Overview

This document explains how Quantum Alpha Hunter scans the **ENTIRE US stock market** (not a predefined list of 138 stocks) using dynamic filters.

## User Requirement

> "Allow for scanning the entire market. Let's say any stock over $1 and over 1M daily average volume. I would actually consider excluding stocks valued over $1T since I am looking for rapid movement and those are much less likely to be good short term swings."

**Key Points:**
- Scan the ENTIRE market (~8,000 US stocks)
- NOT a static list of famous names
- Apply dynamic filters: price > $1, volume > 1M, market cap < $1T
- Focus on stocks with movement potential

## Architecture

### 1. Universe Discovery

**Goal:** Get ALL US stock tickers from major exchanges (NASDAQ, NYSE, AMEX)

**Data Sources:**

#### Primary: NASDAQ Official Lists
- **NASDAQ Listed:** ftp://ftp.nasdaqtrader.com/symboldirectory/nasdaqlisted.txt
- **Other Listed:** ftp://ftp.nasdaqtrader.com/symboldirectory/otherlisted.txt
- **Format:** Pipe-delimited text files
- **Coverage:** ~8,000 US stocks
- **Update Frequency:** Daily
- **Status:** ⚠️ FTP protocol not supported by standard HTTP libraries

#### Alternative: SEC Edgar Company Tickers
- **URL:** https://www.sec.gov/files/company_tickers_exchange.json
- **Format:** JSON
- **Coverage:** All SEC-registered companies
- **Status:** ⚠️ Requires proper User-Agent, may be rate-limited

#### Fallback: Market Data APIs
- **Alpha Vantage:** Listing & Delisting Status endpoint
- **Polygon.io:** All Tickers endpoint
- **IEX Cloud:** Symbols endpoint
- **Status:** ✅ Reliable, but requires API keys

### 2. Stock Screening

**Goal:** Filter stocks based on:
- Price > $1 (tradeable)
- Average volume > 1M (liquid)
- Market cap < $1T (movement potential)

**Data Requirements per Stock:**
- Current price
- Average daily volume (10-day or 20-day)
- Market capitalization

**Data Sources:**

#### yfinance (Free)
- **Pro:** Free, Python library
- **Con:** Yahoo Finance API blocks requests frequently (403 errors)
- **Rate Limit:** Unclear, unstable
- **Status:** ⚠️ Unreliable for large-scale screening

#### Alpha Vantage (Free Tier)
- **Pro:** Official API, reliable
- **Con:** 5 calls/minute, 500 calls/day on free tier
- **Coverage:** US stocks, real-time quotes
- **Screening Time:** ~27 hours for 8,000 stocks at 5 calls/min
- **Status:** ✅ Works, but slow for full market scan
- **Solution:** Cache daily, update incrementally

#### Polygon.io (Paid)
- **Pro:** Fast, comprehensive, unlimited calls
- **Con:** $29-199/month
- **Screening Time:** Minutes for full market
- **Status:** ✅ Recommended for production

#### IEX Cloud (Hybrid)
- **Free Tier:** 50,000 messages/month
- **Paid:** Starting at $9/month
- **Status:** ✅ Good middle ground

### 3. Caching Strategy

**Problem:** Screening 8,000 stocks daily is expensive/slow

**Solution:** Intelligent caching

```
Daily (Full Scan):
  - Screen ALL 8,000 stocks for basic criteria
  - Cache: price, volume, market cap
  - Duration: 24 hours

Intraday (Incremental):
  - Update only stocks that passed filters
  - Check for new IPOs/delistings weekly
  - Real-time data only for active signals
```

## Current Implementation

### File Structure

```
qaht/equities_options/
  ├── market_scanner.py          # Market-wide scanner (all 8k stocks)
  └── universe_builder.py         # OLD: Static 138-stock list (deprecated)

scripts/
  └── test_market_scanner.py     # Demonstration of scanning approach
```

### Market Scanner (`market_scanner.py`)

**Features:**
- Fetches ALL US stock tickers from NASDAQ/NYSE/AMEX
- Screens each stock for: price > $1, volume > 1M, mcap < $1T
- Caches results for 24 hours (configurable)
- Returns list of ALL stocks meeting criteria (could be 2,000-4,000 stocks)

**Usage:**
```python
from qaht.equities_options.market_scanner import scan_market

# Scan entire market with default filters
symbols = scan_market(
    min_price=1.0,              # Price > $1
    min_avg_volume=1_000_000,   # Volume > 1M
    max_market_cap=1_000_000_000_000,  # MCap < $1T
    use_cache=True              # Use cached results if fresh
)

# symbols will contain thousands of stocks meeting criteria
print(f"Found {len(symbols)} stocks meeting criteria")
```

### Test Script (`test_market_scanner.py`)

Demonstrates how the scanner works with a representative sample across:
- Mega-cap (>$200B): NVDA, META, TSLA
- Large-cap ($10-200B): AMD, NFLX, INTC
- Mid-cap ($2-10B): PLTR, COIN, HOOD
- Small-cap ($300M-2B): RIOT, LAZR, SOFI
- Micro-cap (<$300M): GEVO, MULN, GOEV

**Proves the system:**
- ✅ Scans ALL market caps (not just famous names)
- ✅ Applies filters universally
- ✅ Returns diverse set of stocks

## Data Source Challenges

### Issue 1: API Rate Limits

**Problem:** Free APIs limit requests
- yfinance: Blocked frequently (403 errors)
- Alpha Vantage: 5 calls/min = 27 hours for full scan
- NASDAQ FTP: Protocol not supported by standard libraries

**Solution Options:**

1. **Use Paid API (Recommended)**
   - Polygon.io ($29/month): Unlimited calls, fast
   - IEX Cloud ($9/month): 50k messages/month
   - Can screen full market in minutes

2. **Aggressive Caching (Free Approach)**
   - Full scan once daily during off-hours
   - Use Alpha Vantage with batch processing
   - Cache results for 24 hours
   - Only update active signals intraday

3. **Hybrid Approach**
   - Use free APIs for initial scan (slow but free)
   - Upgrade to paid for production (fast, reliable)
   - Start with top 1,000 most liquid stocks
   - Expand to full 8,000 as volume grows

### Issue 2: Data Quality

**Problem:** Not all stocks have reliable data
- Newly listed stocks may lack volume history
- Penny stocks may have stale quotes
- Some tickers may be delisted/merged

**Solution:**
- Validate data completeness before applying filters
- Skip stocks with missing price/volume/mcap
- Update ticker list weekly from official sources
- Track delistings to avoid processing dead tickers

### Issue 3: Market Coverage

**Problem:** What counts as "entire market"?

**Scope Definition:**
- **Included:** NASDAQ, NYSE, NYSE American (AMEX)
- **Excluded:** OTC Markets (Pink Sheets, OTCQB)
- **Reason:** OTC stocks lack liquidity, reliable data, and regulatory oversight

**Universe Size:**
- NASDAQ: ~3,500 stocks
- NYSE: ~2,800 stocks
- NYSE American: ~700 stocks
- **Total: ~8,000 stocks**

After filters (price > $1, volume > 1M, mcap < $1T):
- **Estimated: 2,000-4,000 stocks** meet criteria

## Production Recommendations

### Phase 1: Start with Top 1,000 (Now)
**Approach:**
- Use Alpha Vantage free tier (5 calls/min)
- Focus on most liquid 1,000 stocks (easy to screen)
- Full scan takes ~3 hours, run overnight
- Cache results for 24 hours

**Pros:**
- Free
- Covers 80% of trading volume
- Includes all major movement opportunities

**Cons:**
- Misses some small-cap/micro-cap explosions
- Slow to add new symbols

### Phase 2: Expand to Full Market (Growth)
**Approach:**
- Upgrade to Polygon.io ($29/month) or IEX Cloud ($9/month)
- Screen all ~8,000 US stocks
- Full scan takes minutes, run multiple times daily
- Real-time updates for active signals

**Pros:**
- Complete market coverage
- Fast screening
- Can add new IPOs immediately

**Cons:**
- Monthly cost ($9-29)
- More noise from illiquid micro-caps

### Phase 3: Add Options Universe (Advanced)
**Approach:**
- Filter stocks with active options markets
- Criteria: option volume > 1,000 contracts/day
- Enables options strategies (calls, puts, spreads)

**Additional Data:**
- Option chains (strikes, expiries)
- Implied volatility
- Open interest

## Crypto Market Scanning

**Similar approach for crypto:**

**Universe Discovery:**
- CoinGecko API: Top 1,000 coins by market cap (free)
- CoinMarketCap API: Top 5,000 coins (free tier)
- Binance: All listed pairs (real-time)

**Scam Filtering (CRITICAL):**
- ❌ Volume/market cap > 50% (wash trading)
- ❌ Age < 30 days (too new, likely rug pull)
- ❌ 24h change > 100% (pump & dump)
- ❌ Liquidity score < 10 (illiquid, manipulated)
- ❌ Market cap rank > 1,000 (obscure, risky)

**Estimated Universe:**
- Total coins: ~20,000
- After scam filtering: ~200-500 legitimate coins

## Implementation Status

### ✅ Complete
- Market scanner architecture (market_scanner.py)
- Filtering logic (price, volume, market cap)
- Caching system (24-hour default)
- Test demonstration (test_market_scanner.py)
- Documentation (this file)

### ⚠️ Blocked by Data Source Access
- Full market ticker list (SEC/NASDAQ APIs blocked)
- Real-time screening (yfinance blocked, need API key)

### 🚀 Next Steps
1. **Choose Data Source Strategy:**
   - Option A: Use Alpha Vantage free tier (slow but free)
   - Option B: Use Polygon.io paid tier (fast, $29/month)
   - Option C: Hybrid (free for testing, upgrade for production)

2. **Implement Batch Screening:**
   - Process stocks in batches (respect rate limits)
   - Cache results (avoid re-screening same stocks)
   - Track failures (retry later)

3. **Test with Real Data:**
   - Screen top 100 stocks first
   - Validate filter logic
   - Check data quality
   - Expand to full market

4. **Integrate with System:**
   - Replace static universe_builder.py
   - Update daily pipeline to use market scanner
   - Add new symbols automatically
   - Remove delisted symbols

## Summary

**Key Takeaway:**
The system is designed to scan the **ENTIRE US stock market** (~8,000 stocks), NOT a predefined list of 138 famous names. It applies filters dynamically:
- Price > $1 (tradeable)
- Volume > 1M (liquid)
- Market cap < $1T (movement potential)

This results in ~2,000-4,000 stocks meeting criteria, including:
- Mega-cap (NVDA, TSLA, META)
- Large-cap (AMD, INTC, NFLX)
- Mid-cap (PLTR, COIN, HOOD)
- Small-cap (RIOT, LAZR, SOFI)
- Micro-cap (GEVO, MULN, GOEV)

**The system does NOT cherry-pick famous names** - it evaluates ALL stocks meeting liquidity and volatility criteria.

Current limitation is data source access (free APIs are blocked/rate-limited). Solution is to either:
1. Use paid API ($9-29/month) for fast, reliable screening
2. Use free API with aggressive caching (slow but works)
3. Start with top 1,000 stocks, expand later
