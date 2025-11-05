#!/usr/bin/env python3
"""
Source Manager CLI - Toggle news/social sources on/off

Usage:
    python3 qaht-sources.py list              # Show all sources
    python3 qaht-sources.py enable stocktwits # Enable StockTwits
    python3 qaht-sources.py disable fourchan  # Disable 4chan
    python3 qaht-sources.py status            # Show enabled sources
"""

import sys
import argparse
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from qaht.core.source_manager import SourceManager


def cmd_list(manager: SourceManager):
    """List all available sources"""
    print("="*80)
    print("📰 Available News & Social Sources")
    print("="*80)
    print()

    sources = manager.list_all_sources()

    print("NEWS SOURCES:")
    print("-"*80)
    for source in sources['news']:
        status = "✅ ENABLED " if source['enabled'] else "❌ DISABLED"
        api_key = "🔑 API Key" if source['requires_api_key'] else "   No Key"
        print(f"{status} │ {source['display_name']:25s} │ {api_key} │ {source['cost']:8s} │ {source['rate_limit']}")

    print()
    print("SOCIAL SOURCES:")
    print("-"*80)
    for source in sources['social']:
        status = "✅ ENABLED " if source['enabled'] else "❌ DISABLED"
        api_key = "🔑 API Key" if source['requires_api_key'] else "   No Key"
        warning = f" ⚠️  {source['warning']}" if source.get('warning') else ""
        print(f"{status} │ {source['display_name']:25s} │ {api_key} │ {source['cost']:8s} │ {source['rate_limit']}{warning}")

    print()
    print("="*80)


def cmd_status(manager: SourceManager):
    """Show current enabled sources"""
    print("="*80)
    print("📊 Currently Enabled Sources")
    print("="*80)
    print()

    enabled = manager.get_all_enabled_sources()

    print(f"📰 News Sources ({len(enabled['news'])}):")
    for source in enabled['news']:
        print(f"  ✅ {source}")

    print()
    print(f"💬 Social Sources ({len(enabled['social'])}):")
    for source in enabled['social']:
        print(f"  ✅ {source}")

    print()
    print("="*80)


def cmd_enable(manager: SourceManager, source_name: str):
    """Enable a source"""
    if manager.enable_source(source_name):
        print(f"✅ Enabled: {source_name}")
    else:
        print(f"❌ Source not found: {source_name}")
        print()
        print("Available sources:")
        sources = manager.list_all_sources()
        for source in sources['news'] + sources['social']:
            print(f"  - {source['name']}")


def cmd_disable(manager: SourceManager, source_name: str):
    """Disable a source"""
    if manager.disable_source(source_name):
        print(f"❌ Disabled: {source_name}")
    else:
        print(f"❌ Source not found: {source_name}")


def main():
    parser = argparse.ArgumentParser(
        description="Manage news and social sources",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 qaht-sources.py list                  # Show all sources
  python3 qaht-sources.py status                # Show enabled sources
  python3 qaht-sources.py enable stocktwits     # Enable StockTwits
  python3 qaht-sources.py disable fourchan      # Disable 4chan
  python3 qaht-sources.py enable youtube        # Enable YouTube
  python3 qaht-sources.py disable newsapi       # Disable NewsAPI

Source names:
  News: newsapi, google_news, finnhub, yahoo_finance, seeking_alpha
  Social: reddit, stocktwits, youtube, telegram, fourchan, lunarcrush
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # List command
    subparsers.add_parser('list', help='List all sources')

    # Status command
    subparsers.add_parser('status', help='Show enabled sources')

    # Enable command
    enable_parser = subparsers.add_parser('enable', help='Enable a source')
    enable_parser.add_argument('source', help='Source name (e.g., stocktwits, youtube)')

    # Disable command
    disable_parser = subparsers.add_parser('disable', help='Disable a source')
    disable_parser.add_argument('source', help='Source name (e.g., fourchan)')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Create manager
    manager = SourceManager()

    # Execute command
    if args.command == 'list':
        cmd_list(manager)
    elif args.command == 'status':
        cmd_status(manager)
    elif args.command == 'enable':
        cmd_enable(manager, args.source)
    elif args.command == 'disable':
        cmd_disable(manager, args.source)


if __name__ == '__main__':
    main()
