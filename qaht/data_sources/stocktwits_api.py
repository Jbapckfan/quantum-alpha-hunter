"""
StockTwits API Integration (FREE - 200 calls/hour)

Track trader sentiment via cashtags ($AAPL, $BTC)

Features:
- Real-time sentiment (bullish/bearish)
- Message volume tracking
- Trending tickers
- Watchlist counts

NO API KEY REQUIRED for basic access!
"""

import logging
import requests
import time
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class StockTwitsAPI:
    """
    StockTwits API client (FREE - 200 calls/hour, no API key required)

    API Docs: https://api.stocktwits.com/developers/docs
    """

    def __init__(self):
        self.base_url = "https://api.stocktwits.com/api/2"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'QuantumAlphaHunter/1.0'
        })

    def get_stream(self, symbol: str, limit: int = 30) -> Dict:
        """
        Get message stream for a symbol

        Args:
            symbol: Ticker symbol (e.g., 'AAPL', 'BTC.X')
            limit: Number of messages (max 30)

        Returns:
            Dict with messages and sentiment data
        """
        try:
            url = f"{self.base_url}/streams/symbol/{symbol}.json"
            params = {'limit': min(limit, 30)}

            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            # Parse messages
            messages = data.get('messages', [])

            # Calculate sentiment
            bullish = sum(1 for m in messages if m.get('entities', {}).get('sentiment', {}).get('basic') == 'Bullish')
            bearish = sum(1 for m in messages if m.get('entities', {}).get('sentiment', {}).get('basic') == 'Bearish')
            total = bullish + bearish

            sentiment_ratio = (bullish / total) if total > 0 else 0.5

            return {
                'symbol': symbol,
                'message_count': len(messages),
                'bullish_count': bullish,
                'bearish_count': bearish,
                'sentiment_ratio': sentiment_ratio,  # 0-1 (0=bearish, 1=bullish)
                'sentiment_label': 'BULLISH' if sentiment_ratio > 0.6 else 'BEARISH' if sentiment_ratio < 0.4 else 'NEUTRAL',
                'messages': messages,
                'timestamp': datetime.now().isoformat()
            }

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"Symbol not found on StockTwits: {symbol}")
                return self._empty_result(symbol)
            logger.error(f"StockTwits API error for {symbol}: {e}")
            return self._empty_result(symbol)
        except Exception as e:
            logger.error(f"Failed to fetch StockTwits stream for {symbol}: {e}")
            return self._empty_result(symbol)

    def get_trending(self, limit: int = 30) -> List[Dict]:
        """
        Get trending symbols

        Args:
            limit: Number of trending symbols (max 30)

        Returns:
            List of trending symbols with data
        """
        try:
            url = f"{self.base_url}/trending/symbols.json"
            params = {'limit': min(limit, 30)}

            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            symbols = data.get('symbols', [])

            trending = []
            for symbol_data in symbols:
                trending.append({
                    'symbol': symbol_data.get('symbol'),
                    'title': symbol_data.get('title'),
                    'watchlist_count': symbol_data.get('watchlist_count', 0),
                    'type': 'STOCK' if symbol_data.get('symbol') and '.' not in symbol_data.get('symbol', '') else 'CRYPTO'
                })

            logger.info(f"Found {len(trending)} trending symbols on StockTwits")
            return trending

        except Exception as e:
            logger.error(f"Failed to fetch trending symbols: {e}")
            return []

    def get_watchlist_count(self, symbol: str) -> int:
        """
        Get number of users watching a symbol

        Args:
            symbol: Ticker symbol

        Returns:
            Watchlist count
        """
        try:
            url = f"{self.base_url}/symbols/{symbol}.json"

            response = self.session.get(url, timeout=10)
            response.raise_for_status()

            data = response.json()
            symbol_data = data.get('symbol', {})

            return symbol_data.get('watchlist_count', 0)

        except Exception as e:
            logger.debug(f"Failed to get watchlist count for {symbol}: {e}")
            return 0

    def batch_sentiment(self, symbols: List[str], delay: float = 0.5) -> Dict[str, Dict]:
        """
        Get sentiment for multiple symbols (respects rate limits)

        Args:
            symbols: List of ticker symbols
            delay: Delay between requests in seconds (default: 0.5s = 120/hour)

        Returns:
            Dict mapping symbol -> sentiment data
        """
        results = {}

        for i, symbol in enumerate(symbols):
            logger.info(f"Fetching StockTwits data for {symbol} ({i+1}/{len(symbols)})")

            results[symbol] = self.get_stream(symbol)

            # Rate limit: 200 calls/hour = 1 call per 18 seconds
            # We use 0.5s delay for safety (allows burst, then backs off)
            if i < len(symbols) - 1:
                time.sleep(delay)

        logger.info(f"Fetched StockTwits sentiment for {len(results)} symbols")
        return results

    def _empty_result(self, symbol: str) -> Dict:
        """Return empty result structure"""
        return {
            'symbol': symbol,
            'message_count': 0,
            'bullish_count': 0,
            'bearish_count': 0,
            'sentiment_ratio': 0.5,
            'sentiment_label': 'UNKNOWN',
            'messages': [],
            'timestamp': datetime.now().isoformat()
        }


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    print("="*80)
    print("📱 StockTwits API Test")
    print("="*80)
    print()

    api = StockTwitsAPI()

    # Test: Get trending symbols
    print("🔥 Trending Symbols:")
    print("-"*80)
    trending = api.get_trending(limit=10)
    for i, item in enumerate(trending, 1):
        print(f"{i:2d}. ${item['symbol']:6s} - {item['watchlist_count']:>6d} watchers - {item['type']}")

    print()
    print("="*80)
    print()

    # Test: Get sentiment for specific symbols
    print("💬 Sentiment Analysis:")
    print("-"*80)

    test_symbols = ['AAPL', 'TSLA', 'NVDA', 'BTC.X', 'ETH.X']
    sentiments = api.batch_sentiment(test_symbols, delay=1.0)

    for symbol, data in sentiments.items():
        if data['message_count'] > 0:
            print(f"${symbol:6s} - {data['sentiment_label']:8s} "
                  f"({data['bullish_count']} bull, {data['bearish_count']} bear) "
                  f"- {data['message_count']} messages")
        else:
            print(f"${symbol:6s} - No data")

    print()
    print("="*80)