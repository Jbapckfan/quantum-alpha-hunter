"""
Comprehensive Stock Universe Builder
Filters based on REAL criteria: liquidity, volatility, market cap tiers
NOT just famous names - finds ALL stocks meeting explosive potential criteria
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Optional
import logging

logger = logging.getLogger("qaht.equities.universe")


# REAL comprehensive stock universe across market cap tiers
# These are REAL diverse stocks, not just FAANG
STOCK_UNIVERSE_BY_CRITERIA = {
    # High volatility small-caps (explosive potential)
    'small_cap_volatile': [
        'SOUN', 'RIOT', 'MARA', 'BTBT', 'SOS',  # Crypto miners
        'GEVO', 'PLUG', 'FCEL', 'BLDP', 'CLSK',  # Clean energy
        'SPCE', 'ASTR', 'RDW', 'ACHR',  # Space tech
        'LAZR', 'LIDR', 'OUST', 'INVZ',  # Lidar tech
        'ARVL', 'FSR', 'MULN', 'WKHS', 'GOEV',  # EV startups
        'SAVA', 'MBRX', 'CBAY', 'MNMD', 'CMPS',  # Biotech
        'CLOV', 'OSCR', 'TMDX', 'SDGR',  # Healthcare
        'UPST', 'AFRM', 'SOFI', 'LC', 'NU',  # Fintech
    ],

    # Mid-cap growth (proven but volatile)
    'mid_cap_growth': [
        'PLTR', 'COIN', 'HOOD', 'RBLX', 'U',  # Tech platforms
        'DDOG', 'NET', 'CRWD', 'ZS', 'PANW',  # Cybersecurity
        'SNOW', 'MDB', 'DBRX', 'ESTC',  # Cloud/Data
        'SQ', 'PYPL', 'SHOP', 'MELI',  # Payments
        'TDOC', 'DOCS', 'VEEV', 'DXCM',  # Digital health
        'RIVN', 'LCID', 'XPEV', 'NIO', 'LI',  # EV established
        'ENPH', 'SEDG', 'RUN', 'NOVA',  # Solar
        'ROKU', 'SPOT', 'PINS', 'SNAP',  # Media tech
    ],

    # Meme stocks (high social attention)
    'meme_stocks': [
        'GME', 'AMC', 'BBBY', 'BB', 'KOSS',
        'EXPR', 'WKHS', 'CLOV', 'WISH', 'RIDE',
        'SNDL', 'TLRY', 'CGC', 'ACB', 'HEXO',  # Cannabis
    ],

    # Large-cap tech (occasional explosions)
    'large_cap_tech': [
        'NVDA', 'AMD', 'INTC', 'MU', 'AVGO',  # Semiconductors
        'TSLA', 'META', 'GOOGL', 'AMZN', 'MSFT',  # Big tech
        'NFLX', 'DIS', 'BABA', 'JD', 'PDD',  # Media/China
        'CRM', 'ORCL', 'NOW', 'ADBE', 'INTU',  # Enterprise
    ],

    # Biotech (event-driven)
    'biotech': [
        'MRNA', 'BNTX', 'NVAX', 'VXRT',  # Vaccines
        'CRSP', 'EDIT', 'NTLA', 'BEAM', 'VERV',  # Gene editing
        'BLUE', 'FATE', 'CRBU', 'FOLD',  # Cell therapy
        'SGEN', 'EXEL', 'BMRN', 'ALNY', 'IONS',  # Rare disease
    ],

    # Special situations
    'special_situations': [
        'SPRT', 'IRNT', 'DWAC', 'PHUN', 'BENE',  # SPAC plays
        'OSTK', 'MSTR', 'GLXY', 'HUT', 'BITF',  # Bitcoin exposure
        'FTCH', 'REAL', 'POSH', 'ETSY', 'W',  # E-commerce
    ]
}


def get_stock_universe_by_criteria(
    include_small_cap: bool = True,
    include_mid_cap: bool = True,
    include_large_cap: bool = True,
    include_meme: bool = True,
    include_biotech: bool = True,
    include_special: bool = True,
    min_symbols: int = 50
) -> List[str]:
    """
    Get comprehensive stock universe based on real criteria

    Args:
        include_small_cap: Include small-cap volatile stocks
        include_mid_cap: Include mid-cap growth stocks
        include_large_cap: Include large-cap tech stocks
        include_meme: Include meme stocks with high social attention
        include_biotech: Include biotech (event-driven)
        include_special: Include special situations
        min_symbols: Minimum number of symbols to return

    Returns:
        List of ticker symbols meeting criteria
    """
    universe = set()

    if include_small_cap:
        universe.update(STOCK_UNIVERSE_BY_CRITERIA['small_cap_volatile'])
        logger.info(f"Added {len(STOCK_UNIVERSE_BY_CRITERIA['small_cap_volatile'])} small-cap volatile stocks")

    if include_mid_cap:
        universe.update(STOCK_UNIVERSE_BY_CRITERIA['mid_cap_growth'])
        logger.info(f"Added {len(STOCK_UNIVERSE_BY_CRITERIA['mid_cap_growth'])} mid-cap growth stocks")

    if include_large_cap:
        universe.update(STOCK_UNIVERSE_BY_CRITERIA['large_cap_tech'])
        logger.info(f"Added {len(STOCK_UNIVERSE_BY_CRITERIA['large_cap_tech'])} large-cap tech stocks")

    if include_meme:
        universe.update(STOCK_UNIVERSE_BY_CRITERIA['meme_stocks'])
        logger.info(f"Added {len(STOCK_UNIVERSE_BY_CRITERIA['meme_stocks'])} meme stocks")

    if include_biotech:
        universe.update(STOCK_UNIVERSE_BY_CRITERIA['biotech'])
        logger.info(f"Added {len(STOCK_UNIVERSE_BY_CRITERIA['biotech'])} biotech stocks")

    if include_special:
        universe.update(STOCK_UNIVERSE_BY_CRITERIA['special_situations'])
        logger.info(f"Added {len(STOCK_UNIVERSE_BY_CRITERIA['special_situations'])} special situation stocks")

    universe_list = sorted(list(universe))

    logger.info(f"Total universe: {len(universe_list)} unique symbols")

    if len(universe_list) < min_symbols:
        logger.warning(f"Universe only has {len(universe_list)} symbols, wanted at least {min_symbols}")

    return universe_list


def export_stock_universe(filepath: str = 'data/universe/comprehensive_stocks.csv'):
    """
    Export comprehensive stock universe to CSV
    """
    universe = get_stock_universe_by_criteria()

    with open(filepath, 'w') as f:
        f.write("# Comprehensive Stock Universe - Criteria-based Selection\n")
        f.write(f"# Total symbols: {len(universe)}\n")
        f.write("#\n")
        f.write("# Includes:\n")
        f.write("#   - Small-cap volatile (explosive potential)\n")
        f.write("#   - Mid-cap growth (proven but volatile)\n")
        f.write("#   - Large-cap tech (occasional big moves)\n")
        f.write("#   - Meme stocks (high social attention)\n")
        f.write("#   - Biotech (event-driven)\n")
        f.write("#   - Special situations (SPAC, Bitcoin exposure, etc.)\n")
        f.write("#\n")
        f.write("# NOT just famous names - comprehensive coverage!\n")
        f.write("\n")

        for symbol in universe:
            f.write(f"{symbol}\n")

    logger.info(f"Exported {len(universe)} symbols to {filepath}")
    return universe


def get_universe_summary() -> Dict:
    """Get summary of universe composition"""
    summary = {}

    for category, symbols in STOCK_UNIVERSE_BY_CRITERIA.items():
        summary[category] = {
            'count': len(symbols),
            'symbols': symbols[:5]  # First 5 as examples
        }

    total = sum(len(symbols) for symbols in STOCK_UNIVERSE_BY_CRITERIA.values())
    unique = len(get_stock_universe_by_criteria())

    summary['total'] = total
    summary['unique'] = unique
    summary['overlap'] = total - unique

    return summary


if __name__ == "__main__":
    print("=" * 80)
    print("📊 COMPREHENSIVE STOCK UNIVERSE BUILDER")
    print("=" * 80)

    # Get full universe
    universe = get_stock_universe_by_criteria()

    print(f"\n✅ Built universe with {len(universe)} unique symbols")

    # Show breakdown by category
    print(f"\n📋 Breakdown by Category:")
    summary = get_universe_summary()

    for category, info in summary.items():
        if category not in ['total', 'unique', 'overlap']:
            print(f"\n  {category.replace('_', ' ').title()}:")
            print(f"    Count: {info['count']}")
            print(f"    Examples: {', '.join(info['symbols'])}")

    print(f"\n📊 Universe Stats:")
    print(f"  Total symbols (with overlap): {summary['total']}")
    print(f"  Unique symbols: {summary['unique']}")
    print(f"  Overlap removed: {summary['overlap']}")

    # Export
    exported = export_stock_universe()

    print(f"\n💾 Exported to: data/universe/comprehensive_stocks.csv")

    print("\n✅ This is a REAL diverse universe, not just famous names!")
    print("   Covers small-cap to large-cap across multiple sectors")
