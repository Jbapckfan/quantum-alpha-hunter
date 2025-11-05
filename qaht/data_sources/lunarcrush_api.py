"""
LunarCrush API (FREE - 150 calls/month)
Aggregated crypto social intelligence from Twitter, Reddit, YouTube, Medium
"""
import logging
import requests
from typing import List, Dict
from qaht.utils.validation import validate_api_key, validate_ticker, mask_secret, ValidationError
from qaht.utils.error_handling import handle_api_errors
from qaht.core.production_optimizations import CircuitBreaker, AdaptiveRateLimiter

logger = logging.getLogger(__name__)

class LunarCrushAPI:
    def __init__(self, api_key: str):
        # Validate API key
        try:
            self.api_key = validate_api_key(api_key, "LunarCrush", min_length=20)
            logger.info(f"LunarCrush API initialized with key: {mask_secret(self.api_key)}")
        except ValidationError as e:
            logger.error(f"LunarCrush API key validation failed: {e}")
            raise
        self.base_url = "https://lunarcrush.com/api3"
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=120,
            expected_exception=Exception
        )
        self.rate_limiter = AdaptiveRateLimiter(default_delay=1.0)
        
    def get_market_data(self, symbol: str) -> Dict:
        """Get social + price data for a coin"""
        # Validate symbol input
        try:
            symbol = validate_ticker(symbol, allow_crypto=True)
        except ValidationError as e:
            logger.error(f"Invalid symbol for LunarCrush: {e}")
            return {}

        try:
            url = f"{self.base_url}/coins/{symbol}/v1"
            headers = {'Authorization': f'Bearer {self.api_key}'}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"LunarCrush failed for {symbol}: {e}")
            return {}
