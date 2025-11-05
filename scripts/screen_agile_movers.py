"""
REAL WORKING STOCK SCREENER - Like Finviz but better for our use case.

Screens stocks with extensive filters:
- Market cap, price, volume
- Sector, industry
- Fundamentals (revenue, growth)
- Technical (beta, volatility, RSI, BB compression)
- Custom agile mover criteria

NO MOCKING - Uses real data sources.
"""

import logging
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StockScreener:
    """
    Robust stock screener with extensive filters.
    """

    def __init__(self, max_workers: int = 10):
        """
        Args:
            max_workers: Number of parallel threads for data fetching
        """
        self.max_workers = max_workers
        self.cache = {}

    def fetch_stock_data(self, symbol: str) -> Optional[Dict]:
        """
        Fetch comprehensive data for a stock.

        Returns:
            Dict with all screening data or None if failed
        """
        if symbol in self.cache:
            return self.cache[symbol]

        try:
            ticker = yf.Ticker(symbol)

            # Get quote data (faster than full info)
            fast_info = ticker.fast_info

            # Try to get basic data from fast_info first
            price = fast_info.get('last_price') or fast_info.get('regularMarketPrice')
            market_cap = fast_info.get('market_cap') or fast_info.get('marketCap')

            if price is None or market_cap is None:
                # Fallback to full info (slower)
                info = ticker.info
                price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose')
                market_cap = info.get('marketCap')

                if price is None or market_cap is None:
                    return None

            # Get historical data for technical analysis
            hist = ticker.history(period='3mo')

            if hist.empty or len(hist) < 20:
                return None

            # Calculate metrics
            close_prices = hist['Close']
            volumes = hist['Volume']

            # Volatility
            returns = close_prices.pct_change().dropna()
            volatility = returns.std() * (252 ** 0.5)  # Annualized

            # ATR (simplified - using high-low range)
            atr_pct = ((hist['High'] - hist['Low']) / hist['Close']).tail(14).mean() * 100

            # Beta (vs SPY)
            try:
                spy = yf.Ticker('SPY')
                spy_hist = spy.history(period='3mo')
                if not spy_hist.empty and len(spy_hist) == len(hist):
                    spy_returns = spy_hist['Close'].pct_change().dropna()
                    market_returns = spy_returns[returns.index]
                    covariance = returns.cov(market_returns)
                    market_variance = market_returns.var()
                    beta = covariance / market_variance if market_variance != 0 else 1.0
                else:
                    beta = 1.0
            except:
                beta = 1.0

            # Volume
            avg_volume = volumes.tail(20).mean()

            # Bollinger Bands compression
            bb_window = 20
            bb_middle = close_prices.rolling(bb_window).mean()
            bb_std = close_prices.rolling(bb_window).std()
            bb_width_pct = (2 * bb_std / bb_middle * 100).iloc[-1]

            # RSI
            delta = close_prices.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            current_rsi = rsi.iloc[-1] if not rsi.empty else 50

            # Price change
            price_change_1d = ((close_prices.iloc[-1] - close_prices.iloc[-2]) / close_prices.iloc[-2] * 100) if len(close_prices) > 1 else 0
            price_change_1w = ((close_prices.iloc[-1] - close_prices.iloc[-5]) / close_prices.iloc[-5] * 100) if len(close_prices) > 5 else 0
            price_change_1m = ((close_prices.iloc[-1] - close_prices.iloc[-20]) / close_prices.iloc[-20] * 100) if len(close_prices) > 20 else 0

            # Try to get fundamentals
            try:
                info = ticker.info
                revenue = info.get('totalRevenue', 0)
                sector = info.get('sector', 'Unknown')
                industry = info.get('industry', 'Unknown')
            except:
                revenue = 0
                sector = 'Unknown'
                industry = 'Unknown'

            data = {
                'symbol': symbol,
                'price': float(price),
                'market_cap': float(market_cap),
                'avg_volume': float(avg_volume),
                'volatility': float(volatility),
                'beta': float(beta),
                'atr_pct': float(atr_pct),
                'bb_width_pct': float(bb_width_pct),
                'rsi': float(current_rsi),
                'price_change_1d': float(price_change_1d),
                'price_change_1w': float(price_change_1w),
                'price_change_1m': float(price_change_1m),
                'revenue': float(revenue),
                'sector': sector,
                'industry': industry,
                'last_updated': datetime.now()
            }

            self.cache[symbol] = data
            return data

        except Exception as e:
            logger.debug(f"Failed to fetch {symbol}: {e}")
            return None

    def screen_stocks(
        self,
        symbols: List[str],
        # Price filters
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        # Market cap filters
        min_market_cap: Optional[float] = None,
        max_market_cap: Optional[float] = None,
        # Volume filters
        min_volume: Optional[float] = None,
        # Volatility filters
        min_beta: Optional[float] = None,
        max_beta: Optional[float] = None,
        min_atr_pct: Optional[float] = None,
        # Technical filters
        max_rsi: Optional[float] = None,
        min_rsi: Optional[float] = None,
        max_bb_width_pct: Optional[float] = None,  # For compression
        # Fundamental filters
        min_revenue: Optional[float] = None,
        sectors: Optional[List[str]] = None,
        # Performance filters
        min_price_change_1m: Optional[float] = None,
        max_price_change_1m: Optional[float] = None,
    ) -> pd.DataFrame:
        """
        Screen stocks with extensive filters.

        Returns:
            DataFrame with stocks meeting ALL criteria
        """

        logger.info(f"🔍 Screening {len(symbols)} stocks...")
        logger.info("")

        # Fetch data for all stocks in parallel
        results = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_symbol = {executor.submit(self.fetch_stock_data, symbol): symbol for symbol in symbols}

            for i, future in enumerate(as_completed(future_to_symbol), 1):
                symbol = future_to_symbol[future]
                try:
                    data = future.result()
                    if data:
                        results.append(data)

                    if i % 10 == 0:
                        logger.info(f"  Processed {i}/{len(symbols)} stocks...")

                except Exception as e:
                    logger.debug(f"Error processing {symbol}: {e}")

        logger.info(f"  Successfully fetched data for {len(results)}/{len(symbols)} stocks")
        logger.info("")

        if not results:
            logger.warning("No data fetched")
            return pd.DataFrame()

        # Create DataFrame
        df = pd.DataFrame(results)

        # Apply filters
        logger.info("📊 Applying filters...")
        initial_count = len(df)

        if min_price is not None:
            df = df[df['price'] >= min_price]
            logger.info(f"  Price >= ${min_price}: {len(df)}/{initial_count} remain")

        if max_price is not None:
            df = df[df['price'] <= max_price]
            logger.info(f"  Price <= ${max_price}: {len(df)}/{initial_count} remain")

        if min_market_cap is not None:
            df = df[df['market_cap'] >= min_market_cap]
            logger.info(f"  Market cap >= ${min_market_cap/1e9:.1f}B: {len(df)}/{initial_count} remain")

        if max_market_cap is not None:
            df = df[df['market_cap'] <= max_market_cap]
            logger.info(f"  Market cap <= ${max_market_cap/1e9:.1f}B: {len(df)}/{initial_count} remain")

        if min_volume is not None:
            df = df[df['avg_volume'] >= min_volume]
            logger.info(f"  Volume >= {min_volume/1e6:.1f}M: {len(df)}/{initial_count} remain")

        if min_beta is not None:
            df = df[df['beta'] >= min_beta]
            logger.info(f"  Beta >= {min_beta}: {len(df)}/{initial_count} remain")

        if max_beta is not None:
            df = df[df['beta'] <= max_beta]
            logger.info(f"  Beta <= {max_beta}: {len(df)}/{initial_count} remain")

        if min_atr_pct is not None:
            df = df[df['atr_pct'] >= min_atr_pct]
            logger.info(f"  ATR >= {min_atr_pct}%: {len(df)}/{initial_count} remain")

        if max_rsi is not None:
            df = df[df['rsi'] <= max_rsi]
            logger.info(f"  RSI <= {max_rsi}: {len(df)}/{initial_count} remain")

        if min_rsi is not None:
            df = df[df['rsi'] >= min_rsi]
            logger.info(f"  RSI >= {min_rsi}: {len(df)}/{initial_count} remain")

        if max_bb_width_pct is not None:
            df = df[df['bb_width_pct'] <= max_bb_width_pct]
            logger.info(f"  BB Width <= {max_bb_width_pct}% (compression): {len(df)}/{initial_count} remain")

        if min_revenue is not None:
            df = df[df['revenue'] >= min_revenue]
            logger.info(f"  Revenue >= ${min_revenue/1e6:.0f}M: {len(df)}/{initial_count} remain")

        if sectors is not None and len(sectors) > 0:
            df = df[df['sector'].isin(sectors)]
            logger.info(f"  Sector in {sectors}: {len(df)}/{initial_count} remain")

        if min_price_change_1m is not None:
            df = df[df['price_change_1m'] >= min_price_change_1m]
            logger.info(f"  1M change >= {min_price_change_1m}%: {len(df)}/{initial_count} remain")

        if max_price_change_1m is not None:
            df = df[df['price_change_1m'] <= max_price_change_1m]
            logger.info(f"  1M change <= {max_price_change_1m}%: {len(df)}/{initial_count} remain")

        logger.info("")
        logger.info(f"✅ {len(df)} stocks passed all filters")

        return df


def get_test_universe() -> List[str]:
    """Get test universe of potential agile movers."""
    # This is just a starting point - in production, scan full market
    return [
        # AI/ML
        'RXRX', 'RZLV', 'AI', 'BBAI', 'SOUN',
        # Quantum
        'RGTI', 'IONQ', 'QUBT',
        # Fintech
        'SOFI', 'UPST', 'AFRM', 'LC', 'NU',
        # Proptech
        'OPEN', 'RDFN', 'COMP',
        # Mobility
        'SRFM', 'JOBY', 'ACHR', 'EVTL',
        # Emerging markets
        'JMIA', 'GRAB', 'SEA',
        # Clean energy
        'PLUG', 'FCEL', 'BLDP', 'CLSK',
        # Biotech
        'CRSP', 'EDIT', 'NTLA', 'BEAM',
        # Space
        'SPCE', 'ASTR', 'RDW',
        # Additional growth stocks
        'PLTR', 'COIN', 'HOOD', 'RBLX', 'DDOG', 'NET',
        'CRWD', 'SNOW', 'RIOT', 'MARA', 'LAZR',
    ]


def screen_agile_movers():
    """Screen for agile fast movers like OPEN, RZLV, RXRX, RGTI, SRFM, JMIA."""

    print("="*80)
    print("🚀 AGILE FAST MOVER SCREENER")
    print("="*80)
    print()
    print("Screening for stocks like OPEN, RZLV, RXRX, RGTI, SRFM, JMIA")
    print("Target: 50%+ movement potential with solid fundamentals")
    print()
    print("="*80)
    print()

    screener = StockScreener(max_workers=5)  # Limit concurrent requests

    universe = get_test_universe()

    # SCREEN 1: Agile Movers (high movement potential)
    print("📊 SCREEN 1: Agile Movers (High Movement Potential)")
    print("-"*80)

    agile_movers = screener.screen_stocks(
        symbols=universe,
        min_price=5.0,              # Avoid penny stocks
        min_market_cap=300_000_000,  # $300M minimum
        max_market_cap=20_000_000_000,  # $20B maximum
        min_volume=500_000,         # Good liquidity
        min_beta=1.5,               # High volatility
        min_atr_pct=5.0,            # Can move significantly
        min_revenue=10_000_000,     # Real business
    )

    print()
    print("="*80)
    print(f"✅ Found {len(agile_movers)} agile movers")
    print("="*80)
    print()

    if not agile_movers.empty:
        # Sort by ATR (movement potential)
        agile_movers = agile_movers.sort_values('atr_pct', ascending=False)

        print("Top agile movers by volatility (ATR):")
        print()

        for i, (idx, row) in enumerate(agile_movers.head(20).iterrows(), 1):
            mcap_str = f"${row['market_cap']/1e9:.2f}B" if row['market_cap'] >= 1e9 else f"${row['market_cap']/1e6:.0f}M"
            print(f"{i:2d}. {row['symbol']:6s}  ${row['price']:8.2f}  MCap: {mcap_str:8s}  "
                  f"Vol: {row['avg_volume']/1e6:5.1f}M  Beta: {row['beta']:4.1f}  "
                  f"ATR: {row['atr_pct']:5.1f}%  RSI: {row['rsi']:5.1f}")

    print()
    print("="*80)
    print()

    # SCREEN 2: Compressed Agile Movers (ready to explode)
    print("📊 SCREEN 2: Compressed Agile Movers (Ready to Explode)")
    print("-"*80)

    compressed = screener.screen_stocks(
        symbols=universe,
        min_price=5.0,
        min_market_cap=300_000_000,
        max_market_cap=20_000_000_000,
        min_volume=500_000,
        min_beta=1.5,
        max_bb_width_pct=8.0,       # BB compression
        max_rsi=50,                 # Not overbought
        min_revenue=10_000_000,
    )

    print()
    print("="*80)
    print(f"✅ Found {len(compressed)} compressed stocks (HIGH PRIORITY)")
    print("="*80)
    print()

    if not compressed.empty:
        # Sort by BB width (most compressed first)
        compressed = compressed.sort_values('bb_width_pct')

        print("Most compressed stocks (explosion candidates):")
        print()

        for i, (idx, row) in enumerate(compressed.head(10).iterrows(), 1):
            mcap_str = f"${row['market_cap']/1e9:.2f}B" if row['market_cap'] >= 1e9 else f"${row['market_cap']/1e6:.0f}M"
            print(f"{i:2d}. {row['symbol']:6s}  ${row['price']:8.2f}  MCap: {mcap_str:8s}  "
                  f"BB: {row['bb_width_pct']:5.2f}%  RSI: {row['rsi']:5.1f}  "
                  f"ATR: {row['atr_pct']:5.1f}%  1M: {row['price_change_1m']:+6.1f}%")

    print()
    print("="*80)
    print()

    # Export to CSV
    if not agile_movers.empty:
        agile_movers.to_csv('data/agile_movers_screen.csv', index=False)
        print(f"📁 Exported {len(agile_movers)} agile movers to data/agile_movers_screen.csv")

    if not compressed.empty:
        compressed.to_csv('data/compressed_agile_movers.csv', index=False)
        print(f"📁 Exported {len(compressed)} compressed stocks to data/compressed_agile_movers.csv")

    print()
    print("="*80)


if __name__ == '__main__':
    screen_agile_movers()
