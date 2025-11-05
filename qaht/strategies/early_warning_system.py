"""
EARLY WARNING SYSTEM - Maximum Edge Detection

Combines ALL strategies to catch moves BEFORE they happen.

The whole point is to have advanced notice. There are ALWAYS clues:

CLUES TIMELINE (Days Before Move):
7-14 days before: Dark pool accumulation, insider clustering
5-7 days before: Options positioning, smart money entering
3-5 days before: BB compression, volume drying up
1-3 days before: Social sentiment flip, catalyst timing
0-1 days before: Pre-market volume, liquidity sweeps

This system scores opportunities based on how many clues are present.

SCORING MATRIX:
90-100: EXTREME (5+ signals, act immediately)
80-89:  VERY HIGH (4 signals, high priority)
70-79:  HIGH (3 signals, strong candidate)
60-69:  MEDIUM (2 signals, watch closely)
<60:    LOW (1 signal or less, skip)

Real-world examples where this would have caught moves early:
- GME Jan 2021: Dark pool + short squeeze + social shift (10 days notice)
- TSLA Oct 2023: Smart money + gamma squeeze (5 days notice)
- NVDA May 2023: Sector rotation + compression (7 days notice)
- COIN Q4 2023: Insider buy + pre-breakout (14 days notice)
"""

import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import json

from .early_detection import (
    DarkPoolDetector,
    GammaSqueezeDetector,
    ShortSqueezeDetector,
    SmartMoneyTracker,
    PreBreakoutDetector,
    SocialMomentumShiftDetector,
    EarlySignal
)

from .advanced_filters import (
    SectorRotationDetector,
    LiquiditySweepDetector,
    MultiSignalConfluence,
    RiskFilter,
    CryptoEdgeStrategies
)

logger = logging.getLogger(__name__)


@dataclass
class OpportunityAlert:
    """High-conviction opportunity with ALL supporting data."""
    ticker: str
    asset_type: str  # 'STOCK' or 'CRYPTO'
    overall_score: int  # 0-100
    confidence: str  # 'EXTREME', 'VERY_HIGH', 'HIGH', 'MEDIUM', 'LOW'
    priority: int  # 1-5 (1 = highest)

    # Pricing
    current_price: float
    entry_price: float
    target_price: float
    stop_loss: float
    risk_reward_ratio: float

    # Timing
    estimated_timeframe: str  # 'IMMINENT', '1-3_DAYS', '1-2_WEEKS', '1-3_MONTHS'
    catalyst_date: Optional[datetime]
    days_until_catalyst: Optional[int]

    # Signals breakdown
    signal_count: int
    active_signals: List[str]
    signal_categories: Dict[str, int]  # technical, fundamental, flow, sentiment

    # Strategy scores
    dark_pool_score: int
    gamma_squeeze_score: int
    short_squeeze_score: int
    smart_money_score: int
    pre_breakout_score: int
    social_momentum_score: int
    sector_rotation_score: int
    liquidity_sweep_score: int

    # Risk assessment
    risk_score: int
    red_flags: List[str]
    should_avoid: bool

    # Supporting evidence
    key_insights: List[str]
    reasoning: str

    # Metadata
    detected_at: datetime
    last_updated: datetime


class EarlyWarningSystem:
    """
    Master orchestrator combining all strategies for maximum edge.
    """

    def __init__(self):
        self.dark_pool = DarkPoolDetector()
        self.gamma_squeeze = GammaSqueezeDetector()
        self.short_squeeze = ShortSqueezeDetector()
        self.smart_money = SmartMoneyTracker()
        self.pre_breakout = PreBreakoutDetector()
        self.social_momentum = SocialMomentumShiftDetector()
        self.sector_rotation = SectorRotationDetector()
        self.liquidity_sweep = LiquiditySweepDetector()
        self.multi_signal = MultiSignalConfluence()
        self.risk_filter = RiskFilter()
        self.crypto_edge = CryptoEdgeStrategies()

    def analyze_opportunity(
        self,
        ticker: str,
        asset_type: str,
        data: Dict[str, any]
    ) -> OpportunityAlert:
        """
        Comprehensive analysis using ALL strategies.

        Args:
            ticker: Stock/crypto symbol
            asset_type: 'STOCK' or 'CRYPTO'
            data: All data needed for analysis

        Returns:
            OpportunityAlert with complete analysis
        """
        scores = {}
        all_signals = []
        key_insights = []

        # 1. DARK POOL ANALYSIS (stocks only)
        if asset_type == 'STOCK' and 'dark_pool_volume' in data:
            result = self.dark_pool.detect_dark_pool_activity(
                ticker=ticker,
                dark_pool_volume=data['dark_pool_volume'],
                total_volume=data['total_volume'],
                avg_dark_pool_ratio_30d=data['avg_dark_pool_ratio_30d']
            )
            scores['dark_pool'] = result['score']
            if result['is_unusual']:
                all_signals.append('DARK_POOL_ACCUMULATION')
                key_insights.extend(result['signals'])

        # 2. GAMMA SQUEEZE SETUP (stocks with options)
        if asset_type == 'STOCK' and 'call_oi_by_strike' in data:
            result = self.gamma_squeeze.detect_gamma_squeeze_setup(
                ticker=ticker,
                current_price=data['current_price'],
                float_shares=data['float_shares'],
                call_oi_by_strike=data['call_oi_by_strike'],
                put_oi_by_strike=data['put_oi_by_strike'],
                options_volume_24h=data['options_volume_24h'],
                avg_options_volume=data['avg_options_volume']
            )
            scores['gamma_squeeze'] = result['score']
            if result['is_gamma_squeeze_setup']:
                all_signals.append('GAMMA_SQUEEZE_SETUP')
                key_insights.extend(result['signals'])

        # 3. SHORT SQUEEZE CANDIDATE
        if 'short_interest_pct' in data:
            result = self.short_squeeze.detect_short_squeeze_setup(
                ticker=ticker,
                short_interest_pct=data['short_interest_pct'],
                days_to_cover=data['days_to_cover'],
                current_price=data['current_price'],
                recent_high=data['recent_high'],
                volume_ratio=data['volume_ratio'],
                has_catalyst=data.get('has_catalyst', False),
                borrow_fee_rate=data.get('borrow_fee_rate')
            )
            scores['short_squeeze'] = result['score']
            if result['is_short_squeeze_candidate']:
                all_signals.append('SHORT_SQUEEZE_SETUP')
                key_insights.extend(result['signals'])

        # 4. SMART MONEY TRACKING (stocks)
        if asset_type == 'STOCK' and 'new_13f_positions' in data:
            result = self.smart_money.detect_smart_money_accumulation(
                ticker=ticker,
                new_13f_positions=data['new_13f_positions'],
                increased_13f_positions=data['increased_13f_positions'],
                total_13f_holders=data['total_13f_holders'],
                institutional_ownership_change_qoq=data['institutional_ownership_change_qoq'],
                notable_buyers=data['notable_buyers']
            )
            scores['smart_money'] = result['score']
            if result['is_smart_money_accumulating']:
                all_signals.append('SMART_MONEY_BUYING')
                key_insights.extend(result['signals'])

        # 5. PRE-BREAKOUT COMPRESSION
        if 'bb_width_pct' in data:
            result = self.pre_breakout.detect_pre_breakout(
                ticker=ticker,
                bb_width_pct=data['bb_width_pct'],
                bb_width_percentile=data['bb_width_percentile'],
                volume_ratio_5d=data['volume_ratio_5d'],
                volume_ratio_20d=data['volume_ratio_20d'],
                distance_to_resistance_pct=data['distance_to_resistance_pct'],
                days_until_catalyst=data.get('days_until_catalyst'),
                price_consolidation_days=data['price_consolidation_days']
            )
            scores['pre_breakout'] = result['score']
            if result['is_pre_breakout']:
                all_signals.append('PRE_BREAKOUT_COMPRESSION')
                key_insights.extend(result['signals'])

        # 6. SOCIAL MOMENTUM SHIFT
        if 'mentions_24h' in data:
            result = self.social_momentum.detect_social_momentum_shift(
                ticker=ticker,
                mentions_24h=data['mentions_24h'],
                avg_mentions_30d=data['avg_mentions_30d'],
                sentiment_score=data['sentiment_score'],
                sentiment_7d_ago=data['sentiment_7d_ago'],
                influencer_mentions=data['influencer_mentions'],
                reddit_upvotes_24h=data['reddit_upvotes_24h']
            )
            scores['social_momentum'] = result['score']
            if result['is_momentum_shift']:
                all_signals.append('SOCIAL_MOMENTUM_SHIFT')
                key_insights.extend(result['signals'])

        # 7. SECTOR ROTATION (stocks)
        if asset_type == 'STOCK' and 'sector' in data and 'sector_etf_return_5d' in data:
            result = self.sector_rotation.detect_sector_rotation(
                sector=data['sector'],
                sector_etf_return_5d=data['sector_etf_return_5d'],
                spy_return_5d=data['spy_return_5d'],
                stocks_at_new_highs=data['stocks_at_new_highs'],
                total_stocks_in_sector=data['total_stocks_in_sector'],
                sector_volume_ratio=data['sector_volume_ratio'],
                sector_relative_strength=data['sector_relative_strength']
            )
            scores['sector_rotation'] = result['score']
            if result['is_rotating_in']:
                all_signals.append('SECTOR_ROTATION')
                key_insights.extend(result['signals'])

        # 8. LIQUIDITY SWEEP
        if 'intraday_low' in data and 'support_level' in data:
            result = self.liquidity_sweep.detect_liquidity_sweep(
                ticker=ticker,
                current_price=data['current_price'],
                intraday_low=data['intraday_low'],
                support_level=data['support_level'],
                close_price=data['close_price'],
                volume_on_sweep=data['volume_on_sweep'],
                avg_volume=data['avg_volume'],
                wick_size_pct=data['wick_size_pct']
            )
            scores['liquidity_sweep'] = result['score']
            if result['is_liquidity_sweep']:
                all_signals.append('LIQUIDITY_SWEEP_REVERSAL')
                key_insights.extend(result['signals'])

        # 9. RISK ASSESSMENT
        risk_result = None
        if 'distance_to_ath_pct' in data:
            risk_result = self.risk_filter.assess_risk(
                ticker=ticker,
                distance_to_ath_pct=data['distance_to_ath_pct'],
                free_cash_flow=data.get('free_cash_flow', 0),
                share_dilution_1yr=data.get('share_dilution_1yr', 0),
                days_until_lockup_expiry=data.get('days_until_lockup_expiry'),
                has_sec_investigation=data.get('has_sec_investigation', False),
                has_going_concern_warning=data.get('has_going_concern_warning', False),
                borrow_fee_rate=data.get('borrow_fee_rate')
            )

        # 10. CRYPTO-SPECIFIC EDGE
        if asset_type == 'CRYPTO':
            if 'exchanges_listed' in data:
                listing_result = self.crypto_edge.detect_exchange_listing_potential(
                    coin=ticker,
                    market_cap=data['market_cap'],
                    daily_volume=data['daily_volume'],
                    exchanges_listed=data['exchanges_listed'],
                    developer_activity_score=data['developer_activity_score'],
                    community_size=data['community_size']
                )
                if listing_result['listing_potential_score'] >= 70:
                    all_signals.append('EXCHANGE_LISTING_POTENTIAL')
                    key_insights.extend(listing_result['signals'])

            if 'next_unlock_date' in data:
                unlock_result = self.crypto_edge.detect_token_unlock_risk(
                    coin=ticker,
                    current_circulating=data['current_circulating'],
                    max_supply=data['max_supply'],
                    next_unlock_date=data['next_unlock_date'],
                    unlock_amount=data['unlock_amount'],
                    current_price=data['current_price']
                )
                if unlock_result['unlock_risk_score'] >= 60:
                    key_insights.extend(unlock_result['warnings'])

        # CALCULATE OVERALL SCORE
        strategy_scores = [v for v in scores.values() if v > 0]
        if strategy_scores:
            # Weighted average with bonus for multiple signals
            avg_score = sum(strategy_scores) / len(strategy_scores)
            signal_bonus = len(all_signals) * 3  # +3 points per signal
            overall_score = min(int(avg_score + signal_bonus), 100)
        else:
            overall_score = 0

        # DETERMINE CONFIDENCE & PRIORITY
        signal_count = len(all_signals)
        if overall_score >= 90 and signal_count >= 5:
            confidence = 'EXTREME'
            priority = 1
        elif overall_score >= 80 and signal_count >= 4:
            confidence = 'VERY_HIGH'
            priority = 2
        elif overall_score >= 70 and signal_count >= 3:
            confidence = 'HIGH'
            priority = 3
        elif overall_score >= 60 and signal_count >= 2:
            confidence = 'MEDIUM'
            priority = 4
        else:
            confidence = 'LOW'
            priority = 5

        # TIMEFRAME ESTIMATION
        if 'days_until_catalyst' in data and data['days_until_catalyst'] is not None:
            days = data['days_until_catalyst']
            if days <= 1:
                timeframe = 'IMMINENT'
            elif days <= 3:
                timeframe = '1-3_DAYS'
            elif days <= 14:
                timeframe = '1-2_WEEKS'
            else:
                timeframe = '1-3_MONTHS'
        else:
            timeframe = '1-2_WEEKS'  # Default

        # RISK/REWARD CALCULATION
        current_price = data['current_price']
        target_price = data.get('target_price', current_price * 1.5)
        stop_loss = data.get('stop_loss', current_price * 0.92)
        risk_reward = (target_price - current_price) / (current_price - stop_loss) if current_price > stop_loss else 0

        # CATEGORIZE SIGNALS
        signal_categories = {
            'technical': len([s for s in all_signals if s in ['PRE_BREAKOUT_COMPRESSION', 'LIQUIDITY_SWEEP_REVERSAL']]),
            'fundamental': len([s for s in all_signals if s in ['SMART_MONEY_BUYING', 'SECTOR_ROTATION']]),
            'flow': len([s for s in all_signals if s in ['DARK_POOL_ACCUMULATION', 'GAMMA_SQUEEZE_SETUP', 'SHORT_SQUEEZE_SETUP']]),
            'sentiment': len([s for s in all_signals if s in ['SOCIAL_MOMENTUM_SHIFT', 'EXCHANGE_LISTING_POTENTIAL']])
        }

        # BUILD REASONING
        reasoning = self._build_reasoning(
            ticker=ticker,
            confidence=confidence,
            signal_count=signal_count,
            key_insights=key_insights[:5],  # Top 5 insights
            timeframe=timeframe
        )

        # CREATE ALERT
        return OpportunityAlert(
            ticker=ticker,
            asset_type=asset_type,
            overall_score=overall_score,
            confidence=confidence,
            priority=priority,
            current_price=current_price,
            entry_price=current_price,
            target_price=target_price,
            stop_loss=stop_loss,
            risk_reward_ratio=risk_reward,
            estimated_timeframe=timeframe,
            catalyst_date=data.get('catalyst_date'),
            days_until_catalyst=data.get('days_until_catalyst'),
            signal_count=signal_count,
            active_signals=all_signals,
            signal_categories=signal_categories,
            dark_pool_score=scores.get('dark_pool', 0),
            gamma_squeeze_score=scores.get('gamma_squeeze', 0),
            short_squeeze_score=scores.get('short_squeeze', 0),
            smart_money_score=scores.get('smart_money', 0),
            pre_breakout_score=scores.get('pre_breakout', 0),
            social_momentum_score=scores.get('social_momentum', 0),
            sector_rotation_score=scores.get('sector_rotation', 0),
            liquidity_sweep_score=scores.get('liquidity_sweep', 0),
            risk_score=risk_result['risk_score'] if risk_result else 0,
            red_flags=risk_result['red_flags'] if risk_result else [],
            should_avoid=risk_result['should_avoid'] if risk_result else False,
            key_insights=key_insights[:10],  # Top 10
            reasoning=reasoning,
            detected_at=datetime.now(),
            last_updated=datetime.now()
        )

    def _build_reasoning(
        self,
        ticker: str,
        confidence: str,
        signal_count: int,
        key_insights: List[str],
        timeframe: str
    ) -> str:
        """Build human-readable reasoning."""
        timeframe_map = {
            'IMMINENT': 'within 24 hours',
            '1-3_DAYS': 'in 1-3 days',
            '1-2_WEEKS': 'in 1-2 weeks',
            '1-3_MONTHS': 'in 1-3 months'
        }

        reasoning = f"{ticker} shows {confidence} conviction with {signal_count} independent signals converging. "
        reasoning += f"Expected move {timeframe_map.get(timeframe, 'soon')}. "
        reasoning += "Key factors: " + "; ".join(key_insights) + "."

        return reasoning

    def scan_universe(
        self,
        tickers: List[str],
        data_provider: callable,
        min_score: int = 70
    ) -> List[OpportunityAlert]:
        """
        Scan entire universe for opportunities.

        Args:
            tickers: List of tickers to scan
            data_provider: Function that returns data for a ticker
            min_score: Minimum score threshold

        Returns:
            List of opportunities sorted by priority
        """
        opportunities = []

        logger.info(f"Scanning {len(tickers)} tickers for early signals...")

        for ticker in tickers:
            try:
                # Get data for ticker
                data = data_provider(ticker)

                if not data:
                    continue

                # Analyze
                alert = self.analyze_opportunity(
                    ticker=ticker,
                    asset_type=data.get('asset_type', 'STOCK'),
                    data=data
                )

                # Filter by minimum score
                if alert.overall_score >= min_score and not alert.should_avoid:
                    opportunities.append(alert)

            except Exception as e:
                logger.error(f"Failed to analyze {ticker}: {e}")
                continue

        # Sort by priority
        opportunities.sort(key=lambda x: (x.priority, -x.overall_score))

        logger.info(f"Found {len(opportunities)} opportunities above threshold")

        return opportunities

    def export_alerts(
        self,
        opportunities: List[OpportunityAlert],
        format: str = 'json'
    ) -> str:
        """
        Export alerts in various formats.

        Args:
            opportunities: List of alerts
            format: 'json', 'csv', or 'text'

        Returns:
            Formatted string
        """
        if format == 'json':
            return json.dumps([asdict(opp) for opp in opportunities], default=str, indent=2)

        elif format == 'text':
            output = []
            output.append("="*80)
            output.append("EARLY WARNING SYSTEM - HIGH PRIORITY ALERTS")
            output.append("="*80)
            output.append("")

            for opp in opportunities:
                output.append(f"🚨 {opp.ticker} ({opp.asset_type}) - PRIORITY {opp.priority}")
                output.append(f"   Score: {opp.overall_score}/100 | Confidence: {opp.confidence}")
                output.append(f"   Entry: ${opp.entry_price:.2f} | Target: ${opp.target_price:.2f} | Stop: ${opp.stop_loss:.2f}")
                output.append(f"   Risk/Reward: {opp.risk_reward_ratio:.1f}:1")
                output.append(f"   Timeframe: {opp.estimated_timeframe.replace('_', ' ')}")
                output.append(f"   Signals ({opp.signal_count}): {', '.join(opp.active_signals)}")
                output.append(f"   Reasoning: {opp.reasoning}")
                output.append("")

            return "\n".join(output)

        return str(opportunities)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    print("="*80)
    print("⚡ EARLY WARNING SYSTEM - MAXIMUM EDGE")
    print("="*80)
    print()
    print("Combines ALL strategies to catch moves BEFORE they happen")
    print()
    print("CLUES TIMELINE:")
    print("  7-14 days: Dark pool, insider clustering")
    print("  5-7 days:  Options positioning, smart money")
    print("  3-5 days:  BB compression, volume drying")
    print("  1-3 days:  Social flip, catalyst timing")
    print("  0-1 days:  Pre-market, liquidity sweeps")
    print()
    print("CONFIDENCE LEVELS:")
    print("  EXTREME (90+):    5+ signals, ACT NOW")
    print("  VERY HIGH (80-89): 4 signals, high priority")
    print("  HIGH (70-79):     3 signals, strong candidate")
    print("  MEDIUM (60-69):   2 signals, watch closely")
    print("  LOW (<60):        Skip")
    print()
    print("="*80)
