"""
Integration tests for 4chan /biz/ API
"""
import pytest
import requests
from unittest.mock import Mock
from qaht.data_sources.fourchan_api import FourChanBizAPI


class TestFourChanBizAPIInitialization:
    """Test 4chan API initialization"""

    def test_initialization(self):
        """Test API client initialization"""
        api = FourChanBizAPI()

        assert api.base_url == "https://a.4cdn.org/biz"
        assert api.circuit_breaker is not None
        assert api.circuit_breaker.failure_threshold == 3
        assert api.circuit_breaker.recovery_timeout == 300


class TestFourChanBizAPIGetCatalog:
    """Test catalog retrieval"""

    def setup_method(self):
        """Setup test instance"""
        self.api = FourChanBizAPI()

    def test_get_catalog_success(self, mocker):
        """Test successful catalog retrieval"""
        mock_catalog = [
            {
                'page': 1,
                'threads': [
                    {'no': 123, 'sub': 'AAPL Thread', 'com': 'Apple discussion'},
                    {'no': 124, 'sub': 'BTC pumping', 'com': 'Bitcoin to moon'}
                ]
            },
            {
                'page': 2,
                'threads': [
                    {'no': 125, 'sub': 'General', 'com': 'Market talk'}
                ]
            }
        ]

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_catalog
        mock_response.raise_for_status = Mock()

        mocker.patch('requests.get', return_value=mock_response)

        result = self.api.get_catalog()

        assert len(result) == 2
        assert result[0]['page'] == 1
        assert len(result[0]['threads']) == 2
        assert result[1]['page'] == 2

    def test_get_catalog_timeout(self, mocker):
        """Test catalog retrieval timeout"""
        mocker.patch('requests.get', side_effect=requests.exceptions.Timeout())

        result = self.api.get_catalog()

        # Should return default empty list
        assert result == []

    def test_get_catalog_http_error(self, mocker):
        """Test HTTP error handling"""
        mock_response = Mock()
        mock_response.status_code = 503
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError()

        mocker.patch('requests.get', return_value=mock_response)

        result = self.api.get_catalog()

        assert result == []

    def test_get_catalog_connection_error(self, mocker):
        """Test connection error handling"""
        mocker.patch('requests.get', side_effect=requests.exceptions.ConnectionError())

        result = self.api.get_catalog()

        assert result == []

    def test_get_catalog_timeout_parameter(self, mocker):
        """Test that timeout is set correctly"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()

        mock_get = mocker.patch('requests.get', return_value=mock_response)

        self.api.get_catalog()

        # Verify timeout was passed
        call_args = mock_get.call_args
        assert call_args[1]['timeout'] == 10


class TestFourChanBizAPISearchTicker:
    """Test ticker mention searching"""

    def setup_method(self):
        """Setup test instance"""
        self.api = FourChanBizAPI()

    def test_search_ticker_found_in_subject(self, mocker):
        """Test ticker found in thread subject"""
        mock_catalog = [
            {
                'threads': [
                    {'sub': 'AAPL is mooning!', 'com': 'Discussion'},
                    {'sub': 'AAPL to $200', 'com': 'Price target'},
                    {'sub': 'General', 'com': 'Market talk'}
                ]
            }
        ]

        mocker.patch.object(self.api, 'get_catalog', return_value=mock_catalog)

        count = self.api.search_ticker_mentions('AAPL')

        assert count == 2

    def test_search_ticker_found_in_comment(self, mocker):
        """Test ticker found in thread comment"""
        mock_catalog = [
            {
                'threads': [
                    {'sub': 'Market Discussion', 'com': 'TSLA looking good'},
                    {'sub': 'General', 'com': 'Buy TSLA now'},
                    {'sub': 'Daily Thread', 'com': 'Market updates'}
                ]
            }
        ]

        mocker.patch.object(self.api, 'get_catalog', return_value=mock_catalog)

        count = self.api.search_ticker_mentions('TSLA')

        assert count == 2

    def test_search_ticker_case_insensitive(self, mocker):
        """Test search is case insensitive"""
        mock_catalog = [
            {
                'threads': [
                    {'sub': 'aapl discussion', 'com': 'Lower case'},
                    {'sub': 'AAPL Thread', 'com': 'Upper case'},
                    {'sub': 'General', 'com': 'Aapl mention'}
                ]
            }
        ]

        mocker.patch.object(self.api, 'get_catalog', return_value=mock_catalog)

        # Search with lowercase
        count = self.api.search_ticker_mentions('aapl')
        assert count == 3

        # Should normalize to uppercase
        count = self.api.search_ticker_mentions('AAPL')
        assert count == 3

    def test_search_ticker_not_found(self, mocker):
        """Test ticker not found"""
        mock_catalog = [
            {
                'threads': [
                    {'sub': 'General Discussion', 'com': 'Market talk'},
                    {'sub': 'Daily Thread', 'com': 'Updates'}
                ]
            }
        ]

        mocker.patch.object(self.api, 'get_catalog', return_value=mock_catalog)

        count = self.api.search_ticker_mentions('NONEXISTENT')

        assert count == 0

    def test_search_ticker_validation_error(self, mocker):
        """Test invalid ticker returns 0"""
        mocker.patch.object(self.api, 'get_catalog')

        # Invalid ticker with dangerous characters
        count = self.api.search_ticker_mentions("'; DROP TABLE--")

        assert count == 0
        # get_catalog should not be called for invalid ticker
        assert not self.api.get_catalog.called

    def test_search_ticker_empty_catalog(self, mocker):
        """Test search with empty catalog"""
        mocker.patch.object(self.api, 'get_catalog', return_value=[])

        count = self.api.search_ticker_mentions('AAPL')

        assert count == 0

    def test_search_ticker_missing_fields(self, mocker):
        """Test search with missing subject/comment fields"""
        mock_catalog = [
            {
                'threads': [
                    {'no': 123},  # Missing sub and com
                    {'sub': 'AAPL Thread'},  # Missing com
                    {'com': 'AAPL discussion'}  # Missing sub
                ]
            }
        ]

        mocker.patch.object(self.api, 'get_catalog', return_value=mock_catalog)

        count = self.api.search_ticker_mentions('AAPL')

        # Should find in sub and com despite missing fields
        assert count == 2

    def test_search_ticker_multiple_pages(self, mocker):
        """Test search across multiple catalog pages"""
        mock_catalog = [
            {
                'threads': [
                    {'sub': 'BTC Thread', 'com': 'Bitcoin'},
                    {'sub': 'General', 'com': 'BTC mention'}
                ]
            },
            {
                'threads': [
                    {'sub': 'Daily', 'com': 'BTC to moon'},
                    {'sub': 'BTC Analysis', 'com': 'Technical'}
                ]
            }
        ]

        mocker.patch.object(self.api, 'get_catalog', return_value=mock_catalog)

        count = self.api.search_ticker_mentions('BTC')

        # Should count across all pages
        assert count == 4

    def test_search_crypto_ticker(self, mocker):
        """Test search with crypto ticker format"""
        mock_catalog = [
            {
                'threads': [
                    {'sub': 'BTC.X pumping', 'com': 'Discussion'},
                    {'sub': 'General', 'com': 'BTC.X analysis'}
                ]
            }
        ]

        mocker.patch.object(self.api, 'get_catalog', return_value=mock_catalog)

        count = self.api.search_ticker_mentions('BTC.X')

        assert count == 2


@pytest.mark.integration
class TestFourChanBizAPICircuitBreaker:
    """Test circuit breaker integration"""

    def test_circuit_breaker_initialized(self):
        """Test circuit breaker is properly initialized"""
        api = FourChanBizAPI()

        assert api.circuit_breaker is not None
        assert api.circuit_breaker.failure_threshold == 3
        assert api.circuit_breaker.recovery_timeout == 300  # 5 minutes


@pytest.mark.integration
class TestFourChanBizAPIValidation:
    """Test validation integration"""

    def setup_method(self):
        """Setup test instance"""
        self.api = FourChanBizAPI()

    def test_ticker_validation_in_search(self, mocker):
        """Test ticker validation in search flow"""
        mocker.patch.object(self.api, 'get_catalog')

        # Valid ticker - should proceed
        self.api.search_ticker_mentions('AAPL')
        assert self.api.get_catalog.called

        # Reset mock
        self.api.get_catalog.reset_mock()

        # Invalid ticker - should not call get_catalog
        count = self.api.search_ticker_mentions("'; DROP--")
        assert count == 0
        assert not self.api.get_catalog.called


@pytest.mark.integration
class TestFourChanBizAPIErrorScenarios:
    """Test comprehensive error scenarios"""

    def setup_method(self):
        """Setup test instance"""
        self.api = FourChanBizAPI()

    def test_network_failure_scenarios(self, mocker):
        """Test various network failure scenarios"""
        # DNS resolution failure
        mocker.patch('requests.get', side_effect=requests.exceptions.ConnectionError("DNS lookup failed"))
        result = self.api.get_catalog()
        assert result == []

        # Connection timeout
        mocker.patch('requests.get', side_effect=requests.exceptions.Timeout("Connection timeout"))
        result = self.api.get_catalog()
        assert result == []

        # SSL error
        mocker.patch('requests.get', side_effect=requests.exceptions.SSLError("SSL certificate error"))
        result = self.api.get_catalog()
        assert result == []

    def test_api_error_responses(self, mocker):
        """Test various API error responses"""
        # 500 Internal Server Error
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError()
        mocker.patch('requests.get', return_value=mock_response)
        result = self.api.get_catalog()
        assert result == []

        # 503 Service Unavailable
        mock_response.status_code = 503
        result = self.api.get_catalog()
        assert result == []

        # 429 Rate Limit (shouldn't happen with 4chan but test anyway)
        mock_response.status_code = 429
        result = self.api.get_catalog()
        assert result == []

    def test_malformed_json_response(self, mocker):
        """Test handling of malformed JSON"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.raise_for_status = Mock()

        mocker.patch('requests.get', return_value=mock_response)

        result = self.api.get_catalog()
        assert result == []
