"""
Integration tests for StockTwits API
"""
import pytest
import requests
from unittest.mock import Mock, patch
from qaht.data_sources.stocktwits_api import StockTwitsAPI
from qaht.utils.validation import ValidationError


class TestStockTwitsAPIIntegration:
    """Integration tests for StockTwits API client"""

    def setup_method(self):
        """Setup test instance"""
        self.api = StockTwitsAPI()

    def test_initialization(self):
        """Test API client initialization"""
        assert self.api.base_url == "https://api.stocktwits.com/api/2"
        assert self.api.circuit_breaker is not None
        assert self.api.rate_limiter is not None

    def test_get_stream_success(self, mocker):
        """Test successful stream retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'messages': [
                {
                    'id': 1,
                    'body': 'Bullish on AAPL!',
                    'entities': {
                        'sentiment': {'basic': 'Bullish'}
                    }
                },
                {
                    'id': 2,
                    'body': 'Bearish outlook',
                    'entities': {
                        'sentiment': {'basic': 'Bearish'}
                    }
                },
                {
                    'id': 3,
                    'body': 'AAPL looking good',
                    'entities': {
                        'sentiment': {'basic': 'Bullish'}
                    }
                }
            ]
        }

        mocker.patch.object(self.api.session, 'get', return_value=mock_response)

        result = self.api.get_stream('AAPL')

        assert result['symbol'] == 'AAPL'
        assert result['message_count'] == 3
        assert result['bullish_count'] == 2
        assert result['bearish_count'] == 1
        assert result['sentiment_ratio'] == pytest.approx(2/3, rel=0.01)
        assert result['sentiment_label'] == 'BULLISH'

    def test_get_stream_ticker_validation(self, mocker):
        """Test ticker validation in get_stream"""
        # Mock session to prevent actual API call
        mocker.patch.object(self.api.session, 'get')

        # Valid ticker should be normalized
        result = self.api.get_stream('aapl')
        assert result['symbol'] == 'AAPL'

        # Invalid ticker should return empty result
        result = self.api.get_stream("'; DROP TABLE--")
        assert result['message_count'] == 0
        assert result['sentiment_label'] == 'UNKNOWN'

    def test_get_stream_404_error(self, mocker):
        """Test 404 error handling"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)

        mocker.patch.object(self.api.session, 'get', return_value=mock_response)

        result = self.api.get_stream('INVALID')

        assert result['symbol'] == 'INVALID'
        assert result['message_count'] == 0
        assert result['sentiment_label'] == 'UNKNOWN'

    def test_get_stream_network_error(self, mocker):
        """Test network error handling"""
        mocker.patch.object(
            self.api.session,
            'get',
            side_effect=requests.exceptions.ConnectionError("Network error")
        )

        result = self.api.get_stream('AAPL')

        assert result['symbol'] == 'AAPL'
        assert result['message_count'] == 0
        assert result['sentiment_label'] == 'UNKNOWN'

    def test_get_stream_no_sentiment_data(self, mocker):
        """Test stream with messages but no sentiment"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'messages': [
                {'id': 1, 'body': 'Message without sentiment'},
                {'id': 2, 'body': 'Another message'}
            ]
        }

        mocker.patch.object(self.api.session, 'get', return_value=mock_response)

        result = self.api.get_stream('AAPL')

        assert result['message_count'] == 2
        assert result['bullish_count'] == 0
        assert result['bearish_count'] == 0
        assert result['sentiment_ratio'] == 0.5  # Neutral when no sentiment
        assert result['sentiment_label'] == 'NEUTRAL'

    def test_get_trending_success(self, mocker):
        """Test successful trending symbols retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'symbols': [
                {'symbol': 'AAPL', 'title': 'Apple Inc.', 'watchlist_count': 1000},
                {'symbol': 'TSLA', 'title': 'Tesla Inc.', 'watchlist_count': 950},
                {'symbol': 'BTC.X', 'title': 'Bitcoin', 'watchlist_count': 800}
            ]
        }

        mocker.patch.object(self.api.session, 'get', return_value=mock_response)

        result = self.api.get_trending(limit=10)

        assert len(result) == 3
        assert result[0]['symbol'] == 'AAPL'
        assert result[0]['type'] == 'STOCK'
        assert result[2]['symbol'] == 'BTC.X'
        assert result[2]['type'] == 'CRYPTO'

    def test_get_trending_error(self, mocker):
        """Test trending symbols error handling"""
        mocker.patch.object(
            self.api.session,
            'get',
            side_effect=requests.exceptions.Timeout()
        )

        result = self.api.get_trending()
        assert result == []

    def test_get_watchlist_count_success(self, mocker):
        """Test successful watchlist count retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'symbol': {
                'symbol': 'AAPL',
                'watchlist_count': 1500
            }
        }

        mocker.patch.object(self.api.session, 'get', return_value=mock_response)

        count = self.api.get_watchlist_count('AAPL')
        assert count == 1500

    def test_get_watchlist_count_validation(self, mocker):
        """Test watchlist count with validation"""
        mocker.patch.object(self.api.session, 'get')

        # Invalid ticker should return 0
        count = self.api.get_watchlist_count("'; DROP--")
        assert count == 0

    def test_get_watchlist_count_error(self, mocker):
        """Test watchlist count error handling"""
        mocker.patch.object(
            self.api.session,
            'get',
            side_effect=requests.exceptions.HTTPError()
        )

        count = self.api.get_watchlist_count('AAPL')
        assert count == 0

    def test_batch_sentiment_success(self, mocker):
        """Test batch sentiment retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'messages': [
                {'id': 1, 'entities': {'sentiment': {'basic': 'Bullish'}}}
            ]
        }

        mocker.patch.object(self.api.session, 'get', return_value=mock_response)
        mocker.patch('time.sleep')  # Don't actually sleep

        symbols = ['AAPL', 'MSFT', 'GOOGL']
        results = self.api.batch_sentiment(symbols, delay=0.1)

        assert len(results) == 3
        assert 'AAPL' in results
        assert 'MSFT' in results
        assert 'GOOGL' in results

    def test_batch_sentiment_rate_limiting(self, mocker):
        """Test batch sentiment with rate limiting"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'messages': []}

        mocker.patch.object(self.api.session, 'get', return_value=mock_response)
        mock_sleep = mocker.patch('time.sleep')

        # Small batch (<=10) should use fast delay
        symbols = ['AAPL', 'MSFT', 'GOOGL']
        self.api.batch_sentiment(symbols, delay=2.0)

        # Should sleep between requests
        assert mock_sleep.call_count == 2  # len(symbols) - 1

        # Large batch (>10) should use adaptive delay
        mock_sleep.reset_mock()
        large_symbols = [f'SYM{i}' for i in range(15)]
        self.api.batch_sentiment(large_symbols, delay=2.0)

        # Should sleep with adaptive delay (18s for large batches)
        assert mock_sleep.call_count == 14  # len(symbols) - 1

    def test_sentiment_ratio_calculation(self, mocker):
        """Test sentiment ratio edge cases"""
        mock_response = Mock()
        mock_response.status_code = 200

        # All bullish
        mock_response.json.return_value = {
            'messages': [
                {'id': 1, 'entities': {'sentiment': {'basic': 'Bullish'}}},
                {'id': 2, 'entities': {'sentiment': {'basic': 'Bullish'}}}
            ]
        }
        mocker.patch.object(self.api.session, 'get', return_value=mock_response)
        result = self.api.get_stream('AAPL')
        assert result['sentiment_ratio'] == 1.0
        assert result['sentiment_label'] == 'BULLISH'

        # All bearish
        mock_response.json.return_value = {
            'messages': [
                {'id': 1, 'entities': {'sentiment': {'basic': 'Bearish'}}},
                {'id': 2, 'entities': {'sentiment': {'basic': 'Bearish'}}}
            ]
        }
        result = self.api.get_stream('AAPL')
        assert result['sentiment_ratio'] == 0.0
        assert result['sentiment_label'] == 'BEARISH'

        # Exactly neutral
        mock_response.json.return_value = {
            'messages': [
                {'id': 1, 'entities': {'sentiment': {'basic': 'Bullish'}}},
                {'id': 2, 'entities': {'sentiment': {'basic': 'Bearish'}}}
            ]
        }
        result = self.api.get_stream('AAPL')
        assert result['sentiment_ratio'] == 0.5
        assert result['sentiment_label'] == 'NEUTRAL'


@pytest.mark.integration
class TestStockTwitsAPICircuitBreaker:
    """Test circuit breaker integration"""

    def setup_method(self):
        """Setup test instance"""
        self.api = StockTwitsAPI()

    def test_circuit_breaker_exists(self):
        """Test circuit breaker is initialized"""
        assert self.api.circuit_breaker is not None
        assert self.api.circuit_breaker.failure_threshold == 5
        assert self.api.circuit_breaker.recovery_timeout == 180


@pytest.mark.integration
class TestStockTwitsAPIRateLimiter:
    """Test rate limiter integration"""

    def setup_method(self):
        """Setup test instance"""
        self.api = StockTwitsAPI()

    def test_rate_limiter_exists(self):
        """Test rate limiter is initialized"""
        assert self.api.rate_limiter is not None
        assert hasattr(self.api.rate_limiter, 'delays')
        assert hasattr(self.api.rate_limiter, 'wait')
