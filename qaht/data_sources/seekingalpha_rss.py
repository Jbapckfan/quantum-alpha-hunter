"""
Seeking Alpha RSS Feeds (FREE - unlimited)
Quality analysis and earnings coverage
"""
import logging
import feedparser
from typing import List, Dict

logger = logging.getLogger(__name__)

class SeekingAlphaRSS:
    def __init__(self):
        self.base_url = "https://seekingalpha.com"
        
    def get_market_news(self) -> List[Dict]:
        """Get latest market news"""
        try:
            url = f"{self.base_url}/market_currents.xml"
            feed = feedparser.parse(url)
            return [{'title': entry.title, 'link': entry.link, 'published': entry.published} 
                   for entry in feed.entries[:20]]
        except Exception as e:
            logger.error(f"Seeking Alpha RSS failed: {e}")
            return []
            
    def get_symbol_news(self, symbol: str) -> List[Dict]:
        """Get news for specific symbol"""
        try:
            url = f"{self.base_url}/api/sa/combined/{symbol}.xml"
            feed = feedparser.parse(url)
            return [{'title': entry.title, 'link': entry.link, 'published': entry.published} 
                   for entry in feed.entries[:10]]
        except Exception as e:
            logger.error(f"Seeking Alpha RSS failed for {symbol}: {e}")
            return []
