"""
Filters for "agile fast movers" - stocks that can rapidly move 50%+ but have solid fundamentals.

Examples: OPEN, RZLV, RXRX, RGTI, SRFM, JMIA

Characteristics:
- Mid-cap to small-cap ($300M - $20B)
- High volatility (beta > 1.5 or ATR > 5%)
- Real business with products/revenue
- Growth sectors: tech, biotech, fintech, clean energy, AI
- NOT penny stocks (price > $5 preferred)
- Good liquidity (volume > 500K, preferably > 1M)
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class AgileMoverFilter:
    """
    Identifies "agile fast movers" - quality stocks with 50%+ movement potential.

    Unlike penny stocks or mega-caps, these are in the sweet spot:
    - Established enough to have real business
    - Small enough to move quickly (high beta)
    - Innovative sectors with growth catalysts
    """

    # Target sectors for agile movers
    GROWTH_SECTORS = {
        'ai_ml': [
            'RXRX',  # Recursion Pharma (AI drug discovery)
            'RZLV',  # Rezolve AI (AI retail)
            'AI',    # C3.ai
            'BBAI',  # BigBear.ai
            'SOUN',  # SoundHound AI
        ],
        'quantum_computing': [
            'RGTI',  # Rigetti Computing
            'IONQ',  # IonQ
            'QUBT',  # Quantum Computing Inc
        ],
        'fintech': [
            'SOFI',  # SoFi
            'UPST',  # Upstart
            'AFRM',  # Affirm
            'LC',    # LendingClub
            'NU',    # Nu Holdings
        ],
        'proptech': [
            'OPEN',  # Opendoor
            'RDFN',  # Redfin
            'COMP',  # Compass
        ],
        'mobility': [
            'SRFM',  # Surf Air Mobility
            'JOBY',  # Joby Aviation
            'ACHR',  # Archer Aviation
            'EVTL',  # Vertical Aerospace
        ],
        'emerging_markets': [
            'JMIA',  # Jumia (African e-commerce)
            'GRAB',  # Grab (SE Asian super-app)
            'SEA',   # Sea Limited
        ],
        'clean_energy': [
            'PLUG',  # Plug Power
            'FCEL',  # FuelCell Energy
            'BLDP',  # Ballard Power
            'CLSK',  # CleanSpark
        ],
        'biotech_innovation': [
            'CRSP',  # CRISPR Therapeutics
            'EDIT',  # Editas Medicine
            'NTLA',  # Intellia Therapeutics
            'BEAM',  # Beam Therapeutics
        ],
        'space_tech': [
            'SPCE',  # Virgin Galactic
            'ASTR',  # Astra Space
            'RDW',   # Redwire
        ]
    }

    @staticmethod
    def get_filter_criteria() -> Dict[str, any]:
        """
        Get recommended filter criteria for agile movers.

        Returns:
            Dict with filter parameters
        """
        return {
            # Price filters
            'min_price': 5.0,           # Avoid penny stocks
            'max_price': 500.0,         # Avoid mega-caps (indirectly)

            # Liquidity filters
            'min_avg_volume': 500_000,  # Minimum tradeable
            'preferred_volume': 1_000_000,  # Better liquidity

            # Market cap filters (sweet spot for movement)
            'min_market_cap': 300_000_000,      # $300M (small-cap floor)
            'max_market_cap': 20_000_000_000,   # $20B (mid-cap ceiling)
            'optimal_range': (500_000_000, 5_000_000_000),  # $500M-$5B best

            # Volatility filters (movement potential)
            'min_beta': 1.5,            # Higher volatility than market
            'min_atr_pct': 5.0,         # 5%+ daily ATR
            'preferred_atr_pct': 8.0,   # 8%+ is ideal

            # Fundamental filters (quality check)
            'min_revenue': 10_000_000,  # $10M revenue (real business)
            'has_products': True,       # Not pre-revenue
            'exclude_pure_speculation': True,  # Must have business model
        }

    @staticmethod
    def get_agile_mover_universe() -> List[str]:
        """
        Get comprehensive list of agile mover candidates.

        Returns:
            List of stock symbols
        """
        all_symbols = []
        for sector, symbols in AgileMoverFilter.GROWTH_SECTORS.items():
            all_symbols.extend(symbols)

        # Remove duplicates
        return list(set(all_symbols))

    @staticmethod
    def get_universe_by_sector(sector: str) -> List[str]:
        """
        Get agile movers in specific sector.

        Args:
            sector: One of: ai_ml, quantum_computing, fintech, proptech,
                    mobility, emerging_markets, clean_energy,
                    biotech_innovation, space_tech

        Returns:
            List of stock symbols in that sector
        """
        return AgileMoverFilter.GROWTH_SECTORS.get(sector, [])

    @staticmethod
    def score_agile_mover_potential(stock_data: Dict[str, any]) -> Dict[str, any]:
        """
        Score a stock's potential as an "agile fast mover".

        Args:
            stock_data: Dict with keys: price, market_cap, volume, beta, atr_pct,
                        revenue, sector

        Returns:
            Dict with score (0-100) and reasoning
        """
        score = 0
        reasons = []
        flags = []

        # Extract data
        price = stock_data.get('price', 0)
        market_cap = stock_data.get('market_cap', 0)
        volume = stock_data.get('avg_volume', 0)
        beta = stock_data.get('beta', 1.0)
        atr_pct = stock_data.get('atr_pct', 0)
        revenue = stock_data.get('revenue', 0)
        sector = stock_data.get('sector', '')

        # 1. Market Cap (30 points) - Sweet spot for movement
        if 500_000_000 <= market_cap <= 5_000_000_000:
            score += 30
            reasons.append(f"Optimal market cap ${market_cap/1e9:.1f}B (sweet spot for 50%+ moves)")
        elif 300_000_000 <= market_cap < 500_000_000:
            score += 25
            reasons.append(f"Small-cap ${market_cap/1e9:.1f}B (high movement potential)")
        elif 5_000_000_000 < market_cap <= 20_000_000_000:
            score += 20
            reasons.append(f"Mid-cap ${market_cap/1e9:.1f}B (moderate movement potential)")
        else:
            score += 5
            flags.append(f"Market cap ${market_cap/1e9:.1f}B outside optimal range")

        # 2. Volatility (25 points) - Movement potential
        if atr_pct >= 8.0:
            score += 25
            reasons.append(f"High volatility (ATR {atr_pct:.1f}%)")
        elif atr_pct >= 5.0:
            score += 20
            reasons.append(f"Good volatility (ATR {atr_pct:.1f}%)")
        elif atr_pct >= 3.0:
            score += 10
            flags.append(f"Moderate volatility (ATR {atr_pct:.1f}%)")
        else:
            score += 0
            flags.append(f"Low volatility (ATR {atr_pct:.1f}%)")

        if beta >= 2.0:
            score += 10
            reasons.append(f"Very high beta ({beta:.1f})")
        elif beta >= 1.5:
            score += 8
            reasons.append(f"High beta ({beta:.1f})")
        elif beta >= 1.0:
            score += 5

        # 3. Liquidity (15 points) - Tradeability
        if volume >= 2_000_000:
            score += 15
            reasons.append(f"Excellent liquidity ({volume/1e6:.1f}M volume)")
        elif volume >= 1_000_000:
            score += 12
            reasons.append(f"Good liquidity ({volume/1e6:.1f}M volume)")
        elif volume >= 500_000:
            score += 8
            flags.append(f"Adequate liquidity ({volume/1e6:.1f}M volume)")
        else:
            score += 3
            flags.append(f"Low liquidity ({volume/1e6:.1f}M volume)")

        # 4. Price Range (10 points) - Avoid penny stocks
        if 10.0 <= price <= 100.0:
            score += 10
            reasons.append(f"Good price range (${price:.2f})")
        elif 5.0 <= price < 10.0:
            score += 8
            reasons.append(f"Acceptable price (${price:.2f})")
        elif price >= 100.0:
            score += 6
        else:
            score += 2
            flags.append(f"Low price (${price:.2f}) - penny stock risk")

        # 5. Fundamentals (20 points) - Quality check
        if revenue >= 100_000_000:
            score += 20
            reasons.append(f"Strong revenue (${revenue/1e6:.0f}M)")
        elif revenue >= 10_000_000:
            score += 15
            reasons.append(f"Established revenue (${revenue/1e6:.0f}M)")
        elif revenue >= 1_000_000:
            score += 8
            flags.append(f"Early revenue (${revenue/1e6:.0f}M)")
        else:
            score += 3
            flags.append("Pre-revenue or very early stage")

        # 6. Sector Bonus (5 points) - Growth catalysts
        if sector in AgileMoverFilter.GROWTH_SECTORS:
            score += 5
            reasons.append(f"High-growth sector ({sector})")

        return {
            'score': min(score, 100),
            'rating': 'EXCELLENT' if score >= 80 else 'GOOD' if score >= 60 else 'MODERATE' if score >= 40 else 'POOR',
            'reasons': reasons,
            'flags': flags
        }

    @staticmethod
    def explain_agile_mover_criteria():
        """Print explanation of what makes a good agile mover."""
        print("="*80)
        print("🚀 AGILE FAST MOVER CRITERIA")
        print("="*80)
        print()
        print("Target: Stocks that can move 50%+ rapidly with solid fundamentals")
        print()
        print("Examples:")
        print("  OPEN (Opendoor) - Proptech, real business, volatile")
        print("  RZLV (Rezolve AI) - AI retail, innovative, high growth")
        print("  RXRX (Recursion) - AI drug discovery, cutting-edge")
        print("  RGTI (Rigetti) - Quantum computing, frontier tech")
        print("  SRFM (Surf Air) - Electric aviation, transformative")
        print("  JMIA (Jumia) - African e-commerce, emerging market")
        print()
        print("="*80)
        print("📊 FILTER CRITERIA")
        print("="*80)
        print()
        print("1. Market Cap: $300M - $20B (sweet spot: $500M - $5B)")
        print("   ✅ Big enough to have real business")
        print("   ✅ Small enough to move quickly")
        print("   ❌ Avoid penny stocks (< $300M)")
        print("   ❌ Avoid mega-caps (> $20B too slow)")
        print()
        print("2. Volatility: ATR > 5%, Beta > 1.5")
        print("   ✅ Can move 50%+ in days/weeks")
        print("   ✅ Options premiums worthwhile")
        print()
        print("3. Liquidity: Volume > 500K (prefer > 1M)")
        print("   ✅ Easy to enter/exit positions")
        print("   ✅ Tight bid-ask spreads")
        print()
        print("4. Price: $5 - $500")
        print("   ✅ Avoid penny stocks (< $5)")
        print("   ✅ Avoid ultra high-priced (harder to move %)")
        print()
        print("5. Fundamentals: Revenue > $10M")
        print("   ✅ Real business with products")
        print("   ✅ Not pure speculation")
        print("   ✅ Can justify valuations")
        print()
        print("6. Sectors: AI, quantum, fintech, proptech, mobility,")
        print("            emerging markets, clean energy, biotech, space")
        print("   ✅ Growth catalysts")
        print("   ✅ Innovation potential")
        print("   ✅ Market attention")
        print()
        print("="*80)
        print("🎯 WHY THIS WORKS")
        print("="*80)
        print()
        print("Unlike:")
        print("  ❌ Penny stocks (SOUN, BTBT) - No fundamentals, pure speculation")
        print("  ❌ Mega-caps (AAPL, MSFT) - Too big to move 50%+ quickly")
        print("  ❌ Meme stocks (GME, AMC) - Hype-driven, no business logic")
        print()
        print("Agile movers have:")
        print("  ✅ Real business + revenue")
        print("  ✅ Growth potential (can double valuation)")
        print("  ✅ Market cap sweet spot (big moves possible)")
        print("  ✅ Volatility (compression → explosion works)")
        print("="*80)


if __name__ == '__main__':
    filter_obj = AgileMoverFilter()

    # Show criteria
    filter_obj.explain_agile_mover_criteria()

    print()
    print("="*80)
    print("📋 AGILE MOVER UNIVERSE")
    print("="*80)
    print()

    for sector, symbols in AgileMoverFilter.GROWTH_SECTORS.items():
        print(f"{sector.replace('_', ' ').title()}:")
        print(f"  {', '.join(symbols)}")
        print()

    total = len(filter_obj.get_agile_mover_universe())
    print(f"Total agile movers tracked: {total}")
    print("="*80)
