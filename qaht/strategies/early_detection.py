"""
EARLY DETECTION STRATEGIES - Find plays before the crowd

Advanced filters to identify opportunities before they go mainstream:
1. Dark Pool Activity (institutional accumulation)
2. Gamma Squeeze Setups (options-driven explosions)
3. Short Squeeze Candidates (high SI + catalyst)
4. Smart Money Tracking (13F filings, whale movements)
5. Pre-Breakout Coiling (compression + volume drying up)
6. Social Momentum Shift (sentiment flip before price)
7. Sector Rotation Detection (capital flows)
8. Liquidity Sweeps (stop hunts before reversal)

These strategies identify asymmetric risk/reward BEFORE market awareness.
"""

import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class EarlySignal:
    """Represents an early detection signal."""
    ticker: str
    strategy: str
    score: int  # 0-100
    confidence: str  # 'HIGH', 'MEDIUM', 'LOW'
    entry_price: float
    target_price: float
    stop_loss: float
    timeframe: str  # '1-3 days', '1-2 weeks', '1-3 months'
    risk_reward: float
    signals: List[str]
    reasoning: List[str]
    timestamp: datetime


class DarkPoolDetector:
    """
    Detects unusual dark pool activity (institutional accumulation).

    Dark pools = off-exchange trading where institutions accumulate
    without moving the public price. When this liquidity hits the
    lit exchanges, price can explode.
    """

    @staticmethod
    def detect_dark_pool_activity(
        ticker: str,
        dark_pool_volume: float,
        total_volume: float,
        avg_dark_pool_ratio_30d: float
    ) -> Dict:
        """
        Detect unusual dark pool activity.

        Args:
            ticker: Stock ticker
            dark_pool_volume: Today's dark pool volume
            total_volume: Today's total volume
            avg_dark_pool_ratio_30d: 30-day average dark pool %

        Returns:
            Dict with analysis
        """
        if total_volume == 0:
            return {'is_unusual': False, 'score': 0}

        dark_pool_pct = (dark_pool_volume / total_volume) * 100

        # Typical dark pool is 30-40% of volume
        # > 60% = institutions are accumulating
        # > 70% = VERY bullish (hiding big buys)

        score = 0
        signals = []

        if dark_pool_pct > 70:
            score = 90
            signals.append(f"Extreme dark pool: {dark_pool_pct:.1f}% (institutions hiding)")
        elif dark_pool_pct > 60:
            score = 70
            signals.append(f"High dark pool: {dark_pool_pct:.1f}% (accumulation)")
        elif dark_pool_pct > avg_dark_pool_ratio_30d * 1.5:
            score = 50
            signals.append(f"Above average dark pool: {dark_pool_pct:.1f}%")

        # Check if price stayed flat/down while dark pool was high
        # This is EXTREMELY bullish (institutions buying on dips)

        return {
            'ticker': ticker,
            'is_unusual': score >= 50,
            'score': score,
            'dark_pool_pct': dark_pool_pct,
            'signals': signals,
            'interpretation': 'Institutions accumulating quietly' if score >= 70 else 'Monitor for continuation'
        }


class GammaSqueezeDetector:
    """
    Detects gamma squeeze setups (options-driven price explosions).

    Gamma squeeze = Market makers forced to buy stock to hedge
    as price approaches high call open interest strikes.

    Best setups:
    - Massive call OI at nearby strikes
    - Low float (easier to move)
    - Rising volume
    - Stock approaching strike
    """

    @staticmethod
    def detect_gamma_squeeze_setup(
        ticker: str,
        current_price: float,
        float_shares: float,
        call_oi_by_strike: Dict[float, int],
        put_oi_by_strike: Dict[float, int],
        options_volume_24h: int,
        avg_options_volume: int
    ) -> Dict:
        """
        Detect gamma squeeze potential.

        Args:
            ticker: Stock ticker
            current_price: Current stock price
            float_shares: Float (tradeable shares)
            call_oi_by_strike: {strike: open_interest}
            put_oi_by_strike: {strike: open_interest}
            options_volume_24h: Today's options volume
            avg_options_volume: Average daily options volume

        Returns:
            Dict with gamma squeeze analysis
        """
        score = 0
        signals = []

        # Find strikes within 20% of current price
        nearby_strikes = [
            strike for strike in call_oi_by_strike.keys()
            if current_price * 0.8 <= strike <= current_price * 1.2
        ]

        # Sum call OI at nearby strikes
        total_call_oi = sum(call_oi_by_strike.get(strike, 0) for strike in nearby_strikes)
        total_put_oi = sum(put_oi_by_strike.get(strike, 0) for strike in nearby_strikes)

        # Calculate shares represented by options (1 contract = 100 shares)
        call_shares = total_call_oi * 100

        # Gamma squeeze risk if call shares > 10% of float
        if float_shares > 0:
            call_to_float_ratio = call_shares / float_shares

            if call_to_float_ratio > 0.20:
                score += 50
                signals.append(f"MASSIVE call OI: {call_to_float_ratio:.1%} of float")
            elif call_to_float_ratio > 0.10:
                score += 35
                signals.append(f"Heavy call OI: {call_to_float_ratio:.1%} of float")

        # Check call/put ratio (bullish if more calls)
        if total_put_oi > 0:
            call_put_ratio = total_call_oi / total_put_oi
            if call_put_ratio > 3.0:
                score += 20
                signals.append(f"Bullish call/put ratio: {call_put_ratio:.1f}")

        # Check options volume spike
        if avg_options_volume > 0:
            volume_ratio = options_volume_24h / avg_options_volume
            if volume_ratio > 3.0:
                score += 20
                signals.append(f"Options volume spike: {volume_ratio:.1f}x average")

        # Find highest call OI strike (gamma wall)
        if call_oi_by_strike:
            max_strike = max(call_oi_by_strike.items(), key=lambda x: x[1])
            gamma_wall = max_strike[0]

            # If price approaching gamma wall, score higher
            distance_to_wall = (gamma_wall - current_price) / current_price
            if 0 < distance_to_wall < 0.10:  # Within 10%
                score += 15
                signals.append(f"Approaching gamma wall at ${gamma_wall:.2f} ({distance_to_wall:.1%} away)")

        return {
            'ticker': ticker,
            'is_gamma_squeeze_setup': score >= 50,
            'score': min(score, 100),
            'signals': signals,
            'call_oi': total_call_oi,
            'call_shares': call_shares,
            'call_to_float_ratio': call_to_float_ratio if float_shares > 0 else 0,
            'gamma_wall': gamma_wall if 'gamma_wall' in locals() else None,
            'interpretation': 'HIGH gamma squeeze risk' if score >= 70 else 'Moderate squeeze potential' if score >= 50 else 'Low squeeze risk'
        }


class ShortSqueezeDetector:
    """
    Detects short squeeze candidates (high short interest + catalyst).

    Short squeeze = Short sellers forced to buy back shares,
    driving price up in feedback loop.

    Best setups:
    - High short interest (> 20% of float)
    - Low days to cover (< 5 days)
    - Catalyst (earnings, news, product launch)
    - Rising volume
    - Price breaking key resistance
    """

    @staticmethod
    def detect_short_squeeze_setup(
        ticker: str,
        short_interest_pct: float,
        days_to_cover: float,
        current_price: float,
        recent_high: float,
        volume_ratio: float,
        has_catalyst: bool,
        borrow_fee_rate: Optional[float] = None
    ) -> Dict:
        """
        Detect short squeeze potential.

        Args:
            ticker: Stock ticker
            short_interest_pct: % of float shorted
            days_to_cover: Average volume needed to cover shorts
            current_price: Current price
            recent_high: Recent high (resistance)
            volume_ratio: Current volume / average
            has_catalyst: Boolean if catalyst present
            borrow_fee_rate: Cost to borrow shares (%)

        Returns:
            Dict with short squeeze analysis
        """
        score = 0
        signals = []

        # High short interest (most important)
        if short_interest_pct > 40:
            score += 50
            signals.append(f"EXTREME short interest: {short_interest_pct:.1f}% of float")
        elif short_interest_pct > 30:
            score += 40
            signals.append(f"Very high short interest: {short_interest_pct:.1f}%")
        elif short_interest_pct > 20:
            score += 25
            signals.append(f"High short interest: {short_interest_pct:.1f}%")

        # Days to cover (lower = easier to squeeze)
        if days_to_cover < 2:
            score += 20
            signals.append(f"Low days to cover: {days_to_cover:.1f} days (easy to squeeze)")
        elif days_to_cover < 5:
            score += 10
            signals.append(f"Moderate days to cover: {days_to_cover:.1f} days")

        # Catalyst present
        if has_catalyst:
            score += 15
            signals.append("Catalyst present (trigger for squeeze)")

        # Volume spike (shorts may be covering)
        if volume_ratio > 2.0:
            score += 10
            signals.append(f"Volume spike: {volume_ratio:.1f}x (possible covering)")

        # Borrow fee rate (high = hard to short, bullish)
        if borrow_fee_rate is not None and borrow_fee_rate > 50:
            score += 15
            signals.append(f"HIGH borrow fee: {borrow_fee_rate:.0f}% (shorts in pain)")

        # Price action (breaking resistance = squeeze starting)
        distance_to_high = (recent_high - current_price) / current_price
        if distance_to_high < 0.05:  # Within 5% of recent high
            score += 10
            signals.append(f"Approaching resistance at ${recent_high:.2f}")

        return {
            'ticker': ticker,
            'is_short_squeeze_candidate': score >= 50,
            'score': min(score, 100),
            'signals': signals,
            'short_interest_pct': short_interest_pct,
            'days_to_cover': days_to_cover,
            'borrow_fee_rate': borrow_fee_rate,
            'interpretation': 'HIGH squeeze potential' if score >= 70 else 'Moderate squeeze potential' if score >= 50 else 'Low squeeze potential'
        }


class SmartMoneyTracker:
    """
    Tracks institutional/smart money movements.

    Tracks:
    - 13F filings (hedge fund positions)
    - Whale wallet movements (crypto)
    - Unusual institutional buying
    - Hedge fund clustering (multiple funds buying same stock)
    """

    @staticmethod
    def detect_smart_money_accumulation(
        ticker: str,
        new_13f_positions: int,
        increased_13f_positions: int,
        total_13f_holders: int,
        institutional_ownership_change_qoq: float,
        notable_buyers: List[str]
    ) -> Dict:
        """
        Detect smart money accumulation.

        Args:
            ticker: Stock ticker
            new_13f_positions: # new hedge fund positions
            increased_13f_positions: # funds that increased
            total_13f_holders: Total institutional holders
            institutional_ownership_change_qoq: % change QoQ
            notable_buyers: List of notable fund names

        Returns:
            Dict with smart money analysis
        """
        score = 0
        signals = []

        # New positions (smart money discovering)
        if new_13f_positions > 20:
            score += 40
            signals.append(f"{new_13f_positions} new hedge fund positions (discovery phase)")
        elif new_13f_positions > 10:
            score += 25
            signals.append(f"{new_13f_positions} new institutional positions")

        # Increased positions (continued buying)
        if increased_13f_positions > 30:
            score += 30
            signals.append(f"{increased_13f_positions} funds increased positions (confidence)")
        elif increased_13f_positions > 15:
            score += 20
            signals.append(f"{increased_13f_positions} funds added shares")

        # Ownership change
        if institutional_ownership_change_qoq > 10:
            score += 20
            signals.append(f"Institutional ownership up {institutional_ownership_change_qoq:.1f}%")

        # Notable buyers (Buffett, Ackman, ARK, etc.)
        if notable_buyers:
            score += 15
            signals.append(f"Notable buyers: {', '.join(notable_buyers[:3])}")

        return {
            'ticker': ticker,
            'is_smart_money_accumulating': score >= 50,
            'score': min(score, 100),
            'signals': signals,
            'new_positions': new_13f_positions,
            'increased_positions': increased_13f_positions,
            'notable_buyers': notable_buyers,
            'interpretation': 'Strong institutional buying' if score >= 70 else 'Moderate institutional interest' if score >= 50 else 'Limited institutional interest'
        }


class PreBreakoutDetector:
    """
    Detects stocks coiling BEFORE breakout (compression + catalyst).

    Best entries are BEFORE the breakout, not after.

    Characteristics:
    - BB compression (volatility squeezing)
    - Volume drying up (coiling)
    - Price consolidating near key level
    - Catalyst upcoming (earnings, FDA, product launch)
    - Multiple timeframe alignment
    """

    @staticmethod
    def detect_pre_breakout(
        ticker: str,
        bb_width_pct: float,
        bb_width_percentile: float,
        volume_ratio_5d: float,
        volume_ratio_20d: float,
        distance_to_resistance_pct: float,
        days_until_catalyst: Optional[int],
        price_consolidation_days: int
    ) -> Dict:
        """
        Detect pre-breakout coiling.

        Args:
            ticker: Stock ticker
            bb_width_pct: Current BB width %
            bb_width_percentile: Percentile vs 1yr (lower = more compressed)
            volume_ratio_5d: Current volume / 5d avg
            volume_ratio_20d: Current volume / 20d avg
            distance_to_resistance_pct: % to key resistance
            days_until_catalyst: Days until known catalyst
            price_consolidation_days: Days consolidating

        Returns:
            Dict with pre-breakout analysis
        """
        score = 0
        signals = []

        # BB compression (MOST important for early detection)
        if bb_width_percentile < 10:
            score += 40
            signals.append(f"EXTREME compression: {bb_width_percentile:.0f}th percentile")
        elif bb_width_percentile < 20:
            score += 30
            signals.append(f"High compression: {bb_width_percentile:.0f}th percentile")

        # Volume drying up (coiling)
        if volume_ratio_5d < 0.7 and volume_ratio_20d < 0.8:
            score += 20
            signals.append(f"Volume drying up: {volume_ratio_5d:.2f}x recent avg (coiling)")

        # Near resistance (breakout imminent)
        if distance_to_resistance_pct < 5:
            score += 15
            signals.append(f"Near resistance: {distance_to_resistance_pct:.1f}% away (breakout zone)")

        # Catalyst upcoming
        if days_until_catalyst is not None and days_until_catalyst < 14:
            score += 15
            signals.append(f"Catalyst in {days_until_catalyst} days (timing aligned)")

        # Consolidation period (longer = stronger breakout)
        if price_consolidation_days > 20:
            score += 10
            signals.append(f"Consolidating {price_consolidation_days} days (pressure building)")

        return {
            'ticker': ticker,
            'is_pre_breakout': score >= 60,
            'score': min(score, 100),
            'signals': signals,
            'bb_width_percentile': bb_width_percentile,
            'volume_drying_up': volume_ratio_5d < 0.7,
            'days_until_catalyst': days_until_catalyst,
            'interpretation': 'HIGH probability breakout setup' if score >= 75 else 'Moderate breakout potential' if score >= 60 else 'Early stage coiling'
        }


class SocialMomentumShiftDetector:
    """
    Detects sentiment shift BEFORE price moves.

    Social media sentiment often leads price by hours/days.

    Signals:
    - Sudden spike in mentions (from quiet to trending)
    - Sentiment flip (negative to positive)
    - Influencer attention (specific traders)
    - Reddit/Discord volume increase
    """

    @staticmethod
    def detect_social_momentum_shift(
        ticker: str,
        mentions_24h: int,
        avg_mentions_30d: int,
        sentiment_score: float,  # -1 to +1
        sentiment_7d_ago: float,
        influencer_mentions: int,
        reddit_upvotes_24h: int
    ) -> Dict:
        """
        Detect social sentiment shift.

        Args:
            ticker: Stock ticker
            mentions_24h: Mentions in last 24h
            avg_mentions_30d: 30-day average mentions
            sentiment_score: Current sentiment (-1 to +1)
            sentiment_7d_ago: Sentiment 7 days ago
            influencer_mentions: # influencer mentions
            reddit_upvotes_24h: Reddit upvotes today

        Returns:
            Dict with social momentum analysis
        """
        score = 0
        signals = []

        # Mention spike (going viral)
        if avg_mentions_30d > 0:
            mention_ratio = mentions_24h / avg_mentions_30d

            if mention_ratio > 10:
                score += 40
                signals.append(f"VIRAL: {mention_ratio:.0f}x mentions (going mainstream)")
            elif mention_ratio > 5:
                score += 30
                signals.append(f"Trending: {mention_ratio:.1f}x mentions")
            elif mention_ratio > 3:
                score += 20
                signals.append(f"Rising mentions: {mention_ratio:.1f}x average")

        # Sentiment flip (negative to positive = BULLISH)
        sentiment_change = sentiment_score - sentiment_7d_ago
        if sentiment_change > 0.4:  # Big positive flip
            score += 30
            signals.append(f"SENTIMENT FLIP: {sentiment_7d_ago:.2f} → {sentiment_score:.2f} (bullish reversal)")
        elif sentiment_change > 0.2:
            score += 20
            signals.append(f"Improving sentiment: +{sentiment_change:.2f}")

        # Influencer attention
        if influencer_mentions > 0:
            score += 15
            signals.append(f"{influencer_mentions} influencer mentions (amplification)")

        # Reddit engagement
        if reddit_upvotes_24h > 1000:
            score += 15
            signals.append(f"High Reddit engagement: {reddit_upvotes_24h:,} upvotes")

        return {
            'ticker': ticker,
            'is_momentum_shift': score >= 50,
            'score': min(score, 100),
            'signals': signals,
            'mention_ratio': mention_ratio if avg_mentions_30d > 0 else 0,
            'sentiment_change': sentiment_change,
            'interpretation': 'STRONG social momentum' if score >= 70 else 'Building momentum' if score >= 50 else 'Early stage attention'
        }


def score_early_opportunity(
    ticker: str,
    **kwargs
) -> EarlySignal:
    """
    Combine all early detection strategies for comprehensive scoring.

    Args:
        ticker: Stock ticker
        **kwargs: All data needed for various detectors

    Returns:
        EarlySignal with combined analysis
    """
    total_score = 0
    all_signals = []
    all_reasoning = []

    # Run all detectors
    detectors = []

    # Dark pool
    if 'dark_pool_volume' in kwargs:
        dp = DarkPoolDetector()
        result = dp.detect_dark_pool_activity(ticker, **{k: kwargs[k] for k in ['dark_pool_volume', 'total_volume', 'avg_dark_pool_ratio_30d'] if k in kwargs})
        if result['is_unusual']:
            total_score += result['score'] * 0.2  # 20% weight
            all_signals.extend(result['signals'])
            all_reasoning.append(f"Dark Pool: {result['interpretation']}")

    # Gamma squeeze
    if 'call_oi_by_strike' in kwargs:
        gs = GammaSqueezeDetector()
        result = gs.detect_gamma_squeeze_setup(ticker, **{k: kwargs[k] for k in ['current_price', 'float_shares', 'call_oi_by_strike', 'put_oi_by_strike', 'options_volume_24h', 'avg_options_volume'] if k in kwargs})
        if result['is_gamma_squeeze_setup']:
            total_score += result['score'] * 0.25  # 25% weight
            all_signals.extend(result['signals'])
            all_reasoning.append(f"Gamma Squeeze: {result['interpretation']}")

    # Short squeeze
    if 'short_interest_pct' in kwargs:
        ss = ShortSqueezeDetector()
        result = ss.detect_short_squeeze_setup(ticker, **{k: kwargs[k] for k in ['short_interest_pct', 'days_to_cover', 'current_price', 'recent_high', 'volume_ratio', 'has_catalyst', 'borrow_fee_rate'] if k in kwargs})
        if result['is_short_squeeze_candidate']:
            total_score += result['score'] * 0.2  # 20% weight
            all_signals.extend(result['signals'])
            all_reasoning.append(f"Short Squeeze: {result['interpretation']}")

    # Smart money
    if 'new_13f_positions' in kwargs:
        sm = SmartMoneyTracker()
        result = sm.detect_smart_money_accumulation(ticker, **{k: kwargs[k] for k in ['new_13f_positions', 'increased_13f_positions', 'total_13f_holders', 'institutional_ownership_change_qoq', 'notable_buyers'] if k in kwargs})
        if result['is_smart_money_accumulating']:
            total_score += result['score'] * 0.15  # 15% weight
            all_signals.extend(result['signals'])
            all_reasoning.append(f"Smart Money: {result['interpretation']}")

    # Pre-breakout
    if 'bb_width_pct' in kwargs:
        pb = PreBreakoutDetector()
        result = pb.detect_pre_breakout(ticker, **{k: kwargs[k] for k in ['bb_width_pct', 'bb_width_percentile', 'volume_ratio_5d', 'volume_ratio_20d', 'distance_to_resistance_pct', 'days_until_catalyst', 'price_consolidation_days'] if k in kwargs})
        if result['is_pre_breakout']:
            total_score += result['score'] * 0.15  # 15% weight
            all_signals.extend(result['signals'])
            all_reasoning.append(f"Pre-Breakout: {result['interpretation']}")

    # Social momentum
    if 'mentions_24h' in kwargs:
        sms = SocialMomentumShiftDetector()
        result = sms.detect_social_momentum_shift(ticker, **{k: kwargs[k] for k in ['mentions_24h', 'avg_mentions_30d', 'sentiment_score', 'sentiment_7d_ago', 'influencer_mentions', 'reddit_upvotes_24h'] if k in kwargs})
        if result['is_momentum_shift']:
            total_score += result['score'] * 0.05  # 5% weight
            all_signals.extend(result['signals'])
            all_reasoning.append(f"Social: {result['interpretation']}")

    # Determine confidence
    num_strategies = len([s for s in all_reasoning])
    if total_score >= 80 and num_strategies >= 3:
        confidence = 'HIGH'
    elif total_score >= 60 and num_strategies >= 2:
        confidence = 'MEDIUM'
    else:
        confidence = 'LOW'

    # Calculate risk/reward (simplified)
    current_price = kwargs.get('current_price', 0)
    target_price = current_price * 1.5  # 50% upside
    stop_loss = current_price * 0.92  # 8% stop
    risk_reward = (target_price - current_price) / (current_price - stop_loss) if current_price > stop_loss else 0

    return EarlySignal(
        ticker=ticker,
        strategy='EARLY_DETECTION',
        score=int(total_score),
        confidence=confidence,
        entry_price=current_price,
        target_price=target_price,
        stop_loss=stop_loss,
        timeframe='1-3 weeks',
        risk_reward=risk_reward,
        signals=list(set(all_signals)),  # Dedupe
        reasoning=all_reasoning,
        timestamp=datetime.now()
    )


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    print("="*80)
    print("🔍 EARLY DETECTION STRATEGIES")
    print("="*80)
    print()
    print("Advanced filters to find plays BEFORE the crowd:")
    print()
    print("1. Dark Pool Activity - Institutional accumulation")
    print("2. Gamma Squeeze Setups - Options-driven explosions")
    print("3. Short Squeeze Candidates - High SI + catalyst")
    print("4. Smart Money Tracking - 13F filings, whale movements")
    print("5. Pre-Breakout Coiling - Compression before explosion")
    print("6. Social Momentum Shift - Sentiment flip before price")
    print()
    print("="*80)
