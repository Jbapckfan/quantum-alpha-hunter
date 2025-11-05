"""
Integration tests for YouTube API
"""
import pytest
import requests
from unittest.mock import Mock, patch
from qaht.data_sources.youtube_api import YouTubeAPI
from qaht.utils.validation import ValidationError


class TestYouTubeAPIInitialization:
    """Test YouTube API initialization and validation"""

    def test_valid_api_key(self):
        """Test initialization with valid API key"""
        api_key = "AIzaSyD1234567890abcdefghijklmnop"
        api = YouTubeAPI(api_key)

        assert api.api_key == api_key
        assert api.base_url == "https://www.googleapis.com/youtube/v3"
        assert api.circuit_breaker is not None
        assert api.rate_limiter is not None

    def test_invalid_api_key_too_short(self):
        """Test initialization with too short API key"""
        with pytest.raises(ValidationError, match="too short"):
            YouTubeAPI("short_key")

    def test_invalid_api_key_placeholder(self):
        """Test initialization with placeholder API key"""
        with pytest.raises(ValidationError, match="not configured"):
            YouTubeAPI("your_key_here")

    def test_empty_api_key(self):
        """Test initialization with empty API key"""
        with pytest.raises(ValidationError, match="non-empty string"):
            YouTubeAPI("")

    def test_api_key_whitespace_stripped(self):
        """Test API key whitespace handling"""
        api_key = "  AIzaSyD1234567890abcdefghijklmnop  "
        api = YouTubeAPI(api_key)
        assert api.api_key == "AIzaSyD1234567890abcdefghijklmnop"


class TestYouTubeAPISearchVideos:
    """Test video search functionality"""

    def setup_method(self):
        """Setup test instance"""
        self.api_key = "AIzaSyD1234567890abcdefghijklmnop"
        self.api = YouTubeAPI(self.api_key)

    def test_search_videos_success(self, mocker):
        """Test successful video search"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'items': [
                {
                    'id': {'videoId': 'video1'},
                    'snippet': {
                        'title': 'AAPL Stock Analysis',
                        'channelTitle': 'Stock Guru',
                        'publishedAt': '2024-01-15T12:00:00Z',
                        'description': 'Deep dive into Apple stock'
                    }
                },
                {
                    'id': {'videoId': 'video2'},
                    'snippet': {
                        'title': 'Why AAPL is Bullish',
                        'channelTitle': 'Trader TV',
                        'publishedAt': '2024-01-14T10:00:00Z',
                        'description': 'Technical analysis of AAPL'
                    }
                }
            ]
        }

        mocker.patch('requests.get', return_value=mock_response)

        results = self.api.search_videos('AAPL stock analysis', max_results=10)

        assert len(results) == 2
        assert results[0]['video_id'] == 'video1'
        assert results[0]['title'] == 'AAPL Stock Analysis'
        assert results[0]['channel'] == 'Stock Guru'
        assert results[1]['video_id'] == 'video2'

    def test_search_videos_query_sanitization(self, mocker):
        """Test search query sanitization"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'items': []}

        mock_get = mocker.patch('requests.get', return_value=mock_response)

        # Dangerous query should be sanitized
        dangerous_query = "<script>alert(1)</script> AAPL"
        results = self.api.search_videos(dangerous_query)

        # Should call API with sanitized query
        call_args = mock_get.call_args
        query_param = call_args[1]['params']['q']
        assert '<script>' not in query_param
        assert 'AAPL' in query_param

    def test_search_videos_empty_query(self, mocker):
        """Test search with empty query"""
        mocker.patch('requests.get')

        results = self.api.search_videos('')
        assert results == []

    def test_search_videos_query_too_long(self, mocker):
        """Test search with too long query"""
        mocker.patch('requests.get')

        long_query = 'a' * 200  # Exceeds max_length=100
        results = self.api.search_videos(long_query)
        assert results == []

    def test_search_videos_max_results_limit(self, mocker):
        """Test max_results parameter limiting"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'items': []}

        mock_get = mocker.patch('requests.get', return_value=mock_response)

        # Request 100 results, should cap at 50
        self.api.search_videos('AAPL', max_results=100)

        call_args = mock_get.call_args
        assert call_args[1]['params']['maxResults'] == 50

    def test_search_videos_http_error(self, mocker):
        """Test HTTP error handling"""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError()

        mocker.patch('requests.get', return_value=mock_response)

        results = self.api.search_videos('AAPL')
        assert results == []

    def test_search_videos_timeout(self, mocker):
        """Test timeout error handling"""
        mocker.patch('requests.get', side_effect=requests.exceptions.Timeout())

        results = self.api.search_videos('AAPL')
        assert results == []

    def test_search_videos_connection_error(self, mocker):
        """Test connection error handling"""
        mocker.patch('requests.get', side_effect=requests.exceptions.ConnectionError())

        results = self.api.search_videos('AAPL')
        assert results == []

    def test_search_videos_api_key_included(self, mocker):
        """Test API key is included in request"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'items': []}

        mock_get = mocker.patch('requests.get', return_value=mock_response)

        self.api.search_videos('AAPL')

        call_args = mock_get.call_args
        assert call_args[1]['params']['key'] == self.api_key

    def test_search_videos_empty_results(self, mocker):
        """Test handling of empty results"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'items': []}

        mocker.patch('requests.get', return_value=mock_response)

        results = self.api.search_videos('NONEXISTENT_TICKER_XYZ')
        assert results == []


class TestYouTubeAPIVideoStats:
    """Test video statistics functionality"""

    def setup_method(self):
        """Setup test instance"""
        self.api = YouTubeAPI("AIzaSyD1234567890abcdefghijklmnop")

    def test_get_video_stats_success(self, mocker):
        """Test successful video stats retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'items': [
                {
                    'statistics': {
                        'viewCount': '100000',
                        'likeCount': '5000',
                        'commentCount': '250'
                    }
                }
            ]
        }

        mocker.patch('requests.get', return_value=mock_response)

        stats = self.api.get_video_stats('video_id_123')

        assert stats is not None
        assert stats['views'] == 100000
        assert stats['likes'] == 5000
        assert stats['comments'] == 250

    def test_get_video_stats_missing_counts(self, mocker):
        """Test stats with missing count fields"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'items': [
                {
                    'statistics': {
                        'viewCount': '1000'
                        # likeCount and commentCount missing
                    }
                }
            ]
        }

        mocker.patch('requests.get', return_value=mock_response)

        stats = self.api.get_video_stats('video_id_123')

        assert stats['views'] == 1000
        assert stats['likes'] == 0
        assert stats['comments'] == 0

    def test_get_video_stats_not_found(self, mocker):
        """Test stats for non-existent video"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'items': []}

        mocker.patch('requests.get', return_value=mock_response)

        stats = self.api.get_video_stats('nonexistent_video')
        assert stats is None

    def test_get_video_stats_http_error(self, mocker):
        """Test HTTP error handling"""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError()

        mocker.patch('requests.get', return_value=mock_response)

        stats = self.api.get_video_stats('video_id')
        assert stats is None

    def test_get_video_stats_timeout(self, mocker):
        """Test timeout handling"""
        mocker.patch('requests.get', side_effect=requests.exceptions.Timeout())

        stats = self.api.get_video_stats('video_id')
        assert stats is None

    def test_get_video_stats_api_key_included(self, mocker):
        """Test API key is included in request"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'items': []}

        mock_get = mocker.patch('requests.get', return_value=mock_response)

        self.api.get_video_stats('video_id')

        call_args = mock_get.call_args
        assert call_args[1]['params']['key'] == self.api.api_key


@pytest.mark.integration
class TestYouTubeAPICircuitBreaker:
    """Test circuit breaker integration"""

    def test_circuit_breaker_initialized(self):
        """Test circuit breaker is properly initialized"""
        api = YouTubeAPI("AIzaSyD1234567890abcdefghijklmnop")

        assert api.circuit_breaker is not None
        assert api.circuit_breaker.failure_threshold == 3
        assert api.circuit_breaker.recovery_timeout == 120


@pytest.mark.integration
class TestYouTubeAPIRateLimiter:
    """Test rate limiter integration"""

    def test_rate_limiter_initialized(self):
        """Test rate limiter is properly initialized"""
        api = YouTubeAPI("AIzaSyD1234567890abcdefghijklmnop")

        assert api.rate_limiter is not None
        assert hasattr(api.rate_limiter, 'delays')
        assert hasattr(api.rate_limiter, 'wait')


@pytest.mark.integration
class TestYouTubeAPIValidation:
    """Test validation integration"""

    def test_api_key_validation_on_init(self):
        """Test API key validation during initialization"""
        # Valid key
        api = YouTubeAPI("AIzaSyD1234567890abcdefghijklmnop")
        assert api.api_key is not None

        # Invalid keys should raise ValidationError
        with pytest.raises(ValidationError):
            YouTubeAPI("your_api_key")

        with pytest.raises(ValidationError):
            YouTubeAPI("short")

    def test_query_sanitization_integration(self, mocker):
        """Test query sanitization in search flow"""
        api = YouTubeAPI("AIzaSyD1234567890abcdefghijklmnop")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'items': []}

        mock_get = mocker.patch('requests.get', return_value=mock_response)

        # Dangerous characters should be removed
        api.search_videos("AAPL; DROP TABLE--")

        # Query should be sanitized
        call_args = mock_get.call_args
        query = call_args[1]['params']['q']
        assert ';' not in query
        assert 'DROP' in query  # Alphanumeric kept
        assert 'AAPL' in query
