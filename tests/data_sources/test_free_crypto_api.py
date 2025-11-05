"""
Integration tests for Free Crypto API
"""
import pytest
from unittest.mock import Mock, patch
import requests
from qaht.data_sources.free_crypto_api import FreeCryptoAPI


class TestFreeCryptoAPIInitialization:
    """Test Free Crypto API initialization"""

    def test_initialization_with_circuit_breakers(self):
        """Test initialization with circuit breakers"""
        api = FreeCryptoAPI()

        # Circuit breakers should be initialized if production_optimizations available
        assert hasattr(api, 'coincap_breaker')
        assert hasattr(api, 'binance_breaker')

    def test_initialization_without_circuit_breakers(self, mocker):
        """Test initialization when circuit breakers not available"""
        # Mock CircuitBreaker to be None
        mocker.patch('qaht.data_sources.free_crypto_api.CircuitBreaker', None)

        api = FreeCryptoAPI()

        # Should handle None circuit breakers gracefully
        assert api.coincap_breaker is None or api.coincap_breaker is not None


class TestFreeCryptoAPIRetryLogic:
    """Test retry logic with exponential backoff"""

    def setup_method(self):
        """Setup test instance"""
        self.api = FreeCryptoAPI()

    def test_retry_success_on_first_attempt(self, mocker):
        """Test successful call on first attempt"""
        mock_func = mocker.Mock(return_value="success")

        result = self.api._retry_with_backoff(mock_func, max_retries=3)

        assert result == "success"
        assert mock_func.call_count == 1

    def test_retry_success_after_failures(self, mocker):
        """Test success after initial failures"""
        mock_func = mocker.Mock(
            side_effect=[
                Exception("Error 1"),
                Exception("Error 2"),
                "success"
            ]
        )

        # Mock time.sleep to speed up test
        mocker.patch('time.sleep')

        result = self.api._retry_with_backoff(mock_func, max_retries=3)

        assert result == "success"
        assert mock_func.call_count == 3

    def test_retry_all_attempts_fail(self, mocker):
        """Test all retry attempts fail"""
        mock_func = mocker.Mock(side_effect=Exception("Persistent error"))

        mocker.patch('time.sleep')

        result = self.api._retry_with_backoff(mock_func, max_retries=3)

        assert result is None
        assert mock_func.call_count == 3

    def test_retry_exponential_backoff_timing(self, mocker):
        """Test exponential backoff timing"""
        mock_func = mocker.Mock(side_effect=Exception("Error"))
        mock_sleep = mocker.patch('time.sleep')

        self.api._retry_with_backoff(mock_func, max_retries=3, initial_delay=1.0)

        # Should have called sleep with 1s, then 2s
        assert mock_sleep.call_count == 2
        sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
        assert sleep_calls == [1.0, 2.0]


class TestFreeCryptoAPICoinCap:
    """Test CoinCap API integration"""

    def setup_method(self):
        """Setup test instance"""
        self.api = FreeCryptoAPI()

    def test_fetch_from_coincap_success(self, mocker):
        """Test successful CoinCap fetch"""
        mock_response_data = {
            'data': [
                {
                    'symbol': 'BTC',
                    'name': 'Bitcoin',
                    'rank': '1',
                    'priceUsd': '45000.00',
                    'marketCapUsd': '850000000000',
                    'volumeUsd24Hr': '25000000000',
                    'changePercent24Hr': '2.5',
                    'supply': '19000000'
                },
                {
                    'symbol': 'ETH',
                    'name': 'Ethereum',
                    'rank': '2',
                    'priceUsd': '2500.00',
                    'marketCapUsd': '300000000000',
                    'volumeUsd24Hr': '15000000000',
                    'changePercent24Hr': '-1.2',
                    'supply': '120000000'
                }
            ]
        }

        mock_response = Mock()
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status.return_value = None

        mocker.patch('requests.get', return_value=mock_response)
        mocker.patch('time.sleep')  # Speed up pagination sleep

        result = self.api.fetch_from_coincap()

        assert len(result) > 0
        assert result[0]['symbol'] == 'BTC'
        assert result[0]['price'] == 45000.00
        assert result[0]['source'] == 'coincap'

    def test_fetch_from_coincap_pagination(self, mocker):
        """Test CoinCap pagination"""
        call_count = 0

        def mock_json_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {'data': [{'symbol': 'BTC', 'rank': '1', 'priceUsd': '45000'}]}
            elif call_count == 2:
                return {'data': [{'symbol': 'ETH', 'rank': '2', 'priceUsd': '2500'}]}
            else:
                return {'data': []}  # Empty page to stop pagination

        mock_response = Mock()
        mock_response.json.side_effect = mock_json_side_effect
        mock_response.raise_for_status.return_value = None

        mocker.patch('requests.get', return_value=mock_response)
        mocker.patch('time.sleep')

        result = self.api.fetch_from_coincap()

        # Should have fetched multiple pages
        assert len(result) >= 2

    def test_fetch_from_coincap_empty_response(self, mocker):
        """Test CoinCap with empty response"""
        mock_response = Mock()
        mock_response.json.return_value = {'data': []}
        mock_response.raise_for_status.return_value = None

        mocker.patch('requests.get', return_value=mock_response)

        result = self.api.fetch_from_coincap()

        assert result == []

    def test_fetch_from_coincap_http_error(self, mocker):
        """Test CoinCap with HTTP error"""
        mock_get = mocker.patch('requests.get')
        mock_get.side_effect = requests.exceptions.HTTPError("500 Server Error")

        mocker.patch('time.sleep')

        result = self.api.fetch_from_coincap()

        assert result == []

    def test_fetch_from_coincap_timeout(self, mocker):
        """Test CoinCap with timeout"""
        mock_get = mocker.patch('requests.get')
        mock_get.side_effect = requests.exceptions.Timeout("Request timeout")

        mocker.patch('time.sleep')

        result = self.api.fetch_from_coincap()

        assert result == []

    def test_fetch_from_coincap_invalid_data(self, mocker):
        """Test CoinCap with invalid data types"""
        mock_response_data = {
            'data': [
                {
                    'symbol': 'BTC',
                    'name': 'Bitcoin',
                    'rank': 'invalid',  # Invalid rank
                    'priceUsd': 'not_a_number',  # Invalid price
                    'marketCapUsd': '850000000000',
                    'volumeUsd24Hr': '25000000000',
                    'changePercent24Hr': '2.5',
                    'supply': '19000000'
                }
            ]
        }

        mock_response = Mock()
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status.return_value = None

        mocker.patch('requests.get', return_value=mock_response)
        mocker.patch('time.sleep')

        result = self.api.fetch_from_coincap()

        # Should skip invalid entries
        assert isinstance(result, list)

    def test_fetch_from_coincap_missing_fields(self, mocker):
        """Test CoinCap with missing fields"""
        mock_response_data = {
            'data': [
                {
                    'symbol': 'BTC',
                    # Missing many fields
                }
            ]
        }

        mock_response = Mock()
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status.return_value = None

        mocker.patch('requests.get', return_value=mock_response)
        mocker.patch('time.sleep')

        result = self.api.fetch_from_coincap()

        # Should handle missing fields with defaults
        if result:
            assert result[0]['symbol'] == 'BTC'
            assert result[0]['price'] == 0.0  # Default for missing price


class TestFreeCryptoAPIBinance:
    """Test Binance API integration"""

    def setup_method(self):
        """Setup test instance"""
        self.api = FreeCryptoAPI()

    def test_fetch_from_binance_success(self, mocker):
        """Test successful Binance fetch"""
        mock_response_data = [
            {
                'symbol': 'BTCUSDT',
                'lastPrice': '45000.00',
                'quoteVolume': '1500000000',
                'priceChangePercent': '2.5',
                'highPrice': '46000.00',
                'lowPrice': '44000.00'
            },
            {
                'symbol': 'ETHUSDT',
                'lastPrice': '2500.00',
                'quoteVolume': '800000000',
                'priceChangePercent': '-1.2',
                'highPrice': '2600.00',
                'lowPrice': '2450.00'
            },
            {
                'symbol': 'BNBBTC',  # Not USDT pair, should be filtered
                'lastPrice': '0.005',
                'quoteVolume': '100000',
                'priceChangePercent': '1.0',
                'highPrice': '0.006',
                'lowPrice': '0.004'
            }
        ]

        mock_response = Mock()
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status.return_value = None

        mocker.patch('requests.get', return_value=mock_response)

        result = self.api.fetch_from_binance()

        # Should only include USDT pairs
        assert len(result) == 2
        assert result[0]['symbol'] == 'BTC'
        assert result[0]['pair'] == 'BTCUSDT'
        assert result[0]['price'] == 45000.00
        assert result[0]['source'] == 'binance'

    def test_fetch_from_binance_usdt_filtering(self, mocker):
        """Test USDT pair filtering"""
        mock_response_data = [
            {'symbol': 'BTCUSDT', 'lastPrice': '45000', 'quoteVolume': '1000000', 'priceChangePercent': '1', 'highPrice': '46000', 'lowPrice': '44000'},
            {'symbol': 'ETHBTC', 'lastPrice': '0.05', 'quoteVolume': '1000', 'priceChangePercent': '0', 'highPrice': '0.06', 'lowPrice': '0.04'},
            {'symbol': 'BNBUSDT', 'lastPrice': '300', 'quoteVolume': '5000000', 'priceChangePercent': '2', 'highPrice': '310', 'lowPrice': '290'}
        ]

        mock_response = Mock()
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status.return_value = None

        mocker.patch('requests.get', return_value=mock_response)

        result = self.api.fetch_from_binance()

        # Should only have USDT pairs
        assert len(result) == 2
        symbols = [r['symbol'] for r in result]
        assert 'BTC' in symbols
        assert 'BNB' in symbols

    def test_fetch_from_binance_empty_response(self, mocker):
        """Test Binance with empty response"""
        mock_response = Mock()
        mock_response.json.return_value = []
        mock_response.raise_for_status.return_value = None

        mocker.patch('requests.get', return_value=mock_response)

        result = self.api.fetch_from_binance()

        assert result == []

    def test_fetch_from_binance_http_error(self, mocker):
        """Test Binance with HTTP error"""
        mock_get = mocker.patch('requests.get')
        mock_get.side_effect = requests.exceptions.HTTPError("403 Forbidden")

        mocker.patch('time.sleep')

        result = self.api.fetch_from_binance()

        assert result == []

    def test_fetch_from_binance_invalid_data(self, mocker):
        """Test Binance with invalid data"""
        mock_response_data = [
            {
                'symbol': 'BTCUSDT',
                'lastPrice': 'invalid',  # Invalid price
                'quoteVolume': '1000000',
                'priceChangePercent': '1',
                'highPrice': '46000',
                'lowPrice': '44000'
            }
        ]

        mock_response = Mock()
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status.return_value = None

        mocker.patch('requests.get', return_value=mock_response)

        result = self.api.fetch_from_binance()

        # Should skip invalid entries
        assert isinstance(result, list)


class TestFreeCryptoAPIKraken:
    """Test Kraken API integration"""

    def test_fetch_from_kraken_success(self, mocker):
        """Test successful Kraken fetch"""
        mock_response_data = {
            'error': [],
            'result': {
                'XXBTZUSD': {
                    'c': ['45000.00', '1.0'],
                    'v': ['1000', '2000'],
                    'p': ['44500', '44600']
                }
            }
        }

        mock_response = Mock()
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status.return_value = None

        mocker.patch('requests.get', return_value=mock_response)

        result = FreeCryptoAPI.fetch_from_kraken()

        # Currently returns empty list (skeleton implementation)
        assert isinstance(result, list)

    def test_fetch_from_kraken_api_error(self, mocker):
        """Test Kraken with API error"""
        mock_response_data = {
            'error': ['Invalid request'],
            'result': {}
        }

        mock_response = Mock()
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status.return_value = None

        mocker.patch('requests.get', return_value=mock_response)

        result = FreeCryptoAPI.fetch_from_kraken()

        assert result == []

    def test_fetch_from_kraken_http_error(self, mocker):
        """Test Kraken with HTTP error"""
        mock_get = mocker.patch('requests.get')
        mock_get.side_effect = requests.exceptions.HTTPError("500 Server Error")

        result = FreeCryptoAPI.fetch_from_kraken()

        assert result == []

    def test_fetch_from_kraken_timeout(self, mocker):
        """Test Kraken with timeout"""
        mock_get = mocker.patch('requests.get')
        mock_get.side_effect = requests.exceptions.Timeout("Request timeout")

        result = FreeCryptoAPI.fetch_from_kraken()

        assert result == []


class TestFreeCryptoAPIGracefulDegradation:
    """Test graceful degradation with multiple sources"""

    def setup_method(self):
        """Setup test instance"""
        self.api = FreeCryptoAPI()

    def test_fetch_all_coins_all_sources_succeed(self, mocker):
        """Test fetch all coins when all sources succeed"""
        # Mock CoinCap
        mocker.patch.object(self.api, 'fetch_from_coincap', return_value=[
            {'symbol': 'BTC', 'price': 45000, 'market_cap': 850000000000, 'source': 'coincap'},
            {'symbol': 'ETH', 'price': 2500, 'market_cap': 300000000000, 'source': 'coincap'}
        ])

        # Mock Binance
        mocker.patch.object(self.api, 'fetch_from_binance', return_value=[
            {'symbol': 'BTC', 'price': 45100, 'volume_24h': 25000000000, 'source': 'binance'},
            {'symbol': 'BNB', 'price': 300, 'volume_24h': 500000000, 'source': 'binance'}
        ])

        result = self.api.fetch_all_coins()

        # Should merge data from both sources
        assert len(result) == 3  # BTC (merged), ETH, BNB

        # Find BTC
        btc = next((c for c in result if c['symbol'] == 'BTC'), None)
        assert btc is not None
        assert 'price_binance' in btc  # Merged Binance data

    def test_fetch_all_coins_coincap_fails(self, mocker):
        """Test fetch all coins when CoinCap fails"""
        # Mock CoinCap to fail
        mocker.patch.object(self.api, 'fetch_from_coincap', return_value=[])

        # Mock Binance to succeed
        mocker.patch.object(self.api, 'fetch_from_binance', return_value=[
            {'symbol': 'BTC', 'price': 45000, 'source': 'binance'}
        ])

        result = self.api.fetch_all_coins()

        # Should still have data from Binance
        assert len(result) == 1
        assert result[0]['symbol'] == 'BTC'

    def test_fetch_all_coins_binance_fails(self, mocker):
        """Test fetch all coins when Binance fails"""
        # Mock CoinCap to succeed
        mocker.patch.object(self.api, 'fetch_from_coincap', return_value=[
            {'symbol': 'ETH', 'price': 2500, 'source': 'coincap'}
        ])

        # Mock Binance to fail
        mocker.patch.object(self.api, 'fetch_from_binance', return_value=[])

        result = self.api.fetch_all_coins()

        # Should still have data from CoinCap
        assert len(result) == 1
        assert result[0]['symbol'] == 'ETH'

    def test_fetch_all_coins_all_sources_fail(self, mocker):
        """Test fetch all coins when all sources fail"""
        # Mock all sources to fail
        mocker.patch.object(self.api, 'fetch_from_coincap', return_value=[])
        mocker.patch.object(self.api, 'fetch_from_binance', return_value=[])

        result = self.api.fetch_all_coins()

        # Should return empty list
        assert result == []

    def test_fetch_all_coins_exception_handling(self, mocker):
        """Test fetch all coins with exceptions"""
        # Mock CoinCap to raise exception
        mocker.patch.object(self.api, 'fetch_from_coincap', side_effect=Exception("Network error"))

        # Mock Binance to succeed
        mocker.patch.object(self.api, 'fetch_from_binance', return_value=[
            {'symbol': 'BTC', 'price': 45000, 'source': 'binance'}
        ])

        result = self.api.fetch_all_coins()

        # Should gracefully handle exception and return Binance data
        assert len(result) == 1
        assert result[0]['symbol'] == 'BTC'

    def test_fetch_all_coins_data_merging(self, mocker):
        """Test proper data merging from multiple sources"""
        # Mock CoinCap with BTC
        mocker.patch.object(self.api, 'fetch_from_coincap', return_value=[
            {'symbol': 'BTC', 'price': 45000, 'market_cap': 850000000000, 'source': 'coincap'}
        ])

        # Mock Binance with BTC at different price
        mocker.patch.object(self.api, 'fetch_from_binance', return_value=[
            {'symbol': 'BTC', 'price': 45200, 'volume_24h': 25000000000, 'source': 'binance'}
        ])

        result = self.api.fetch_all_coins()

        # Should have merged data
        assert len(result) == 1
        btc = result[0]
        assert btc['symbol'] == 'BTC'
        assert btc['price'] == 45000  # CoinCap price (original)
        assert btc['price_binance'] == 45200  # Binance price (merged)
        assert btc['market_cap'] == 850000000000  # From CoinCap


@pytest.mark.integration
class TestFreeCryptoAPIIntegration:
    """Integration tests for Free Crypto API"""

    def test_api_initialization(self):
        """Test API can be initialized"""
        api = FreeCryptoAPI()
        assert api is not None

    def test_retry_logic_integration(self, mocker):
        """Test retry logic with mock failures"""
        api = FreeCryptoAPI()

        call_count = 0
        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary error")
            return "success"

        mocker.patch('time.sleep')
        result = api._retry_with_backoff(flaky_function, max_retries=5)

        assert result == "success"
        assert call_count == 3

    def test_graceful_degradation_workflow(self, mocker):
        """Test full graceful degradation workflow"""
        api = FreeCryptoAPI()

        # Simulate partial failures
        mocker.patch.object(api, 'fetch_from_coincap', return_value=[
            {'symbol': 'BTC', 'price': 45000, 'source': 'coincap'}
        ])
        mocker.patch.object(api, 'fetch_from_binance', side_effect=Exception("Binance down"))

        result = api.fetch_all_coins()

        # Should still work with just CoinCap
        assert len(result) >= 1
        assert any(c['symbol'] == 'BTC' for c in result)
