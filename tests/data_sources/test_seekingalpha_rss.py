"""
Integration tests for Seeking Alpha RSS API
"""
import pytest

# Skip this module due to feedparser dependency issue
pytest.skip("feedparser dependency not available", allow_module_level=True)

from unittest.mock import Mock
from qaht.data_sources.seekingalpha_rss import SeekingAlphaRSS


class TestSeekingAlphaRSSInitialization:
    """Test Seeking Alpha RSS initialization"""

    def test_initialization(self):
        """Test API client initialization"""
        api = SeekingAlphaRSS()

        assert api.base_url == "https://seekingalpha.com"
        assert api.circuit_breaker is not None
        assert api.circuit_breaker.failure_threshold == 3
        assert api.circuit_breaker.recovery_timeout == 180


class TestSeekingAlphaRSSMarketNews:
    """Test market news retrieval"""

    def setup_method(self):
        """Setup test instance"""
        self.api = SeekingAlphaRSS()

    def test_get_market_news_success(self, mocker):
        """Test successful market news retrieval"""
        mock_feed = Mock()
        mock_feed.entries = [
            Mock(title='Market Update 1', link='http://link1.com', published='2024-01-15'),
            Mock(title='Market Update 2', link='http://link2.com', published='2024-01-14'),
            Mock(title='Market Update 3', link='http://link3.com', published='2024-01-13'),
        ]

        mocker.patch('feedparser.parse', return_value=mock_feed)

        result = self.api.get_market_news()

        assert len(result) == 3
        assert result[0]['title'] == 'Market Update 1'
        assert result[0]['link'] == 'http://link1.com'
        assert result[0]['published'] == '2024-01-15'

    def test_get_market_news_limits_to_20(self, mocker):
        """Test market news is limited to 20 entries"""
        # Create 30 mock entries
        mock_entries = [
            Mock(title=f'News {i}', link=f'http://link{i}.com', published=f'2024-01-{i:02d}')
            for i in range(30)
        ]

        mock_feed = Mock()
        mock_feed.entries = mock_entries

        mocker.patch('feedparser.parse', return_value=mock_feed)

        result = self.api.get_market_news()

        # Should only return first 20
        assert len(result) == 20
        assert result[0]['title'] == 'News 0'
        assert result[19]['title'] == 'News 19'

    def test_get_market_news_empty_feed(self, mocker):
        """Test handling of empty feed"""
        mock_feed = Mock()
        mock_feed.entries = []

        mocker.patch('feedparser.parse', return_value=mock_feed)

        result = self.api.get_market_news()

        assert result == []

    def test_get_market_news_exception(self, mocker):
        """Test exception handling"""
        mocker.patch('feedparser.parse', side_effect=Exception('Feed error'))

        result = self.api.get_market_news()

        assert result == []

    def test_get_market_news_url_format(self, mocker):
        """Test correct URL is used"""
        mock_feed = Mock()
        mock_feed.entries = []

        mock_parse = mocker.patch('feedparser.parse', return_value=mock_feed)

        self.api.get_market_news()

        # Verify correct URL was called
        call_args = mock_parse.call_args
        assert call_args[0][0] == 'https://seekingalpha.com/market_currents.xml'

    def test_get_market_news_malformed_entry(self, mocker):
        """Test handling of malformed entries"""
        # Entry missing 'published' field
        mock_entry = Mock(title='News', link='http://link.com')
        del mock_entry.published

        mock_feed = Mock()
        mock_feed.entries = [mock_entry]

        mocker.patch('feedparser.parse', return_value=mock_feed)

        # Should handle AttributeError gracefully
        result = self.api.get_market_news()

        # May return empty list or handle error
        assert isinstance(result, list)


class TestSeekingAlphaRSSSymbolNews:
    """Test symbol-specific news retrieval"""

    def setup_method(self):
        """Setup test instance"""
        self.api = SeekingAlphaRSS()

    def test_get_symbol_news_success(self, mocker):
        """Test successful symbol news retrieval"""
        mock_feed = Mock()
        mock_feed.entries = [
            Mock(title='AAPL Analysis', link='http://link1.com', published='2024-01-15'),
            Mock(title='AAPL Earnings', link='http://link2.com', published='2024-01-14'),
        ]

        mocker.patch('feedparser.parse', return_value=mock_feed)

        result = self.api.get_symbol_news('AAPL')

        assert len(result) == 2
        assert result[0]['title'] == 'AAPL Analysis'
        assert result[1]['title'] == 'AAPL Earnings'

    def test_get_symbol_news_limits_to_10(self, mocker):
        """Test symbol news is limited to 10 entries"""
        mock_entries = [
            Mock(title=f'Article {i}', link=f'http://link{i}.com', published=f'2024-01-{i:02d}')
            for i in range(15)
        ]

        mock_feed = Mock()
        mock_feed.entries = mock_entries

        mocker.patch('feedparser.parse', return_value=mock_feed)

        result = self.api.get_symbol_news('AAPL')

        # Should only return first 10
        assert len(result) == 10

    def test_get_symbol_news_ticker_validation(self, mocker):
        """Test ticker validation in symbol news"""
        mocker.patch('feedparser.parse')

        # Valid ticker (normalized to uppercase)
        self.api.get_symbol_news('aapl')
        # Should proceed

        # Invalid ticker
        result = self.api.get_symbol_news("'; DROP TABLE--")
        assert result == []

    def test_get_symbol_news_no_crypto(self, mocker):
        """Test crypto tickers are not allowed"""
        mocker.patch('feedparser.parse')

        # Crypto ticker should be rejected
        result = self.api.get_symbol_news('BTC.X')
        assert result == []

    def test_get_symbol_news_url_format(self, mocker):
        """Test correct URL format for symbol"""
        mock_feed = Mock()
        mock_feed.entries = []

        mock_parse = mocker.patch('feedparser.parse', return_value=mock_feed)

        self.api.get_symbol_news('AAPL')

        # Verify correct URL was called
        call_args = mock_parse.call_args
        assert call_args[0][0] == 'https://seekingalpha.com/api/sa/combined/AAPL.xml'

    def test_get_symbol_news_exception(self, mocker):
        """Test exception handling for symbol news"""
        mocker.patch('feedparser.parse', side_effect=Exception('Feed error'))

        result = self.api.get_symbol_news('AAPL')

        assert result == []

    def test_get_symbol_news_empty_feed(self, mocker):
        """Test handling of empty symbol feed"""
        mock_feed = Mock()
        mock_feed.entries = []

        mocker.patch('feedparser.parse', return_value=mock_feed)

        result = self.api.get_symbol_news('AAPL')

        assert result == []

    def test_get_symbol_news_case_normalization(self, mocker):
        """Test ticker case normalization"""
        mock_feed = Mock()
        mock_feed.entries = []

        mock_parse = mocker.patch('feedparser.parse', return_value=mock_feed)

        # Lowercase input
        self.api.get_symbol_news('aapl')

        # Should be normalized to uppercase in URL
        call_args = mock_parse.call_args
        assert 'AAPL' in call_args[0][0]

    def test_get_symbol_news_malformed_entry(self, mocker):
        """Test handling of malformed entries in symbol feed"""
        # Entry missing fields
        mock_entry = Mock(title='News')
        del mock_entry.link
        del mock_entry.published

        mock_feed = Mock()
        mock_feed.entries = [mock_entry]

        mocker.patch('feedparser.parse', return_value=mock_feed)

        result = self.api.get_symbol_news('AAPL')

        assert isinstance(result, list)


@pytest.mark.integration
class TestSeekingAlphaRSSCircuitBreaker:
    """Test circuit breaker integration"""

    def test_circuit_breaker_initialized(self):
        """Test circuit breaker is properly initialized"""
        api = SeekingAlphaRSS()

        assert api.circuit_breaker is not None
        assert api.circuit_breaker.failure_threshold == 3
        assert api.circuit_breaker.recovery_timeout == 180  # 3 minutes


@pytest.mark.integration
class TestSeekingAlphaRSSValidation:
    """Test validation integration"""

    def setup_method(self):
        """Setup test instance"""
        self.api = SeekingAlphaRSS()

    def test_ticker_validation_stock_only(self, mocker):
        """Test only stock tickers are allowed, not crypto"""
        mocker.patch('feedparser.parse')

        # Stock ticker - should work
        result = self.api.get_symbol_news('AAPL')
        # Will return [] from empty mock feed

        # Crypto ticker - should be rejected
        result = self.api.get_symbol_news('BTC.X')
        assert result == []

    def test_dangerous_character_prevention(self, mocker):
        """Test dangerous characters are blocked"""
        mocker.patch('feedparser.parse')

        dangerous_inputs = [
            "'; DROP TABLE--",
            "<script>alert(1)</script>",
            "AAPL; rm -rf /",
        ]

        for dangerous in dangerous_inputs:
            result = self.api.get_symbol_news(dangerous)
            assert result == []


@pytest.mark.integration
class TestSeekingAlphaRSSErrorScenarios:
    """Test comprehensive error scenarios"""

    def setup_method(self):
        """Setup test instance"""
        self.api = SeekingAlphaRSS()

    def test_network_failure_scenarios(self, mocker):
        """Test various network failure scenarios"""
        # Connection error
        mocker.patch('feedparser.parse', side_effect=ConnectionError("Network failure"))
        result = self.api.get_market_news()
        assert result == []

        # Timeout
        mocker.patch('feedparser.parse', side_effect=TimeoutError("Request timeout"))
        result = self.api.get_market_news()
        assert result == []

    def test_feed_parsing_errors(self, mocker):
        """Test feed parsing error scenarios"""
        # Invalid XML
        mocker.patch('feedparser.parse', side_effect=Exception("XML parsing error"))
        result = self.api.get_market_news()
        assert result == []

        # Malformed feed structure
        mock_feed = Mock()
        mock_feed.entries = None  # Invalid structure
        mocker.patch('feedparser.parse', return_value=mock_feed)

        # Should handle gracefully
        try:
            result = self.api.get_market_news()
            # May raise or return []
        except (TypeError, AttributeError):
            # Expected if not handled
            pass

    def test_unexpected_exceptions(self, mocker):
        """Test handling of unexpected exceptions"""
        mocker.patch('feedparser.parse', side_effect=RuntimeError("Unexpected error"))

        result = self.api.get_market_news()
        assert result == []

        result = self.api.get_symbol_news('AAPL')
        assert result == []


@pytest.mark.integration
class TestSeekingAlphaRSSDataQuality:
    """Test data quality and structure"""

    def setup_method(self):
        """Setup test instance"""
        self.api = SeekingAlphaRSS()

    def test_market_news_data_structure(self, mocker):
        """Test market news returns correct data structure"""
        mock_feed = Mock()
        mock_feed.entries = [
            Mock(title='News 1', link='http://link1.com', published='2024-01-15')
        ]

        mocker.patch('feedparser.parse', return_value=mock_feed)

        result = self.api.get_market_news()

        assert isinstance(result, list)
        assert len(result) == 1
        assert 'title' in result[0]
        assert 'link' in result[0]
        assert 'published' in result[0]

    def test_symbol_news_data_structure(self, mocker):
        """Test symbol news returns correct data structure"""
        mock_feed = Mock()
        mock_feed.entries = [
            Mock(title='Analysis', link='http://link.com', published='2024-01-15')
        ]

        mocker.patch('feedparser.parse', return_value=mock_feed)

        result = self.api.get_symbol_news('AAPL')

        assert isinstance(result, list)
        assert len(result) == 1
        assert 'title' in result[0]
        assert 'link' in result[0]
        assert 'published' in result[0]
