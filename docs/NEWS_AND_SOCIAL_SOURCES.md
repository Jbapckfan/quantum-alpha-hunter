# 📰 News & Social Sentiment Sources

Complete list of all current and recommended sources for market intelligence.

---

## ✅ CURRENTLY INTEGRATED

### News Sources (4 Active)

| Source | Type | Cost | Rate Limit | Coverage |
|--------|------|------|------------|----------|
| **NewsAPI** | REST API | 100/day FREE | 100 calls/day | General news, business, crypto |
| **Google News RSS** | RSS Feed | Unlimited FREE | No limit | All topics, real-time |
| **Finnhub** | REST API | 60/min FREE | 60 calls/min | Stock news, company updates |
| **Yahoo Finance RSS** | RSS Feed | Unlimited FREE | No limit | Stock-specific news |

**Total:** 4 news sources (all FREE)

### Social Sentiment Sources (Reddit)

| Platform | Subreddits | Metrics Tracked |
|----------|------------|-----------------|
| **Reddit** | 11 subreddits | Mentions, engagement, author entropy |

**Equity Subreddits (7):**
- r/wallstreetbets (15M+ members) - Retail sentiment king
- r/stocks (6M+ members) - Quality discussions
- r/investing (2.4M+ members) - Long-term focus
- r/StockMarket (2M+ members) - Market analysis
- r/pennystocks (314K+ members) - Small cap focus
- r/Shortsqueeze (138K+ members) - Squeeze plays
- r/smallstreetbets (361K+ members) - Small account traders

**Crypto Subreddits (4):**
- r/CryptoCurrency (7.9M+ members) - Largest crypto community
- r/CryptoMarkets (2.1M+ members) - Trading focus
- r/CryptoMoonShots (1.5M+ members) - Altcoin speculation
- r/SatoshiStreetBets (526K+ members) - Crypto WSB

**Metrics Tracked:**
- Mention count (7-day vs 30-day delta)
- Author entropy (organic vs coordinated)
- Engagement ratio (upvotes, comments)
- Sentiment (positive, negative, neutral)

---

## 🚀 RECOMMENDED ADDITIONS (10+ High-Yield Sources)

### 1. Twitter/X (CRITICAL - Highest Signal)

**Why:** Real-time breaking news, institutional traders, influencers

**Key Accounts to Track:**

**Market-Moving Influencers:**
- @elonmusk (200M+ followers) - Tesla, crypto moves markets
- @CathieDWood (2M+) - ARK Invest, growth stocks
- @jimcramer (2M+) - CNBC, retail sentiment indicator
- @chamath (1.7M+) - SPAC king, growth stocks
- @GaryGensler (300K+) - SEC Chair, regulatory news

**Crypto Influencers:**
- @VitalikButerin (5.3M+) - Ethereum founder
- @APompliano (1.7M+) - Bitcoin bull
- @CryptoCobain (868K+) - Trading alpha
- @TheCryptoLark (515K+) - Altcoin analysis
- @AltcoinGordon (470K+) - Crypto moonshots

**Whale Watchers & Data:**
- @whale_alert (1.3M+) - Large transactions
- @lookonchain (450K+) - On-chain analysis
- @unusual_whales (600K+) - Options flow
- @SwaggyStocks (120K+) - WSB tracker

**Financial News:**
- @zerohedge (1.4M+) - Breaking financial news
- @FT (5M+) - Financial Times
- @WSJ (21M+) - Wall Street Journal
- @Bloomberg (4M+) - Bloomberg News
- @Reuters (27M+) - Reuters

**API:** Twitter API v2 (Essential tier: $100/month, 50K tweets/month)
**Alternative:** Nitter instances (FREE but rate limited)

### 2. StockTwits (Essential for Stocks & Crypto)

**Why:** Trader-focused social network, real-time sentiment, cashtag tracking

**Features:**
- Cashtag tracking ($AAPL, $BTC)
- Sentiment labels (bullish/bearish)
- Trending tickers
- Message volume spikes
- Follower counts per ticker

**API:** 200 calls/hour FREE, 400/hour with upgrade
**URL:** https://stocktwits.com
**Docs:** https://api.stocktwits.com/developers/docs

**Example metrics:**
- Message volume (24h, 7d delta)
- Bullish vs bearish ratio
- Top trending tickers
- Influencer sentiment

### 3. Discord Servers (High-Quality Alpha)

**Why:** Private communities, early signals, insider discussions

**Top Stock Discord Servers:**
- **Quant's Playground** (100K+ members) - Options flow, unusual activity
- **Stock Market Live** (50K+) - Day trading community
- **Penny Stock Hub** (30K+) - Small cap plays
- **Options Millionaires** (25K+) - Options trading
- **Bulls on Wall Street** (20K+) - Technical analysis

**Top Crypto Discord Servers:**
- **Wall Street Bets** (500K+ members) - Cross-asset
- **The Whale's Lounge** (150K+) - Crypto trading
- **CryptoHQ** (100K+) - Altcoin alpha
- **Hodlers Paradise** (80K+) - Long-term investing
- **DeFi Pulse** (50K+) - DeFi projects

**Metrics to Track:**
- Message volume (spikes indicate action)
- Ticker mentions frequency
- Sentiment (positive/negative keywords)
- Influential member sentiment
- New channel creation (project-specific)

**API:** Discord.py library (FREE)
**Note:** Requires bot setup per server (some servers allow, some don't)

### 4. Telegram Groups (Crypto-Heavy)

**Why:** Crypto-native platform, early project announcements, pump groups (to fade)

**Top Groups:**
- **Crypto Signals** (500K+ members)
- **Binance English** (400K+)
- **CoinMarketCap** (300K+)
- **CryptoWhales** (250K+)
- **DeFi Talks** (150K+)
- **Altcoin Buzz** (120K+)

**Metrics:**
- Message volume
- New member growth rate
- Admin announcements (project updates)
- Bot commands (price checks)

**API:** Telethon library (FREE)
**URL:** https://core.telegram.org/api

### 5. YouTube (Video Sentiment & Retail Hype)

**Why:** Retail investor sentiment, influencer reach, trending topics

**Top Finance YouTubers:**
- **Meet Kevin** (1.9M+ subs) - Stocks, real estate, market analysis
- **Andrei Jikh** (2.6M+) - Personal finance, investing
- **Graham Stephan** (4.5M+) - Real estate, investing
- **Financial Education** (1.3M+) - Stock analysis
- **Jeremy Financial Education** (1M+) - Stock picks

**Top Crypto YouTubers:**
- **Coin Bureau** (2.6M+ subs) - Crypto education, analysis
- **Altcoin Daily** (1.5M+) - Daily crypto news
- **BitBoy Crypto** (1.4M+) - Crypto moonshots (fade signal)
- **Ivan on Tech** (471K+) - DeFi, blockchain
- **The Moon** (700K+) - Bitcoin analysis

**Metrics to Track:**
- Video upload frequency
- Views (24h, 7d)
- Like/dislike ratio
- Comment sentiment
- Trending videos by ticker

**API:** YouTube Data API v3 (10K queries/day FREE)
**URL:** https://developers.google.com/youtube/v3

### 6. 4chan /biz/ Board (Early Signals, High Noise)

**Why:** Early meme stock detection, contrarian indicators, crypto moonshots

**What to Track:**
- Thread creation frequency per ticker
- Post volume
- Unique IDs (active users)
- Keywords: "moon", "dump", "scam", "gem"

**Signal Quality:**
- HIGH NOISE, but early signals (GME, DOGE were 4chan darlings first)
- Track 7-day mention delta
- Useful for crypto altcoins before they hit Reddit

**API:** 4chan API (FREE, no auth required)
**URL:** https://a.4cdn.org/biz/catalog.json
**Docs:** https://github.com/4chan/4chan-API

**Note:** Filter heavily, high spam/shill ratio

### 7. Seeking Alpha (Quality Analysis)

**Why:** Professional-grade analysis, earnings coverage, institutional sentiment

**Features:**
- Analyst ratings
- Earnings transcripts
- Market analysis
- Sector rotation
- Dividend tracking

**API:** Seeking Alpha Quant Ratings (paid)
**Alternative:** RSS feeds (FREE)
**URL:** https://seekingalpha.com

### 8. TradingView Ideas & Scripts (Technical Sentiment)

**Why:** Trader sentiment, technical analysis, chart patterns

**Metrics:**
- Published ideas (bullish vs bearish)
- Script mentions (e.g., RSI oversold)
- Popular ideas by ticker
- Indicator alerts

**API:** TradingView Public API (limited)
**Alternative:** Scrape public profiles (respectfully)
**URL:** https://www.tradingview.com

### 9. Benzinga News & Social (Real-Time)

**Why:** Real-time news, options flow, social sentiment scores

**Features:**
- Breaking news alerts
- Options flow unusual activity
- Social sentiment scores
- Pre-market movers

**API:** Benzinga Cloud (paid, but has free tier)
**URL:** https://www.benzinga.com/apis/cloud

### 10. Quiver Quantitative (Alternative Data)

**Why:** Reddit, Congress trades, lobbying, insider trading

**Features:**
- Reddit WSB tracker
- Congressional stock trades
- Lobbying activity
- Insider trading filings
- Government contracts

**API:** Quiver Quant API (paid)
**Alternative:** Free dashboard tracking
**URL:** https://www.quiverquant.com

### 11. LunarCrush (Crypto Social Intelligence)

**Why:** Aggregated crypto social metrics from Twitter, Reddit, YouTube, Medium

**Features:**
- Galaxy Score (social + price)
- AltRank (social volume rank)
- Social engagement
- Influencer tracking
- Sentiment analysis

**API:** LunarCrush API (FREE tier: 150 calls/month)
**URL:** https://lunarcrush.com/developers/api

### 12. Santiment (On-Chain + Social)

**Why:** On-chain data + social sentiment for crypto

**Features:**
- Social volume (Twitter, Reddit, Telegram, Discord)
- Whale transactions
- Development activity
- Network growth
- Token age consumed

**API:** SanAPI (paid, but has free tier)
**URL:** https://app.santiment.net

---

## 📊 IMPLEMENTATION PRIORITY

### Tier 1: Must-Have (Highest Signal-to-Noise)
1. **Twitter/X** - Market-moving, real-time, influencer tracking
2. **StockTwits** - Trader sentiment, ticker-specific
3. **YouTube** - Retail hype indicator, trending topics
4. **Seeking Alpha** - Quality analysis, earnings

### Tier 2: High Value (Strong Signal)
5. **Discord** - Private communities, early alpha
6. **Telegram** - Crypto-specific, project announcements
7. **LunarCrush** - Aggregated crypto social
8. **Quiver Quant** - Alternative data (Congress, insiders)

### Tier 3: Specialized (Niche but Valuable)
9. **TradingView** - Technical trader sentiment
10. **4chan /biz/** - Very early signals (high noise)
11. **Benzinga** - Real-time news + options flow
12. **Santiment** - On-chain + social for crypto

---

## 🎯 RECOMMENDED INTEGRATION ORDER

### Phase 1: Add the Big 3
```python
# 1. Twitter/X API
#    Cost: $100/month (Essential tier)
#    Signal: 🔥🔥🔥🔥🔥
#    Track: @whale_alert, @unusual_whales, @elonmusk, etc.

# 2. StockTwits API
#    Cost: FREE (200 calls/hour)
#    Signal: 🔥🔥🔥🔥
#    Track: Cashtags, sentiment, trending

# 3. YouTube API
#    Cost: FREE (10K queries/day)
#    Signal: 🔥🔥🔥
#    Track: Video uploads, views, comments
```

### Phase 2: Add Specialized
```python
# 4. LunarCrush (crypto)
#    Cost: FREE tier
#    Signal: 🔥🔥🔥

# 5. Discord bots
#    Cost: FREE (setup required)
#    Signal: 🔥🔥🔥🔥

# 6. Telegram
#    Cost: FREE
#    Signal: 🔥🔥🔥
```

### Phase 3: Advanced
```python
# 7. Quiver Quant
#    Cost: Paid
#    Signal: 🔥🔥🔥🔥

# 8. Seeking Alpha
#    Cost: RSS free, API paid
#    Signal: 🔥🔥🔥

# 9. 4chan /biz/
#    Cost: FREE
#    Signal: 🔥🔥 (high noise)
```

---

## 💡 KEY INSIGHTS

### What to Track (Most Predictive)

1. **Volume Delta (7d vs 30d)**
   - 5x+ spike = explosion incoming
   - GME: 100 → 5,000 mentions in 3 days

2. **Influencer Sentiment Flips**
   - When whales change direction
   - @elonmusk tweets move markets

3. **Cross-Platform Convergence**
   - When same ticker trends on Reddit + Twitter + StockTwits + YouTube
   - Multi-platform confirmation = strong signal

4. **Author Entropy**
   - High entropy = organic growth
   - Low entropy = coordinated pump

5. **Engagement Quality**
   - High engagement = conviction
   - Low engagement = passing mention

### Signal Quality Ranking

| Platform | Signal | Noise | Best For |
|----------|--------|-------|----------|
| **Twitter/X** | ⭐⭐⭐⭐⭐ | ⭐⭐ | Real-time, breaking news, whales |
| **StockTwits** | ⭐⭐⭐⭐ | ⭐⭐ | Trader sentiment, cashtags |
| **Discord** | ⭐⭐⭐⭐⭐ | ⭐ | Private alpha, early signals |
| **Reddit** | ⭐⭐⭐⭐ | ⭐⭐⭐ | Retail sentiment, meme stocks |
| **YouTube** | ⭐⭐⭐ | ⭐⭐ | Retail hype, trending |
| **Telegram** | ⭐⭐⭐ | ⭐⭐⭐⭐ | Crypto early signals, pumps (fade) |
| **Seeking Alpha** | ⭐⭐⭐⭐ | ⭐ | Quality analysis |
| **4chan /biz/** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Very early signals (filter heavily) |

---

## 📝 QUICK START (On Your MacBook)

### 1. Install Dependencies
```bash
pip install tweepy praw stocktwits discord.py telethon youtube-data-api lunarcrush-python
```

### 2. Get API Keys (Free Tiers)

```bash
# Add to .env file:

# Twitter (Required - $100/month Essential tier)
TWITTER_API_KEY=your_key
TWITTER_API_SECRET=your_secret
TWITTER_BEARER_TOKEN=your_token

# StockTwits (FREE - 200 calls/hour)
STOCKTWITS_ACCESS_TOKEN=your_token

# YouTube (FREE - 10K queries/day)
YOUTUBE_API_KEY=your_key

# Reddit (Already configured)
REDDIT_CLIENT_ID=your_id
REDDIT_CLIENT_SECRET=your_secret

# LunarCrush (FREE - 150 calls/month)
LUNARCRUSH_API_KEY=your_key

# Discord (FREE - per server)
DISCORD_BOT_TOKEN=your_token

# Telegram (FREE)
TELEGRAM_API_ID=your_id
TELEGRAM_API_HASH=your_hash
```

### 3. Priority Order
1. **Twitter** - Pay $100/month, highest ROI
2. **StockTwits** - FREE, easy integration
3. **YouTube** - FREE, retail sentiment
4. **LunarCrush** - FREE tier, crypto aggregate
5. **Discord/Telegram** - FREE, setup takes time

---

## 🎯 SUMMARY

**Currently Integrated:**
- ✅ 4 news sources (NewsAPI, Google News, Finnhub, Yahoo Finance)
- ✅ 1 social platform (Reddit with 11 subreddits)

**High-Yield Additions (Recommended):**
1. ⭐⭐⭐⭐⭐ Twitter/X ($100/month) - Highest signal
2. ⭐⭐⭐⭐⭐ StockTwits (FREE) - Easy win
3. ⭐⭐⭐⭐⭐ Discord (FREE) - Private alpha
4. ⭐⭐⭐⭐ YouTube (FREE) - Retail hype
5. ⭐⭐⭐⭐ LunarCrush (FREE) - Crypto aggregate
6. ⭐⭐⭐⭐ Quiver Quant (Paid) - Alt data
7. ⭐⭐⭐ Telegram (FREE) - Crypto early signals
8. ⭐⭐⭐ Seeking Alpha (RSS Free) - Quality analysis
9. ⭐⭐⭐ TradingView (Limited) - Technical sentiment
10. ⭐⭐⭐ 4chan /biz/ (FREE) - Very early (noisy)
11. ⭐⭐⭐ Benzinga (Paid) - Real-time + options
12. ⭐⭐⭐ Santiment (Paid) - Crypto on-chain

**Next Step:** Add Twitter/X (best ROI) and StockTwits (FREE, easy) first.

---

**Questions?** Check individual API docs or ask for integration help!
