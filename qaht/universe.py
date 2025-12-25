"""
Universe management - filter symbols for multi-bagger potential
CRITICAL: No mega-caps (AAPL, TSLA, NVDA) - they can't 10x
"""
import yfinance as yf
import pandas as pd
from typing import List, Dict, Optional, Tuple
import logging

logger = logging.getLogger("qaht.universe")

# Mega-cap blocklist - these can NEVER be multi-baggers
# Market cap > $500B = too big to 10x
MEGA_CAP_BLOCKLIST = {
    # Tech Giants ($1T+)
    'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'NVDA', 'META', 'TSLA',

    # Financial Giants
    'BRK.A', 'BRK.B', 'JPM', 'V', 'MA', 'BAC', 'WFC',

    # Consumer Giants
    'JNJ', 'WMT', 'PG', 'KO', 'PEP', 'COST', 'HD', 'NKE',

    # Other Mega-Caps
    'CVX', 'XOM', 'MRK', 'ABBV', 'TMO', 'ORCL', 'ACN',
    'DIS', 'CSCO', 'ABT', 'CRM', 'VZ', 'ADBE', 'TXN',
    'INTC', 'AMD', 'QCOM', 'UNH', 'LLY', 'PFE', 'NVO',

    # Indices/ETFs
    'SPY', 'QQQ', 'IWM', 'DIA', 'VOO', 'VTI'
}


def get_market_cap(symbol: str) -> Optional[float]:
    """
    Get market capitalization for a symbol

    Args:
        symbol: Ticker symbol

    Returns:
        Market cap in USD or None if unavailable
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        market_cap = info.get('marketCap')
        return float(market_cap) if market_cap else None
    except Exception as e:
        logger.warning(f"Could not get market cap for {symbol}: {e}")
        return None


def filter_by_market_cap(
    symbols: List[str],
    min_market_cap: float = 100_000_000,      # $100M minimum (avoid penny stocks)
    max_market_cap: float = 10_000_000_000,   # $10B maximum (room to grow)
    fetch_caps: bool = True
) -> Tuple[List[str], Dict[str, str]]:
    """
    Filter symbols by market cap for multi-bagger potential

    Args:
        symbols: List of symbols to filter
        min_market_cap: Minimum market cap ($100M default)
        max_market_cap: Maximum market cap ($10B default)
        fetch_caps: Whether to fetch market caps (slow but accurate)

    Returns:
        (filtered_symbols, rejection_reasons)
    """
    filtered = []
    rejections = {}

    for symbol in symbols:
        # Block mega-caps immediately (no API call needed)
        if symbol in MEGA_CAP_BLOCKLIST:
            rejections[symbol] = f"Mega-cap blocklist - no 10x potential"
            continue

        # Fetch market cap if requested
        if fetch_caps:
            market_cap = get_market_cap(symbol)

            if market_cap is None:
                logger.warning(f"{symbol}: Could not determine market cap, including anyway")
                filtered.append(symbol)
                continue

            if market_cap < min_market_cap:
                rejections[symbol] = f"Too small: ${market_cap/1e6:.0f}M < ${min_market_cap/1e6:.0f}M"
                continue

            if market_cap > max_market_cap:
                rejections[symbol] = f"Too large: ${market_cap/1e9:.1f}B > ${max_market_cap/1e9:.1f}B (limited upside)"
                continue

        # Passed all filters
        filtered.append(symbol)

    logger.info(f"Filtered {len(symbols)} symbols -> {len(filtered)} eligible ({len(rejections)} rejected)")

    return filtered, rejections


def build_multi_bagger_universe(
    base_symbols: Optional[List[str]] = None,
    include_small_caps: bool = True,
    include_mid_caps: bool = True,
    include_crypto: bool = True
) -> List[str]:
    """
    Build a universe optimized for multi-bagger detection

    Focus on:
    - Small caps ($300M - $2B): High risk, high reward
    - Mid caps ($2B - $10B): Moderate risk, growth potential
    - Emerging sectors: AI, biotech, clean energy, crypto
    - Recent IPOs (< 2 years): Still undiscovered

    Args:
        base_symbols: Starting list of symbols (None = curated list)
        include_small_caps: Include small cap stocks
        include_mid_caps: Include mid cap stocks
        include_crypto: Include crypto assets

    Returns:
        List of symbols with multi-bagger potential
    """
    universe = []

    # Curated list of high-potential sectors
    if base_symbols is None:
        # Small-cap AI/Tech
        small_cap_ai = [
            'SOUN', 'BBAI', 'BKSY', 'RKLB', 'SPCE',  # Space/AI
            'PATH', 'FROG', 'SNOW', 'DDOG', 'CRWD',  # Software (when smaller)
        ]

        # Small-cap Biotech (high volatility, potential 10x+)
        small_cap_bio = [
            'SAVA', 'VXRT', 'OCGN', 'ATOS', 'INO',
            'NVAX', 'MRNA', 'BNTX',  # mRNA (when opportunities arise)
        ]

        # Small-cap Clean Energy
        small_cap_clean = [
            'PLUG', 'FCEL', 'BE', 'CLSK', 'RIOT',  # Alt energy/Bitcoin mining
        ]

        # Mid-cap Growth
        mid_cap_growth = [
            'PLTR', 'SOFI', 'HOOD', 'COIN',  # Fintech
            'U', 'DASH', 'UBER', 'LYFT',      # Gig economy
        ]

        # Recent IPOs (< 2 years - still being discovered)
        recent_ipos = [
            # Check for newest IPOs dynamically
        ]

        if include_small_caps:
            universe.extend(small_cap_ai)
            universe.extend(small_cap_bio)
            universe.extend(small_cap_clean)

        if include_mid_caps:
            universe.extend(mid_cap_growth)

    else:
        universe = base_symbols.copy()

    # Add crypto if requested
    if include_crypto:
        crypto = [
            'BTC-USD', 'ETH-USD',      # Major (still 2-3x potential)
            'SOL-USD', 'AVAX-USD',     # L1s
            'MATIC-USD', 'LINK-USD',   # Infrastructure
            'UNI-USD', 'AAVE-USD',     # DeFi
        ]
        universe.extend(crypto)

    # Remove duplicates
    universe = list(set(universe))

    # Apply market cap filter
    filtered, rejections = filter_by_market_cap(
        universe,
        min_market_cap=100_000_000,    # $100M min
        max_market_cap=10_000_000_000, # $10B max
        fetch_caps=True  # Verify market caps
    )

    logger.info(f"Built multi-bagger universe: {len(filtered)} symbols")

    if rejections:
        logger.info("Rejected symbols:")
        for symbol, reason in list(rejections.items())[:10]:  # Show first 10
            logger.info(f"  {symbol}: {reason}")

    return filtered


def validate_universe_quality(symbols: List[str]) -> Dict:
    """
    Validate that universe has multi-bagger potential

    Checks:
    - No mega-caps
    - Market cap distribution
    - Sector diversity
    - Volatility (high = good for explosions)

    Args:
        symbols: List of symbols to validate

    Returns:
        Dict with validation metrics
    """
    metrics = {
        'total_symbols': len(symbols),
        'mega_caps': 0,
        'small_caps': 0,
        'mid_caps': 0,
        'large_caps': 0,
        'crypto': 0,
        'avg_market_cap': None,
        'max_market_cap': None
    }

    market_caps = []

    for symbol in symbols:
        # Count mega-caps (should be 0!)
        if symbol in MEGA_CAP_BLOCKLIST:
            metrics['mega_caps'] += 1
            logger.error(f"MEGA-CAP DETECTED: {symbol} - REMOVE FROM UNIVERSE")
            continue

        # Count crypto
        if '-USD' in symbol or 'BTC' in symbol or 'ETH' in symbol:
            metrics['crypto'] += 1
            continue

        # Get market cap
        market_cap = get_market_cap(symbol)
        if market_cap:
            market_caps.append(market_cap)

            # Categorize
            if market_cap < 2_000_000_000:  # < $2B
                metrics['small_caps'] += 1
            elif market_cap < 10_000_000_000:  # $2B - $10B
                metrics['mid_caps'] += 1
            else:  # > $10B
                metrics['large_caps'] += 1
                logger.warning(f"{symbol}: Large cap ${market_cap/1e9:.1f}B - limited upside")

    if market_caps:
        metrics['avg_market_cap'] = sum(market_caps) / len(market_caps)
        metrics['max_market_cap'] = max(market_caps)

    # Assess quality
    quality_score = 0

    if metrics['mega_caps'] == 0:
        quality_score += 40  # Critical
    else:
        logger.error(f"UNIVERSE CONTAMINATED: {metrics['mega_caps']} mega-caps found")

    if metrics['small_caps'] > 0:
        quality_score += 30  # Small caps = high upside

    if metrics['mid_caps'] > 0:
        quality_score += 20  # Mid caps = good risk/reward

    if metrics['crypto'] > 0:
        quality_score += 10  # Crypto = volatility

    metrics['quality_score'] = quality_score

    logger.info(f"Universe Quality Score: {quality_score}/100")
    logger.info(f"  Small caps: {metrics['small_caps']} (${metrics.get('avg_market_cap', 0)/1e9:.1f}B avg)")
    logger.info(f"  Mid caps: {metrics['mid_caps']}")
    logger.info(f"  Large caps: {metrics['large_caps']}")
    logger.info(f"  Crypto: {metrics['crypto']}")
    logger.info(f"  Mega-caps: {metrics['mega_caps']} (SHOULD BE 0!)")

    return metrics
