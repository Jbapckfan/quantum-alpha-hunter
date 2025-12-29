"""
News sentiment analysis from multiple free sources.

FREE sources:
1. NewsAPI (100 requests/day free)
2. Yahoo Finance news (via yfinance)
3. Sentiment analysis using basic NLP

Positive headlines = bullish, negative = bearish.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import re

import requests

logger = logging.getLogger(__name__)


class NewsSentimentAnalyzer:
    """
    Analyze news sentiment for stocks.

    Uses:
    1. NewsAPI for recent headlines (free tier: 100 requests/day)
    2. Yahoo Finance news via yfinance
    3. Basic sentiment analysis (positive/negative keywords)
    """

    # Sentiment keyword lists
    POSITIVE_KEYWORDS = {
        'strong', 'beat', 'beats', 'surge', 'soar', 'rally', 'jump', 'climbs',
        'upgrade', 'upgraded', 'bullish', 'buy', 'buying', 'growth', 'record',
        'breakthrough', 'profit', 'profits', 'revenue', 'earnings', 'outperform',
        'exceed', 'exceeds', 'positive', 'gains', 'winner', 'success', 'innovation',
        'expand', 'expansion', 'partnership', 'deal', 'acquisition', 'launch'
    }

    NEGATIVE_KEYWORDS = {
        'weak', 'miss', 'misses', 'plunge', 'drop', 'fall', 'decline', 'crash',
        'downgrade', 'downgraded', 'bearish', 'sell', 'selling', 'loss', 'losses',
        'lawsuit', 'investigation', 'fraud', 'scandal', 'warning', 'concern',
        'risk', 'risks', 'threat', 'bankruptcy', 'debt', 'struggle', 'fail',
        'failure', 'layoff', 'layoffs', 'cut', 'cuts', 'negative'
    }

    NEWSAPI_URL = "https://newsapi.org/v2/everything"

    def __init__(self, newsapi_key: Optional[str] = None):
        """
        Initialize news sentiment analyzer.

        Args:
            newsapi_key: NewsAPI key (optional, get free at newsapi.org)
        """
        self.newsapi_key = newsapi_key
        self.session = requests.Session()

    def get_sentiment_score(
        self,
        symbol: str,
        ticker_obj=None,
        days_back: int = 7
    ) -> Dict:
        """
        Get news sentiment score for a symbol.

        Args:
            symbol: Stock ticker
            ticker_obj: yfinance Ticker object (optional)
            days_back: Days of news to analyze

        Returns:
            Dict with:
                - sentiment_score: 0-100 (100 = very bullish)
                - positive_count: Number of positive headlines
                - negative_count: Number of negative headlines
                - neutral_count: Number of neutral headlines
                - sentiment: 'bullish', 'bearish', 'neutral'
                - headlines: List of recent headlines
        """
        try:
            headlines = []

            # 1. Try Yahoo Finance news (always available)
            yahoo_headlines = self._fetch_yahoo_news(symbol, ticker_obj)
            headlines.extend(yahoo_headlines)

            # 2. Try NewsAPI if key provided
            if self.newsapi_key:
                newsapi_headlines = self._fetch_newsapi(symbol, days_back)
                headlines.extend(newsapi_headlines)

            if not headlines:
                logger.debug(f"No news found for {symbol}")
                return self._empty_sentiment()

            # Analyze sentiment
            return self._analyze_sentiment(headlines, symbol)

        except Exception as e:
            logger.error(f"Error analyzing news sentiment for {symbol}: {e}")
            return self._empty_sentiment()

    def _fetch_yahoo_news(self, symbol: str, ticker_obj=None) -> List[str]:
        """Fetch news headlines from Yahoo Finance."""
        try:
            try:
                import yfinance as yf
            except ImportError:
                return []

            if ticker_obj is None:
                ticker_obj = yf.Ticker(symbol)

            news = ticker_obj.news

            if not news:
                return []

            # Extract titles
            headlines = []
            for item in news[:10]:  # Top 10 news items
                title = item.get('title', '')
                if title:
                    headlines.append(title)

            logger.debug(f"Fetched {len(headlines)} Yahoo Finance headlines for {symbol}")
            return headlines

        except Exception as e:
            logger.debug(f"Could not fetch Yahoo news for {symbol}: {e}")
            return []

    def _fetch_newsapi(self, symbol: str, days_back: int) -> List[str]:
        """Fetch headlines from NewsAPI."""
        try:
            if not self.newsapi_key:
                return []

            from_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')

            params = {
                'q': symbol,
                'from': from_date,
                'sortBy': 'publishedAt',
                'language': 'en',
                'apiKey': self.newsapi_key
            }

            response = self.session.get(self.NEWSAPI_URL, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            if data.get('status') != 'ok':
                return []

            articles = data.get('articles', [])

            headlines = []
            for article in articles[:20]:  # Top 20
                title = article.get('title', '')
                description = article.get('description', '')
                combined = f"{title} {description}".strip()
                if combined:
                    headlines.append(combined)

            logger.debug(f"Fetched {len(headlines)} NewsAPI headlines for {symbol}")
            return headlines

        except Exception as e:
            logger.debug(f"Could not fetch NewsAPI for {symbol}: {e}")
            return []

    def _analyze_sentiment(self, headlines: List[str], symbol: str) -> Dict:
        """Analyze sentiment of headlines."""
        positive_count = 0
        negative_count = 0
        neutral_count = 0

        for headline in headlines:
            headline_lower = headline.lower()

            # Count positive/negative keywords
            pos_matches = sum(1 for kw in self.POSITIVE_KEYWORDS if kw in headline_lower)
            neg_matches = sum(1 for kw in self.NEGATIVE_KEYWORDS if kw in headline_lower)

            if pos_matches > neg_matches:
                positive_count += 1
            elif neg_matches > pos_matches:
                negative_count += 1
            else:
                neutral_count += 1

        total = len(headlines)
        if total == 0:
            return self._empty_sentiment()

        # Compute sentiment score (0-100)
        # 50 = neutral, >50 = bullish, <50 = bearish
        sentiment_ratio = (positive_count - negative_count) / total
        score = 50 + (sentiment_ratio * 50)  # Scale to 0-100
        score = max(0, min(100, score))

        # Determine sentiment label
        if score >= 60:
            sentiment = 'bullish'
        elif score <= 40:
            sentiment = 'bearish'
        else:
            sentiment = 'neutral'

        logger.info(f"{symbol} news sentiment: {score:.0f}/100 ({positive_count}+ {negative_count}- {neutral_count}=, {sentiment})")

        return {
            'sentiment_score': round(score, 1),
            'positive_count': positive_count,
            'negative_count': negative_count,
            'neutral_count': neutral_count,
            'sentiment': sentiment,
            'headlines': headlines[:5]  # Top 5 for reference
        }

    def _empty_sentiment(self) -> Dict:
        """Return empty sentiment when no data."""
        return {
            'sentiment_score': 50,  # Neutral
            'positive_count': 0,
            'negative_count': 0,
            'neutral_count': 0,
            'sentiment': 'neutral',
            'headlines': []
        }


def get_news_sentiment(symbol: str, newsapi_key: Optional[str] = None, days_back: int = 7) -> Dict:
    """
    Get news sentiment score for a symbol.

    Args:
        symbol: Stock ticker
        newsapi_key: NewsAPI key (optional, get free at newsapi.org)
        days_back: Days of news to analyze

    Returns:
        Dict with sentiment_score (0-100) and details.
    """
    analyzer = NewsSentimentAnalyzer(newsapi_key=newsapi_key)
    return analyzer.get_sentiment_score(symbol, days_back=days_back)
