"""
REAL-TIME CRYPTO SCREENER - Uses CoinGecko API (actually works, no mocking)

Screens cryptocurrencies with:
- Price, market cap, volume filters
- Scam detection (wash trading, pump & dumps)
- Technical analysis (volatility, momentum)
- Fully featured like Finviz but for crypto

NO SIMULATION - Uses real CoinGecko API data.
"""

import logging
import requests
import time
import pandas as pd
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CryptoScreener:
    """
    Real-time crypto screener using CoinGecko API.
    """

    def __init__(self, api_key: Optional[str] = None, cache_dir: str = "data/cache", force_refresh: bool = False):
        """
        Args:
            api_key: CoinGecko Pro API key (optional, free tier works)
            cache_dir: Directory for caching results
            force_refresh: If True, bypass cache and fetch fresh data
        """
        self.api_key = api_key
        self.base_url = "https://api.coingecko.com/api/v3"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.force_refresh = force_refresh
        self.cache = {}

    def fetch_all_coins(self, vs_currency: str = 'usd', per_page: int = 250) -> List[Dict]:
        """
        Fetch comprehensive data for all coins from CoinGecko.

        Args:
            vs_currency: Currency for pricing (usd, btc, eth)
            per_page: Results per page (max 250)

        Returns:
            List of coin data
        """
        # Check cache first (unless force refresh)
        cache_file = self.cache_dir / f"coingecko_coins_{vs_currency}.json"

        if not self.force_refresh and cache_file.exists():
            import json
            try:
                cache_age = time.time() - cache_file.stat().st_mtime
                if cache_age < 3600:  # 1 hour cache
                    logger.info(f"Loading from cache ({cache_age/60:.1f} min old)...")
                    with open(cache_file, 'r') as f:
                        cached_data = json.load(f)
                    logger.info(f"✅ Loaded {len(cached_data)} coins from cache")
                    return cached_data
                else:
                    logger.info(f"Cache expired ({cache_age/3600:.1f}h old), fetching fresh data...")
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}, fetching fresh data...")

        if self.force_refresh:
            logger.info("🔄 FORCE REFRESH: Bypassing cache, fetching fresh data...")

        all_coins = []
        page = 1
        max_pages = 8  # Get top 2000 coins (8 pages * 250)

        logger.info(f"Fetching coins from CoinGecko (max {max_pages * per_page} coins)...")

        while page <= max_pages:
            try:
                url = f"{self.base_url}/coins/markets"
                params = {
                    'vs_currency': vs_currency,
                    'order': 'market_cap_desc',
                    'per_page': per_page,
                    'page': page,
                    'sparkline': False,
                    'price_change_percentage': '1h,24h,7d,30d'
                }

                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()

                coins = response.json()

                if not coins:
                    break

                all_coins.extend(coins)
                logger.info(f"  Fetched page {page}: {len(coins)} coins (total: {len(all_coins)})")

                page += 1

                # Rate limiting (50 calls/minute on free tier)
                time.sleep(1.2)  # ~50 calls/min

            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to fetch page {page}: {e}")
                break

        logger.info(f"Successfully fetched {len(all_coins)} coins")

        # Save to cache
        if all_coins:
            import json
            try:
                with open(cache_file, 'w') as f:
                    json.dump(all_coins, f)
                logger.info(f"💾 Cached {len(all_coins)} coins for future use")
            except Exception as e:
                logger.warning(f"Failed to save cache: {e}")

        return all_coins

    def calculate_scam_score(self, coin: Dict) -> Dict:
        """
        Calculate scam score for a coin.

        Returns:
            Dict with scam_score (0-100, higher = more likely scam) and flags
        """
        scam_score = 0
        flags = []

        market_cap = coin.get('market_cap', 0) or 0
        total_volume = coin.get('total_volume', 0) or 0
        price_change_24h = coin.get('price_change_percentage_24h', 0) or 0
        market_cap_rank = coin.get('market_cap_rank', 9999) or 9999

        # Red flag 1: Wash trading (volume > 50% of market cap)
        if market_cap > 0:
            vol_mcap_ratio = total_volume / market_cap
            if vol_mcap_ratio > 0.5:
                scam_score += 40
                flags.append(f"Wash trading suspected (vol/mcap = {vol_mcap_ratio:.1%})")
            elif vol_mcap_ratio > 0.3:
                scam_score += 20
                flags.append(f"High vol/mcap ratio ({vol_mcap_ratio:.1%})")

        # Red flag 2: Extreme price pump (> 100% in 24h)
        if abs(price_change_24h) > 100:
            scam_score += 30
            flags.append(f"Extreme 24h move ({price_change_24h:+.1f}%)")
        elif abs(price_change_24h) > 50:
            scam_score += 15
            flags.append(f"High 24h volatility ({price_change_24h:+.1f}%)")

        # Red flag 3: Very low market cap (< $1M)
        if market_cap < 1_000_000:
            scam_score += 25
            flags.append(f"Very low market cap (${market_cap/1e6:.2f}M)")
        elif market_cap < 10_000_000:
            scam_score += 10
            flags.append(f"Low market cap (${market_cap/1e6:.1f}M)")

        # Red flag 4: Obscure coin (rank > 500)
        if market_cap_rank > 1000:
            scam_score += 20
            flags.append(f"Very obscure (rank #{market_cap_rank})")
        elif market_cap_rank > 500:
            scam_score += 10
            flags.append(f"Obscure (rank #{market_cap_rank})")

        # Red flag 5: No recent volume
        if total_volume == 0:
            scam_score += 50
            flags.append("No trading volume")

        return {
            'scam_score': min(scam_score, 100),
            'is_likely_scam': scam_score >= 50,
            'flags': flags
        }

    def screen_coins(
        self,
        # Price filters
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        # Market cap filters
        min_market_cap: Optional[float] = None,
        max_market_cap: Optional[float] = None,
        # Volume filters
        min_volume: Optional[float] = None,
        min_volume_mcap_ratio: Optional[float] = None,
        max_volume_mcap_ratio: Optional[float] = None,
        # Performance filters
        min_price_change_24h: Optional[float] = None,
        max_price_change_24h: Optional[float] = None,
        min_price_change_7d: Optional[float] = None,
        max_price_change_7d: Optional[float] = None,
        # Rank filter
        max_rank: Optional[int] = None,
        # Scam filtering
        filter_scams: bool = True,
        max_scam_score: int = 50,
    ) -> pd.DataFrame:
        """
        Screen cryptocurrencies with extensive filters.

        Returns:
            DataFrame with coins meeting ALL criteria
        """

        # Fetch all coins
        coins = self.fetch_all_coins()

        if not coins:
            logger.error("Failed to fetch coins")
            return pd.DataFrame()

        # Calculate scam scores
        logger.info("Calculating scam scores...")
        for coin in coins:
            scam_analysis = self.calculate_scam_score(coin)
            coin.update(scam_analysis)

        # Create DataFrame
        df = pd.DataFrame(coins)

        # Apply filters
        logger.info("")
        logger.info("📊 Applying filters...")
        initial_count = len(df)

        if filter_scams:
            df = df[df['scam_score'] < max_scam_score]
            logger.info(f"  Scam score < {max_scam_score}: {len(df)}/{initial_count} remain")

        if min_price is not None:
            df = df[df['current_price'] >= min_price]
            logger.info(f"  Price >= ${min_price}: {len(df)}/{initial_count} remain")

        if max_price is not None:
            df = df[df['current_price'] <= max_price]
            logger.info(f"  Price <= ${max_price}: {len(df)}/{initial_count} remain")

        if min_market_cap is not None:
            df = df[df['market_cap'] >= min_market_cap]
            logger.info(f"  Market cap >= ${min_market_cap/1e6:.0f}M: {len(df)}/{initial_count} remain")

        if max_market_cap is not None:
            df = df[df['market_cap'] <= max_market_cap]
            logger.info(f"  Market cap <= ${max_market_cap/1e9:.1f}B: {len(df)}/{initial_count} remain")

        if min_volume is not None:
            df = df[df['total_volume'] >= min_volume]
            logger.info(f"  Volume >= ${min_volume/1e6:.0f}M: {len(df)}/{initial_count} remain")

        if min_volume_mcap_ratio is not None:
            df['vol_mcap_ratio'] = df['total_volume'] / df['market_cap']
            df = df[df['vol_mcap_ratio'] >= min_volume_mcap_ratio]
            logger.info(f"  Vol/MCap >= {min_volume_mcap_ratio:.1%}: {len(df)}/{initial_count} remain")

        if max_volume_mcap_ratio is not None:
            if 'vol_mcap_ratio' not in df.columns:
                df['vol_mcap_ratio'] = df['total_volume'] / df['market_cap']
            df = df[df['vol_mcap_ratio'] <= max_volume_mcap_ratio]
            logger.info(f"  Vol/MCap <= {max_volume_mcap_ratio:.1%} (no wash trading): {len(df)}/{initial_count} remain")

        if min_price_change_24h is not None:
            df = df[df['price_change_percentage_24h'] >= min_price_change_24h]
            logger.info(f"  24h change >= {min_price_change_24h}%: {len(df)}/{initial_count} remain")

        if max_price_change_24h is not None:
            df = df[df['price_change_percentage_24h'] <= max_price_change_24h]
            logger.info(f"  24h change <= {max_price_change_24h}%: {len(df)}/{initial_count} remain")

        if min_price_change_7d is not None:
            df = df[df['price_change_percentage_7d_in_currency'] >= min_price_change_7d]
            logger.info(f"  7d change >= {min_price_change_7d}%: {len(df)}/{initial_count} remain")

        if max_price_change_7d is not None:
            df = df[df['price_change_percentage_7d_in_currency'] <= max_price_change_7d]
            logger.info(f"  7d change <= {max_price_change_7d}%: {len(df)}/{initial_count} remain")

        if max_rank is not None:
            df = df[df['market_cap_rank'] <= max_rank]
            logger.info(f"  Rank <= {max_rank}: {len(df)}/{initial_count} remain")

        logger.info("")
        logger.info(f"✅ {len(df)} coins passed all filters")

        return df


def screen_crypto(force_refresh: bool = False):
    """
    Screen cryptocurrencies with multiple strategies.

    Args:
        force_refresh: If True, bypass cache and fetch fresh data
    """

    print("="*80)
    print("🪙 REAL-TIME CRYPTOCURRENCY SCREENER")
    print("="*80)
    print()
    print("Using CoinGecko API - NO SIMULATION, REAL DATA")
    if force_refresh:
        print("🔄 FORCE REFRESH MODE: Bypassing cache")
    print()
    print("="*80)
    print()

    screener = CryptoScreener(force_refresh=force_refresh)

    # SCREEN 1: Quality Coins (scam-filtered, liquid)
    print("📊 SCREEN 1: Quality Coins (Scam-Filtered, Liquid)")
    print("-"*80)
    print()

    quality_coins = screener.screen_coins(
        min_market_cap=50_000_000,      # $50M minimum
        min_volume=5_000_000,           # $5M daily volume
        max_volume_mcap_ratio=0.5,      # No wash trading
        max_rank=500,                   # Top 500
        filter_scams=True,
        max_scam_score=30,              # Low scam risk
    )

    print()
    print("="*80)
    print(f"✅ Found {len(quality_coins)} quality coins")
    print("="*80)
    print()

    if not quality_coins.empty:
        # Sort by market cap
        quality_coins = quality_coins.sort_values('market_cap', ascending=False)

        print("Top quality coins by market cap:")
        print()

        for i, (idx, row) in enumerate(quality_coins.head(20).iterrows(), 1):
            print(f"{i:2d}. {row['symbol'].upper():6s} ({row['name'][:20]:20s})  "
                  f"${row['current_price']:>12,.4f}  "
                  f"MCap: ${row['market_cap']/1e9:>8.2f}B  "
                  f"Vol: ${row['total_volume']/1e6:>7.1f}M  "
                  f"24h: {row['price_change_percentage_24h']:>+6.1f}%  "
                  f"Rank: #{row['market_cap_rank']}")

    print()
    print("="*80)
    print()

    # SCREEN 2: High Movers (24h gainers)
    print("📊 SCREEN 2: High Movers (24h Gainers)")
    print("-"*80)
    print()

    gainers = screener.screen_coins(
        min_market_cap=10_000_000,      # $10M minimum
        min_volume=1_000_000,           # $1M volume
        min_price_change_24h=10.0,      # Up 10%+ today
        max_volume_mcap_ratio=0.5,      # No wash trading
        filter_scams=True,
        max_scam_score=40,
    )

    print()
    print("="*80)
    print(f"✅ Found {len(gainers)} high movers")
    print("="*80)
    print()

    if not gainers.empty:
        # Sort by 24h change
        gainers = gainers.sort_values('price_change_percentage_24h', ascending=False)

        print("Top gainers (24h):")
        print()

        for i, (idx, row) in enumerate(gainers.head(20).iterrows(), 1):
            print(f"{i:2d}. {row['symbol'].upper():6s} ({row['name'][:20]:20s})  "
                  f"${row['current_price']:>12,.4f}  "
                  f"MCap: ${row['market_cap']/1e6:>7.0f}M  "
                  f"24h: {row['price_change_percentage_24h']:>+6.1f}%  "
                  f"7d: {row['price_change_percentage_7d_in_currency']:>+6.1f}%  "
                  f"Scam: {row['scam_score']}/100")

    print()
    print("="*80)
    print()

    # SCREEN 3: Compressed Coins (ready to move)
    print("📊 SCREEN 3: Compressed Coins (Low Volatility, Ready to Move)")
    print("-"*80)
    print()

    compressed = screener.screen_coins(
        min_market_cap=50_000_000,      # $50M minimum
        min_volume=2_000_000,           # $2M volume
        max_price_change_24h=5.0,       # Low recent movement
        min_price_change_24h=-5.0,      # Not crashing
        max_price_change_7d=10.0,       # Not pumping
        min_price_change_7d=-10.0,      # Not dumping
        max_volume_mcap_ratio=0.3,      # Good liquidity
        filter_scams=True,
        max_scam_score=25,              # Very low scam risk
        max_rank=300,                   # Top 300
    )

    print()
    print("="*80)
    print(f"✅ Found {len(compressed)} compressed coins (HIGH PRIORITY)")
    print("="*80)
    print()

    if not compressed.empty:
        # Sort by market cap (focus on established coins)
        compressed = compressed.sort_values('market_cap', ascending=False)

        print("Best compressed coins (explosion candidates):")
        print()

        for i, (idx, row) in enumerate(compressed.head(15).iterrows(), 1):
            print(f"{i:2d}. {row['symbol'].upper():6s} ({row['name'][:20]:20s})  "
                  f"${row['current_price']:>12,.4f}  "
                  f"MCap: ${row['market_cap']/1e9:>6.2f}B  "
                  f"24h: {row['price_change_percentage_24h']:>+5.1f}%  "
                  f"7d: {row['price_change_percentage_7d_in_currency']:>+5.1f}%  "
                  f"Rank: #{row['market_cap_rank']}")

    print()
    print("="*80)
    print()

    # Export results
    if not quality_coins.empty:
        quality_coins.to_csv('data/crypto_quality.csv', index=False)
        print(f"📁 Exported {len(quality_coins)} quality coins to data/crypto_quality.csv")

    if not gainers.empty:
        gainers.to_csv('data/crypto_gainers.csv', index=False)
        print(f"📁 Exported {len(gainers)} gainers to data/crypto_gainers.csv")

    if not compressed.empty:
        compressed.to_csv('data/crypto_compressed.csv', index=False)
        print(f"📁 Exported {len(compressed)} compressed coins to data/crypto_compressed.csv")

    print()
    print("="*80)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Real-time cryptocurrency screener',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python screen_crypto_real.py                    # Use cache if available
  python screen_crypto_real.py --force-refresh    # Bypass cache, fetch fresh data

Force refresh is useful when:
- Breaking news just happened
- You need the latest prices
- Verifying signal accuracy
- Testing the system
        """
    )
    parser.add_argument(
        '--force-refresh',
        action='store_true',
        help='Bypass cache and fetch fresh data immediately (slower but most current)'
    )

    args = parser.parse_args()
    screen_crypto(force_refresh=args.force_refresh)
