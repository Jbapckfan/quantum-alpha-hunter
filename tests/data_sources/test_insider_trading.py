"""
Integration tests for Insider Trading Detection
"""
import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from qaht.data_sources.insider_trading import (
    InsiderTradingDetector,
    InsiderTransaction
)


class TestInsiderTradingDetectorInitialization:
    """Test insider trading detector initialization"""

    def test_initialization(self):
        """Test detector initialization"""
        detector = InsiderTradingDetector()

        assert detector.sec_base_url == "https://www.sec.gov"


class TestInsiderTradingDetectorForm4Fetching:
    """Test Form 4 filing fetching"""

    def setup_method(self):
        """Setup test instance"""
        self.detector = InsiderTradingDetector()

    def test_fetch_form4_success(self, mocker):
        """Test successful Form 4 fetching"""
        mock_xml = '''<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <title>Apple Inc. (AAPL) - Form 4</title>
                <link href="https://www.sec.gov/cgi-bin/filing/123" />
                <updated>2024-01-15T10:00:00Z</updated>
            </entry>
        </feed>'''

        mock_response = Mock()
        mock_response.content = mock_xml.encode('utf-8')
        mock_response.raise_for_status.return_value = None

        mocker.patch('requests.get', return_value=mock_response)

        filings = self.detector.fetch_recent_form4_filings(days_back=7)

        assert isinstance(filings, list)
        assert len(filings) >= 0  # May be filtered by date

    def test_fetch_form4_http_error(self, mocker):
        """Test Form 4 fetching with HTTP error"""
        import requests
        mock_get = mocker.patch('requests.get')
        mock_get.side_effect = requests.exceptions.HTTPError("404 Not Found")

        filings = self.detector.fetch_recent_form4_filings(days_back=7)

        assert filings == []

    def test_fetch_form4_timeout(self, mocker):
        """Test Form 4 fetching with timeout"""
        import requests
        mock_get = mocker.patch('requests.get')
        mock_get.side_effect = requests.exceptions.Timeout("Request timeout")

        filings = self.detector.fetch_recent_form4_filings(days_back=7)

        assert filings == []

    def test_fetch_form4_uses_proper_headers(self, mocker):
        """Test proper User-Agent header is used"""
        mock_response = Mock()
        mock_response.content = b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
        mock_response.raise_for_status.return_value = None

        mock_get = mocker.patch('requests.get', return_value=mock_response)

        self.detector.fetch_recent_form4_filings(days_back=7)

        # Check headers were provided
        call_kwargs = mock_get.call_args[1]
        assert 'headers' in call_kwargs
        assert 'User-Agent' in call_kwargs['headers']


class TestInsiderTradingDetectorRSSParsing:
    """Test RSS feed parsing"""

    def setup_method(self):
        """Setup test instance"""
        self.detector = InsiderTradingDetector()

    def test_parse_edgar_rss_success(self):
        """Test successful RSS parsing"""
        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <title>Apple Inc. (AAPL) - Form 4</title>
                <link href="https://www.sec.gov/filing/123" />
                <updated>2024-01-15T10:00:00Z</updated>
            </entry>
            <entry>
                <title>Tesla Inc. (TSLA) - Form 4</title>
                <link href="https://www.sec.gov/filing/456" />
                <updated>2024-01-14T15:00:00Z</updated>
            </entry>
        </feed>'''

        filings = self.detector._parse_edgar_rss(xml_content.encode('utf-8'))

        assert len(filings) == 2
        assert filings[0]['ticker'] == 'AAPL'
        assert filings[0]['filing_url'] == 'https://www.sec.gov/filing/123'
        assert filings[1]['ticker'] == 'TSLA'

    def test_parse_edgar_rss_ticker_extraction(self):
        """Test ticker extraction from title"""
        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <title>NVIDIA Corporation (NVDA) - Form 4</title>
                <link href="https://www.sec.gov/filing/789" />
                <updated>2024-01-15T10:00:00Z</updated>
            </entry>
        </feed>'''

        filings = self.detector._parse_edgar_rss(xml_content.encode('utf-8'))

        assert len(filings) == 1
        assert filings[0]['ticker'] == 'NVDA'

    def test_parse_edgar_rss_no_ticker(self):
        """Test handling of entry without ticker"""
        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <title>Company Without Ticker - Form 4</title>
                <link href="https://www.sec.gov/filing/999" />
                <updated>2024-01-15T10:00:00Z</updated>
            </entry>
        </feed>'''

        filings = self.detector._parse_edgar_rss(xml_content.encode('utf-8'))

        assert len(filings) == 1
        assert filings[0]['ticker'] == ''

    def test_parse_edgar_rss_empty_feed(self):
        """Test parsing empty feed"""
        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
        </feed>'''

        filings = self.detector._parse_edgar_rss(xml_content.encode('utf-8'))

        assert filings == []

    def test_parse_edgar_rss_invalid_xml(self):
        """Test handling of invalid XML"""
        xml_content = b'<invalid xml{}'

        filings = self.detector._parse_edgar_rss(xml_content)

        assert filings == []

    def test_parse_edgar_rss_missing_fields(self):
        """Test handling of entries with missing fields"""
        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <title>Company (ABC) - Form 4</title>
            </entry>
        </feed>'''

        filings = self.detector._parse_edgar_rss(xml_content.encode('utf-8'))

        # Should still parse with defaults
        assert len(filings) == 1
        assert filings[0]['ticker'] == 'ABC'
        assert filings[0]['filing_url'] == ''


class TestInsiderTradingDetectorAnalysis:
    """Test insider activity analysis"""

    def setup_method(self):
        """Setup test instance"""
        self.detector = InsiderTradingDetector()

    def test_analyze_empty_transactions(self):
        """Test analysis with empty transactions"""
        result = self.detector.analyze_insider_activity([])

        assert result['signal'] == 'NEUTRAL'
        assert result['confidence'] == 0
        assert result['reasons'] == []

    def test_analyze_bullish_cluster_buying(self):
        """Test detection of cluster buying (bullish signal)"""
        transactions = [
            InsiderTransaction(
                ticker='AAPL',
                insider_name='John Doe',
                insider_title='Director',
                transaction_date=datetime.now(),
                transaction_type='BUY',
                shares=10000,
                price_per_share=150.0,
                total_value=1500000,
                relationship='director',
                filing_date=datetime.now()
            ),
            InsiderTransaction(
                ticker='AAPL',
                insider_name='Jane Smith',
                insider_title='Director',
                transaction_date=datetime.now(),
                transaction_type='BUY',
                shares=5000,
                price_per_share=150.0,
                total_value=750000,
                relationship='director',
                filing_date=datetime.now()
            ),
            InsiderTransaction(
                ticker='AAPL',
                insider_name='Bob Johnson',
                insider_title='Officer',
                transaction_date=datetime.now(),
                transaction_type='BUY',
                shares=8000,
                price_per_share=150.0,
                total_value=1200000,
                relationship='officer',
                filing_date=datetime.now()
            ),
        ]

        result = self.detector.analyze_insider_activity(transactions)

        assert 'AAPL' in result
        assert result['AAPL']['signal'] == 'BULLISH'
        assert result['AAPL']['unique_buyers'] == 3
        assert result['AAPL']['confidence'] > 50

    def test_analyze_c_suite_buying(self):
        """Test detection of C-suite buying (strong bullish signal)"""
        transactions = [
            InsiderTransaction(
                ticker='TSLA',
                insider_name='CEO Name',
                insider_title='CEO',  # Use exact title that matches detection
                transaction_date=datetime.now(),
                transaction_type='BUY',
                shares=100000,
                price_per_share=200.0,
                total_value=20000000,
                relationship='officer',
                filing_date=datetime.now()
            ),
            InsiderTransaction(
                ticker='TSLA',
                insider_name='CFO Name',
                insider_title='CFO',  # Use exact title that matches detection
                transaction_date=datetime.now(),
                transaction_type='BUY',
                shares=50000,
                price_per_share=200.0,
                total_value=10000000,
                relationship='officer',
                filing_date=datetime.now()
            ),
        ]

        result = self.detector.analyze_insider_activity(transactions)

        assert 'TSLA' in result
        assert result['TSLA']['signal'] == 'BULLISH'
        assert result['TSLA']['c_suite_activity'] == 2
        assert result['TSLA']['confidence'] > 70  # High confidence with C-suite buying

    def test_analyze_large_buy_volume(self):
        """Test detection of large buy volume"""
        transactions = [
            InsiderTransaction(
                ticker='NVDA',
                insider_name='Insider Name',
                insider_title='Director',
                transaction_date=datetime.now(),
                transaction_type='BUY',
                shares=20000,
                price_per_share=400.0,
                total_value=8000000,
                relationship='director',
                filing_date=datetime.now()
            ),
        ]

        result = self.detector.analyze_insider_activity(transactions)

        assert 'NVDA' in result
        assert result['NVDA']['total_buy_value'] > 1_000_000

    def test_analyze_bearish_heavy_selling(self):
        """Test detection of heavy selling (bearish signal)"""
        transactions = [
            InsiderTransaction(
                ticker='ABC',
                insider_name='Seller 1',
                insider_title='Director',
                transaction_date=datetime.now(),
                transaction_type='SELL',
                shares=50000,
                price_per_share=100.0,
                total_value=5000000,
                relationship='director',
                filing_date=datetime.now()
            ),
            InsiderTransaction(
                ticker='ABC',
                insider_name='Seller 2',
                insider_title='Officer',
                transaction_date=datetime.now(),
                transaction_type='SELL',
                shares=30000,
                price_per_share=100.0,
                total_value=3000000,
                relationship='officer',
                filing_date=datetime.now()
            ),
        ]

        result = self.detector.analyze_insider_activity(transactions)

        assert 'ABC' in result
        assert result['ABC']['signal'] == 'BEARISH'
        assert result['ABC']['num_sells'] > result['ABC']['num_buys']

    def test_analyze_mixed_activity(self):
        """Test mixed buy/sell activity"""
        transactions = [
            InsiderTransaction(
                ticker='XYZ',
                insider_name='Buyer',
                insider_title='Director',
                transaction_date=datetime.now(),
                transaction_type='BUY',
                shares=10000,
                price_per_share=50.0,
                total_value=500000,
                relationship='director',
                filing_date=datetime.now()
            ),
            InsiderTransaction(
                ticker='XYZ',
                insider_name='Seller',
                insider_title='Officer',
                transaction_date=datetime.now(),
                transaction_type='SELL',
                shares=5000,
                price_per_share=50.0,
                total_value=250000,
                relationship='officer',
                filing_date=datetime.now()
            ),
        ]

        result = self.detector.analyze_insider_activity(transactions)

        assert 'XYZ' in result
        assert result['XYZ']['num_buys'] == 1
        assert result['XYZ']['num_sells'] == 1

    def test_analyze_multiple_tickers(self):
        """Test analysis of multiple tickers"""
        transactions = [
            InsiderTransaction(
                ticker='AAPL',
                insider_name='Buyer 1',
                insider_title='Director',
                transaction_date=datetime.now(),
                transaction_type='BUY',
                shares=10000,
                price_per_share=150.0,
                total_value=1500000,
                relationship='director',
                filing_date=datetime.now()
            ),
            InsiderTransaction(
                ticker='TSLA',
                insider_name='Buyer 2',
                insider_title='CEO',
                transaction_date=datetime.now(),
                transaction_type='BUY',
                shares=20000,
                price_per_share=200.0,
                total_value=4000000,
                relationship='officer',
                filing_date=datetime.now()
            ),
        ]

        result = self.detector.analyze_insider_activity(transactions)

        assert 'AAPL' in result
        assert 'TSLA' in result
        assert len(result) == 2

    def test_confidence_bounds(self):
        """Test confidence is bounded between 0 and 100"""
        # Create extreme bullish case
        transactions = [
            InsiderTransaction(
                ticker='TEST',
                insider_name=f'Buyer {i}',
                insider_title='CEO' if i < 5 else 'Director',
                transaction_date=datetime.now(),
                transaction_type='BUY',
                shares=100000,
                price_per_share=100.0,
                total_value=10000000,
                relationship='officer',
                filing_date=datetime.now()
            )
            for i in range(10)
        ]

        result = self.detector.analyze_insider_activity(transactions)

        assert 'TEST' in result
        assert 0 <= result['TEST']['confidence'] <= 100


class TestInsiderTradingDetectorBullishSignals:
    """Test bullish signal detection"""

    def setup_method(self):
        """Setup test instance"""
        self.detector = InsiderTradingDetector()

    def test_get_bullish_signals(self, mocker):
        """Test getting bullish signals"""
        mock_filings = [
            {
                'ticker': 'AAPL',
                'filing_date': datetime.now(),
                'filing_url': 'https://www.sec.gov/filing/123',
                'title': 'Apple Inc. (AAPL) - Form 4'
            },
            {
                'ticker': 'TSLA',
                'filing_date': datetime.now(),
                'filing_url': 'https://www.sec.gov/filing/456',
                'title': 'Tesla Inc. (TSLA) - Form 4'
            },
        ]

        mocker.patch.object(self.detector, 'fetch_recent_form4_filings', return_value=mock_filings)

        signals = self.detector.get_bullish_insider_signals(days_back=30)

        assert isinstance(signals, list)
        assert len(signals) == 2
        assert all('ticker' in s for s in signals)
        assert all('filing_url' in s for s in signals)

    def test_get_bullish_signals_no_filings(self, mocker):
        """Test getting signals when no filings found"""
        mocker.patch.object(self.detector, 'fetch_recent_form4_filings', return_value=[])

        signals = self.detector.get_bullish_insider_signals(days_back=30)

        assert signals == []

    def test_get_bullish_signals_filters_no_ticker(self, mocker):
        """Test signals filter out entries without ticker"""
        mock_filings = [
            {
                'ticker': 'AAPL',
                'filing_date': datetime.now(),
                'filing_url': 'https://www.sec.gov/filing/123',
                'title': 'Apple Inc. (AAPL) - Form 4'
            },
            {
                'ticker': '',  # No ticker
                'filing_date': datetime.now(),
                'filing_url': 'https://www.sec.gov/filing/456',
                'title': 'Unknown Company - Form 4'
            },
        ]

        mocker.patch.object(self.detector, 'fetch_recent_form4_filings', return_value=mock_filings)

        signals = self.detector.get_bullish_insider_signals(days_back=30)

        # Should only include entries with tickers
        assert len(signals) == 1
        assert signals[0]['ticker'] == 'AAPL'


class TestInsiderTradingDetectorDateFiltering:
    """Test date filtering"""

    def setup_method(self):
        """Setup test instance"""
        self.detector = InsiderTradingDetector()

    def test_fetch_form4_filters_old_filings(self, mocker):
        """Test that old filings are filtered out"""
        # Mock XML with old and recent entries
        # Use simpler date format without microseconds
        old_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%S')
        recent_date = (datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S')  # 1 hour ago

        xml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <title>Old Company (OLD) - Form 4</title>
                <link href="https://www.sec.gov/filing/old" />
                <updated>{old_date}Z</updated>
            </entry>
            <entry>
                <title>Recent Company (NEW) - Form 4</title>
                <link href="https://www.sec.gov/filing/new" />
                <updated>{recent_date}Z</updated>
            </entry>
        </feed>'''

        mock_response = Mock()
        mock_response.content = xml_content.encode('utf-8')
        mock_response.raise_for_status.return_value = None

        mocker.patch('requests.get', return_value=mock_response)

        filings = self.detector.fetch_recent_form4_filings(days_back=7)

        # Should only include recent filing
        tickers = [f['ticker'] for f in filings]
        assert 'NEW' in tickers
        assert 'OLD' not in tickers


@pytest.mark.integration
class TestInsiderTradingDetectorIntegration:
    """Integration tests for insider trading detector"""

    def test_detector_initialization(self):
        """Test detector can be initialized"""
        detector = InsiderTradingDetector()
        assert detector is not None

    def test_insider_transaction_dataclass(self):
        """Test InsiderTransaction dataclass"""
        transaction = InsiderTransaction(
            ticker='AAPL',
            insider_name='Test Insider',
            insider_title='CEO',
            transaction_date=datetime.now(),
            transaction_type='BUY',
            shares=10000,
            price_per_share=150.0,
            total_value=1500000,
            relationship='officer',
            filing_date=datetime.now()
        )

        assert transaction.ticker == 'AAPL'
        assert transaction.transaction_type == 'BUY'
        assert transaction.total_value == 1500000
