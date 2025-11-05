"""
4chan /biz/ Board API (FREE - unlimited)
Very early signals (high noise). Use caution.
"""
import logging
import requests
from typing import List, Dict
from qaht.utils.validation import validate_ticker, ValidationError
from qaht.utils.error_handling import handle_api_errors
from qaht.core.production_optimizations import CircuitBreaker

logger = logging.getLogger(__name__)

class FourChanBizAPI:
    def __init__(self):
        self.base_url = "https://a.4cdn.org/biz"
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=300,  # 5 minutes
            expected_exception=Exception
        )
        
    @handle_api_errors("4chan", default_return=[], log_level="warning")
    def get_catalog(self) -> List[Dict]:
        """Get /biz/ catalog threads"""
        def _fetch():
            url = f"{self.base_url}/catalog.json"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()

        return self.circuit_breaker.call(_fetch)
            
    def search_ticker_mentions(self, ticker: str) -> int:
        """Count mentions of a ticker in recent threads"""
        # Validate ticker input
        try:
            ticker = validate_ticker(ticker, allow_crypto=True)
        except ValidationError as e:
            logger.error(f"Invalid ticker for 4chan search: {e}")
            return 0

        catalog = self.get_catalog()
        count = 0
        for page in catalog:
            for thread in page.get('threads', []):
                subject = thread.get('sub', '').upper()
                comment = thread.get('com', '').upper()
                if ticker.upper() in subject or ticker.upper() in comment:
                    count += 1
        return count
