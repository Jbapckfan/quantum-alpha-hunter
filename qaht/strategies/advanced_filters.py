"""
ADVANCED FILTERING STRATEGIES

Additional edge-finding strategies:
1. Sector Rotation Detection (capital flows between sectors)
2. Liquidity Sweep Detection (stop hunts before reversals)
3. Multi-Signal Confluence (4+ signals = highest conviction)
4. Risk Filters (avoid landmines)
5. Crypto-Specific Edge (exchange listings, token unlocks, whale tracking)
6. Earnings Beat Probability (whisper numbers, options positioning)
7. Float Rotation Analysis (% of float traded recently)
"""

import logging
from typing import List, Dict, Optional, Set
from datetime import datetime, timedelta
from dataclasses import dataclass
from collections import defaultdict

logger = logging.getLogger(__name__)


class SectorRotationDetector:
    """
    Detects sector rotation (capital flowing from one sector to another).

    When institutional money rotates into a sector, ALL stocks in that
    sector tend to rise together. Catching rotation early = alpha.

    Signals:
    - Sector ETF outperforming SPY
    - Multiple stocks in sector making new highs
    - Increasing volume across sector
    - Relative strength improving
    """

    @staticmethod
    def detect_sector_rotation(
        sector: str,
        sector_etf_return_5d: float,
        spy_return_5d: float,
        stocks_at_new_highs: int,
        total_stocks_in_sector: int,
        sector_volume_ratio: float,
        sector_relative_strength: float
    ) -> Dict:
        """
        Detect if capital is rotating into sector.

        Args:
            sector: Sector name (e.g., 'Technology', 'Healthcare')
            sector_etf_return_5d: Sector ETF 5-day return %
            spy_return_5d: SPY 5-day return %
            stocks_at_new_highs: # stocks at 52-week highs
            total_stocks_in_sector: Total stocks in sector
            sector_volume_ratio: Current volume / avg volume
            sector_relative_strength: Relative to market (0-100)

        Returns:
            Dict with rotation analysis
        """
        score = 0
        signals = []

        # Sector outperforming market
        outperformance = sector_etf_return_5d - spy_return_5d

        if outperformance > 5:
            score += 40
            signals.append(f"STRONG outperformance: +{outperformance:.1f}% vs SPY")
        elif outperformance > 3:
            score += 30
            signals.append(f"Outperforming: +{outperformance:.1f}% vs market")
        elif outperformance > 1:
            score += 15
            signals.append(f"Modest outperformance: +{outperformance:.1f}%")

        # Breadth (% stocks at new highs)
        if total_stocks_in_sector > 0:
            new_high_pct = (stocks_at_new_highs / total_stocks_in_sector) * 100

            if new_high_pct > 20:
                score += 30
                signals.append(f"Wide breadth: {new_high_pct:.0f}% at new highs")
            elif new_high_pct > 10:
                score += 20
                signals.append(f"Good breadth: {new_high_pct:.0f}% at highs")

        # Volume (institutions buying)
        if sector_volume_ratio > 1.5:
            score += 20
            signals.append(f"Volume surge: {sector_volume_ratio:.1f}x average")

        # Relative strength
        if sector_relative_strength > 70:
            score += 10
            signals.append(f"Strong momentum: RS = {sector_relative_strength:.0f}")

        return {
            'sector': sector,
            'is_rotating_in': score >= 50,
            'score': min(score, 100),
            'signals': signals,
            'outperformance': outperformance,
            'new_high_pct': new_high_pct if 'new_high_pct' in locals() else 0,
            'interpretation': 'STRONG rotation into sector' if score >= 70 else 'Capital flowing in' if score >= 50 else 'Neutral'
        }


class LiquiditySweepDetector:
    """
    Detects liquidity sweeps (stop hunts before reversals).

    Market makers often hunt stops below support/above resistance
    before reversing. These create amazing entries.

    Characteristics:
    - Spike below support, immediate reversal
    - High volume on sweep, low volume after
    - Long wick on candlestick
    - Happens at round numbers ($10, $50, $100)
    """

    @staticmethod
    def detect_liquidity_sweep(
        ticker: str,
        current_price: float,
        intraday_low: float,
        support_level: float,
        close_price: float,
        volume_on_sweep: int,
        avg_volume: int,
        wick_size_pct: float
    ) -> Dict:
        """
        Detect liquidity sweep setup.

        Args:
            ticker: Stock ticker
            current_price: Current price
            intraday_low: Today's low
            support_level: Key support level
            close_price: Close price
            volume_on_sweep: Volume during sweep
            avg_volume: Average volume
            wick_size_pct: Wick size as % of candle

        Returns:
            Dict with sweep analysis
        """
        score = 0
        signals = []

        # Did price sweep below support?
        if intraday_low < support_level:
            sweep_distance = ((support_level - intraday_low) / support_level) * 100

            # Immediate reversal (closed above support)
            if close_price > support_level:
                score += 50
                signals.append(f"SWEEP & REVERSAL: Dipped {sweep_distance:.1f}% below support, recovered")

                # Long lower wick (classic liquidity grab)
                if wick_size_pct > 60:
                    score += 20
                    signals.append(f"Long wick: {wick_size_pct:.0f}% (stop hunt)")

                # Volume spike on sweep
                if avg_volume > 0:
                    volume_ratio = volume_on_sweep / avg_volume
                    if volume_ratio > 2.0:
                        score += 15
                        signals.append(f"Volume on sweep: {volume_ratio:.1f}x (shakeout)")

                # Round number (institutions love these levels)
                if support_level in [5, 10, 15, 20, 25, 30, 40, 50, 75, 100]:
                    score += 15
                    signals.append(f"Swept round number: ${support_level:.0f}")

        return {
            'ticker': ticker,
            'is_liquidity_sweep': score >= 50,
            'score': min(score, 100),
            'signals': signals,
            'support_level': support_level,
            'sweep_distance': sweep_distance if 'sweep_distance' in locals() else 0,
            'interpretation': 'HIGH probability reversal' if score >= 70 else 'Potential reversal setup' if score >= 50 else 'No sweep'
        }


class MultiSignalConfluence:
    """
    Scores based on multiple independent signals converging.

    When 4+ different signals fire simultaneously, probability of
    success is dramatically higher than single signal.

    Tracks:
    - Technical signals (compression, volume, RSI)
    - Fundamental signals (earnings, revenue growth)
    - Flow signals (insider, options, dark pool)
    - Sentiment signals (news, social, analyst upgrades)
    """

    @staticmethod
    def calculate_confluence_score(
        ticker: str,
        signals: Dict[str, bool]
    ) -> Dict:
        """
        Calculate confluence score from multiple signals.

        Args:
            ticker: Stock ticker
            signals: Dict of signal name -> True/False

        Returns:
            Dict with confluence analysis
        """
        active_signals = [name for name, is_active in signals.items() if is_active]
        num_signals = len(active_signals)

        # Score based on number of signals
        if num_signals >= 5:
            score = 95
            confidence = 'EXTREME'
        elif num_signals >= 4:
            score = 85
            confidence = 'VERY HIGH'
        elif num_signals >= 3:
            score = 70
            confidence = 'HIGH'
        elif num_signals >= 2:
            score = 55
            confidence = 'MEDIUM'
        else:
            score = 30
            confidence = 'LOW'

        # Group signals by category
        categories = {
            'technical': ['compression', 'volume_spike', 'rsi_oversold', 'macd_cross', 'break_resistance'],
            'fundamental': ['earnings_beat', 'revenue_growth', 'positive_guidance', 'contract_win'],
            'flow': ['insider_buy', 'options_sweep', 'dark_pool', 'institutional_buying'],
            'sentiment': ['news_positive', 'social_trending', 'analyst_upgrade', 'influencer_mention']
        }

        category_coverage = {}
        for category, category_signals in categories.items():
            category_active = [s for s in category_signals if signals.get(s, False)]
            category_coverage[category] = len(category_active)

        # Bonus for coverage across multiple categories
        categories_with_signals = sum(1 for count in category_coverage.values() if count > 0)
        if categories_with_signals >= 4:
            score += 10
        elif categories_with_signals >= 3:
            score += 5

        return {
            'ticker': ticker,
            'confluence_score': min(score, 100),
            'confidence': confidence,
            'num_signals': num_signals,
            'active_signals': active_signals,
            'category_coverage': category_coverage,
            'interpretation': f'{num_signals} signals aligned across {categories_with_signals} categories'
        }


class RiskFilter:
    """
    Filters out high-risk plays (avoid landmines).

    Excludes:
    - Stocks near all-time highs (overextended)
    - Negative cash flow (bankruptcy risk)
    - Heavy dilution history
    - Upcoming lock-up expiry
    - Regulatory issues
    - Accounting concerns
    """

    @staticmethod
    def assess_risk(
        ticker: str,
        distance_to_ath_pct: float,
        free_cash_flow: float,
        share_dilution_1yr: float,
        days_until_lockup_expiry: Optional[int],
        has_sec_investigation: bool,
        has_going_concern_warning: bool,
        borrow_fee_rate: Optional[float]
    ) -> Dict:
        """
        Assess risk factors.

        Args:
            ticker: Stock ticker
            distance_to_ath_pct: % from all-time high
            free_cash_flow: Free cash flow (negative = burning)
            share_dilution_1yr: % dilution in last year
            days_until_lockup_expiry: Days until shares unlock
            has_sec_investigation: SEC investigation ongoing
            has_going_concern_warning: Going concern warning
            borrow_fee_rate: Borrow fee % (high = risky)

        Returns:
            Dict with risk assessment
        """
        risk_score = 0
        red_flags = []
        warnings = []

        # Near ATH (overextended)
        if distance_to_ath_pct < 5:
            risk_score += 25
            red_flags.append(f"Near ATH: {distance_to_ath_pct:.1f}% from peak (overextended)")
        elif distance_to_ath_pct < 10:
            risk_score += 10
            warnings.append(f"Close to ATH: {distance_to_ath_pct:.1f}% from peak")

        # Negative cash flow
        if free_cash_flow < 0:
            risk_score += 30
            red_flags.append(f"Burning cash: ${abs(free_cash_flow)/1e6:.0f}M negative FCF")

        # Dilution
        if share_dilution_1yr > 20:
            risk_score += 25
            red_flags.append(f"Heavy dilution: {share_dilution_1yr:.0f}% shares added")
        elif share_dilution_1yr > 10:
            risk_score += 15
            warnings.append(f"Moderate dilution: {share_dilution_1yr:.0f}%")

        # Lock-up expiry (insider selling coming)
        if days_until_lockup_expiry is not None and days_until_lockup_expiry < 30:
            risk_score += 20
            warnings.append(f"Lock-up expires in {days_until_lockup_expiry} days")

        # Regulatory issues
        if has_sec_investigation:
            risk_score += 40
            red_flags.append("SEC investigation ongoing")

        if has_going_concern_warning:
            risk_score += 50
            red_flags.append("GOING CONCERN WARNING (bankruptcy risk)")

        # Extreme borrow fee (squeeze risk, but also risky)
        if borrow_fee_rate is not None and borrow_fee_rate > 100:
            risk_score += 15
            warnings.append(f"Extreme borrow fee: {borrow_fee_rate:.0f}% (volatile)")

        # Determine risk level
        if risk_score >= 60:
            risk_level = 'EXTREME'
            should_avoid = True
        elif risk_score >= 40:
            risk_level = 'HIGH'
            should_avoid = True
        elif risk_score >= 20:
            risk_level = 'MODERATE'
            should_avoid = False
        else:
            risk_level = 'LOW'
            should_avoid = False

        return {
            'ticker': ticker,
            'risk_score': risk_score,
            'risk_level': risk_level,
            'should_avoid': should_avoid,
            'red_flags': red_flags,
            'warnings': warnings,
            'interpretation': f'AVOID - {len(red_flags)} red flags' if should_avoid else 'Acceptable risk'
        }


class CryptoEdgeStrategies:
    """
    Crypto-specific edge strategies.

    Opportunities unique to crypto:
    - Exchange listings (pump on listing announcement)
    - Token unlock schedules (supply shock)
    - Whale wallet tracking (follow smart money)
    - Developer activity (GitHub commits)
    - Smart contract audits (safety signal)
    """

    @staticmethod
    def detect_exchange_listing_potential(
        coin: str,
        market_cap: float,
        daily_volume: float,
        exchanges_listed: List[str],
        developer_activity_score: int,
        community_size: int
    ) -> Dict:
        """
        Detect coins likely to get major exchange listings.

        Binance/Coinbase listings often 2-10x prices.

        Args:
            coin: Coin symbol
            market_cap: Market cap
            daily_volume: 24h volume
            exchanges_listed: Current exchanges
            developer_activity_score: GitHub activity (0-100)
            community_size: Twitter/Discord followers

        Returns:
            Dict with listing potential
        """
        score = 0
        signals = []

        major_exchanges = {'Binance', 'Coinbase', 'Kraken', 'Gemini'}
        listed_major = set(exchanges_listed) & major_exchanges
        missing_major = major_exchanges - listed_major

        # Not on major exchanges yet (listing potential)
        if len(missing_major) > 0:
            score += 30
            signals.append(f"Not on {len(missing_major)} major exchanges (listing catalyst)")

        # Right size (too small = won't list, too big = already listed)
        if 50_000_000 < market_cap < 500_000_000:
            score += 25
            signals.append(f"Sweet spot market cap: ${market_cap/1e6:.0f}M")

        # Good volume (exchanges want liquid coins)
        if daily_volume > 1_000_000:
            score += 20
            signals.append(f"Strong volume: ${daily_volume/1e6:.1f}M daily")

        # Active development
        if developer_activity_score > 70:
            score += 15
            signals.append(f"Active development: {developer_activity_score}/100")

        # Community size
        if community_size > 50_000:
            score += 10
            signals.append(f"Large community: {community_size:,} followers")

        return {
            'coin': coin,
            'listing_potential_score': min(score, 100),
            'signals': signals,
            'missing_exchanges': list(missing_major),
            'interpretation': 'HIGH listing potential' if score >= 70 else 'Moderate potential' if score >= 50 else 'Low potential'
        }

    @staticmethod
    def detect_token_unlock_risk(
        coin: str,
        current_circulating: float,
        max_supply: float,
        next_unlock_date: datetime,
        unlock_amount: float,
        current_price: float
    ) -> Dict:
        """
        Detect upcoming token unlock risk.

        Token unlocks = supply shock = price dump (usually).

        Args:
            coin: Coin symbol
            current_circulating: Current circulating supply
            max_supply: Maximum supply
            next_unlock_date: Date of next unlock
            unlock_amount: # tokens unlocking
            current_price: Current price

        Returns:
            Dict with unlock risk
        """
        risk_score = 0
        warnings = []

        days_until_unlock = (next_unlock_date - datetime.now()).days

        # Upcoming unlock
        if days_until_unlock < 30:
            unlock_pct = (unlock_amount / current_circulating) * 100

            if unlock_pct > 20:
                risk_score = 80
                warnings.append(f"MAJOR unlock in {days_until_unlock} days: {unlock_pct:.0f}% supply increase")
            elif unlock_pct > 10:
                risk_score = 60
                warnings.append(f"Significant unlock: {unlock_pct:.0f}% in {days_until_unlock} days")
            elif unlock_pct > 5:
                risk_score = 40
                warnings.append(f"Moderate unlock: {unlock_pct:.0f}% incoming")

        return {
            'coin': coin,
            'unlock_risk_score': risk_score,
            'days_until_unlock': days_until_unlock,
            'unlock_pct': unlock_pct if 'unlock_pct' in locals() else 0,
            'warnings': warnings,
            'interpretation': 'HIGH RISK - avoid' if risk_score >= 60 else 'Moderate risk' if risk_score >= 40 else 'Low risk'
        }


def create_advanced_screener(
    enable_sector_rotation: bool = True,
    enable_liquidity_sweeps: bool = True,
    enable_confluence: bool = True,
    enable_risk_filter: bool = True,
    enable_crypto_edge: bool = True
) -> Dict[str, any]:
    """
    Create advanced screener with all filters.

    Returns:
        Dict with screener configuration
    """
    return {
        'sector_rotation': enable_sector_rotation,
        'liquidity_sweeps': enable_liquidity_sweeps,
        'multi_signal_confluence': enable_confluence,
        'risk_filter': enable_risk_filter,
        'crypto_edge': enable_crypto_edge,
        'description': 'Advanced screener with edge-finding strategies'
    }


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    print("="*80)
    print("🎯 ADVANCED FILTERING STRATEGIES")
    print("="*80)
    print()
    print("Additional edge-finding filters:")
    print()
    print("1. Sector Rotation Detection")
    print("   → Catch capital flows between sectors")
    print()
    print("2. Liquidity Sweep Detection")
    print("   → Stop hunts before reversals (amazing entries)")
    print()
    print("3. Multi-Signal Confluence")
    print("   → 4+ signals = highest conviction plays")
    print()
    print("4. Risk Filters")
    print("   → Avoid landmines (dilution, bankruptcy, SEC issues)")
    print()
    print("5. Crypto Edge Strategies")
    print("   → Exchange listings, token unlocks, whale tracking")
    print()
    print("="*80)
    print()
    print("💡 Pro Tip:")
    print("Combine early detection + advanced filters for maximum edge")
    print("Best plays = Pre-breakout + Multi-signal confluence + Low risk")
    print("="*80)
