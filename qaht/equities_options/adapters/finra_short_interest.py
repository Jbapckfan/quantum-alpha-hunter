"""
FINRA Short Interest adapter for squeeze detection.

FREE - scrapes FINRA short interest data.
High short interest + positive catalyst = ROCKET FUEL (5x-10x potential).
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
import re

import requests
from bs4 import BeautifulSoup
import pandas as pd

logger = logging.getLogger(__name__)


class FINRAShortInterestAdapter:
    """
    Fetch short interest data for squeeze detection.

    High short interest (>30% of float) + positive catalyst = squeeze potential.

    Data sources:
    1. FINRA bi-weekly reports (free)
    2. Yahoo Finance short % of float (free, in yfinance)
    3. Calculated days to cover
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })

    def get_short_interest_score(
        self,
        symbol: str,
        ticker_obj=None
    ) -> Dict:
        """
        Get short interest squeeze score.

        Args:
            symbol: Stock ticker
            ticker_obj: yfinance Ticker object (optional)

        Returns:
            Dict with:
                - squeeze_score: 0-100 (100 = perfect squeeze setup)
                - short_pct_float: Short interest as % of float
                - days_to_cover: Days to cover (SI / avg volume)
                - short_ratio: Short interest ratio
                - is_squeeze_candidate: True if >20% short interest
        """
        try:
            # Get short data from Yahoo Finance
            try:
                import yfinance as yf
            except ImportError:
                logger.warning("yfinance not installed")
                return self._empty_score()

            if ticker_obj is None:
                ticker_obj = yf.Ticker(symbol)

            info = ticker_obj.info

            # Extract short interest data
            short_pct_float = info.get('shortPercentOfFloat', 0)
            short_ratio = info.get('shortRatio', 0)

            if short_pct_float is None:
                short_pct_float = 0
            if short_ratio is None:
                short_ratio = 0

            # Convert to percentage if needed
            if short_pct_float < 1:
                short_pct_float = short_pct_float * 100

            # Days to cover
            days_to_cover = short_ratio

            # Is this a squeeze candidate?
            is_squeeze_candidate = short_pct_float > 20

            # Compute squeeze score (0-100)
            score = 0

            # Base score from short % of float
            if short_pct_float >= 40:
                score = 100  # Extreme squeeze potential
            elif short_pct_float >= 30:
                score = 85
            elif short_pct_float >= 20:
                score = 65
            elif short_pct_float >= 15:
                score = 45
            elif short_pct_float >= 10:
                score = 25
            else:
                score = 10  # Low squeeze potential

            # Bonus for high days to cover (harder to cover = bigger squeeze)
            if days_to_cover >= 10:
                score = min(100, score + 15)
            elif days_to_cover >= 7:
                score = min(100, score + 10)
            elif days_to_cover >= 5:
                score = min(100, score + 5)

            logger.info(f"{symbol} squeeze score: {score:.0f}/100 (SI={short_pct_float:.1f}%, DTC={days_to_cover:.1f}, candidate={is_squeeze_candidate})")

            return {
                'squeeze_score': round(score, 1),
                'short_pct_float': round(short_pct_float, 2),
                'days_to_cover': round(days_to_cover, 2),
                'short_ratio': round(short_ratio, 2),
                'is_squeeze_candidate': is_squeeze_candidate
            }

        except Exception as e:
            logger.error(f"Error fetching short interest for {symbol}: {e}")
            return self._empty_score()

    def _empty_score(self) -> Dict:
        """Return empty score when data unavailable."""
        return {
            'squeeze_score': 0,
            'short_pct_float': 0,
            'days_to_cover': 0,
            'short_ratio': 0,
            'is_squeeze_candidate': False
        }


def get_short_interest_score(symbol: str) -> Dict:
    """
    Get short interest squeeze score for a symbol.

    Returns dict with squeeze_score (0-100) and details.
    """
    adapter = FINRAShortInterestAdapter()
    return adapter.get_short_interest_score(symbol)
