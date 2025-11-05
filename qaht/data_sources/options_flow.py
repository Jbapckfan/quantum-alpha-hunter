"""
Options Flow Detection - Tracks unusual options activity

Detects:
1. Options sweeps (large market orders)
2. Unusual options volume (vs 20-day average)
3. Large premium transactions (> $100K)
4. Bullish/bearish bias (calls vs puts)
5. Near-term expiries (catalyst expected)

FREE Sources:
- CBOE delayed data (15-min delay)
- Options volume from stock APIs
- Calculated unusual activity metrics

PAID Sources (better real-time):
- Unusual Whales API
- FlowAlgo
- Market Chameleon
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
import requests

logger = logging.getLogger(__name__)


@dataclass
class OptionsFlow:
    """Represents an unusual options transaction."""
    ticker: str
    timestamp: datetime
    expiry: str
    strike: float
    option_type: str  # 'CALL' or 'PUT'
    volume: int
    open_interest: int
    premium: float
    spot_price: float
    is_sweep: bool
    sentiment: str  # 'BULLISH', 'BEARISH', 'NEUTRAL'


class OptionsFlowDetector:
    """
    Detects unusual options activity and sweeps.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Args:
            api_key: Optional API key for paid services
        """
        self.api_key = api_key

    def calculate_unusual_activity(
        self,
        ticker: str,
        current_volume: int,
        avg_volume_20d: int,
        open_interest: int
    ) -> Dict:
        """
        Determine if options volume is unusual.

        Args:
            ticker: Stock ticker
            current_volume: Today's options volume
            avg_volume_20d: 20-day average volume
            open_interest: Current open interest

        Returns:
            Dict with analysis
        """
        is_unusual = False
        reasons = []
        score = 0

        # Check 1: Volume spike (> 2x average)
        if avg_volume_20d > 0:
            volume_ratio = current_volume / avg_volume_20d

            if volume_ratio > 5.0:
                is_unusual = True
                score += 40
                reasons.append(f"Extreme volume: {volume_ratio:.1f}x average")
            elif volume_ratio > 3.0:
                is_unusual = True
                score += 30
                reasons.append(f"High volume: {volume_ratio:.1f}x average")
            elif volume_ratio > 2.0:
                is_unusual = True
                score += 20
                reasons.append(f"Elevated volume: {volume_ratio:.1f}x average")

        # Check 2: Volume > Open Interest (fresh positions)
        if open_interest > 0:
            vol_oi_ratio = current_volume / open_interest

            if vol_oi_ratio > 2.0:
                score += 30
                reasons.append(f"High vol/OI: {vol_oi_ratio:.1f}x (fresh positions)")
            elif vol_oi_ratio > 1.0:
                score += 20
                reasons.append(f"Volume > OI: {vol_oi_ratio:.1f}x")

        # Check 3: Absolute volume threshold
        if current_volume > 10000:
            score += 20
            reasons.append(f"Large absolute volume: {current_volume:,} contracts")

        return {
            'ticker': ticker,
            'is_unusual': is_unusual or score >= 50,
            'score': min(score, 100),
            'reasons': reasons,
            'volume_ratio': volume_ratio if avg_volume_20d > 0 else 0,
            'vol_oi_ratio': vol_oi_ratio if open_interest > 0 else 0
        }

    def detect_options_sweep(
        self,
        premium: float,
        execution_speed: str,
        volume: int
    ) -> bool:
        """
        Determine if transaction is likely an options sweep.

        Sweeps = Large market orders executed quickly, often institutional.

        Args:
            premium: Total premium paid
            execution_speed: 'INSTANT', 'FAST', 'NORMAL'
            volume: Number of contracts

        Returns:
            True if likely a sweep
        """
        # Sweeps typically have:
        # 1. Large premium (> $100K)
        # 2. Fast execution (market order)
        # 3. Large size

        is_sweep = False

        if premium > 100_000 and execution_speed in ['INSTANT', 'FAST']:
            is_sweep = True

        if premium > 500_000:
            is_sweep = True

        if volume > 1000 and execution_speed == 'INSTANT':
            is_sweep = True

        return is_sweep

    def calculate_sentiment(
        self,
        call_volume: int,
        put_volume: int,
        call_premium: float,
        put_premium: float
    ) -> Dict:
        """
        Calculate bullish/bearish sentiment from options flow.

        Args:
            call_volume: Total call volume
            put_volume: Total put volume
            call_premium: Total premium on calls
            put_premium: Total premium on puts

        Returns:
            Dict with sentiment analysis
        """
        total_volume = call_volume + put_volume
        total_premium = call_premium + put_premium

        if total_volume == 0:
            return {
                'sentiment': 'NEUTRAL',
                'confidence': 0,
                'call_put_ratio': 1.0,
                'premium_ratio': 1.0
            }

        # Calculate ratios
        call_put_ratio = call_volume / put_volume if put_volume > 0 else float('inf')
        premium_ratio = call_premium / put_premium if put_premium > 0 else float('inf')

        # Determine sentiment
        sentiment = 'NEUTRAL'
        confidence = 50

        # Bullish signals
        if call_put_ratio > 3.0:
            sentiment = 'BULLISH'
            confidence += 20
        elif call_put_ratio > 2.0:
            sentiment = 'BULLISH'
            confidence += 15
        elif call_put_ratio > 1.5:
            sentiment = 'BULLISH'
            confidence += 10

        # Bearish signals
        if call_put_ratio < 0.33:
            sentiment = 'BEARISH'
            confidence = 30
        elif call_put_ratio < 0.5:
            sentiment = 'BEARISH'
            confidence = 35
        elif call_put_ratio < 0.67:
            sentiment = 'BEARISH'
            confidence = 40

        # Premium-weighted adjustment
        if premium_ratio > call_put_ratio * 1.5:
            # Calls getting more premium per contract (more aggressive)
            confidence += 10
        elif premium_ratio < call_put_ratio * 0.67:
            # Puts getting more premium per contract
            confidence -= 10

        return {
            'sentiment': sentiment,
            'confidence': min(max(confidence, 0), 100),
            'call_put_ratio': call_put_ratio,
            'premium_ratio': premium_ratio,
            'call_volume': call_volume,
            'put_volume': put_volume,
            'call_premium': call_premium,
            'put_premium': put_premium
        }

    def get_unusual_options_activity(
        self,
        tickers: Optional[List[str]] = None,
        min_premium: float = 100_000,
        min_unusual_score: int = 50
    ) -> List[Dict]:
        """
        Get unusual options activity.

        Args:
            tickers: List of tickers to check (None = all)
            min_premium: Minimum premium to consider
            min_unusual_score: Minimum unusual score (0-100)

        Returns:
            List of unusual activity sorted by score
        """
        logger.info("Scanning for unusual options activity...")

        # In production, this would:
        # 1. Fetch real-time options data from CBOE or paid API
        # 2. Calculate unusual metrics
        # 3. Detect sweeps
        # 4. Analyze sentiment

        # For now, return structure
        unusual_activity = []

        logger.info(f"Found {len(unusual_activity)} unusual options flows")
        return unusual_activity


class UnusualVolumeDetector:
    """
    Detects unusual stock volume (not options).
    """

    @staticmethod
    def detect_unusual_volume(
        ticker: str,
        current_volume: int,
        avg_volume_20d: int,
        avg_volume_50d: int
    ) -> Dict:
        """
        Detect unusual stock volume.

        Args:
            ticker: Stock ticker
            current_volume: Today's volume
            avg_volume_20d: 20-day average
            avg_volume_50d: 50-day average

        Returns:
            Dict with analysis
        """
        score = 0
        reasons = []

        # Check against 20-day average
        if avg_volume_20d > 0:
            ratio_20d = current_volume / avg_volume_20d

            if ratio_20d > 5.0:
                score += 40
                reasons.append(f"Extreme volume: {ratio_20d:.1f}x 20-day avg")
            elif ratio_20d > 3.0:
                score += 30
                reasons.append(f"Very high volume: {ratio_20d:.1f}x 20-day avg")
            elif ratio_20d > 2.0:
                score += 20
                reasons.append(f"High volume: {ratio_20d:.1f}x 20-day avg")

        # Check against 50-day average
        if avg_volume_50d > 0:
            ratio_50d = current_volume / avg_volume_50d

            if ratio_50d > 3.0:
                score += 20
                reasons.append(f"Volume spike: {ratio_50d:.1f}x 50-day avg")

        # Absolute volume check
        if current_volume > 50_000_000:
            score += 10
            reasons.append(f"Massive absolute volume: {current_volume/1e6:.1f}M")

        return {
            'ticker': ticker,
            'is_unusual': score >= 50,
            'score': min(score, 100),
            'reasons': reasons,
            'current_volume': current_volume,
            'avg_volume_20d': avg_volume_20d,
            'ratio_20d': current_volume / avg_volume_20d if avg_volume_20d > 0 else 0
        }


def scan_for_unusual_activity(
    tickers: List[str],
    check_options: bool = True,
    check_volume: bool = True,
    check_sweeps: bool = True
) -> Dict[str, List[Dict]]:
    """
    Scan for all types of unusual activity.

    Args:
        tickers: List of tickers to scan
        check_options: Check options flow
        check_volume: Check stock volume
        check_sweeps: Check for sweeps

    Returns:
        Dict with different types of signals
    """
    results = {
        'unusual_options': [],
        'unusual_volume': [],
        'options_sweeps': [],
        'bullish_flow': [],
        'bearish_flow': []
    }

    logger.info(f"Scanning {len(tickers)} tickers for unusual activity...")

    if check_options:
        options_detector = OptionsFlowDetector()
        results['unusual_options'] = options_detector.get_unusual_options_activity(tickers)

    # More detectors would be added here...

    return results


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    print("="*80)
    print("📊 OPTIONS FLOW & UNUSUAL ACTIVITY DETECTOR")
    print("="*80)
    print()
    print("Tracks:")
    print("  • Options sweeps (large institutional orders)")
    print("  • Unusual options volume (vs 20-day average)")
    print("  • Large premium transactions (> $100K)")
    print("  • Bullish/bearish sentiment (call/put ratio)")
    print("  • Unusual stock volume")
    print()
    print("="*80)
    print()
    print("📝 Data Sources:")
    print()
    print("FREE:")
    print("  • CBOE delayed data (15-min delay)")
    print("  • Calculated unusual metrics")
    print("  • Volume ratios from stock data")
    print()
    print("PAID (recommended for real-time):")
    print("  • Unusual Whales ($50/month)")
    print("  • FlowAlgo ($149/month)")
    print("  • Market Chameleon ($69/month)")
    print()
    print("="*80)
    print()
    print("💡 How to Use:")
    print("  1. Track stocks with unusual options volume (> 2x average)")
    print("  2. Focus on sweeps (> $100K premium, fast execution)")
    print("  3. Analyze sentiment (call/put ratio)")
    print("  4. Cross-reference with compression signals")
    print("  5. Near-term expiries = catalyst expected soon")
    print()
    print("="*80)
