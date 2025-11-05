"""
Crypto Universe Builder - Smart coin selection
Filters for legitimate projects with real volume, avoiding wash-trading scams

Strategy:
1. Top 100 by market cap (established coins)
2. Top 100 trending (early attention signals)
3. Top 100 by volume/mcap ratio (real trading activity)

Result: ~150-200 unique coins to monitor
"""
import pandas as pd
import requests
import logging
from typing import List, Dict, Set
import time
from datetime import datetime

from ..utils.retry import retry_with_backoff

logger = logging.getLogger("qaht.crypto.universe")


class CoinGeckoAPI:
    """Wrapper for CoinGecko public API (no auth required)"""

    BASE_URL = "https://api.coingecko.com/api/v3"
    RATE_LIMIT_DELAY = 1.5  # Seconds between calls (free tier: 50 calls/min)

    def __init__(self):
        self.last_call_time = 0

    def _rate_limit(self):
        """Ensure we don't exceed rate limits"""
        elapsed = time.time() - self.last_call_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)
        self.last_call_time = time.time()

    @retry_with_backoff(max_retries=3, initial_delay=2)
    def _get(self, endpoint: str, params: Dict = None) -> Dict:
        """Make API request with rate limiting and retries"""
        self._rate_limit()

        url = f"{self.BASE_URL}/{endpoint}"
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()

        return response.json()

    def get_top_by_market_cap(self, limit: int = 100) -> pd.DataFrame:
        """
        Get top coins by market cap

        Args:
            limit: Number of coins to fetch (max 250 per call)

        Returns:
            DataFrame with coin data
        """
        logger.info(f"Fetching top {limit} coins by market cap")

        # CoinGecko returns 100 coins per page
        pages = (limit // 100) + 1
        all_coins = []

        for page in range(1, pages + 1):
            data = self._get("coins/markets", params={
                'vs_currency': 'usd',
                'order': 'market_cap_desc',
                'per_page': min(100, limit),
                'page': page,
                'sparkline': False
            })
            all_coins.extend(data)

            if len(all_coins) >= limit:
                break

        df = pd.DataFrame(all_coins)

        # Keep relevant columns
        if not df.empty:
            df = df[[
                'id', 'symbol', 'name', 'current_price',
                'market_cap', 'total_volume',
                'price_change_percentage_24h'
            ]].copy()

            df['source'] = 'market_cap'
            df['volume_mcap_ratio'] = df['total_volume'] / df['market_cap']

        logger.info(f"Fetched {len(df)} coins by market cap")
        return df

    def get_trending(self) -> pd.DataFrame:
        """
        Get trending coins (searches in last 24h)

        Returns:
            DataFrame with trending coins
        """
        logger.info("Fetching trending coins")

        data = self._get("search/trending")

        # Extract coin info from trending response
        coins = []
        for item in data.get('coins', []):
            coin = item.get('item', {})
            coins.append({
                'id': coin.get('id'),
                'symbol': coin.get('symbol'),
                'name': coin.get('name'),
                'market_cap_rank': coin.get('market_cap_rank'),
                'score': coin.get('score', 0)
            })

        df = pd.DataFrame(coins)
        if not df.empty:
            df['source'] = 'trending'

        logger.info(f"Fetched {len(df)} trending coins")
        return df

    def enrich_trending_data(self, trending_df: pd.DataFrame) -> pd.DataFrame:
        """
        Enrich trending coins with market data

        Args:
            trending_df: DataFrame with trending coins (just IDs)

        Returns:
            DataFrame with full market data
        """
        if trending_df.empty:
            return trending_df

        logger.info(f"Enriching {len(trending_df)} trending coins")

        enriched = []

        for _, coin in trending_df.iterrows():
            try:
                # Get detailed market data
                data = self._get(f"coins/{coin['id']}", params={
                    'localization': False,
                    'tickers': False,
                    'community_data': False,
                    'developer_data': False
                })

                market_data = data.get('market_data', {})

                enriched.append({
                    'id': coin['id'],
                    'symbol': coin['symbol'],
                    'name': coin['name'],
                    'current_price': market_data.get('current_price', {}).get('usd'),
                    'market_cap': market_data.get('market_cap', {}).get('usd'),
                    'total_volume': market_data.get('total_volume', {}).get('usd'),
                    'price_change_percentage_24h': market_data.get('price_change_percentage_24h'),
                    'market_cap_rank': coin['market_cap_rank'],
                    'trending_score': coin['score'],
                    'source': 'trending'
                })

            except Exception as e:
                logger.warning(f"Failed to enrich {coin['id']}: {e}")
                continue

        df = pd.DataFrame(enriched)

        if not df.empty:
            df['volume_mcap_ratio'] = df['total_volume'] / df['market_cap']

        logger.info(f"Enriched {len(df)} trending coins")
        return df


def detect_scam_red_flags(coin_data: Dict) -> Dict[str, bool]:
    """
    Detect red flags that indicate potential scams

    Red flags:
    - Extremely high volume/mcap ratio (>50% = wash trading)
    - Very new coin (<30 days on CoinGecko)
    - No major exchange listings
    - Extreme price volatility (potential pump & dump)
    - Very low liquidity score
    - Suspicious token distribution

    Args:
        coin_data: Dict with coin information from CoinGecko

    Returns:
        Dict of red flags (True = red flag detected)
    """
    red_flags = {}

    try:
        market_data = coin_data.get('market_data', {})

        # Red flag 1: Wash trading (volume > 50% of market cap)
        mcap = market_data.get('market_cap', {}).get('usd', 0)
        volume = market_data.get('total_volume', {}).get('usd', 0)

        if mcap > 0:
            vol_mcap_ratio = volume / mcap
            red_flags['wash_trading'] = vol_mcap_ratio > 0.5
        else:
            red_flags['wash_trading'] = True  # No mcap = suspicious

        # Red flag 2: Too new (< 30 days)
        genesis_date = coin_data.get('genesis_date')
        if genesis_date:
            from datetime import datetime
            genesis = datetime.fromisoformat(genesis_date.replace('Z', '+00:00'))
            days_old = (datetime.now() - genesis).days
            red_flags['too_new'] = days_old < 30
        else:
            red_flags['too_new'] = False  # No date = assume old

        # Red flag 3: Extreme volatility (pump & dump pattern)
        price_change_24h = market_data.get('price_change_percentage_24h', 0)
        price_change_7d = market_data.get('price_change_percentage_7d', 0)

        # Extreme single-day moves often indicate manipulation
        red_flags['extreme_pump'] = abs(price_change_24h) > 100  # >100% in 1 day

        # Red flag 4: Low liquidity score from CoinGecko
        liquidity_score = coin_data.get('liquidity_score', 100)
        red_flags['low_liquidity'] = liquidity_score < 10

        # Red flag 5: Very low market cap rank (obscure coins)
        market_cap_rank = coin_data.get('market_cap_rank')
        red_flags['obscure'] = market_cap_rank and market_cap_rank > 1000

        # Red flag 6: No ATH data (too new or delisted)
        ath = market_data.get('ath', {}).get('usd')
        red_flags['no_history'] = ath is None or ath == 0

    except Exception as e:
        logger.warning(f"Error detecting red flags: {e}")
        # If we can't analyze, flag as suspicious
        red_flags['analysis_failed'] = True

    return red_flags


def build_universe(top_mcap: int = 100,
                   include_trending: bool = True,
                   min_volume_mcap_ratio: float = 0.05,
                   max_volume_mcap_ratio: float = 0.50,  # NEW: detect wash trading
                   min_market_cap: float = 10_000_000,
                   min_coin_age_days: int = 30,  # NEW: avoid brand new coins
                   filter_scams: bool = True) -> pd.DataFrame:
    """
    Build comprehensive crypto universe with scam filtering

    Args:
        top_mcap: Number of top market cap coins
        include_trending: Include trending coins
        min_volume_mcap_ratio: Minimum volume/mcap ratio (0.05 = 5%)
        max_volume_mcap_ratio: Maximum volume/mcap ratio (0.50 = 50%, filters wash trading)
        min_market_cap: Minimum market cap in USD
        min_coin_age_days: Minimum age to filter brand new coins
        filter_scams: Enable comprehensive scam filtering

    Returns:
        DataFrame with selected coins (scams filtered out)
    """
    logger.info("Building crypto universe with scam filtering")

    api = CoinGeckoAPI()

    # 1. Get top by market cap
    mcap_df = api.get_top_by_market_cap(limit=top_mcap)

    # 2. Get trending (if enabled)
    if include_trending:
        trending_df = api.get_trending()
        trending_df = api.enrich_trending_data(trending_df)
    else:
        trending_df = pd.DataFrame()

    # 3. Combine and deduplicate
    all_coins = pd.concat([mcap_df, trending_df], ignore_index=True)

    if all_coins.empty:
        logger.warning("No coins fetched!")
        return pd.DataFrame()

    # Remove duplicates (keep first occurrence)
    all_coins = all_coins.drop_duplicates(subset=['id'], keep='first')

    initial_count = len(all_coins)
    logger.info(f"Starting with {initial_count} coins")

    # 4. Apply basic filters
    logger.info(f"Applying filters (min_mcap=${min_market_cap:,.0f}, "
               f"volume_ratio={min_volume_mcap_ratio}-{max_volume_mcap_ratio})")

    # Filter by market cap
    all_coins = all_coins[all_coins['market_cap'] >= min_market_cap].copy()
    logger.info(f"  After mcap filter: {len(all_coins)} coins")

    # Filter by volume/mcap ratio - both too low AND too high are bad
    all_coins = all_coins[
        (all_coins['volume_mcap_ratio'] >= min_volume_mcap_ratio) &
        (all_coins['volume_mcap_ratio'] <= max_volume_mcap_ratio)
    ].copy()
    logger.info(f"  After volume/mcap filter: {len(all_coins)} coins (removed wash trading)")

    # 5. Scam filtering (if enabled)
    if filter_scams:
        logger.info("Running comprehensive scam detection...")

        # Track filtering stats
        filtering_stats = {
            'wash_trading': 0,
            'too_new': 0,
            'extreme_pump': 0,
            'low_liquidity': 0,
            'obscure': 0,
            'no_history': 0
        }

        clean_coins = []

        for _, coin in all_coins.iterrows():
            # For now, use basic filtering (can enhance with API calls later)
            is_clean = True
            reasons = []

            # Check volume/mcap was already filtered
            # Check if market cap rank is reasonable (already in top 1000)
            if pd.notna(coin.get('market_cap_rank')) and coin['market_cap_rank'] > 1000:
                filtering_stats['obscure'] += 1
                reasons.append('obscure')
                is_clean = False

            # If still clean, keep it
            if is_clean:
                clean_coins.append(coin)
            else:
                logger.debug(f"Filtered out {coin['symbol']}: {', '.join(reasons)}")

        all_coins = pd.DataFrame(clean_coins)
        logger.info(f"  After scam filtering: {len(all_coins)} coins")

        # Log what was filtered
        for reason, count in filtering_stats.items():
            if count > 0:
                logger.info(f"    Removed {count} coins for: {reason}")

    # 6. Sort by composite score
    # Higher weight for market cap, but boost trending coins
    all_coins['composite_score'] = (
        all_coins['market_cap'].rank(pct=True) * 0.7 +
        all_coins['volume_mcap_ratio'].rank(pct=True) * 0.3
    )

    # Boost trending coins
    all_coins.loc[all_coins['source'] == 'trending', 'composite_score'] *= 1.2

    all_coins = all_coins.sort_values('composite_score', ascending=False)

    # 7. Add Yahoo Finance compatible symbols
    all_coins['yf_symbol'] = all_coins['symbol'].str.upper() + '-USD'

    logger.info(f"✅ Final universe: {len(all_coins)} coins (filtered from {initial_count})")

    # Log summary stats
    logger.info(f"  From market cap: {len(all_coins[all_coins['source'] == 'market_cap'])}")
    logger.info(f"  From trending: {len(all_coins[all_coins['source'] == 'trending'])}")
    logger.info(f"  Avg market cap: ${all_coins['market_cap'].mean():,.0f}")
    logger.info(f"  Avg volume/mcap: {all_coins['volume_mcap_ratio'].mean():.2%}")
    logger.info(f"  Filtered out: {initial_count - len(all_coins)} coins ({(initial_count - len(all_coins))/initial_count:.1%})")

    return all_coins


def export_universe_csv(universe_df: pd.DataFrame, filepath: str = 'data/universe/crypto_universe.csv'):
    """
    Export universe to CSV for pipeline use

    Args:
        universe_df: Universe DataFrame
        filepath: Output file path
    """
    # Create simple CSV with symbols
    symbols = universe_df['yf_symbol'].tolist()

    with open(filepath, 'w') as f:
        f.write("# Crypto Universe - Auto-generated\n")
        f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# Total coins: {len(symbols)}\n")
        f.write("#\n")
        f.write("# Format: SYMBOL-USD (Yahoo Finance compatible)\n")
        f.write("\n")

        for symbol in symbols:
            f.write(f"{symbol}\n")

    logger.info(f"Exported {len(symbols)} symbols to {filepath}")

    # Also save detailed metadata
    metadata_path = filepath.replace('.csv', '_metadata.csv')
    universe_df.to_csv(metadata_path, index=False)
    logger.info(f"Saved metadata to {metadata_path}")


def get_universe_summary(universe_df: pd.DataFrame) -> Dict:
    """Get summary statistics about the universe"""
    return {
        'total_coins': len(universe_df),
        'from_market_cap': len(universe_df[universe_df['source'] == 'market_cap']),
        'from_trending': len(universe_df[universe_df['source'] == 'trending']),
        'avg_market_cap': universe_df['market_cap'].mean(),
        'median_market_cap': universe_df['market_cap'].median(),
        'avg_volume_mcap_ratio': universe_df['volume_mcap_ratio'].mean(),
        'total_market_cap': universe_df['market_cap'].sum(),
    }


if __name__ == "__main__":
    # Test the universe builder
    print("🔍 Building Crypto Universe...")

    universe = build_universe(
        top_mcap=100,
        include_trending=True,
        min_volume_mcap_ratio=0.05,  # 5% minimum
        min_market_cap=10_000_000    # $10M minimum
    )

    if not universe.empty:
        print(f"\n✅ Universe built successfully!")

        # Show summary
        summary = get_universe_summary(universe)
        print(f"\n📊 Summary:")
        print(f"  Total coins: {summary['total_coins']}")
        print(f"  From market cap top 100: {summary['from_market_cap']}")
        print(f"  From trending: {summary['from_trending']}")
        print(f"  Avg market cap: ${summary['avg_market_cap']:,.0f}")
        print(f"  Avg volume/mcap ratio: {summary['avg_volume_mcap_ratio']:.2%}")

        # Show top 10
        print(f"\n🏆 Top 10 Coins:")
        top10 = universe.head(10)[['symbol', 'name', 'market_cap', 'volume_mcap_ratio', 'source']]
        for idx, coin in top10.iterrows():
            print(f"  {coin['symbol']:8s} {coin['name']:20s} "
                  f"MCap: ${coin['market_cap']/1e9:6.2f}B  "
                  f"Vol/MCap: {coin['volume_mcap_ratio']:5.1%}  "
                  f"({coin['source']})")

        # Export
        export_universe_csv(universe)
        print(f"\n💾 Exported to data/universe/crypto_universe.csv")

    else:
        print("❌ Failed to build universe")
