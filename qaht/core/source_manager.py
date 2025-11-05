"""
Source Manager - Easy toggling of news and social sources

Usage:
    from qaht.core.source_manager import SourceManager

    manager = SourceManager()

    # Get enabled sources
    news_sources = manager.get_enabled_news_sources()
    social_sources = manager.get_enabled_social_sources()

    # Toggle sources
    manager.disable_source('fourchan')
    manager.enable_source('stocktwits')
"""

import yaml
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class SourceManager:
    """Manage news and social source configuration"""

    def __init__(self, config_path: Optional[str] = None):
        """
        Args:
            config_path: Path to sources.yaml (default: config/sources.yaml)
        """
        if config_path is None:
            self.config_path = Path(__file__).parent.parent.parent / "config" / "sources.yaml"
        else:
            self.config_path = Path(config_path)

        self.config = self._load_config()

    def _load_config(self) -> Dict:
        """Load configuration from YAML file"""
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            logger.debug(f"Loaded config from {self.config_path}")
            return config
        except FileNotFoundError:
            logger.error(f"Config file not found: {self.config_path}")
            return self._get_default_config()
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return self._get_default_config()

    def _save_config(self):
        """Save configuration to YAML file"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)
            logger.info(f"Saved config to {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def _get_default_config(self) -> Dict:
        """Get default configuration"""
        return {
            'news_sources': {},
            'social_sources': {},
            'settings': {
                'cache_enabled': True,
                'cache_hours': 1,
                'force_refresh': False
            }
        }

    def get_enabled_news_sources(self) -> List[str]:
        """Get list of enabled news sources"""
        sources = []
        for source_name, config in self.config.get('news_sources', {}).items():
            if config.get('enabled', False):
                sources.append(source_name)
        return sources

    def get_enabled_social_sources(self) -> List[str]:
        """Get list of enabled social sources"""
        sources = []
        for source_name, config in self.config.get('social_sources', {}).items():
            if config.get('enabled', False):
                sources.append(source_name)
        return sources

    def get_all_enabled_sources(self) -> Dict[str, List[str]]:
        """Get all enabled sources grouped by type"""
        return {
            'news': self.get_enabled_news_sources(),
            'social': self.get_enabled_social_sources()
        }

    def is_source_enabled(self, source_name: str) -> bool:
        """Check if a source is enabled"""
        # Check news sources
        if source_name in self.config.get('news_sources', {}):
            return self.config['news_sources'][source_name].get('enabled', False)

        # Check social sources
        if source_name in self.config.get('social_sources', {}):
            return self.config['social_sources'][source_name].get('enabled', False)

        return False

    def enable_source(self, source_name: str) -> bool:
        """
        Enable a source

        Args:
            source_name: Name of the source (e.g., 'stocktwits', 'youtube')

        Returns:
            True if successful, False otherwise
        """
        # Check news sources
        if source_name in self.config.get('news_sources', {}):
            self.config['news_sources'][source_name]['enabled'] = True
            self._save_config()
            logger.info(f"Enabled news source: {source_name}")
            return True

        # Check social sources
        if source_name in self.config.get('social_sources', {}):
            self.config['social_sources'][source_name]['enabled'] = True
            self._save_config()
            logger.info(f"Enabled social source: {source_name}")
            return True

        logger.warning(f"Source not found: {source_name}")
        return False

    def disable_source(self, source_name: str) -> bool:
        """
        Disable a source

        Args:
            source_name: Name of the source (e.g., 'stocktwits', 'youtube')

        Returns:
            True if successful, False otherwise
        """
        # Check news sources
        if source_name in self.config.get('news_sources', {}):
            self.config['news_sources'][source_name]['enabled'] = False
            self._save_config()
            logger.info(f"Disabled news source: {source_name}")
            return True

        # Check social sources
        if source_name in self.config.get('social_sources', {}):
            self.config['social_sources'][source_name]['enabled'] = False
            self._save_config()
            logger.info(f"Disabled social source: {source_name}")
            return True

        logger.warning(f"Source not found: {source_name}")
        return False

    def get_source_config(self, source_name: str) -> Optional[Dict]:
        """Get configuration for a specific source"""
        # Check news sources
        if source_name in self.config.get('news_sources', {}):
            return self.config['news_sources'][source_name]

        # Check social sources
        if source_name in self.config.get('social_sources', {}):
            return self.config['social_sources'][source_name]

        return None

    def list_all_sources(self) -> Dict[str, List[Dict]]:
        """List all sources with their status"""
        news = []
        for name, config in self.config.get('news_sources', {}).items():
            news.append({
                'name': name,
                'display_name': config.get('name', name),
                'enabled': config.get('enabled', False),
                'cost': config.get('cost', 'UNKNOWN'),
                'rate_limit': config.get('rate_limit', 'UNKNOWN'),
                'requires_api_key': config.get('requires_api_key', False)
            })

        social = []
        for name, config in self.config.get('social_sources', {}).items():
            social.append({
                'name': name,
                'display_name': config.get('name', name),
                'enabled': config.get('enabled', False),
                'cost': config.get('cost', 'UNKNOWN'),
                'rate_limit': config.get('rate_limit', 'UNKNOWN'),
                'requires_api_key': config.get('requires_api_key', False),
                'warning': config.get('warning', None)
            })

        return {
            'news': news,
            'social': social
        }

    def get_setting(self, setting_name: str, default=None):
        """Get a setting value"""
        return self.config.get('settings', {}).get(setting_name, default)

    def set_setting(self, setting_name: str, value):
        """Set a setting value"""
        if 'settings' not in self.config:
            self.config['settings'] = {}

        self.config['settings'][setting_name] = value
        self._save_config()
        logger.info(f"Updated setting {setting_name} = {value}")


if __name__ == '__main__':
    # Test the source manager
    logging.basicConfig(level=logging.INFO)

    manager = SourceManager()

    print("="*80)
    print("📊 Source Manager - Current Status")
    print("="*80)
    print()

    sources = manager.list_all_sources()

    print("NEWS SOURCES:")
    print("-"*80)
    for source in sources['news']:
        status = "✅ ENABLED" if source['enabled'] else "❌ DISABLED"
        print(f"{status:15s} {source['display_name']:25s} ({source['cost']}, {source['rate_limit']})")

    print()
    print("SOCIAL SOURCES:")
    print("-"*80)
    for source in sources['social']:
        status = "✅ ENABLED" if source['enabled'] else "❌ DISABLED"
        warning = f" ⚠️  {source['warning']}" if source.get('warning') else ""
        print(f"{status:15s} {source['display_name']:25s} ({source['cost']}, {source['rate_limit']}){warning}")

    print()
    print("="*80)
    print()

    # Show enabled sources
    enabled = manager.get_all_enabled_sources()
    print(f"📰 Enabled news sources: {', '.join(enabled['news'])}")
    print(f"💬 Enabled social sources: {', '.join(enabled['social'])}")
