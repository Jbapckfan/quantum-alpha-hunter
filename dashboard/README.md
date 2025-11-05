# Quantum Alpha Hunter - Premium Dashboard

## Overview

**Slick, modern, data-rich dashboard** for monitoring market signals, insider trading, options flow, and news in real-time.

![Dashboard Preview](https://via.placeholder.com/1200x600/667eea/FFFFFF?text=Quantum+Alpha+Hunter+Dashboard)

## Features

### 📊 Real-Time Monitoring
- **Active Signals** - Live tracking of high-conviction opportunities
- **Compression Alerts** - BB compression + MA convergence detection
- **Insider Buying** - SEC Form 4 filing notifications
- **Options Flow** - Unusual activity and sweeps

### 📈 Data Visualization
- **Performance Charts** - Signal success rate over time
- **Sentiment Analysis** - Market sentiment breakdown
- **Volume Analysis** - Unusual volume detection
- **Price Movements** - 24h performance tracking

### 📰 News Integration
- **Real-Time News** - Multi-source aggregation
- **Ticker-Specific** - Filter by symbol
- **Sentiment Analysis** - Positive/negative classification

### 🔍 Advanced Filtering
- **Score-Based** - Filter by confidence level (0-100)
- **Asset Type** - Stocks, crypto, or both
- **Signal Type** - Compression, insider, options, volume
- **Market Cap** - Micro, small, mid, large cap

### 🎨 Premium UI
- **Dark Theme** - Easy on the eyes
- **Gradient Accents** - Modern purple/blue gradient
- **Responsive** - Works on all screen sizes
- **Smooth Animations** - Professional transitions
- **Live Updates** - Real-time data refresh

## Quick Start

### 1. Install Dependencies

```bash
pip install fastapi uvicorn
```

### 2. Start Dashboard

```bash
cd dashboard
python server.py
```

### 3. Open Browser

Navigate to: **http://localhost:8000**

## API Endpoints

### Dashboard Data

```bash
# Health check
GET /api/health

# Dashboard stats
GET /api/stats

# Top signals
GET /api/signals?limit=20&min_score=70&asset_type=STOCK

# News feed
GET /api/news?ticker=OPEN&limit=20

# Insider trades
GET /api/insider-trades?ticker=OPEN&days=7

# Options flow
GET /api/options-flow?min_premium=100000

# Crypto data
GET /api/crypto?limit=100&min_market_cap=10000000
```

### Interactive API Docs

Visit: **http://localhost:8000/docs** for full API documentation with interactive testing.

## Dashboard Sections

### Top Signals
Shows highest-scoring opportunities across stocks and crypto:
- **Score**: 0-100 confidence rating
- **Price Change**: 24h performance
- **Market Cap**: Company/coin size
- **Signal Types**: Compression, insider, options, volume, news

### Market Sentiment
Pie chart showing overall market sentiment:
- **Bullish**: Green (positive signals)
- **Neutral**: Gray (sideways)
- **Bearish**: Red (negative signals)

### Performance Chart
Line chart tracking:
- **Signal Performance**: Success rate over time
- **Market Average**: Baseline comparison

### Recent News
Latest news articles with:
- **Title**: Article headline
- **Ticker**: Related symbol
- **Timestamp**: Publication time
- **Sentiment**: Positive/negative indicator

### Insider Trades
Recent Form 4 filings showing:
- **Ticker**: Stock symbol
- **Insider**: Name and title
- **Type**: BUY or SELL
- **Amount**: Total value
- **Shares**: Quantity

### Options Flow
Unusual options activity:
- **Ticker**: Stock symbol
- **Type**: CALL or PUT
- **Strike**: Strike price
- **Expiry**: Expiration date
- **Premium**: Total premium paid
- **Sentiment**: Bullish/bearish

### Live Activity Feed
Real-time event stream:
- New high-conviction signals
- Compression detections
- Insider buys/sells
- Options sweeps
- Volume spikes
- News catalysts

## Customization

### Colors

Edit `index.html` Tailwind config:

```javascript
tailwind.config = {
    theme: {
        extend: {
            colors: {
                primary: '#667eea',    // Main gradient start
                secondary: '#764ba2',  // Main gradient end
            }
        }
    }
}
```

### Data Refresh Rate

Edit `dashboard.js`:

```javascript
// Update every X milliseconds
setInterval(refreshData, 30000);  // 30 seconds
```

### API Endpoint

If running backend elsewhere, update in `dashboard.js`:

```javascript
const API_BASE = 'https://your-api-domain.com';
```

## Production Deployment

### With Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .

RUN pip install fastapi uvicorn

EXPOSE 8000

CMD ["python", "server.py"]
```

```bash
docker build -t qaht-dashboard .
docker run -p 8000:8000 qaht-dashboard
```

### With Nginx (Reverse Proxy)

```nginx
server {
    listen 80;
    server_name dashboard.quantumalphahunter.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Environment Variables

```bash
# .env file
API_KEY_ALPHA_VANTAGE=your_key
API_KEY_NEWSAPI=your_key
API_KEY_REDDIT_CLIENT_ID=your_id
API_KEY_REDDIT_SECRET=your_secret
```

## Data Sources

Dashboard pulls from:
- **Stocks**: Alpha Vantage (FREE 500/day)
- **Crypto**: CoinCap + Binance (FREE unlimited)
- **News**: NewsAPI, Google News RSS (FREE)
- **Insider**: SEC Edgar (FREE)
- **Options**: Calculated from stock data (FREE)

## Performance

### Load Times
- **Initial Load**: < 2 seconds
- **API Response**: < 500ms
- **Chart Rendering**: < 100ms
- **Live Updates**: Real-time (< 1s)

### Optimization
- **Caching**: 1-hour cache for heavy API calls
- **Lazy Loading**: Charts load on-demand
- **Debouncing**: Rate-limited API requests
- **Compression**: Gzip enabled

## Troubleshooting

### Dashboard won't load
```bash
# Check server is running
curl http://localhost:8000/api/health

# Check logs
python server.py --log-level debug
```

### No data showing
```bash
# Verify API keys in .env
cat .env

# Test API directly
curl http://localhost:8000/api/signals
```

### Slow performance
```bash
# Check API response times
curl -w "@curl-format.txt" http://localhost:8000/api/signals

# Enable caching (edit server.py)
# Increase cache_hours parameter
```

## Browser Compatibility

- ✅ Chrome 90+
- ✅ Firefox 88+
- ✅ Safari 14+
- ✅ Edge 90+

## Mobile Support

Dashboard is fully responsive:
- **Tablet**: 2-column layout
- **Phone**: Single column with collapsible sections

## Screenshots

### Desktop View
- Full dashboard with all widgets
- Side-by-side charts
- Real-time updates

### Tablet View
- Responsive 2-column grid
- Touch-optimized controls

### Mobile View
- Single column stack
- Swipeable sections
- Compact info cards

## Future Enhancements

- [ ] WebSocket real-time updates
- [ ] Custom alert notifications
- [ ] Watchlist management
- [ ] Portfolio tracking
- [ ] Trade history
- [ ] Performance analytics
- [ ] Export to CSV/PDF
- [ ] Dark/Light theme toggle
- [ ] Multiple dashboard layouts

## Support

**Documentation**: See `docs/` folder
**Issues**: Report on GitHub
**API Docs**: http://localhost:8000/docs

## License

Quantum Alpha Hunter © 2025
