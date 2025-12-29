"""
SEC EDGAR adapter for insider trading (Form 4) and material events (Form 8-K).

Completely FREE - no API key needed.
Insiders know before the market. Form 4 cluster buying = strong signal.
"""

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class SECEdgarAdapter:
    """
    Fetch insider trading (Form 4) and material events (Form 8-K) from SEC EDGAR.

    Form 4: Insider trading transactions (buy/sell)
    Form 8-K: Material company events (M&A, CEO change, earnings, etc.)

    All data is FREE and does not require an API key.
    """

    BASE_URL = "https://www.sec.gov"
    HEADERS = {
        "User-Agent": "Quantum Alpha Hunter Tech/1.0 (research@example.com)",  # SEC requires User-Agent
        "Accept-Encoding": "gzip, deflate",
        "Host": "www.sec.gov"
    }

    def __init__(self):
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create requests session with retry logic."""
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            backoff_factor=1
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update(self.HEADERS)
        return session

    def get_insider_trading_score(
        self,
        symbol: str,
        cik: Optional[str] = None,
        days_back: int = 90
    ) -> Dict:
        """
        Compute insider trading score from Form 4 filings.

        Args:
            symbol: Stock ticker symbol
            cik: CIK number (optional, will lookup if not provided)
            days_back: Number of days to look back for filings

        Returns:
            Dict with:
                - insider_buy_score: 0-100 (100 = strong cluster buying)
                - num_buyers: Number of insiders buying
                - num_sellers: Number of insiders selling
                - total_buy_value: Total dollar value of buys
                - total_sell_value: Total dollar value of sells
                - recent_filings: List of recent Form 4 filings
                - has_cluster_buying: True if 3+ insiders bought in last 30 days
        """
        try:
            if not cik:
                cik = self._lookup_cik(symbol)
                if not cik:
                    logger.warning(f"Could not find CIK for {symbol}")
                    return self._empty_insider_score()

            # Fetch Form 4 filings
            filings = self._fetch_form4_filings(cik, days_back)

            if not filings:
                return self._empty_insider_score()

            # Analyze filings
            return self._analyze_insider_activity(filings, symbol)

        except Exception as e:
            logger.error(f"Error fetching insider trading for {symbol}: {e}")
            return self._empty_insider_score()

    def get_material_events_score(
        self,
        symbol: str,
        cik: Optional[str] = None,
        days_back: int = 30
    ) -> Dict:
        """
        Detect material events from Form 8-K filings.

        Args:
            symbol: Stock ticker symbol
            cik: CIK number (optional)
            days_back: Number of days to look back

        Returns:
            Dict with:
                - event_score: 0-100 (100 = major positive event)
                - num_events: Number of 8-K filings
                - event_types: List of event types
                - has_major_event: True if M&A, CEO change, or major announcement
                - recent_events: List of recent 8-K filings
        """
        try:
            if not cik:
                cik = self._lookup_cik(symbol)
                if not cik:
                    return self._empty_event_score()

            # Fetch Form 8-K filings
            filings = self._fetch_form8k_filings(cik, days_back)

            if not filings:
                return self._empty_event_score()

            # Analyze events
            return self._analyze_material_events(filings, symbol)

        except Exception as e:
            logger.error(f"Error fetching material events for {symbol}: {e}")
            return self._empty_event_score()

    def _lookup_cik(self, symbol: str) -> Optional[str]:
        """
        Lookup CIK (Central Index Key) from ticker symbol.

        Uses SEC company tickers JSON endpoint.
        """
        try:
            url = "https://www.sec.gov/files/company_tickers.json"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()

            data = response.json()

            # Search for ticker
            for entry in data.values():
                if entry.get("ticker", "").upper() == symbol.upper():
                    cik = str(entry["cik_str"]).zfill(10)  # Pad to 10 digits
                    logger.info(f"Found CIK {cik} for {symbol}")
                    return cik

            logger.warning(f"No CIK found for {symbol}")
            return None

        except Exception as e:
            logger.error(f"Error looking up CIK for {symbol}: {e}")
            return None

    def _fetch_form4_filings(self, cik: str, days_back: int) -> List[Dict]:
        """
        Fetch Form 4 filings for a given CIK.

        Returns list of filing metadata.
        """
        try:
            # SEC EDGAR RSS feed for recent filings
            url = f"{self.BASE_URL}/cgi-bin/browse-edgar"
            params = {
                "action": "getcompany",
                "CIK": cik,
                "type": "4",  # Form 4
                "dateb": "",  # End date (today)
                "owner": "include",  # Include insider transactions
                "start": 0,
                "count": 100,  # Max filings to fetch
                "output": "atom"  # XML format
            }

            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()

            # Parse XML
            filings = self._parse_edgar_xml(response.text, days_back)

            logger.info(f"Found {len(filings)} Form 4 filings for CIK {cik}")
            return filings

        except Exception as e:
            logger.error(f"Error fetching Form 4 filings: {e}")
            return []

    def _fetch_form8k_filings(self, cik: str, days_back: int) -> List[Dict]:
        """
        Fetch Form 8-K filings for a given CIK.
        """
        try:
            url = f"{self.BASE_URL}/cgi-bin/browse-edgar"
            params = {
                "action": "getcompany",
                "CIK": cik,
                "type": "8-K",  # Form 8-K
                "dateb": "",
                "owner": "exclude",
                "start": 0,
                "count": 40,
                "output": "atom"
            }

            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()

            filings = self._parse_edgar_xml(response.text, days_back)

            logger.info(f"Found {len(filings)} Form 8-K filings for CIK {cik}")
            return filings

        except Exception as e:
            logger.error(f"Error fetching Form 8-K filings: {e}")
            return []

    def _parse_edgar_xml(self, xml_text: str, days_back: int) -> List[Dict]:
        """
        Parse EDGAR XML/Atom feed response.
        """
        try:
            # Remove namespace for easier parsing
            xml_text = xml_text.replace('xmlns="http://www.w3.org/2005/Atom"', '')

            root = ET.fromstring(xml_text)
            filings = []

            cutoff_date = datetime.now() - timedelta(days=days_back)

            for entry in root.findall('.//entry'):
                filing_date_str = entry.findtext('filing-date')
                if not filing_date_str:
                    continue

                filing_date = datetime.strptime(filing_date_str, '%Y-%m-%d')

                if filing_date < cutoff_date:
                    continue

                filing = {
                    'title': entry.findtext('title', ''),
                    'filing_date': filing_date_str,
                    'link': entry.find('.//link[@rel="alternate"]').get('href') if entry.find('.//link[@rel="alternate"]') is not None else '',
                    'summary': entry.findtext('summary', '')
                }

                filings.append(filing)

            return filings

        except Exception as e:
            logger.error(f"Error parsing EDGAR XML: {e}")
            return []

    def _analyze_insider_activity(self, filings: List[Dict], symbol: str) -> Dict:
        """
        Analyze Form 4 filings to compute insider trading score.

        High score = cluster buying by multiple insiders.
        """
        num_buyers = 0
        num_sellers = 0
        recent_30d_buyers = 0

        cutoff_30d = datetime.now() - timedelta(days=30)

        for filing in filings:
            title = filing['title'].lower()
            summary = filing['summary'].lower()

            filing_date = datetime.strptime(filing['filing_date'], '%Y-%m-%d')

            # Detect buys vs sells (simple heuristic)
            is_buy = 'purchase' in title or 'buy' in summary or 'acquired' in summary
            is_sell = 'sale' in title or 'sell' in summary or 'disposed' in summary

            if is_buy:
                num_buyers += 1
                if filing_date >= cutoff_30d:
                    recent_30d_buyers += 1
            elif is_sell:
                num_sellers += 1

        # Cluster buying = 3+ insiders in last 30 days
        has_cluster_buying = recent_30d_buyers >= 3

        # Compute score (0-100)
        score = 0

        # Base score from buy/sell ratio
        if num_buyers > 0 or num_sellers > 0:
            buy_ratio = num_buyers / (num_buyers + num_sellers)
            score += buy_ratio * 50  # Max 50 points

        # Bonus for cluster buying
        if has_cluster_buying:
            score += 30  # +30 points for cluster

        # Bonus for recent activity
        if recent_30d_buyers > 0:
            score += min(recent_30d_buyers * 5, 20)  # Up to +20 points

        score = min(score, 100)

        logger.info(f"{symbol} insider score: {score:.0f} ({num_buyers} buyers, {num_sellers} sellers, cluster={has_cluster_buying})")

        return {
            'insider_buy_score': round(score, 1),
            'num_buyers': num_buyers,
            'num_sellers': num_sellers,
            'total_buy_value': 0,  # Would need to parse filing details
            'total_sell_value': 0,
            'recent_filings': filings[:10],  # Top 10 most recent
            'has_cluster_buying': has_cluster_buying,
            'recent_30d_buyers': recent_30d_buyers
        }

    def _analyze_material_events(self, filings: List[Dict], symbol: str) -> Dict:
        """
        Analyze Form 8-K filings to detect material events.

        High score = major positive events (M&A, product launch, earnings beat).
        """
        num_events = len(filings)
        event_types = []
        has_major_event = False

        # Keywords for different event types
        POSITIVE_KEYWORDS = ['acquisition', 'merger', 'partnership', 'agreement', 'launch', 'beat', 'exceed']
        NEGATIVE_KEYWORDS = ['investigation', 'lawsuit', 'departure', 'restatement', 'warning', 'miss']
        MAJOR_KEYWORDS = ['acquisition', 'merger', 'ceo', 'chief executive']

        positive_count = 0
        negative_count = 0

        for filing in filings:
            title = filing['title'].lower()
            summary = filing['summary'].lower()
            text = title + ' ' + summary

            # Detect major events
            if any(kw in text for kw in MAJOR_KEYWORDS):
                has_major_event = True
                event_types.append('MAJOR')

            # Detect positive/negative
            if any(kw in text for kw in POSITIVE_KEYWORDS):
                positive_count += 1
                event_types.append('POSITIVE')
            elif any(kw in text for kw in NEGATIVE_KEYWORDS):
                negative_count += 1
                event_types.append('NEGATIVE')
            else:
                event_types.append('NEUTRAL')

        # Compute score
        score = 50  # Neutral baseline

        if num_events > 0:
            event_sentiment = (positive_count - negative_count) / num_events
            score += event_sentiment * 30  # -30 to +30 points

        if has_major_event:
            score += 20  # Bonus for major event

        score = max(0, min(score, 100))

        logger.info(f"{symbol} event score: {score:.0f} ({num_events} events, {positive_count} positive, {negative_count} negative)")

        return {
            'event_score': round(score, 1),
            'num_events': num_events,
            'event_types': event_types[:10],
            'has_major_event': has_major_event,
            'recent_events': filings[:5],
            'positive_count': positive_count,
            'negative_count': negative_count
        }

    def _empty_insider_score(self) -> Dict:
        """Return empty insider trading score."""
        return {
            'insider_buy_score': 0,
            'num_buyers': 0,
            'num_sellers': 0,
            'total_buy_value': 0,
            'total_sell_value': 0,
            'recent_filings': [],
            'has_cluster_buying': False,
            'recent_30d_buyers': 0
        }

    def _empty_event_score(self) -> Dict:
        """Return empty material events score."""
        return {
            'event_score': 50,  # Neutral
            'num_events': 0,
            'event_types': [],
            'has_major_event': False,
            'recent_events': [],
            'positive_count': 0,
            'negative_count': 0
        }


# Convenience functions
def get_insider_trading_score(symbol: str, days_back: int = 90) -> Dict:
    """
    Get insider trading score for a symbol.

    Returns dict with insider_buy_score (0-100) and details.
    """
    adapter = SECEdgarAdapter()
    return adapter.get_insider_trading_score(symbol, days_back=days_back)


def get_material_events_score(symbol: str, days_back: int = 30) -> Dict:
    """
    Get material events score for a symbol.

    Returns dict with event_score (0-100) and details.
    """
    adapter = SECEdgarAdapter()
    return adapter.get_material_events_score(symbol, days_back=days_back)
