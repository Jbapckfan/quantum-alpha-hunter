"""
Integration tests for Options Flow Detection
"""
import pytest
from datetime import datetime
from qaht.data_sources.options_flow import (
    OptionsFlowDetector,
    UnusualVolumeDetector,
    OptionsFlow,
    scan_for_unusual_activity
)


class TestOptionsFlowDetectorInitialization:
    """Test options flow detector initialization"""

    def test_initialization_without_api_key(self):
        """Test initialization without API key"""
        detector = OptionsFlowDetector()

        assert detector.api_key is None

    def test_initialization_with_api_key(self):
        """Test initialization with API key"""
        detector = OptionsFlowDetector(api_key="test_key")

        assert detector.api_key == "test_key"


class TestOptionsFlowDetectorUnusualActivity:
    """Test unusual activity calculation"""

    def setup_method(self):
        """Setup test instance"""
        self.detector = OptionsFlowDetector()

    def test_calculate_unusual_activity_extreme_volume(self):
        """Test extreme volume detection (> 5x average)"""
        result = self.detector.calculate_unusual_activity(
            ticker='AAPL',
            current_volume=60000,  # 6x average (> 5.0)
            avg_volume_20d=10000,
            open_interest=20000
        )

        assert result['is_unusual'] is True
        assert result['score'] >= 40
        assert result['volume_ratio'] == 6.0
        assert 'Extreme volume' in ' '.join(result['reasons'])

    def test_calculate_unusual_activity_high_volume(self):
        """Test high volume detection (> 3x average)"""
        result = self.detector.calculate_unusual_activity(
            ticker='TSLA',
            current_volume=40000,
            avg_volume_20d=10000,
            open_interest=30000
        )

        assert result['is_unusual'] is True
        assert result['score'] >= 30
        assert result['volume_ratio'] == 4.0
        assert 'High volume' in ' '.join(result['reasons'])

    def test_calculate_unusual_activity_elevated_volume(self):
        """Test elevated volume detection (> 2x average)"""
        result = self.detector.calculate_unusual_activity(
            ticker='NVDA',
            current_volume=25000,
            avg_volume_20d=10000,
            open_interest=15000
        )

        assert result['is_unusual'] is True
        assert result['score'] >= 20
        assert result['volume_ratio'] == 2.5

    def test_calculate_unusual_activity_high_vol_oi_ratio(self):
        """Test high volume/OI ratio (> 2.0)"""
        result = self.detector.calculate_unusual_activity(
            ticker='SPY',
            current_volume=30000,
            avg_volume_20d=15000,  # 2x average
            open_interest=10000    # 3x OI
        )

        assert result['vol_oi_ratio'] == 3.0
        assert result['score'] >= 50  # Volume + vol/OI bonuses

    def test_calculate_unusual_activity_large_absolute_volume(self):
        """Test large absolute volume detection"""
        result = self.detector.calculate_unusual_activity(
            ticker='AAPL',
            current_volume=15000,
            avg_volume_20d=10000,
            open_interest=20000
        )

        assert result['score'] >= 20  # Gets bonus for > 10k contracts

    def test_calculate_unusual_activity_normal_volume(self):
        """Test normal volume (not unusual)"""
        result = self.detector.calculate_unusual_activity(
            ticker='ABC',
            current_volume=5000,
            avg_volume_20d=10000,
            open_interest=8000
        )

        assert result['is_unusual'] is False
        assert result['score'] < 50
        assert result['volume_ratio'] == 0.5

    def test_calculate_unusual_activity_zero_avg_volume(self):
        """Test handling of zero average volume"""
        result = self.detector.calculate_unusual_activity(
            ticker='NEW',
            current_volume=5000,
            avg_volume_20d=0,
            open_interest=1000
        )

        assert result['volume_ratio'] == 0
        # Should still check other metrics

    def test_calculate_unusual_activity_zero_open_interest(self):
        """Test handling of zero open interest"""
        result = self.detector.calculate_unusual_activity(
            ticker='TEST',
            current_volume=20000,
            avg_volume_20d=5000,
            open_interest=0
        )

        assert result['vol_oi_ratio'] == 0
        # Should still calculate volume ratio

    def test_calculate_unusual_activity_score_cap(self):
        """Test score is capped at 100"""
        result = self.detector.calculate_unusual_activity(
            ticker='EXTREME',
            current_volume=200000,  # Extreme volume
            avg_volume_20d=10000,   # 20x average
            open_interest=50000     # 4x OI
        )

        assert result['score'] <= 100


class TestOptionsFlowDetectorSweepDetection:
    """Test options sweep detection"""

    def setup_method(self):
        """Setup test instance"""
        self.detector = OptionsFlowDetector()

    def test_detect_sweep_large_premium_fast(self):
        """Test sweep detection with large premium and fast execution"""
        is_sweep = self.detector.detect_options_sweep(
            premium=150000,
            execution_speed='INSTANT',
            volume=500
        )

        assert is_sweep is True

    def test_detect_sweep_very_large_premium(self):
        """Test sweep detection with very large premium"""
        is_sweep = self.detector.detect_options_sweep(
            premium=600000,
            execution_speed='NORMAL',
            volume=300
        )

        assert is_sweep is True

    def test_detect_sweep_large_volume_instant(self):
        """Test sweep detection with large volume and instant execution"""
        is_sweep = self.detector.detect_options_sweep(
            premium=50000,  # Below threshold
            execution_speed='INSTANT',
            volume=1500
        )

        assert is_sweep is True

    def test_detect_sweep_not_a_sweep(self):
        """Test non-sweep transaction"""
        is_sweep = self.detector.detect_options_sweep(
            premium=50000,
            execution_speed='NORMAL',
            volume=100
        )

        assert is_sweep is False

    def test_detect_sweep_medium_premium_slow(self):
        """Test medium premium with slow execution (not a sweep)"""
        is_sweep = self.detector.detect_options_sweep(
            premium=200000,
            execution_speed='NORMAL',
            volume=200
        )

        assert is_sweep is False

    def test_detect_sweep_fast_execution(self):
        """Test fast execution (not instant) with premium"""
        is_sweep = self.detector.detect_options_sweep(
            premium=120000,
            execution_speed='FAST',
            volume=400
        )

        assert is_sweep is True


class TestOptionsFlowDetectorSentiment:
    """Test sentiment calculation"""

    def setup_method(self):
        """Setup test instance"""
        self.detector = OptionsFlowDetector()

    def test_calculate_sentiment_bullish_strong(self):
        """Test strong bullish sentiment (> 3x calls)"""
        result = self.detector.calculate_sentiment(
            call_volume=15000,
            put_volume=4000,
            call_premium=1500000,
            put_premium=400000
        )

        assert result['sentiment'] == 'BULLISH'
        assert result['confidence'] > 50
        assert result['call_put_ratio'] == 3.75

    def test_calculate_sentiment_bullish_moderate(self):
        """Test moderate bullish sentiment (> 2x calls)"""
        result = self.detector.calculate_sentiment(
            call_volume=10000,
            put_volume=4000,
            call_premium=1000000,
            put_premium=400000
        )

        assert result['sentiment'] == 'BULLISH'
        assert result['call_put_ratio'] == 2.5

    def test_calculate_sentiment_bullish_weak(self):
        """Test weak bullish sentiment (> 1.5x calls)"""
        result = self.detector.calculate_sentiment(
            call_volume=9000,
            put_volume=5000,
            call_premium=900000,
            put_premium=500000
        )

        assert result['sentiment'] == 'BULLISH'
        assert result['call_put_ratio'] == 1.8

    def test_calculate_sentiment_bearish_strong(self):
        """Test strong bearish sentiment (< 0.33x calls)"""
        result = self.detector.calculate_sentiment(
            call_volume=2000,
            put_volume=8000,
            call_premium=200000,
            put_premium=800000
        )

        assert result['sentiment'] == 'BEARISH'
        assert result['call_put_ratio'] == 0.25
        assert result['confidence'] < 50

    def test_calculate_sentiment_bearish_moderate(self):
        """Test moderate bearish sentiment (< 0.5x calls)"""
        result = self.detector.calculate_sentiment(
            call_volume=3000,
            put_volume=7000,
            call_premium=300000,
            put_premium=700000
        )

        assert result['sentiment'] == 'BEARISH'
        assert result['call_put_ratio'] < 0.5

    def test_calculate_sentiment_neutral(self):
        """Test neutral sentiment (balanced)"""
        result = self.detector.calculate_sentiment(
            call_volume=5000,
            put_volume=5000,
            call_premium=500000,
            put_premium=500000
        )

        assert result['sentiment'] == 'NEUTRAL'
        assert result['call_put_ratio'] == 1.0
        assert result['premium_ratio'] == 1.0

    def test_calculate_sentiment_zero_volume(self):
        """Test sentiment with zero volume"""
        result = self.detector.calculate_sentiment(
            call_volume=0,
            put_volume=0,
            call_premium=0,
            put_premium=0
        )

        assert result['sentiment'] == 'NEUTRAL'
        assert result['confidence'] == 0
        assert result['call_put_ratio'] == 1.0

    def test_calculate_sentiment_zero_puts(self):
        """Test sentiment with zero puts (extreme bullish)"""
        result = self.detector.calculate_sentiment(
            call_volume=10000,
            put_volume=0,
            call_premium=1000000,
            put_premium=0
        )

        assert result['sentiment'] == 'BULLISH'
        assert result['call_put_ratio'] == float('inf')
        assert result['premium_ratio'] == float('inf')

    def test_calculate_sentiment_premium_weighted_adjustment(self):
        """Test premium-weighted confidence adjustment"""
        result = self.detector.calculate_sentiment(
            call_volume=6000,
            put_volume=4000,
            call_premium=1200000,  # High premium per call
            put_premium=400000
        )

        # Call/put ratio is 1.5 (bullish), premium ratio is 3.0
        # Premium ratio (3.0) > call_put_ratio (1.5) * 1.5 = 2.25
        # Should get +10 confidence boost
        assert result['sentiment'] == 'NEUTRAL'  # 1.5 doesn't trigger bullish threshold
        assert result['confidence'] >= 50  # Base 50 + 10 for premium weighting

    def test_calculate_sentiment_confidence_bounds(self):
        """Test confidence is bounded between 0 and 100"""
        result = self.detector.calculate_sentiment(
            call_volume=20000,
            put_volume=1000,
            call_premium=5000000,
            put_premium=100000
        )

        assert 0 <= result['confidence'] <= 100


class TestOptionsFlowDetectorActivity:
    """Test getting unusual options activity"""

    def setup_method(self):
        """Setup test instance"""
        self.detector = OptionsFlowDetector()

    def test_get_unusual_options_activity_returns_list(self):
        """Test get unusual options activity returns list"""
        result = self.detector.get_unusual_options_activity()

        assert isinstance(result, list)

    def test_get_unusual_options_activity_with_tickers(self):
        """Test get unusual options activity with ticker list"""
        result = self.detector.get_unusual_options_activity(
            tickers=['AAPL', 'TSLA'],
            min_premium=50000,
            min_unusual_score=40
        )

        assert isinstance(result, list)

    def test_get_unusual_options_activity_with_filters(self):
        """Test get unusual options activity with filters"""
        result = self.detector.get_unusual_options_activity(
            min_premium=200000,
            min_unusual_score=70
        )

        assert isinstance(result, list)


class TestUnusualVolumeDetector:
    """Test unusual stock volume detection"""

    def test_detect_unusual_volume_extreme(self):
        """Test extreme volume detection (> 5x 20-day avg)"""
        result = UnusualVolumeDetector.detect_unusual_volume(
            ticker='AAPL',
            current_volume=50000000,
            avg_volume_20d=8000000,
            avg_volume_50d=7000000
        )

        assert result['is_unusual'] is True
        assert result['score'] >= 60
        assert 'Extreme volume' in ' '.join(result['reasons'])

    def test_detect_unusual_volume_very_high(self):
        """Test very high volume (> 3x 20-day avg)"""
        result = UnusualVolumeDetector.detect_unusual_volume(
            ticker='TSLA',
            current_volume=35000000,
            avg_volume_20d=10000000,
            avg_volume_50d=9000000
        )

        assert result['is_unusual'] is True
        assert result['score'] >= 30

    def test_detect_unusual_volume_high(self):
        """Test high volume (> 2x 20-day avg)"""
        result = UnusualVolumeDetector.detect_unusual_volume(
            ticker='NVDA',
            current_volume=25000000,
            avg_volume_20d=10000000,
            avg_volume_50d=9500000
        )

        assert result['score'] >= 20

    def test_detect_unusual_volume_50d_spike(self):
        """Test volume spike vs 50-day average"""
        result = UnusualVolumeDetector.detect_unusual_volume(
            ticker='SPY',
            current_volume=32000000,
            avg_volume_20d=15000000,  # ~2x
            avg_volume_50d=10000000   # 3.2x
        )

        # Should get points for both 20d and 50d
        assert result['score'] >= 40

    def test_detect_unusual_volume_massive_absolute(self):
        """Test massive absolute volume bonus"""
        result = UnusualVolumeDetector.detect_unusual_volume(
            ticker='AAPL',
            current_volume=60000000,
            avg_volume_20d=50000000,
            avg_volume_50d=48000000
        )

        # Should get bonus for > 50M volume
        assert result['score'] >= 10

    def test_detect_unusual_volume_normal(self):
        """Test normal volume (not unusual)"""
        result = UnusualVolumeDetector.detect_unusual_volume(
            ticker='ABC',
            current_volume=8000000,
            avg_volume_20d=10000000,
            avg_volume_50d=9000000
        )

        assert result['is_unusual'] is False
        assert result['score'] < 50

    def test_detect_unusual_volume_zero_averages(self):
        """Test handling of zero averages"""
        result = UnusualVolumeDetector.detect_unusual_volume(
            ticker='NEW',
            current_volume=5000000,
            avg_volume_20d=0,
            avg_volume_50d=0
        )

        assert result['ratio_20d'] == 0
        # Should not crash

    def test_detect_unusual_volume_score_cap(self):
        """Test score is capped at 100"""
        result = UnusualVolumeDetector.detect_unusual_volume(
            ticker='EXTREME',
            current_volume=200000000,
            avg_volume_20d=10000000,  # 20x
            avg_volume_50d=8000000    # 25x
        )

        assert result['score'] <= 100


class TestOptionsFlowDataclass:
    """Test OptionsFlow dataclass"""

    def test_options_flow_creation(self):
        """Test OptionsFlow dataclass creation"""
        flow = OptionsFlow(
            ticker='AAPL',
            timestamp=datetime.now(),
            expiry='2024-01-19',
            strike=180.0,
            option_type='CALL',
            volume=5000,
            open_interest=10000,
            premium=500000,
            spot_price=175.0,
            is_sweep=True,
            sentiment='BULLISH'
        )

        assert flow.ticker == 'AAPL'
        assert flow.option_type == 'CALL'
        assert flow.strike == 180.0
        assert flow.is_sweep is True
        assert flow.sentiment == 'BULLISH'


class TestScanForUnusualActivity:
    """Test main scanning function"""

    def test_scan_for_unusual_activity_returns_dict(self):
        """Test scan returns proper dict structure"""
        result = scan_for_unusual_activity(
            tickers=['AAPL', 'TSLA'],
            check_options=True,
            check_volume=True,
            check_sweeps=True
        )

        assert isinstance(result, dict)
        assert 'unusual_options' in result
        assert 'unusual_volume' in result
        assert 'options_sweeps' in result
        assert 'bullish_flow' in result
        assert 'bearish_flow' in result

    def test_scan_for_unusual_activity_with_options(self):
        """Test scan with options check enabled"""
        result = scan_for_unusual_activity(
            tickers=['AAPL'],
            check_options=True,
            check_volume=False,
            check_sweeps=False
        )

        assert 'unusual_options' in result
        assert isinstance(result['unusual_options'], list)

    def test_scan_for_unusual_activity_empty_tickers(self):
        """Test scan with empty ticker list"""
        result = scan_for_unusual_activity(
            tickers=[],
            check_options=True,
            check_volume=True,
            check_sweeps=True
        )

        assert isinstance(result, dict)


@pytest.mark.integration
class TestOptionsFlowDetectorIntegration:
    """Integration tests for options flow detector"""

    def test_full_workflow_unusual_detection(self):
        """Test full workflow of unusual activity detection"""
        detector = OptionsFlowDetector()

        # Test unusual activity calculation
        activity = detector.calculate_unusual_activity(
            ticker='AAPL',
            current_volume=30000,
            avg_volume_20d=10000,
            open_interest=15000
        )

        assert activity['is_unusual'] is True

        # Test sentiment calculation
        sentiment = detector.calculate_sentiment(
            call_volume=12000,
            put_volume=4000,
            call_premium=1200000,
            put_premium=400000
        )

        assert sentiment['sentiment'] == 'BULLISH'

    def test_full_workflow_sweep_detection(self):
        """Test full workflow of sweep detection"""
        detector = OptionsFlowDetector()

        # Test sweep detection
        is_sweep = detector.detect_options_sweep(
            premium=250000,
            execution_speed='INSTANT',
            volume=800
        )

        assert is_sweep is True

    def test_unusual_volume_detection_workflow(self):
        """Test unusual volume detection workflow"""
        result = UnusualVolumeDetector.detect_unusual_volume(
            ticker='TSLA',
            current_volume=40000000,
            avg_volume_20d=12000000,
            avg_volume_50d=11000000
        )

        assert result['is_unusual'] is True
        assert result['ticker'] == 'TSLA'
