"""
Wikipedia pageview spike detection.

Completely FREE - no API key needed.
Attention = Price moves.

Research shows: 10x pageview spike = high probability of >5% move.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests
import pandas as pd

logger = logging.getLogger(__name__)


class WikipediaPageviewsAdapter:
    """
    Detect attention spikes using Wikipedia pageview data.

    Wikimedia provides free API for pageview statistics.
    No API key required.

    Attention spikes often precede price volatility.
    """

    BASE_URL = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"

    # Company name mappings (ticker -> Wikipedia article title)
    COMPANY_MAPPINGS = {
        # Tech
        'AAPL': 'Apple_Inc.',
        'MSFT': 'Microsoft',
        'GOOGL': 'Google',
        'AMZN': 'Amazon_(company)',
        'TSLA': 'Tesla,_Inc.',
        'META': 'Meta_Platforms',
        'NVDA': 'Nvidia',
        # Growth
        'PLTR': 'Palantir_Technologies',
        'SOFI': 'SoFi',
        'HOOD': 'Robinhood_Markets',
        'COIN': 'Coinbase',
        # Energy
        'PLUG': 'Plug_Power',
        # Add more mappings as needed
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Quantum Alpha Hunter/1.0 (research@example.com)'
        })

    def get_pageview_spike(
        self,
        symbol: str,
        days_back: int = 30,
        article_title: Optional[str] = None
    ) -> Dict:
        """
        Detect Wikipedia pageview spikes for a company.

        Args:
            symbol: Stock ticker symbol
            days_back: Number of days to analyze
            article_title: Wikipedia article title (optional, will lookup if not provided)

        Returns:
            Dict with:
                - spike_score: 0-100 (100 = massive attention spike)
                - spike_ratio: Current views / 7-day avg baseline
                - current_views: Today's pageviews
                - baseline_views: 7-day average
                - trend: 'accelerating', 'decelerating', 'stable'
                - pageview_history: List of daily pageviews
        """
        try:
            # Lookup article title
            if article_title is None:
                article_title = self._get_article_title(symbol)
                if not article_title:
                    logger.warning(f"Could not find Wikipedia article for {symbol}")
                    return self._empty_spike_score()

            # Fetch pageview data
            pageviews = self._fetch_pageviews(article_title, days_back)

            if not pageviews or len(pageviews) < 7:
                logger.debug(f"Insufficient pageview data for {symbol}")
                return self._empty_spike_score()

            # Analyze spike
            return self._analyze_pageview_spike(pageviews, symbol)

        except Exception as e:
            logger.error(f"Error fetching pageview spike for {symbol}: {e}")
            return self._empty_spike_score()

    def _get_article_title(self, symbol: str) -> Optional[str]:
        """
        Get Wikipedia article title for a ticker symbol.

        First checks hardcoded mappings, then attempts search.
        """
        # Check mappings
        if symbol.upper() in self.COMPANY_MAPPINGS:
            return self.COMPANY_MAPPINGS[symbol.upper()]

        # Attempt to find via Wikipedia search
        try:
            search_url = "https://en.wikipedia.org/w/api.php"
            params = {
                'action': 'opensearch',
                'format': 'json',
                'search': symbol,
                'limit': 1
            }

            response = self.session.get(search_url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            if len(data) > 1 and len(data[1]) > 0:
                # Get first search result
                article_title = data[1][0].replace(' ', '_')
                logger.info(f"Found Wikipedia article '{article_title}' for {symbol}")
                return article_title

        except Exception as e:
            logger.debug(f"Could not search Wikipedia for {symbol}: {e}")

        return None

    def _fetch_pageviews(self, article_title: str, days_back: int) -> List[Dict]:
        """
        Fetch daily pageview data from Wikimedia API.

        Returns list of {date, views} dicts.
        """
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)

            # Format dates as YYYYMMDD
            start_str = start_date.strftime('%Y%m%d')
            end_str = end_date.strftime('%Y%m%d')

            # Construct API URL
            url = f"{self.BASE_URL}/en.wikipedia/all-access/all-agents/{article_title}/daily/{start_str}/{end_str}"

            response = self.session.get(url, timeout=15)
            response.raise_for_status()

            data = response.json()

            if 'items' not in data:
                return []

            # Extract pageviews
            pageviews = []
            for item in data['items']:
                pageviews.append({
                    'date': datetime.strptime(item['timestamp'], '%Y%m%d00'),
                    'views': item['views']
                })

            return pageviews

        except Exception as e:
            logger.error(f"Error fetching pageviews for {article_title}: {e}")
            return []

    def _analyze_pageview_spike(self, pageviews: List[Dict], symbol: str) -> Dict:
        """
        Analyze pageview data to detect spikes.

        High spike ratio = major attention event.
        """
        if len(pageviews) < 7:
            return self._empty_spike_score()

        # Convert to dataframe for easier analysis
        df = pd.DataFrame(pageviews)
        df = df.sort_values('date')

        # Current views (most recent day)
        current_views = df.iloc[-1]['views']

        # Baseline = 7-day average (excluding current day)
        baseline_views = df.iloc[-8:-1]['views'].mean()

        # Spike ratio
        spike_ratio = current_views / baseline_views if baseline_views > 0 else 1.0

        # Trend analysis (is spike accelerating or decelerating?)
        if len(df) >= 3:
            recent_3d_avg = df.iloc[-3:]['views'].mean()
            prev_3d_avg = df.iloc[-6:-3]['views'].mean()

            if recent_3d_avg > prev_3d_avg * 1.2:
                trend = 'accelerating'
            elif recent_3d_avg < prev_3d_avg * 0.8:
                trend = 'decelerating'
            else:
                trend = 'stable'
        else:
            trend = 'unknown'

        # Compute spike score (0-100)
        score = 0

        # Base score from spike ratio
        if spike_ratio >= 10:
            score = 100  # Massive spike
        elif spike_ratio >= 5:
            score = 80
        elif spike_ratio >= 3:
            score = 60
        elif spike_ratio >= 2:
            score = 40
        elif spike_ratio >= 1.5:
            score = 25
        else:
            score = 10  # No spike

        # Bonus for accelerating trend
        if trend == 'accelerating':
            score = min(100, score + 15)

        # Penalty for decelerating
        if trend == 'decelerating':
            score = max(0, score - 15)

        logger.info(f"{symbol} pageview spike: {score:.0f} (ratio={spike_ratio:.1f}x, current={current_views}, baseline={baseline_views:.0f}, trend={trend})")

        return {
            'spike_score': round(score, 1),
            'spike_ratio': round(spike_ratio, 2),
            'current_views': int(current_views),
            'baseline_views': int(baseline_views),
            'trend': trend,
            'pageview_history': pageviews[-14:]  # Last 2 weeks
        }

    def _empty_spike_score(self) -> Dict:
        """Return empty spike score when data unavailable."""
        return {
            'spike_score': 0,
            'spike_ratio': 1.0,
            'current_views': 0,
            'baseline_views': 0,
            'trend': 'unknown',
            'pageview_history': []
        }


# Convenience function
def get_pageview_spike(symbol: str, days_back: int = 30) -> Dict:
    """
    Get Wikipedia pageview spike score for a symbol.

    Returns dict with spike_score (0-100) and details.
    """
    adapter = WikipediaPageviewsAdapter()
    return adapter.get_pageview_spike(symbol, days_back=days_back)
