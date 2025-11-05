"""
Integration tests for LunarCrush API
"""
import pytest
import requests
from unittest.mock import Mock, patch
from qaht.data_sources.lunarcrush_api import LunarCrushAPI
from qaht.utils.validation import ValidationError


class TestLunarCrushAPIInitialization:
    """Test LunarCrush API initialization and validation"""

    def test_valid_api_key(self):
        """Test initialization with valid API key"""
        api_key = "lc_1234567890abcdefghijklmnop"
        api = LunarCrushAPI(api_key)

        assert api.api_key == api_key
        assert api.base_url == "https://lunarcrush.com/api3"
        assert api.circuit_breaker is not None
        assert api.rate_limiter is not None

    def test_invalid_api_key_too_short(self):
        """Test initialization with too short API key"""
        with pytest.raises(ValidationError, match="too short"):
            LunarCrushAPI("short")

    def test_invalid_api_key_placeholder(self):
        """Test initialization with placeholder API key"""
        with pytest.raises(ValidationError, match="not configured"):
            LunarCrushAPI("your_key_here")

    def test_empty_api_key(self):
        """Test initialization with empty API key"""
        with pytest.raises(ValidationError, match="non-empty string"):
            LunarCrushAPI("")

    def test_none_api_key(self):
        """Test initialization with None API key"""
        with pytest.raises(ValidationError, match="non-empty string"):
            LunarCrushAPI(None)

    def test_api_key_whitespace_stripped(self):
        """Test API key whitespace handling"""
        api_key = "  lc_1234567890abcdefghijklmnop  "
        api = LunarCrushAPI(api_key)
        assert api.api_key == "lc_1234567890abcdefghijklmnop"


class TestLunarCrushAPIMarketData:
    """Test market data functionality"""

    def setup_method(self):
        """Setup test instance"""
        self.api_key = "lc_1234567890abcdefghijklmnop"
        self.api = LunarCrushAPI(self.api_key)

    def test_get_market_data_success(self, mocker):
        """Test successful market data retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'data': {
                'symbol': 'BTC',
                'name': 'Bitcoin',
                'price': 45000.50,
                'price_change_24h': 2.5,
                'volume_24h': 25000000000,
                'market_cap': 900000000000,
                'social': {
                    'social_score': 85.5,
                    'social_volume': 125000,
                    'social_dominance': 42.3,
                    'sentiment': 'bullish'
                },
                'galaxy_score': 72.5,
                'alt_rank': 1
            }
        }

        mocker.patch('requests.get', return_value=mock_response)

        result = self.api.get_market_data('BTC')

        assert result is not None
        assert 'data' in result
        assert result['data']['symbol'] == 'BTC'
        assert result['data']['price'] == 45000.50

    def test_get_market_data_ticker_validation(self, mocker):
        """Test ticker validation in get_market_data"""
        # Mock to prevent actual API call
        mocker.patch('requests.get')

        # Valid ticker should be normalized
        self.api.get_market_data('btc')
        # Should normalize to 'BTC'

        # Invalid ticker should return empty dict
        result = self.api.get_market_data("'; DROP TABLE--")
        assert result == {}

    def test_get_market_data_crypto_ticker(self, mocker):
        """Test crypto ticker with .X suffix"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': {'symbol': 'BTC.X'}}

        mocker.patch('requests.get', return_value=mock_response)

        result = self.api.get_market_data('BTC.X')
        assert result is not None

    def test_get_market_data_http_error(self, mocker):
        """Test HTTP error handling"""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError()

        mocker.patch('requests.get', return_value=mock_response)

        result = self.api.get_market_data('BTC')
        assert result == {}

    def test_get_market_data_timeout(self, mocker):
        """Test timeout error handling"""
        mocker.patch('requests.get', side_effect=requests.exceptions.Timeout())

        result = self.api.get_market_data('BTC')
        assert result == {}

    def test_get_market_data_connection_error(self, mocker):
        """Test connection error handling"""
        mocker.patch('requests.get', side_effect=requests.exceptions.ConnectionError())

        result = self.api.get_market_data('BTC')
        assert result == {}

    def test_get_market_data_404_not_found(self, mocker):
        """Test 404 error for unknown symbol"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)

        mocker.patch('requests.get', return_value=mock_response)

        result = self.api.get_market_data('UNKNOWNCOIN')
        assert result == {}

    def test_get_market_data_401_unauthorized(self, mocker):
        """Test 401 error for invalid API key"""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)

        mocker.patch('requests.get', return_value=mock_response)

        result = self.api.get_market_data('BTC')
        assert result == {}

    def test_get_market_data_429_rate_limit(self, mocker):
        """Test 429 rate limit error"""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)

        mocker.patch('requests.get', return_value=mock_response)

        result = self.api.get_market_data('BTC')
        assert result == {}

    def test_get_market_data_api_key_in_header(self, mocker):
        """Test API key is included in request header"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': {}}

        mock_get = mocker.patch('requests.get', return_value=mock_response)

        self.api.get_market_data('BTC')

        call_args = mock_get.call_args
        headers = call_args[1]['headers']
        assert 'Authorization' in headers
        assert headers['Authorization'] == f'Bearer {self.api_key}'

    def test_get_market_data_correct_url(self, mocker):
        """Test correct API URL is used"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': {}}

        mock_get = mocker.patch('requests.get', return_value=mock_response)

        self.api.get_market_data('BTC')

        call_args = mock_get.call_args
        url = call_args[0][0]
        assert url == f"{self.api.base_url}/coins/BTC/v1"

    def test_get_market_data_json_parse_error(self, mocker):
        """Test JSON parsing error handling"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")

        mocker.patch('requests.get', return_value=mock_response)

        result = self.api.get_market_data('BTC')
        assert result == {}

    def test_get_market_data_empty_response(self, mocker):
        """Test empty response handling"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        mocker.patch('requests.get', return_value=mock_response)

        result = self.api.get_market_data('BTC')
        assert result == {}

    def test_get_market_data_partial_data(self, mocker):
        """Test handling of partial data"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'data': {
                'symbol': 'ETH',
                'price': 3000.00
                # Missing other fields
            }
        }

        mocker.patch('requests.get', return_value=mock_response)

        result = self.api.get_market_data('ETH')
        assert result is not None
        assert result['data']['symbol'] == 'ETH'
        assert result['data']['price'] == 3000.00


@pytest.mark.integration
class TestLunarCrushAPICircuitBreaker:
    """Test circuit breaker integration"""

    def test_circuit_breaker_initialized(self):
        """Test circuit breaker is properly initialized"""
        api = LunarCrushAPI("lc_1234567890abcdefghijklmnop")

        assert api.circuit_breaker is not None
        assert api.circuit_breaker.failure_threshold == 3
        assert api.circuit_breaker.recovery_timeout == 120


@pytest.mark.integration
class TestLunarCrushAPIRateLimiter:
    """Test rate limiter integration"""

    def test_rate_limiter_initialized(self):
        """Test rate limiter is properly initialized"""
        api = LunarCrushAPI("lc_1234567890abcdefghijklmnop")

        assert api.rate_limiter is not None
        assert hasattr(api.rate_limiter, 'delays')
        assert hasattr(api.rate_limiter, 'wait')


@pytest.mark.integration
class TestLunarCrushAPIValidation:
    """Test validation integration"""

    def test_api_key_validation_on_init(self):
        """Test API key validation during initialization"""
        # Valid key
        api = LunarCrushAPI("lc_1234567890abcdefghijklmnop")
        assert api.api_key is not None

        # Invalid keys should raise ValidationError
        with pytest.raises(ValidationError):
            LunarCrushAPI("your_api_key")

        with pytest.raises(ValidationError):
            LunarCrushAPI("short")

        with pytest.raises(ValidationError):
            LunarCrushAPI("")

    def test_ticker_validation_integration(self, mocker):
        """Test ticker validation in market data flow"""
        api = LunarCrushAPI("lc_1234567890abcdefghijklmnop")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': {}}

        mocker.patch('requests.get', return_value=mock_response)

        # Valid crypto tickers
        result = api.get_market_data('BTC')
        assert result is not None

        result = api.get_market_data('ETH')
        assert result is not None

        # Invalid tickers should return empty dict
        result = api.get_market_data("'; DROP--")
        assert result == {}

        result = api.get_market_data("<script>alert(1)</script>")
        assert result == {}

    def test_case_normalization(self, mocker):
        """Test ticker case normalization"""
        api = LunarCrushAPI("lc_1234567890abcdefghijklmnop")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': {}}

        mock_get = mocker.patch('requests.get', return_value=mock_response)

        # Lowercase should be normalized to uppercase
        api.get_market_data('btc')

        call_args = mock_get.call_args
        url = call_args[0][0]
        assert 'BTC' in url


@pytest.mark.integration
class TestLunarCrushAPIErrorScenarios:
    """Test comprehensive error scenarios"""

    def setup_method(self):
        """Setup test instance"""
        self.api = LunarCrushAPI("lc_1234567890abcdefghijklmnop")

    def test_network_failure_scenarios(self, mocker):
        """Test various network failure scenarios"""
        # DNS resolution failure
        mocker.patch('requests.get', side_effect=requests.exceptions.ConnectionError("DNS lookup failed"))
        result = self.api.get_market_data('BTC')
        assert result == {}

        # Connection timeout
        mocker.patch('requests.get', side_effect=requests.exceptions.Timeout("Connection timeout"))
        result = self.api.get_market_data('BTC')
        assert result == {}

        # SSL error
        mocker.patch('requests.get', side_effect=requests.exceptions.SSLError("SSL certificate error"))
        result = self.api.get_market_data('BTC')
        assert result == {}

    def test_api_error_responses(self, mocker):
        """Test various API error responses"""
        # 500 Internal Server Error
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)
        mocker.patch('requests.get', return_value=mock_response)
        result = self.api.get_market_data('BTC')
        assert result == {}

        # 503 Service Unavailable
        mock_response.status_code = 503
        result = self.api.get_market_data('BTC')
        assert result == {}

    def test_unexpected_exceptions(self, mocker):
        """Test handling of unexpected exceptions"""
        mocker.patch('requests.get', side_effect=RuntimeError("Unexpected error"))

        result = self.api.get_market_data('BTC')
        assert result == {}
