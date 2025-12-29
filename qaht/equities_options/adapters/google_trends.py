"""
Google Trends search volume analysis.

Completely FREE - uses pytrends library.
Retail interest drives momentum.

Search spikes predict buying pressure and FOMO.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class GoogleTrendsAdapter:
    """
    Analyze Google Search trends for ticker symbols and companies.

    Uses pytrends library (unofficial Google Trends API).
    Completely free, no API key required.

    Search volume spikes = retail interest = potential momentum.
    """

    def __init__(self):
        self._pytrend = None

    def _get_pytrend(self):
        """Lazy initialize pytrends (to avoid import errors if not installed)."""
        if self._pytrend is None:
            try:
                from pytrends.request import TrendReq
                self._pytrend = TrendReq(
                    hl='en-US',
                    tz=360,
                    timeout=(10, 25),
                    retries=2,
                    backoff_factor=0.5
                )
            except ImportError:
                logger.warning("pytrends not installed. Run: pip install pytrends")
                raise ImportError("pytrends library required for Google Trends analysis")
        return self._pytrend

    def get_search_trend(
        self,
        symbol: str,
        timeframe: str = 'today 3-m',
        company_name: Optional[str] = None
    ) -> Dict:
        """
        Get Google Trends search volume trend for a symbol.

        Args:
            symbol: Stock ticker symbol (e.g., 'TSLA')
            timeframe: Google Trends timeframe (e.g., 'today 3-m', 'today 1-m')
            company_name: Company name to search for (optional)

        Returns:
            Dict with:
                - trend_score: 0-100 (100 = massive search spike)
                - current_interest: Current search interest (0-100)
                - avg_interest: Average search interest over period
                - spike_ratio: Current / average
                - trend: 'rising', 'falling', 'stable'
                - related_queries: Top related search queries
                - interest_over_time: Time series data
        """
        try:
            pytrend = self._get_pytrend()

            # Search for both ticker and company name
            search_terms = [symbol]
            if company_name:
                search_terms.append(company_name)

            # Build payload
            pytrend.build_payload(
                kw_list=search_terms[:5],  # Max 5 terms
                timeframe=timeframe,
                geo='US'  # Focus on US market
            )

            # Get interest over time
            interest_df = pytrend.interest_over_time()

            if interest_df.empty or symbol not in interest_df.columns:
                logger.debug(f"No Google Trends data for {symbol}")
                return self._empty_trend_score()

            # Analyze trend
            return self._analyze_search_trend(interest_df, symbol)

        except ImportError as e:
            logger.error(f"pytrends not installed: {e}")
            return self._empty_trend_score()
        except Exception as e:
            logger.error(f"Error fetching Google Trends for {symbol}: {e}")
            return self._empty_trend_score()

    def get_related_queries(self, symbol: str) -> Dict:
        """
        Get related and rising search queries for a symbol.

        Returns dict with 'top' and 'rising' query lists.
        """
        try:
            pytrend = self._get_pytrend()

            pytrend.build_payload(kw_list=[symbol], timeframe='today 3-m', geo='US')

            # Get related queries
            related = pytrend.related_queries()

            if symbol not in related:
                return {'top': [], 'rising': []}

            result = {}

            # Top queries
            if related[symbol]['top'] is not None:
                result['top'] = related[symbol]['top'].head(10).to_dict('records')
            else:
                result['top'] = []

            # Rising queries
            if related[symbol]['rising'] is not None:
                result['rising'] = related[symbol]['rising'].head(10).to_dict('records')
            else:
                result['rising'] = []

            return result

        except Exception as e:
            logger.debug(f"Could not fetch related queries for {symbol}: {e}")
            return {'top': [], 'rising': []}

    def compare_symbols(self, symbols: List[str], timeframe: str = 'today 3-m') -> pd.DataFrame:
        """
        Compare search interest for multiple symbols.

        Args:
            symbols: List of ticker symbols (max 5)
            timeframe: Google Trends timeframe

        Returns:
            DataFrame with normalized search interest for each symbol
        """
        try:
            pytrend = self._get_pytrend()

            # Limit to 5 symbols (Google Trends API limit)
            symbols = symbols[:5]

            pytrend.build_payload(kw_list=symbols, timeframe=timeframe, geo='US')

            interest_df = pytrend.interest_over_time()

            if interest_df.empty:
                return pd.DataFrame()

            # Remove 'isPartial' column if present
            if 'isPartial' in interest_df.columns:
                interest_df = interest_df.drop(columns=['isPartial'])

            return interest_df

        except Exception as e:
            logger.error(f"Error comparing symbols: {e}")
            return pd.DataFrame()

    def _analyze_search_trend(self, interest_df: pd.DataFrame, symbol: str) -> Dict:
        """
        Analyze search interest time series to compute trend score.

        High spike = retail FOMO = potential continuation.
        """
        if symbol not in interest_df.columns:
            return self._empty_trend_score()

        # Get search interest values
        values = interest_df[symbol].values

        # Current interest (last available)
        current_interest = values[-1]

        # Average interest over period
        avg_interest = values.mean()

        # Spike ratio
        spike_ratio = current_interest / avg_interest if avg_interest > 0 else 1.0

        # Trend direction (last 7 days vs previous 7 days)
        if len(values) >= 14:
            recent_avg = values[-7:].mean()
            prev_avg = values[-14:-7].mean()

            if recent_avg > prev_avg * 1.2:
                trend = 'rising'
            elif recent_avg < prev_avg * 0.8:
                trend = 'falling'
            else:
                trend = 'stable'
        else:
            trend = 'unknown'

        # Compute trend score (0-100)
        score = 0

        # Base score from spike ratio
        if spike_ratio >= 5:
            score = 100  # Massive spike
        elif spike_ratio >= 3:
            score = 80
        elif spike_ratio >= 2:
            score = 60
        elif spike_ratio >= 1.5:
            score = 40
        elif spike_ratio >= 1.2:
            score = 25
        else:
            score = 10  # Below average

        # Bonus for rising trend
        if trend == 'rising':
            score = min(100, score + 15)

        # Penalty for falling
        if trend == 'falling':
            score = max(0, score - 10)

        # Bonus for high absolute interest
        if current_interest >= 80:
            score = min(100, score + 10)

        logger.info(f"{symbol} Google Trends: {score:.0f} (interest={current_interest}, spike={spike_ratio:.1f}x, trend={trend})")

        # Get related queries
        try:
            related = self.get_related_queries(symbol)
        except:
            related = {'top': [], 'rising': []}

        return {
            'trend_score': round(score, 1),
            'current_interest': int(current_interest),
            'avg_interest': round(avg_interest, 1),
            'spike_ratio': round(spike_ratio, 2),
            'trend': trend,
            'related_queries': related,
            'interest_over_time': interest_df[symbol].tail(30).to_dict()  # Last 30 days
        }

    def _empty_trend_score(self) -> Dict:
        """Return empty trend score when data unavailable."""
        return {
            'trend_score': 0,
            'current_interest': 0,
            'avg_interest': 0,
            'spike_ratio': 1.0,
            'trend': 'unknown',
            'related_queries': {'top': [], 'rising': []},
            'interest_over_time': {}
        }


# Convenience functions
def get_search_trend(symbol: str, timeframe: str = 'today 3-m') -> Dict:
    """
    Get Google Trends search volume trend for a symbol.

    Returns dict with trend_score (0-100) and details.
    """
    adapter = GoogleTrendsAdapter()
    return adapter.get_search_trend(symbol, timeframe=timeframe)


def compare_symbols(symbols: List[str], timeframe: str = 'today 3-m') -> pd.DataFrame:
    """
    Compare Google Trends interest for multiple symbols.

    Returns DataFrame with normalized search interest.
    """
    adapter = GoogleTrendsAdapter()
    return adapter.compare_symbols(symbols, timeframe=timeframe)
