#!/usr/bin/env python3
"""
Quantum Alpha Hunter - CLI Tool

Makes running the system SUPER EASY and FAST.

Usage:
    qaht scan crypto              # Scan cryptocurrencies
    qaht scan stocks              # Scan stocks for agile movers
    qaht scan all                 # Scan everything
    qaht dashboard                # Start dashboard
    qaht automate                 # Setup automated scanning
    qaht schedule                 # View scheduled tasks
    qaht alert                    # Check for new alerts

Examples:
    qaht scan crypto --force-refresh
    qaht scan stocks --min-score 80
    qaht dashboard --port 8000
    qaht automate --interval 1h
"""

import sys
import argparse
import subprocess
import os
from pathlib import Path
from typing import Optional

# Add project to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


class QAHTCLI:
    """Quantum Alpha Hunter Command-Line Interface"""

    def __init__(self):
        self.root = PROJECT_ROOT

    def scan_crypto(self, force_refresh: bool = False, min_score: int = 70):
        """Scan cryptocurrencies"""
        print("🪙 Scanning cryptocurrencies...")
        print()

        cmd = [sys.executable, str(self.root / "scripts/screen_crypto_real.py")]
        if force_refresh:
            cmd.append("--force-refresh")

        subprocess.run(cmd)

    def scan_stocks(self, force_refresh: bool = False, min_score: int = 70):
        """Scan stocks for agile movers"""
        print("📈 Scanning stocks for agile movers...")
        print()

        # Import and run stock screener
        try:
            from qaht.equities_options.market_scanner import MarketScanner
            from qaht.equities_options.agile_movers_filter import AgileMoverFilter

            scanner = MarketScanner()
            agile_filter = AgileMoverFilter()

            print("Scanning entire US market...")
            stocks = scanner.screen_stocks(
                min_price=1.0,
                min_avg_volume=1_000_000,
                max_market_cap=1_000_000_000_000,  # $1T
                use_cache=not force_refresh
            )

            print(f"Found {len(stocks)} stocks meeting basic criteria")
            print()
            print("Filtering for agile movers...")

            agile_movers = []
            for stock in stocks[:100]:  # Sample
                score_result = agile_filter.score_agile_mover_potential(stock)
                if score_result['score'] >= min_score:
                    agile_movers.append(score_result)

            print(f"✅ Found {len(agile_movers)} agile movers (score >= {min_score})")

            # Display top 10
            agile_movers.sort(key=lambda x: x['score'], reverse=True)
            print()
            print("Top 10 Agile Movers:")
            print("="*80)
            for i, mover in enumerate(agile_movers[:10], 1):
                print(f"{i:2d}. {mover['ticker']:6s} - Score: {mover['score']}/100 - {mover['rating']}")

        except Exception as e:
            print(f"❌ Error scanning stocks: {e}")
            print("    (This might fail in sandboxed environment - will work on MacBook)")

    def scan_all(self, force_refresh: bool = False, min_score: int = 70):
        """Scan everything (crypto + stocks)"""
        print("🚀 Scanning EVERYTHING...")
        print("="*80)
        print()

        self.scan_crypto(force_refresh, min_score)

        print()
        print("="*80)
        print()

        self.scan_stocks(force_refresh, min_score)

    def start_dashboard(self, port: int = 8000, host: str = "0.0.0.0"):
        """Start the web dashboard"""
        print(f"🚀 Starting Quantum Alpha Hunter Dashboard on http://localhost:{port}")
        print()
        print("Press CTRL+C to stop")
        print("="*80)

        dashboard_dir = self.root / "dashboard"
        subprocess.run(
            [sys.executable, str(dashboard_dir / "server.py")],
            cwd=str(dashboard_dir)
        )

    def setup_automation(self, interval: str = "1h", cron: bool = True):
        """Setup automated scanning"""
        print("⚙️  Setting up automated scanning...")
        print()

        if cron:
            # Generate crontab entries
            print("Add these lines to your crontab (run: crontab -e):")
            print("="*80)
            print()

            if interval == "15m":
                print("# Run every 15 minutes")
                print(f"*/15 * * * * cd {self.root} && {sys.executable} qaht-cli.py scan all >> logs/auto_scan.log 2>&1")
            elif interval == "30m":
                print("# Run every 30 minutes")
                print(f"*/30 * * * * cd {self.root} && {sys.executable} qaht-cli.py scan all >> logs/auto_scan.log 2>&1")
            elif interval == "1h":
                print("# Run every hour")
                print(f"0 * * * * cd {self.root} && {sys.executable} qaht-cli.py scan all >> logs/auto_scan.log 2>&1")
            elif interval == "4h":
                print("# Run every 4 hours")
                print(f"0 */4 * * * cd {self.root} && {sys.executable} qaht-cli.py scan all >> logs/auto_scan.log 2>&1")
            elif interval == "daily":
                print("# Run daily at 9 AM")
                print(f"0 9 * * * cd {self.root} && {sys.executable} qaht-cli.py scan all >> logs/auto_scan.log 2>&1")

            print()
            print("# Start dashboard on boot")
            print(f"@reboot cd {self.root}/dashboard && {sys.executable} server.py >> logs/dashboard.log 2>&1 &")
            print()
            print("="*80)
        else:
            print("Creating systemd service...")
            # TODO: Generate systemd service file

    def show_schedule(self):
        """Show current cron schedule"""
        print("📅 Current scheduled tasks:")
        print("="*80)
        print()

        try:
            result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                if result.stdout.strip():
                    print(result.stdout)
                else:
                    print("No scheduled tasks found")
            else:
                print("No crontab for current user")
        except Exception as e:
            print(f"Error reading crontab: {e}")

    def check_alerts(self, min_score: int = 80):
        """Check for high-priority alerts"""
        print("🔔 Checking for high-priority alerts...")
        print()

        # TODO: Load recent scan results and show high-score signals
        print(f"Looking for signals with score >= {min_score}...")
        print("(Feature coming soon)")


def main():
    parser = argparse.ArgumentParser(
        description="Quantum Alpha Hunter - Fast & Easy CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  qaht scan crypto                    # Scan cryptocurrencies
  qaht scan crypto --force-refresh    # Force fresh data
  qaht scan stocks --min-score 80     # High-quality stocks only
  qaht scan all                       # Scan everything
  qaht dashboard                      # Start web dashboard
  qaht dashboard --port 8080          # Custom port
  qaht automate --interval 1h         # Setup hourly scans
  qaht schedule                       # View cron schedule
  qaht alert                          # Check for alerts

Automation intervals:
  15m, 30m, 1h, 4h, daily
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Scan command
    scan_parser = subparsers.add_parser('scan', help='Scan for opportunities')
    scan_parser.add_argument('type', choices=['crypto', 'stocks', 'all'], help='What to scan')
    scan_parser.add_argument('--force-refresh', action='store_true', help='Bypass cache')
    scan_parser.add_argument('--min-score', type=int, default=70, help='Minimum score (default: 70)')

    # Dashboard command
    dashboard_parser = subparsers.add_parser('dashboard', help='Start web dashboard')
    dashboard_parser.add_argument('--port', type=int, default=8000, help='Port (default: 8000)')
    dashboard_parser.add_argument('--host', default='0.0.0.0', help='Host (default: 0.0.0.0)')

    # Automate command
    automate_parser = subparsers.add_parser('automate', help='Setup automation')
    automate_parser.add_argument('--interval', choices=['15m', '30m', '1h', '4h', 'daily'], default='1h', help='Scan interval')
    automate_parser.add_argument('--no-cron', action='store_true', help='Use systemd instead of cron')

    # Schedule command
    subparsers.add_parser('schedule', help='Show scheduled tasks')

    # Alert command
    alert_parser = subparsers.add_parser('alert', help='Check for alerts')
    alert_parser.add_argument('--min-score', type=int, default=80, help='Minimum score for alerts')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    cli = QAHTCLI()

    # Execute command
    if args.command == 'scan':
        if args.type == 'crypto':
            cli.scan_crypto(args.force_refresh, args.min_score)
        elif args.type == 'stocks':
            cli.scan_stocks(args.force_refresh, args.min_score)
        elif args.type == 'all':
            cli.scan_all(args.force_refresh, args.min_score)

    elif args.command == 'dashboard':
        cli.start_dashboard(args.port, args.host)

    elif args.command == 'automate':
        cli.setup_automation(args.interval, not args.no_cron)

    elif args.command == 'schedule':
        cli.show_schedule()

    elif args.command == 'alert':
        cli.check_alerts(args.min_score)


if __name__ == '__main__':
    main()
