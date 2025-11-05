"""
FREE Crypto Data Sources (No API Key Required)

Uses:
1. CoinCap API - FREE, unlimited, real-time
2. Binance Public API - FREE, real-time
3. Kraken Public API - FREE, real-time

All work without authentication.
"""

import logging
import requests
import time
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class FreeCryptoAPI:
    """
    Fetch real-time crypto data from free sources.
    """

    @staticmethod
    def fetch_from_coincap() -> List[Dict]:
        """
        Fetch from CoinCap API (FREE, unlimited, real-time).

        Returns:
            List of coins with price, market cap, volume
        """
        try:
            logger.info("Fetching from CoinCap API (free, unlimited)...")

            all_coins = []

            # CoinCap has pagination, fetch multiple pages
            for offset in [0, 100, 200, 300, 400, 500]:
                url = f"https://api.coincap.io/v2/assets"
                params = {
                    'limit': 100,
                    'offset': offset
                }

                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()

                data = response.json()
                coins = data.get('data', [])

                if not coins:
                    break

                all_coins.extend(coins)
                logger.info(f"  Fetched offset {offset}: {len(coins)} coins")

                time.sleep(0.5)  # Be nice to free API

            logger.info(f"Successfully fetched {len(all_coins)} coins from CoinCap")

            # Transform to standard format
            transformed = []
            for coin in all_coins:
                try:
                    transformed.append({
                        'symbol': coin.get('symbol', '').upper(),
                        'name': coin.get('name', ''),
                        'rank': int(coin.get('rank', 9999)),
                        'price': float(coin.get('priceUsd', 0)),
                        'market_cap': float(coin.get('marketCapUsd', 0)),
                        'volume_24h': float(coin.get('volumeUsd24Hr', 0)),
                        'change_24h': float(coin.get('changePercent24Hr', 0)),
                        'supply': float(coin.get('supply', 0)),
                        'source': 'coincap'
                    })
                except (ValueError, TypeError) as e:
                    continue

            return transformed

        except Exception as e:
            logger.error(f"Failed to fetch from CoinCap: {e}")
            return []

    @staticmethod
    def fetch_from_binance() -> List[Dict]:
        """
        Fetch from Binance Public API (FREE, real-time).

        Returns:
            List of trading pairs with price, volume
        """
        try:
            logger.info("Fetching from Binance API (free, real-time)...")

            # Get 24hr ticker stats for all pairs
            url = "https://api.binance.com/api/v3/ticker/24hr"

            response = requests.get(url, timeout=10)
            response.raise_for_status()

            tickers = response.json()

            # Filter for USDT pairs (most liquid)
            usdt_pairs = []
            for ticker in tickers:
                symbol = ticker.get('symbol', '')
                if symbol.endswith('USDT'):
                    base_symbol = symbol.replace('USDT', '')

                    try:
                        usdt_pairs.append({
                            'symbol': base_symbol,
                            'pair': symbol,
                            'price': float(ticker.get('lastPrice', 0)),
                            'volume_24h': float(ticker.get('quoteVolume', 0)),  # in USDT
                            'change_24h': float(ticker.get('priceChangePercent', 0)),
                            'high_24h': float(ticker.get('highPrice', 0)),
                            'low_24h': float(ticker.get('lowPrice', 0)),
                            'source': 'binance'
                        })
                    except (ValueError, TypeError):
                        continue

            logger.info(f"Successfully fetched {len(usdt_pairs)} pairs from Binance")
            return usdt_pairs

        except Exception as e:
            logger.error(f"Failed to fetch from Binance: {e}")
            return []

    @staticmethod
    def fetch_from_kraken() -> List[Dict]:
        """
        Fetch from Kraken Public API (FREE, real-time).

        Returns:
            List of trading pairs
        """
        try:
            logger.info("Fetching from Kraken API (free, real-time)...")

            # Get ticker info
            url = "https://api.kraken.com/0/public/Ticker"

            response = requests.get(url, timeout=10)
            response.raise_for_status()

            data = response.json()

            if data.get('error'):
                logger.warning(f"Kraken API error: {data['error']}")
                return []

            tickers = data.get('result', {})

            # Parse ticker data
            pairs = []
            for pair_name, ticker_data in tickers.items():
                # Kraken uses weird pair names (XXBTZUSD), skip for now
                # We'll primarily use CoinCap and Binance
                pass

            logger.info(f"Fetched data from Kraken")
            return pairs

        except Exception as e:
            logger.error(f"Failed to fetch from Kraken: {e}")
            return []

    @classmethod
    def fetch_all_coins(cls) -> List[Dict]:
        """
        Fetch from all free sources and merge data.

        Returns:
            Comprehensive list of coins from multiple sources
        """
        all_coins = {}

        # Fetch from CoinCap (most comprehensive)
        coincap_data = cls.fetch_from_coincap()
        for coin in coincap_data:
            symbol = coin['symbol']
            all_coins[symbol] = coin

        # Fetch from Binance (real-time prices)
        binance_data = cls.fetch_from_binance()
        for coin in binance_data:
            symbol = coin['symbol']
            if symbol in all_coins:
                # Merge data (prefer Binance prices for real-time)
                all_coins[symbol]['price_binance'] = coin['price']
                all_coins[symbol]['volume_binance'] = coin['volume_24h']
            else:
                # Add new coin from Binance
                all_coins[symbol] = coin

        logger.info(f"Total unique coins: {len(all_coins)}")
        return list(all_coins.values())


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    # Test fetching
    api = FreeCryptoAPI()

    print("Testing FREE crypto APIs...")
    print()

    coins = api.fetch_all_coins()

    print(f"✅ Fetched {len(coins)} coins from free sources")
    print()

    print("Sample coins:")
    for coin in coins[:10]:
        print(f"  {coin['symbol']:6s}: ${coin['price']:>12,.4f}  "
              f"MCap: ${coin.get('market_cap', 0)/1e9:>6.2f}B  "
              f"24h: {coin.get('change_24h', 0):>+6.2f}%")
