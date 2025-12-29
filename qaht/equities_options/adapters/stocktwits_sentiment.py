"""
StockTwits sentiment analysis.

FREE API - real-time retail sentiment.
Complements Reddit data we already have.
"""

import logging
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class StockTwitsSentimentAnalyzer:
    """
    Fetch and analyze StockTwits sentiment.

    StockTwits API is FREE and provides:
    - Message volume
    - Bullish/bearish sentiment percentages
    - Trending status
    - Watch count

    Combined with Reddit, gives complete retail sentiment picture.
    """

    BASE_URL = "https://api.stocktwits.com/api/2"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Quantum Alpha Hunter/1.0'
        })

    def get_sentiment_score(self, symbol: str) -> Dict:
        """
        Get StockTwits sentiment score.

        Args:
            symbol: Stock ticker

        Returns:
            Dict with:
                - stocktwits_score: 0-100 (100 = very bullish)
                - bullish_pct: % of bullish messages
                - bearish_pct: % of bearish messages
                - message_volume: Number of recent messages
                - is_trending: True if trending on StockTwits
                - watchers: Number of watchers
        """
        try:
            # Fetch streams (recent messages)
            stream_data = self._fetch_stream(symbol)

            if not stream_data:
                return self._empty_sentiment()

            # Analyze sentiment
            return self._analyze_sentiment(stream_data, symbol)

        except Exception as e:
            logger.error(f"Error fetching StockTwits for {symbol}: {e}")
            return self._empty_sentiment()

    def _fetch_stream(self, symbol: str) -> Optional[Dict]:
        """Fetch StockTwits stream for symbol."""
        try:
            url = f"{self.BASE_URL}/streams/symbol/{symbol}.json"

            response = self.session.get(url, timeout=10)

            if response.status_code == 404:
                logger.debug(f"No StockTwits data for {symbol}")
                return None

            response.raise_for_status()
            data = response.json()

            return data

        except Exception as e:
            logger.debug(f"Could not fetch StockTwits stream for {symbol}: {e}")
            return None

    def _analyze_sentiment(self, data: Dict, symbol: str) -> Dict:
        """Analyze StockTwits sentiment from API response."""
        try:
            # Extract messages
            messages = data.get('messages', [])
            symbol_data = data.get('symbol', {})

            if not messages:
                return self._empty_sentiment()

            # Count sentiment
            bullish_count = 0
            bearish_count = 0
            total_count = 0

            for msg in messages:
                entities = msg.get('entities', {})
                sentiment = entities.get('sentiment', {})

                if sentiment:
                    basic = sentiment.get('basic')
                    if basic == 'Bullish':
                        bullish_count += 1
                        total_count += 1
                    elif basic == 'Bearish':
                        bearish_count += 1
                        total_count += 1

            # Get watchers and trending status
            watchers = symbol_data.get('watchlist_count', 0)
            is_trending = symbol_data.get('is_trending', False)

            # Calculate percentages
            if total_count > 0:
                bullish_pct = (bullish_count / total_count) * 100
                bearish_pct = (bearish_count / total_count) * 100
            else:
                bullish_pct = 50
                bearish_pct = 50

            # Compute score (0-100)
            # Base: bullish % = score
            score = bullish_pct

            # Bonus for trending
            if is_trending:
                score = min(100, score + 15)

            # Bonus for high message volume
            if len(messages) >= 30:
                score = min(100, score + 10)
            elif len(messages) >= 20:
                score = min(100, score + 5)

            # Bonus for watchers
            if watchers >= 10000:
                score = min(100, score + 5)

            logger.info(f"{symbol} StockTwits: {score:.0f}/100 ({bullish_pct:.0f}% bull, {bearish_pct:.0f}% bear, {len(messages)} msgs, trending={is_trending})")

            return {
                'stocktwits_score': round(score, 1),
                'bullish_pct': round(bullish_pct, 1),
                'bearish_pct': round(bearish_pct, 1),
                'message_volume': len(messages),
                'is_trending': is_trending,
                'watchers': watchers
            }

        except Exception as e:
            logger.error(f"Error analyzing StockTwits data: {e}")
            return self._empty_sentiment()

    def _empty_sentiment(self) -> Dict:
        """Return empty sentiment when no data."""
        return {
            'stocktwits_score': 50,  # Neutral
            'bullish_pct': 50,
            'bearish_pct': 50,
            'message_volume': 0,
            'is_trending': False,
            'watchers': 0
        }


def get_stocktwits_sentiment(symbol: str) -> Dict:
    """
    Get StockTwits sentiment score for a symbol.

    Returns dict with stocktwits_score (0-100) and details.
    """
    analyzer = StockTwitsSentimentAnalyzer()
    return analyzer.get_sentiment_score(symbol)
