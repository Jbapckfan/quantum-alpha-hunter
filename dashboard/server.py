"""
FastAPI Backend for Quantum Alpha Hunter Dashboard

Serves the dashboard and provides real-time data APIs

PRODUCTION-GRADE with:
- Performance monitoring (track all API response times)
- Comprehensive error handling
- Real-time metrics endpoint
"""

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Optional
from datetime import datetime
import uvicorn
import sys
from pathlib import Path

# Add parent directory to path to import qaht modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import production optimizations
try:
    from qaht.core.production_optimizations import PerformanceMonitor
    performance_monitor = PerformanceMonitor()
except ImportError:
    # Fallback if not available
    performance_monitor = None

# Create FastAPI app
app = FastAPI(
    title="Quantum Alpha Hunter API",
    description="Real-time market intelligence API",
    version="1.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Root endpoint - serve dashboard
@app.get("/")
async def read_root():
    """Serve the dashboard HTML"""
    return FileResponse('index.html')


# Health check
@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    if performance_monitor:
        with performance_monitor.time_operation('health_check'):
            performance_monitor.increment('health_checks')
            return {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "version": "1.0.0"
            }
    else:
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": "1.0.0"
        }


# Get dashboard stats
@app.get("/api/stats")
async def get_stats():
    """Get dashboard statistics"""
    if performance_monitor:
        with performance_monitor.time_operation('get_stats'):
            performance_monitor.increment('stats_requests')
            # In production, fetch from database/cache
            return {
                "active_signals": 23,
                "high_conviction": 7,
                "compressed": 12,
                "insider_buying": 9,
                "last_updated": datetime.now().isoformat()
            }
    else:
        return {
            "active_signals": 23,
            "high_conviction": 7,
            "compressed": 12,
            "insider_buying": 9,
            "last_updated": datetime.now().isoformat()
        }


# Get top signals
@app.get("/api/signals")
async def get_signals(
    limit: int = 20,
    min_score: int = 70,
    asset_type: Optional[str] = None
):
    """
    Get top trading signals

    Args:
        limit: Maximum number of signals to return
        min_score: Minimum score threshold
        asset_type: Filter by 'STOCK' or 'CRYPTO'
    """
    # In production, query from database
    signals = [
        {
            "ticker": "OPEN",
            "score": 92,
            "change_24h": 12.4,
            "price": 2.51,
            "market_cap": 1600000000,
            "type": "STOCK",
            "signals": ["COMPRESSION", "INSIDER_BUY", "OPTIONS_SWEEP"],
            "timestamp": datetime.now().isoformat()
        },
        # More signals...
    ]

    # Filter by type if specified
    if asset_type:
        signals = [s for s in signals if s['type'] == asset_type.upper()]

    # Filter by min score
    signals = [s for s in signals if s['score'] >= min_score]

    return {
        "count": len(signals),
        "signals": signals[:limit]
    }


# Get news
@app.get("/api/news")
async def get_news(ticker: Optional[str] = None, limit: int = 20):
    """
    Get recent news articles

    Args:
        ticker: Filter by ticker symbol
        limit: Maximum number of articles
    """
    # In production, fetch from news collector
    news = [
        {
            "title": "OPEN announces new expansion plans",
            "ticker": "OPEN",
            "source": "Reuters",
            "url": "https://example.com/news/1",
            "published": datetime.now().isoformat(),
            "sentiment": "positive"
        },
        # More news...
    ]

    if ticker:
        news = [n for n in news if n['ticker'] == ticker.upper()]

    return {
        "count": len(news),
        "news": news[:limit]
    }


# Get insider trades
@app.get("/api/insider-trades")
async def get_insider_trades(
    ticker: Optional[str] = None,
    days: int = 7,
    limit: int = 20
):
    """
    Get recent insider trading activity

    Args:
        ticker: Filter by ticker symbol
        days: Days to look back
        limit: Maximum number of trades
    """
    # In production, fetch from insider trading detector
    trades = [
        {
            "ticker": "OPEN",
            "insider_name": "CEO John Smith",
            "insider_title": "Chief Executive Officer",
            "transaction_type": "BUY",
            "shares": 100000,
            "price_per_share": 2.50,
            "total_value": 250000,
            "transaction_date": datetime.now().isoformat()
        },
        # More trades...
    ]

    if ticker:
        trades = [t for t in trades if t['ticker'] == ticker.upper()]

    return {
        "count": len(trades),
        "trades": trades[:limit]
    }


# Get options flow
@app.get("/api/options-flow")
async def get_options_flow(
    ticker: Optional[str] = None,
    min_premium: float = 100000,
    limit: int = 20
):
    """
    Get unusual options activity

    Args:
        ticker: Filter by ticker symbol
        min_premium: Minimum premium threshold
        limit: Maximum number of flows
    """
    # In production, fetch from options flow detector
    flows = [
        {
            "ticker": "PLTR",
            "option_type": "CALL",
            "strike": 30.0,
            "expiry": "2025-12-20",
            "premium": 425000,
            "volume": 5000,
            "sentiment": "bullish",
            "timestamp": datetime.now().isoformat()
        },
        # More flows...
    ]

    if ticker:
        flows = [f for f in flows if f['ticker'] == ticker.upper()]

    flows = [f for f in flows if f['premium'] >= min_premium]

    return {
        "count": len(flows),
        "flows": flows[:limit]
    }


# Get crypto data
@app.get("/api/crypto")
async def get_crypto_data(
    limit: int = 100,
    min_market_cap: float = 10000000
):
    """
    Get cryptocurrency data

    Args:
        limit: Maximum number of coins
        min_market_cap: Minimum market cap filter
    """
    # In production, fetch from crypto API
    try:
        if performance_monitor:
            with performance_monitor.time_operation('fetch_crypto'):
                performance_monitor.increment('crypto_requests')
                from qaht.data_sources.free_crypto_api import FreeCryptoAPI

                api = FreeCryptoAPI()
                coins = api.fetch_all_coins()

                # Filter by market cap
                coins = [c for c in coins if c.get('market_cap', 0) >= min_market_cap]

                # Sort by market cap
                coins.sort(key=lambda x: x.get('market_cap', 0), reverse=True)

                return {
                    "count": len(coins),
                    "coins": coins[:limit]
                }
        else:
            from qaht.data_sources.free_crypto_api import FreeCryptoAPI

            api = FreeCryptoAPI()
            coins = api.fetch_all_coins()

            # Filter by market cap
            coins = [c for c in coins if c.get('market_cap', 0) >= min_market_cap]

            # Sort by market cap
            coins.sort(key=lambda x: x.get('market_cap', 0), reverse=True)

            return {
                "count": len(coins),
                "coins": coins[:limit]
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch crypto data: {str(e)}")


# Performance metrics endpoint
@app.get("/api/metrics")
async def get_performance_metrics():
    """
    Get real-time performance metrics

    Returns:
        Performance statistics including:
        - API response times (mean, P95, min, max)
        - Request counts
        - Cache hit rates
        - Uptime
    """
    if performance_monitor:
        stats = performance_monitor.get_stats()
        return {
            "status": "success",
            "metrics": stats
        }
    else:
        return {
            "status": "unavailable",
            "message": "Performance monitoring not enabled"
        }


# Serve static files (JS, CSS)
app.mount("/static", StaticFiles(directory="."), name="static")


if __name__ == "__main__":
    print("="*80)
    print("🚀 Quantum Alpha Hunter Dashboard")
    print("="*80)
    print()
    print("Starting server...")
    print("Dashboard: http://localhost:8000")
    print("API Docs: http://localhost:8000/docs")
    print()
    print("Press CTRL+C to stop")
    print("="*80)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
