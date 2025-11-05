"""
LunarCrush API (FREE - 150 calls/month)
Aggregated crypto social intelligence from Twitter, Reddit, YouTube, Medium
"""
import logging
import requests
from typing import List, Dict

logger = logging.getLogger(__name__)

class LunarCrushAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://lunarcrush.com/api3"
        
    def get_market_data(self, symbol: str) -> Dict:
        """Get social + price data for a coin"""
        try:
            url = f"{self.base_url}/coins/{symbol}/v1"
            headers = {'Authorization': f'Bearer {self.api_key}'}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"LunarCrush failed for {symbol}: {e}")
            return {}
