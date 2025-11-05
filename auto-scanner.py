#!/usr/bin/env python3
"""
Automated Scanner - Runs scans on schedule and sends alerts

Run this in the background to automatically scan markets and alert you
to high-conviction opportunities.

Usage:
    python3 auto-scanner.py --interval 1h          # Scan every hour
    python3 auto-scanner.py --interval 30m         # Scan every 30 minutes
    python3 auto-scanner.py --daemon               # Run as background daemon

Features:
- Scheduled scanning (15m, 30m, 1h, 4h)
- Auto-refresh for latest data
- High-priority alerts (score >= 80)
- Email/webhook notifications (optional)
- Log all results
"""

import sys
import time
import argparse
import logging
from datetime import datetime
from pathlib import Path
import json

# Add project to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Setup logging
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "auto_scanner.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class AutoScanner:
    """Automated market scanner"""

    def __init__(self, interval_minutes: int = 60, min_alert_score: int = 80):
        """
        Args:
            interval_minutes: Minutes between scans
            min_alert_score: Minimum score for alerts
        """
        self.interval_minutes = interval_minutes
        self.min_alert_score = min_alert_score
        self.scan_count = 0
        self.alert_count = 0
        self.results_dir = PROJECT_ROOT / "results" / "auto_scans"
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def scan_markets(self):
        """Run a complete market scan"""
        logger.info(f"Starting scan #{self.scan_count + 1}")
        logger.info("="*80)

        scan_results = {
            'timestamp': datetime.now().isoformat(),
            'scan_number': self.scan_count + 1,
            'crypto': [],
            'stocks': [],
            'alerts': []
        }

        # Scan crypto
        try:
            logger.info("📊 Scanning cryptocurrencies...")
            crypto_results = self._scan_crypto()
            scan_results['crypto'] = crypto_results
            logger.info(f"   Found {len(crypto_results)} crypto opportunities")
        except Exception as e:
            logger.error(f"   ❌ Crypto scan failed: {e}")

        # Scan stocks
        try:
            logger.info("📊 Scanning stocks...")
            stock_results = self._scan_stocks()
            scan_results['stocks'] = stock_results
            logger.info(f"   Found {len(stock_results)} stock opportunities")
        except Exception as e:
            logger.error(f"   ❌ Stock scan failed: {e}")

        # Find high-priority alerts
        alerts = self._find_alerts(scan_results)
        scan_results['alerts'] = alerts

        if alerts:
            logger.warning(f"🔔 {len(alerts)} HIGH-PRIORITY ALERTS!")
            for alert in alerts:
                logger.warning(f"   🚨 {alert['ticker']} - Score: {alert['score']}/100 - {alert['reason']}")
            self.alert_count += len(alerts)

        # Save results
        self._save_results(scan_results)

        self.scan_count += 1
        logger.info("="*80)
        logger.info(f"✅ Scan complete. Total scans: {self.scan_count}, Total alerts: {self.alert_count}")
        logger.info("")

        return scan_results

    def _scan_crypto(self):
        """Scan cryptocurrencies"""
        # Import and run crypto screener
        try:
            from qaht.data_sources.free_crypto_api import FreeCryptoAPI

            api = FreeCryptoAPI()
            coins = api.fetch_all_coins()

            # Filter for quality opportunities
            opportunities = []
            for coin in coins:
                # Simple scoring (in production, use full strategy)
                score = 0
                if coin.get('market_cap', 0) > 50_000_000:  # > $50M
                    score += 20
                if coin.get('volume_24h', 0) > 1_000_000:  # > $1M volume
                    score += 20
                if abs(coin.get('change_24h', 0)) > 5:  # Moving
                    score += 30
                if 0 < coin.get('rank', 9999) <= 300:  # Top 300
                    score += 30

                if score >= self.min_alert_score:
                    opportunities.append({
                        'ticker': coin['symbol'],
                        'score': score,
                        'price': coin.get('price', 0),
                        'change_24h': coin.get('change_24h', 0),
                        'market_cap': coin.get('market_cap', 0),
                        'volume_24h': coin.get('volume_24h', 0),
                        'type': 'CRYPTO'
                    })

            return opportunities

        except Exception as e:
            logger.error(f"Crypto scan error: {e}")
            return []

    def _scan_stocks(self):
        """Scan stocks"""
        # In production, run full agile mover filter
        # For now, return placeholder
        try:
            from qaht.equities_options.market_scanner import MarketScanner
            from qaht.equities_options.agile_movers_filter import AgileMoverFilter

            scanner = MarketScanner()
            agile_filter = AgileMoverFilter()

            # Get sample of stocks (in production, scan all)
            stocks = scanner.screen_stocks(
                min_price=1.0,
                min_avg_volume=1_000_000,
                use_cache=False  # Always fresh data for automation
            )

            opportunities = []
            for stock in stocks[:50]:  # Sample
                score_result = agile_filter.score_agile_mover_potential(stock)
                if score_result['score'] >= self.min_alert_score:
                    opportunities.append({
                        'ticker': score_result['ticker'],
                        'score': score_result['score'],
                        'rating': score_result['rating'],
                        'type': 'STOCK'
                    })

            return opportunities

        except Exception as e:
            logger.error(f"Stock scan error: {e}")
            return []

    def _find_alerts(self, scan_results):
        """Find high-priority alerts"""
        alerts = []

        # Crypto alerts
        for crypto in scan_results.get('crypto', []):
            if crypto['score'] >= self.min_alert_score:
                alerts.append({
                    'ticker': crypto['ticker'],
                    'score': crypto['score'],
                    'type': 'CRYPTO',
                    'reason': f"Score {crypto['score']}, Change: {crypto['change_24h']:+.1f}%"
                })

        # Stock alerts
        for stock in scan_results.get('stocks', []):
            if stock['score'] >= self.min_alert_score:
                alerts.append({
                    'ticker': stock['ticker'],
                    'score': stock['score'],
                    'type': 'STOCK',
                    'reason': f"Score {stock['score']}, Rating: {stock['rating']}"
                })

        # Sort by score
        alerts.sort(key=lambda x: x['score'], reverse=True)

        return alerts

    def _save_results(self, results):
        """Save scan results to file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.results_dir / f"scan_{timestamp}.json"

        try:
            with open(filename, 'w') as f:
                json.dump(results, f, indent=2)
            logger.debug(f"Results saved to {filename}")
        except Exception as e:
            logger.error(f"Failed to save results: {e}")

    def run(self, daemon: bool = False):
        """
        Run the automated scanner

        Args:
            daemon: If True, run as background daemon
        """
        logger.info("🚀 Quantum Alpha Hunter - Automated Scanner")
        logger.info("="*80)
        logger.info(f"Interval: {self.interval_minutes} minutes")
        logger.info(f"Alert threshold: {self.min_alert_score}/100")
        logger.info(f"Daemon mode: {daemon}")
        logger.info("="*80)
        logger.info("")

        if daemon:
            logger.info("Running as daemon (press CTRL+C to stop)")
        else:
            logger.info("Running in foreground (press CTRL+C to stop)")

        logger.info("")

        try:
            while True:
                # Run scan
                self.scan_markets()

                # Wait for next interval
                logger.info(f"💤 Sleeping for {self.interval_minutes} minutes...")
                logger.info("")
                time.sleep(self.interval_minutes * 60)

        except KeyboardInterrupt:
            logger.info("")
            logger.info("="*80)
            logger.info("🛑 Scanner stopped by user")
            logger.info(f"Total scans: {self.scan_count}")
            logger.info(f"Total alerts: {self.alert_count}")
            logger.info("="*80)


def main():
    parser = argparse.ArgumentParser(
        description='Automated market scanner with alerts',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 auto-scanner.py --interval 1h           # Scan every hour
  python3 auto-scanner.py --interval 30m          # Scan every 30 min
  python3 auto-scanner.py --daemon                # Run as background daemon
  python3 auto-scanner.py --interval 15m --min-score 85  # High-quality only

Intervals:
  15m, 30m, 1h, 2h, 4h, 6h, 12h, 24h
        """
    )

    parser.add_argument(
        '--interval',
        default='1h',
        help='Scan interval (15m, 30m, 1h, 2h, 4h, 6h, 12h, 24h)'
    )
    parser.add_argument(
        '--min-score',
        type=int,
        default=80,
        help='Minimum score for alerts (default: 80)'
    )
    parser.add_argument(
        '--daemon',
        action='store_true',
        help='Run as background daemon'
    )

    args = parser.parse_args()

    # Parse interval
    interval_str = args.interval.lower()
    if interval_str.endswith('m'):
        interval_minutes = int(interval_str[:-1])
    elif interval_str.endswith('h'):
        interval_minutes = int(interval_str[:-1]) * 60
    else:
        print(f"Invalid interval: {interval_str}")
        print("Use format: 15m, 30m, 1h, 2h, etc.")
        sys.exit(1)

    # Create and run scanner
    scanner = AutoScanner(
        interval_minutes=interval_minutes,
        min_alert_score=args.min_score
    )

    scanner.run(daemon=args.daemon)


if __name__ == '__main__':
    main()
