"""
YouTube API Integration (FREE - 10,000 queries/day)

Track retail sentiment via finance YouTubers

Features:
- Video upload tracking
- View count monitoring
- Comment sentiment
- Trending topics

Requires: YouTube Data API v3 key (FREE)
"""

import logging
import requests
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class YouTubeAPI:
    """YouTube Data API v3 client (FREE - 10K queries/day)"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://www.googleapis.com/youtube/v3"

    def search_videos(self, query: str, max_results: int = 10) -> List[Dict]:
        """Search for videos about a topic/ticker"""
        try:
            url = f"{self.base_url}/search"
            params = {
                'part': 'snippet',
                'q': query,
                'type': 'video',
                'maxResults': min(max_results, 50),
                'order': 'relevance',
                'key': self.api_key
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            videos = []

            for item in data.get('items', []):
                videos.append({
                    'video_id': item['id']['videoId'],
                    'title': item['snippet']['title'],
                    'channel': item['snippet']['channelTitle'],
                    'published_at': item['snippet']['publishedAt'],
                    'description': item['snippet']['description']
                })

            logger.info(f"Found {len(videos)} YouTube videos for '{query}'")
            return videos

        except Exception as e:
            logger.error(f"YouTube search failed for '{query}': {e}")
            return []

    def get_video_stats(self, video_id: str) -> Optional[Dict]:
        """Get video statistics"""
        try:
            url = f"{self.base_url}/videos"
            params = {
                'part': 'statistics',
                'id': video_id,
                'key': self.api_key
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            items = data.get('items', [])

            if not items:
                return None

            stats = items[0]['statistics']
            return {
                'views': int(stats.get('viewCount', 0)),
                'likes': int(stats.get('likeCount', 0)),
                'comments': int(stats.get('commentCount', 0))
            }

        except Exception as e:
            logger.error(f"Failed to get stats for video {video_id}: {e}")
            return None
