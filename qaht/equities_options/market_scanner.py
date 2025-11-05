"""
Market-wide stock scanner with dynamic filters.

Scans the ENTIRE US stock market (not a predefined list) and applies filters:
- Price > $1
- Average daily volume > 1M
- Market cap < $1T (optional, to focus on high-movement stocks)

This can return thousands of stocks that meet the criteria.
"""

import logging
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import requests
import yfinance as yf
from sqlalchemy import create_engine, Column, String, Float, Integer, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from qaht.config import get_config

logger = logging.getLogger(__name__)

Base = declarative_base()


class StockScreening(Base):
    """Cache of stock screening results."""
    __tablename__ = 'stock_screening'

    symbol = Column(String, primary_key=True)
    price = Column(Float, nullable=True)
    avg_volume = Column(Float, nullable=True)
    market_cap = Column(Float, nullable=True)
    exchange = Column(String, nullable=True)
    name = Column(String, nullable=True)
    last_updated = Column(DateTime, nullable=False)


class MarketScanner:
    """Scans entire US stock market with filters."""

    def __init__(self, cache_hours: int = 24):
        """
        Args:
            cache_hours: How many hours to cache screening results
        """
        self.cache_hours = cache_hours
        config = get_config()
        self.engine = create_engine(config.db_url)
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()

    def get_all_us_tickers(self) -> List[Dict[str, str]]:
        """
        Get all US stock tickers from NASDAQ FTP site.

        Returns:
            List of dicts with 'symbol', 'name', 'exchange'
        """
        logger.info("Fetching all US stock tickers from NASDAQ...")

        tickers = []

        # Try NASDAQ FTP site (more reliable than SEC)
        exchanges = [
            ('ftp://ftp.nasdaqtrader.com/symboldirectory/nasdaqlisted.txt', 'NASDAQ'),
            ('ftp://ftp.nasdaqtrader.com/symboldirectory/otherlisted.txt', 'NYSE/AMEX')
        ]

        for url, exchange_name in exchanges:
            try:
                logger.info(f"Fetching from {exchange_name}...")
                response = requests.get(url, timeout=30)
                response.raise_for_status()

                lines = response.text.split('\n')

                # Skip header and footer
                for line in lines[1:-1]:
                    if not line.strip():
                        continue

                    parts = line.split('|')
                    if len(parts) >= 2:
                        symbol = parts[0].strip()
                        name = parts[1].strip() if len(parts) > 1 else ''

                        # Skip test symbols
                        if symbol and not symbol.startswith('TEST'):
                            tickers.append({
                                'symbol': symbol,
                                'name': name,
                                'exchange': exchange_name
                            })

            except Exception as e:
                logger.warning(f"Failed to fetch from {exchange_name}: {e}")
                continue

        if tickers:
            logger.info(f"Found {len(tickers)} tickers from NASDAQ/NYSE/AMEX")
            return tickers

        # If NASDAQ fails, try alternative source
        logger.info("Trying alternative source (yfinance)...")
        return self._get_tickers_from_yfinance()

    def _get_tickers_from_yfinance(self) -> List[Dict[str, str]]:
        """
        Get tickers using yfinance screening (fallback method).
        Returns a sample of liquid stocks to test with.
        """
        logger.info("Using yfinance to get sample tickers...")

        # Get a diverse sample of well-known liquid stocks
        # This is just a fallback to ensure something works
        sample_tickers = [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'TSLA', 'META', 'AMD',
            'NFLX', 'INTC', 'COIN', 'PLTR', 'RIOT', 'MARA', 'SOFI', 'HOOD',
            'GME', 'AMC', 'BB', 'LAZR', 'SPCE', 'PLUG', 'FCEL', 'GEVO',
            'MRNA', 'BNTX', 'CRSP', 'EDIT', 'NTLA', 'BLUE', 'BMRN', 'ALNY'
        ]

        tickers = []
        for symbol in sample_tickers:
            tickers.append({
                'symbol': symbol,
                'name': symbol,
                'exchange': 'US'
            })

        logger.warning(f"Using limited fallback sample: {len(tickers)} tickers")
        return tickers

    def _get_fallback_tickers(self) -> List[Dict[str, str]]:
        """Fallback ticker list (same as yfinance method)."""
        return self._get_tickers_from_yfinance()

    def screen_stocks(
        self,
        min_price: float = 1.0,
        min_avg_volume: float = 1_000_000,
        max_market_cap: Optional[float] = 1_000_000_000_000,  # $1T
        use_cache: bool = True,
        batch_size: int = 100,
        max_stocks: Optional[int] = None
    ) -> List[Dict[str, any]]:
        """
        Screen entire market for stocks meeting criteria.

        Args:
            min_price: Minimum stock price (default $1)
            min_avg_volume: Minimum average daily volume (default 1M)
            max_market_cap: Maximum market cap (default $1T, set None for no limit)
            use_cache: Use cached results if available
            batch_size: Process stocks in batches (for rate limiting)
            max_stocks: Maximum number of stocks to process (for testing)

        Returns:
            List of stocks meeting criteria with their data
        """
        logger.info("="*80)
        logger.info("🔍 MARKET-WIDE STOCK SCANNER")
        logger.info("="*80)
        logger.info(f"Filters: Price > ${min_price}, Volume > {min_avg_volume:,.0f}")
        if max_market_cap:
            logger.info(f"         Market Cap < ${max_market_cap:,.0f}")
        logger.info("")

        # Check cache first
        if use_cache:
            cached = self._get_cached_results(min_price, min_avg_volume, max_market_cap)
            if cached:
                logger.info(f"✅ Using cached results: {len(cached)} stocks")
                return cached

        # Get all tickers
        all_tickers = self.get_all_us_tickers()

        if max_stocks:
            logger.info(f"⚠️  Testing mode: Limiting to {max_stocks} stocks")
            all_tickers = all_tickers[:max_stocks]

        logger.info(f"📊 Screening {len(all_tickers)} stocks...")

        # Screen stocks in batches
        passing_stocks = []
        failed_count = 0

        for i in range(0, len(all_tickers), batch_size):
            batch = all_tickers[i:i+batch_size]

            logger.info(f"Processing batch {i//batch_size + 1} ({i+1}-{min(i+batch_size, len(all_tickers))} of {len(all_tickers)})...")

            for ticker_info in batch:
                symbol = ticker_info['symbol']

                try:
                    # Fetch stock data
                    stock_data = self._fetch_stock_data(symbol)

                    if stock_data is None:
                        failed_count += 1
                        continue

                    # Apply filters
                    price = stock_data.get('price', 0)
                    avg_volume = stock_data.get('avg_volume', 0)
                    market_cap = stock_data.get('market_cap', 0)

                    passes_filters = True

                    if price < min_price:
                        passes_filters = False

                    if avg_volume < min_avg_volume:
                        passes_filters = False

                    if max_market_cap and market_cap > max_market_cap:
                        passes_filters = False

                    if passes_filters:
                        stock_data['symbol'] = symbol
                        stock_data['name'] = ticker_info.get('name', '')
                        stock_data['exchange'] = ticker_info.get('exchange', '')
                        passing_stocks.append(stock_data)

                        # Cache the result
                        self._cache_stock_data(symbol, stock_data)

                except Exception as e:
                    logger.debug(f"Failed to screen {symbol}: {e}")
                    failed_count += 1
                    continue

            # Rate limiting
            time.sleep(1)

        logger.info("")
        logger.info("="*80)
        logger.info("📊 SCREENING RESULTS")
        logger.info("="*80)
        logger.info(f"Total stocks screened: {len(all_tickers)}")
        logger.info(f"Passed filters: {len(passing_stocks)}")
        logger.info(f"Failed/skipped: {failed_count}")
        logger.info("")

        # Show distribution
        if passing_stocks:
            self._show_distribution(passing_stocks)

        return passing_stocks

    def _fetch_stock_data(self, symbol: str) -> Optional[Dict[str, any]]:
        """
        Fetch stock data (price, volume, market cap) for screening.

        Returns:
            Dict with price, avg_volume, market_cap, or None if failed
        """
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            # Get current price
            price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose')

            # Get average volume
            avg_volume = info.get('averageVolume') or info.get('averageVolume10days')

            # Get market cap
            market_cap = info.get('marketCap')

            # Validate we have minimum data
            if price is None or avg_volume is None:
                return None

            return {
                'price': float(price),
                'avg_volume': float(avg_volume),
                'market_cap': float(market_cap) if market_cap else 0
            }

        except Exception as e:
            logger.debug(f"Failed to fetch data for {symbol}: {e}")
            return None

    def _cache_stock_data(self, symbol: str, data: Dict[str, any]):
        """Cache stock screening data."""
        try:
            screening = self.session.query(StockScreening).filter_by(symbol=symbol).first()

            if screening:
                screening.price = data['price']
                screening.avg_volume = data['avg_volume']
                screening.market_cap = data['market_cap']
                screening.name = data.get('name', '')
                screening.exchange = data.get('exchange', '')
                screening.last_updated = datetime.now()
            else:
                screening = StockScreening(
                    symbol=symbol,
                    price=data['price'],
                    avg_volume=data['avg_volume'],
                    market_cap=data['market_cap'],
                    name=data.get('name', ''),
                    exchange=data.get('exchange', ''),
                    last_updated=datetime.now()
                )
                self.session.add(screening)

            self.session.commit()

        except Exception as e:
            logger.debug(f"Failed to cache {symbol}: {e}")
            self.session.rollback()

    def _get_cached_results(
        self,
        min_price: float,
        min_avg_volume: float,
        max_market_cap: Optional[float]
    ) -> Optional[List[Dict[str, any]]]:
        """Get cached screening results if available."""
        try:
            cutoff_time = datetime.now() - timedelta(hours=self.cache_hours)

            query = self.session.query(StockScreening).filter(
                StockScreening.last_updated >= cutoff_time,
                StockScreening.price >= min_price,
                StockScreening.avg_volume >= min_avg_volume
            )

            if max_market_cap:
                query = query.filter(StockScreening.market_cap <= max_market_cap)

            results = query.all()

            if len(results) < 100:  # If cache is too small, re-scan
                return None

            return [{
                'symbol': r.symbol,
                'price': r.price,
                'avg_volume': r.avg_volume,
                'market_cap': r.market_cap,
                'name': r.name,
                'exchange': r.exchange
            } for r in results]

        except Exception as e:
            logger.debug(f"Failed to get cached results: {e}")
            return None

    def _show_distribution(self, stocks: List[Dict[str, any]]):
        """Show distribution of passing stocks."""
        # Price distribution
        prices = [s['price'] for s in stocks]
        price_buckets = {
            '$1-$10': len([p for p in prices if 1 <= p < 10]),
            '$10-$50': len([p for p in prices if 10 <= p < 50]),
            '$50-$200': len([p for p in prices if 50 <= p < 200]),
            '$200+': len([p for p in prices if p >= 200])
        }

        # Volume distribution
        volumes = [s['avg_volume'] for s in stocks]
        volume_buckets = {
            '1M-5M': len([v for v in volumes if 1_000_000 <= v < 5_000_000]),
            '5M-10M': len([v for v in volumes if 5_000_000 <= v < 10_000_000]),
            '10M-50M': len([v for v in volumes if 10_000_000 <= v < 50_000_000]),
            '50M+': len([v for v in volumes if v >= 50_000_000])
        }

        # Market cap distribution
        mcaps = [s['market_cap'] for s in stocks if s['market_cap'] > 0]
        mcap_buckets = {
            'Micro (<$300M)': len([m for m in mcaps if m < 300_000_000]),
            'Small ($300M-$2B)': len([m for m in mcaps if 300_000_000 <= m < 2_000_000_000]),
            'Mid ($2B-$10B)': len([m for m in mcaps if 2_000_000_000 <= m < 10_000_000_000]),
            'Large ($10B-$200B)': len([m for m in mcaps if 10_000_000_000 <= m < 200_000_000_000]),
            'Mega ($200B+)': len([m for m in mcaps if m >= 200_000_000_000])
        }

        logger.info("📊 Price Distribution:")
        for bucket, count in price_buckets.items():
            pct = 100 * count / len(stocks)
            logger.info(f"  {bucket:15s}: {count:5d} ({pct:5.1f}%)")

        logger.info("")
        logger.info("📊 Volume Distribution:")
        for bucket, count in volume_buckets.items():
            pct = 100 * count / len(stocks)
            logger.info(f"  {bucket:15s}: {count:5d} ({pct:5.1f}%)")

        logger.info("")
        logger.info("📊 Market Cap Distribution:")
        for bucket, count in mcap_buckets.items():
            pct = 100 * count / len(stocks) if len(stocks) > 0 else 0
            logger.info(f"  {bucket:25s}: {count:5d} ({pct:5.1f}%)")

        logger.info("")
        logger.info("📈 Top 20 by Volume:")
        sorted_by_vol = sorted(stocks, key=lambda x: x['avg_volume'], reverse=True)[:20]
        for i, s in enumerate(sorted_by_vol, 1):
            logger.info(f"  {i:2d}. {s['symbol']:6s}  ${s['price']:8.2f}  Vol: {s['avg_volume']:>12,.0f}  MCap: ${s['market_cap']/1e9:>6.1f}B")


def scan_market(
    min_price: float = 1.0,
    min_avg_volume: float = 1_000_000,
    max_market_cap: Optional[float] = 1_000_000_000_000,
    use_cache: bool = True,
    max_stocks_for_testing: Optional[int] = None
) -> List[str]:
    """
    Scan entire US stock market and return symbols meeting criteria.

    Args:
        min_price: Minimum stock price (default $1)
        min_avg_volume: Minimum average daily volume (default 1M)
        max_market_cap: Maximum market cap (default $1T)
        use_cache: Use cached results if available
        max_stocks_for_testing: Limit processing for testing (default None = all)

    Returns:
        List of stock symbols meeting criteria
    """
    scanner = MarketScanner()

    stocks = scanner.screen_stocks(
        min_price=min_price,
        min_avg_volume=min_avg_volume,
        max_market_cap=max_market_cap,
        use_cache=use_cache,
        max_stocks=max_stocks_for_testing
    )

    return [s['symbol'] for s in stocks]


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    # Test with small sample first
    print("\n🧪 Testing scanner with 100 stocks...\n")

    symbols = scan_market(
        min_price=1.0,
        min_avg_volume=1_000_000,
        max_market_cap=1_000_000_000_000,  # $1T
        use_cache=False,
        max_stocks_for_testing=100  # Test with 100 first
    )

    print(f"\n✅ Scanner found {len(symbols)} stocks meeting criteria")
    print(f"Sample symbols: {', '.join(symbols[:20])}")
