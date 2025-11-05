"""
ROBUST News Collection System

Collects from multiple FREE sources:
1. NewsAPI (100 calls/day FREE)
2. Google News RSS (unlimited FREE)
3. Finnhub (60 calls/min FREE)
4. Yahoo Finance RSS (unlimited FREE)

Features:
- Retry logic with exponential backoff
- Caching to avoid duplicate API calls
- Data validation and cleaning
- Fallback sources if primary fails
- Sentiment analysis
"""

import logging
import requests
import feedparser
import time
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import json
import hashlib
from pathlib import Path
import re

logger = logging.getLogger(__name__)


@dataclass
class NewsArticle:
    """Represents a news article."""
    title: str
    source: str
    url: str
    published: datetime
    summary: str
    ticker: Optional[str]
    sentiment: str  # 'POSITIVE', 'NEGATIVE', 'NEUTRAL'
    relevance: float  # 0-1
    category: str  # 'earnings', 'merger', 'product', 'general', etc.


class RobustNewsCollector:
    """
    Bulletproof news collector with retry logic, caching, and validation.
    """

    def __init__(
        self,
        newsapi_key: Optional[str] = None,
        finnhub_key: Optional[str] = None,
        cache_dir: str = "data/cache/news",
        cache_hours: int = 1
    ):
        """
        Args:
            newsapi_key: NewsAPI key (optional, 100/day free)
            finnhub_key: Finnhub key (optional, 60/min free)
            cache_dir: Directory for caching
            cache_hours: Hours to cache results
        """
        self.newsapi_key = newsapi_key
        self.finnhub_key = finnhub_key
        self.cache_dir = Path(cache_dir)
        self.cache_hours = cache_hours
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _retry_with_backoff(self, func, max_retries: int = 3, initial_delay: float = 1.0):
        """
        Retry function with exponential backoff.

        Args:
            func: Function to retry
            max_retries: Maximum retry attempts
            initial_delay: Initial delay in seconds

        Returns:
            Function result or None if all retries fail
        """
        for attempt in range(max_retries):
            try:
                return func()
            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:
                    logger.error(f"All {max_retries} retries failed: {e}")
                    return None

                delay = initial_delay * (2 ** attempt)
                logger.warning(f"Attempt {attempt + 1} failed, retrying in {delay}s: {e}")
                time.sleep(delay)

        return None

    def _get_cache_key(self, source: str, query: str) -> str:
        """Generate cache key."""
        combined = f"{source}:{query}"
        return hashlib.md5(combined.encode()).hexdigest()

    def _load_from_cache(self, cache_key: str) -> Optional[List[Dict]]:
        """Load data from cache if not expired."""
        cache_file = self.cache_dir / f"{cache_key}.json"

        if not cache_file.exists():
            return None

        try:
            with open(cache_file, 'r') as f:
                cached = json.load(f)

            # Check expiry
            cached_time = datetime.fromisoformat(cached['timestamp'])
            if datetime.now() - cached_time > timedelta(hours=self.cache_hours):
                logger.debug(f"Cache expired: {cache_key}")
                return None

            logger.info(f"Loaded from cache: {cache_key} ({len(cached['data'])} articles)")
            return cached['data']

        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
            return None

    def _save_to_cache(self, cache_key: str, data: List[Dict]):
        """Save data to cache."""
        cache_file = self.cache_dir / f"{cache_key}.json"

        try:
            cached = {
                'timestamp': datetime.now().isoformat(),
                'data': data
            }

            with open(cache_file, 'w') as f:
                json.dump(cached, f)

            logger.debug(f"Saved to cache: {cache_key}")

        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    def _validate_article(self, article: Dict) -> bool:
        """Validate article data."""
        required_fields = ['title', 'url']

        for field in required_fields:
            if field not in article or not article[field]:
                return False

        # Validate URL format
        url = article['url']
        if not url.startswith('http'):
            return False

        return True

    def _clean_html(self, text: str) -> str:
        """Remove HTML tags and clean text."""
        if not text:
            return ""

        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)

        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        return text

    def _extract_ticker_from_text(self, text: str) -> Optional[str]:
        """
        Extract ticker symbol from text.

        Looks for patterns like:
        - $AAPL
        - (NASDAQ:AAPL)
        - ticker: AAPL
        """
        if not text:
            return None

        # Pattern 1: $TICKER
        match = re.search(r'\$([A-Z]{1,5})\b', text)
        if match:
            return match.group(1)

        # Pattern 2: (EXCHANGE:TICKER)
        match = re.search(r'\((?:NASDAQ|NYSE|NYSEAMERICAN):\s*([A-Z]{1,5})\)', text, re.IGNORECASE)
        if match:
            return match.group(1)

        # Pattern 3: ticker: TICKER
        match = re.search(r'ticker:\s*([A-Z]{1,5})\b', text, re.IGNORECASE)
        if match:
            return match.group(1)

        return None

    def fetch_from_newsapi(self, query: str, language: str = 'en') -> List[Dict]:
        """
        Fetch from NewsAPI (100 calls/day FREE).

        Args:
            query: Search query
            language: Language code

        Returns:
            List of articles
        """
        if not self.newsapi_key:
            logger.warning("NewsAPI key not provided, skipping")
            return []

        # Check cache first
        cache_key = self._get_cache_key('newsapi', query)
        cached = self._load_from_cache(cache_key)
        if cached:
            return cached

        logger.info(f"Fetching from NewsAPI: {query}")

        def _fetch():
            url = "https://newsapi.org/v2/everything"
            params = {
                'q': query,
                'language': language,
                'sortBy': 'publishedAt',
                'apiKey': self.newsapi_key,
                'pageSize': 100
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()

        data = self._retry_with_backoff(_fetch)

        if not data or data.get('status') != 'ok':
            logger.error(f"NewsAPI error: {data}")
            return []

        # Transform to standard format
        articles = []
        for article in data.get('articles', []):
            if not self._validate_article(article):
                continue

            try:
                published = datetime.fromisoformat(article['publishedAt'].replace('Z', '+00:00'))
            except (ValueError, TypeError, KeyError, AttributeError) as e:
                logger.debug(f"Failed to parse date from NewsAPI: {e}")
                published = datetime.now()

            articles.append({
                'title': self._clean_html(article['title']),
                'source': article.get('source', {}).get('name', 'Unknown'),
                'url': article['url'],
                'published': published.isoformat(),
                'summary': self._clean_html(article.get('description', '')),
                'content': self._clean_html(article.get('content', '')),
                'ticker': self._extract_ticker_from_text(article['title'] + ' ' + article.get('description', '')),
                'image': article.get('urlToImage', '')
            })

        # Cache results
        self._save_to_cache(cache_key, articles)

        logger.info(f"Fetched {len(articles)} articles from NewsAPI")
        return articles

    def fetch_from_google_news_rss(self, query: str) -> List[Dict]:
        """
        Fetch from Google News RSS (unlimited FREE).

        Args:
            query: Search query

        Returns:
            List of articles
        """
        # Check cache first
        cache_key = self._get_cache_key('google_news', query)
        cached = self._load_from_cache(cache_key)
        if cached:
            return cached

        logger.info(f"Fetching from Google News RSS: {query}")

        def _fetch():
            url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.text

        content = self._retry_with_backoff(_fetch)

        if not content:
            return []

        # Parse RSS feed
        feed = feedparser.parse(content)

        articles = []
        for entry in feed.entries:
            try:
                published = datetime(*entry.published_parsed[:6])
            except (ValueError, TypeError, AttributeError) as e:
                logger.debug(f"Failed to parse date from Google News RSS: {e}")
                published = datetime.now()

            articles.append({
                'title': self._clean_html(entry.title),
                'source': entry.get('source', {}).get('title', 'Google News'),
                'url': entry.link,
                'published': published.isoformat(),
                'summary': self._clean_html(entry.get('summary', '')),
                'ticker': self._extract_ticker_from_text(entry.title)
            })

        # Cache results
        self._save_to_cache(cache_key, articles)

        logger.info(f"Fetched {len(articles)} articles from Google News")
        return articles

    def fetch_from_finnhub(self, ticker: str) -> List[Dict]:
        """
        Fetch company news from Finnhub (60 calls/min FREE).

        Args:
            ticker: Stock ticker

        Returns:
            List of articles
        """
        if not self.finnhub_key:
            logger.warning("Finnhub key not provided, skipping")
            return []

        # Check cache first
        cache_key = self._get_cache_key('finnhub', ticker)
        cached = self._load_from_cache(cache_key)
        if cached:
            return cached

        logger.info(f"Fetching from Finnhub: {ticker}")

        def _fetch():
            # Get news from last 7 days
            from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            to_date = datetime.now().strftime('%Y-%m-%d')

            url = f"https://finnhub.io/api/v1/company-news"
            params = {
                'symbol': ticker,
                'from': from_date,
                'to': to_date,
                'token': self.finnhub_key
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()

        data = self._retry_with_backoff(_fetch)

        if not data:
            return []

        # Transform to standard format
        articles = []
        for article in data:
            try:
                published = datetime.fromtimestamp(article['datetime'])
            except (ValueError, TypeError, KeyError, OSError) as e:
                logger.debug(f"Failed to parse date from Finnhub: {e}")
                published = datetime.now()

            articles.append({
                'title': self._clean_html(article['headline']),
                'source': article.get('source', 'Finnhub'),
                'url': article['url'],
                'published': published.isoformat(),
                'summary': self._clean_html(article.get('summary', '')),
                'ticker': ticker,
                'category': article.get('category', 'general')
            })

        # Cache results
        self._save_to_cache(cache_key, articles)

        logger.info(f"Fetched {len(articles)} articles from Finnhub")
        return articles

    def fetch_from_yahoo_finance_rss(self, ticker: str) -> List[Dict]:
        """
        Fetch from Yahoo Finance RSS (unlimited FREE).

        Args:
            ticker: Stock ticker

        Returns:
            List of articles
        """
        # Check cache first
        cache_key = self._get_cache_key('yahoo_finance', ticker)
        cached = self._load_from_cache(cache_key)
        if cached:
            return cached

        logger.info(f"Fetching from Yahoo Finance RSS: {ticker}")

        def _fetch():
            url = f"https://finance.yahoo.com/rss/headline?s={ticker}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.text

        content = self._retry_with_backoff(_fetch)

        if not content:
            return []

        # Parse RSS feed
        feed = feedparser.parse(content)

        articles = []
        for entry in feed.entries:
            try:
                published = datetime(*entry.published_parsed[:6])
            except (ValueError, TypeError, AttributeError) as e:
                logger.debug(f"Failed to parse date from Yahoo Finance RSS: {e}")
                published = datetime.now()

            articles.append({
                'title': self._clean_html(entry.title),
                'source': 'Yahoo Finance',
                'url': entry.link,
                'published': published.isoformat(),
                'summary': self._clean_html(entry.get('summary', '')),
                'ticker': ticker
            })

        # Cache results
        self._save_to_cache(cache_key, articles)

        logger.info(f"Fetched {len(articles)} articles from Yahoo Finance")
        return articles

    def collect_all_news(
        self,
        ticker: Optional[str] = None,
        query: Optional[str] = None,
        use_newsapi: bool = True,
        use_google: bool = True,
        use_finnhub: bool = True,
        use_yahoo: bool = True
    ) -> List[Dict]:
        """
        Collect news from all available sources.

        Args:
            ticker: Stock ticker (for ticker-specific news)
            query: Search query (for general news)
            use_newsapi: Use NewsAPI
            use_google: Use Google News
            use_finnhub: Use Finnhub
            use_yahoo: Use Yahoo Finance

        Returns:
            Deduplicated list of articles from all sources
        """
        all_articles = []

        # Determine search term
        search_term = ticker or query

        if not search_term:
            logger.error("Must provide either ticker or query")
            return []

        logger.info(f"Collecting news for: {search_term}")

        # Collect from all sources (with error handling)
        if use_newsapi and self.newsapi_key:
            try:
                articles = self.fetch_from_newsapi(search_term)
                all_articles.extend(articles)
            except Exception as e:
                logger.error(f"NewsAPI failed: {e}")

        if use_google:
            try:
                articles = self.fetch_from_google_news_rss(search_term)
                all_articles.extend(articles)
            except Exception as e:
                logger.error(f"Google News failed: {e}")

        if use_finnhub and self.finnhub_key and ticker:
            try:
                articles = self.fetch_from_finnhub(ticker)
                all_articles.extend(articles)
            except Exception as e:
                logger.error(f"Finnhub failed: {e}")

        if use_yahoo and ticker:
            try:
                articles = self.fetch_from_yahoo_finance_rss(ticker)
                all_articles.extend(articles)
            except Exception as e:
                logger.error(f"Yahoo Finance failed: {e}")

        # Deduplicate by URL
        seen_urls = set()
        unique_articles = []

        for article in all_articles:
            url = article['url']
            if url not in seen_urls:
                seen_urls.add(url)
                unique_articles.append(article)

        # Sort by published date (newest first)
        unique_articles.sort(key=lambda x: x.get('published', ''), reverse=True)

        logger.info(f"Collected {len(unique_articles)} unique articles from {len(all_articles)} total")
        return unique_articles


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    print("="*80)
    print("📰 ROBUST NEWS COLLECTOR")
    print("="*80)
    print()

    # Initialize collector
    collector = RobustNewsCollector()

    # Test Google News RSS (no auth required)
    print("Testing Google News RSS (FREE, no auth)...")
    articles = collector.fetch_from_google_news_rss("NVDA stock")

    print(f"✅ Fetched {len(articles)} articles")
    print()

    if articles:
        print("Sample articles:")
        for i, article in enumerate(articles[:5], 1):
            print(f"{i}. {article['title'][:80]}")
            print(f"   Source: {article['source']}")
            print(f"   URL: {article['url'][:80]}...")
            print()

    print("="*80)
