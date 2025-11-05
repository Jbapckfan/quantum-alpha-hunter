"""
Configuration management with type safety and environment variable support
"""
import os
import configparser
from pathlib import Path
from typing import List
from dataclasses import dataclass
import logging

logger = logging.getLogger("qaht.config")


@dataclass
class PipelineConfig:
    """Pipeline execution configuration"""
    lookback_days: int = 400
    intraday: bool = False
    max_concurrent: int = 5


@dataclass
class FeatureConfig:
    """Feature computation configuration"""
    bb_window: int = 20
    ma_windows: List[int] = None
    atr_window: int = 14
    social_delta_window: int = 7

    def __post_init__(self):
        if self.ma_windows is None:
            self.ma_windows = [20, 50, 200]


@dataclass
class BacktestConfig:
    """Backtesting configuration"""
    initial_capital: float = 100000.0
    risk_per_trade: float = 0.02
    max_positions: int = 10
    horizon_days: int = 10
    explosion_threshold_equity: float = 0.50
    explosion_threshold_crypto: float = 0.30


@dataclass
class ScoringConfig:
    """Model scoring configuration"""
    min_samples: int = 200
    cv_folds: int = 5
    calibration_method: str = "isotonic"


class ConfigManager:
    """
    Central configuration manager
    Reads from qaht.cfg and .env files
    """

    def __init__(self, config_path: str = "qaht.cfg", env_path: str = ".env"):
        self.config_path = Path(config_path)
        self.env_path = Path(env_path)
        self._config = configparser.ConfigParser()

        if self.config_path.exists():
            self._config.read(config_path)
        else:
            logger.warning(f"Config file {config_path} not found, using defaults")

        self._load_env()

    def _load_env(self):
        """Load environment variables from .env file"""
        if self.env_path.exists():
            try:
                from dotenv import load_dotenv
                load_dotenv(self.env_path)
                logger.info(f"Loaded environment from {self.env_path}")
            except ImportError:
                logger.warning("python-dotenv not installed, skipping .env loading")

    @property
    def db_url(self) -> str:
        """Database connection URL"""
        return os.getenv("QAHT_DB_URL", "sqlite:///data/qaht.db")

    @property
    def log_level(self) -> str:
        """Logging level"""
        return os.getenv("LOG_LEVEL", "INFO")

    @property
    def log_file(self) -> str:
        """Log file path"""
        return os.getenv("LOG_FILE", "logs/qaht.log")

    @property
    def pipeline(self) -> PipelineConfig:
        """Pipeline configuration"""
        if "pipeline" not in self._config:
            return PipelineConfig()

        section = self._config["pipeline"]
        return PipelineConfig(
            lookback_days=section.getint("lookback_days", 400),
            intraday=section.getboolean("intraday", False),
            max_concurrent=section.getint("max_concurrent", 5)
        )

    @property
    def features(self) -> FeatureConfig:
        """Feature computation configuration"""
        if "features" not in self._config:
            return FeatureConfig()

        section = self._config["features"]
        ma_windows_str = section.get("ma_windows", "20,50,200")
        ma_windows = [int(x.strip()) for x in ma_windows_str.split(",")]

        return FeatureConfig(
            bb_window=section.getint("bb_window", 20),
            ma_windows=ma_windows,
            atr_window=section.getint("atr_window", 14),
            social_delta_window=section.getint("social_delta_window", 7)
        )

    @property
    def backtest(self) -> BacktestConfig:
        """Backtesting configuration"""
        if "backtest" not in self._config:
            return BacktestConfig()

        section = self._config["backtest"]
        return BacktestConfig(
            initial_capital=section.getfloat("initial_capital", 100000.0),
            risk_per_trade=section.getfloat("risk_per_trade", 0.02),
            max_positions=section.getint("max_positions", 10),
            horizon_days=section.getint("horizon_days", 10),
            explosion_threshold_equity=section.getfloat("explosion_threshold_equity", 0.50),
            explosion_threshold_crypto=section.getfloat("explosion_threshold_crypto", 0.30)
        )

    @property
    def scoring(self) -> ScoringConfig:
        """Model scoring configuration"""
        if "scoring" not in self._config:
            return ScoringConfig()

        section = self._config["scoring"]
        return ScoringConfig(
            min_samples=section.getint("min_samples", 200),
            cv_folds=section.getint("cv_folds", 5),
            calibration_method=section.get("calibration_method", "isotonic")
        )

    def get_universe_symbols(self) -> List[str]:
        """
        Load symbols from configured universe file
        Returns list of uppercase ticker symbols
        """
        if "universe" not in self._config:
            logger.warning("No universe section in config, returning empty list")
            return []

        symbols_file = self._config["universe"].get("symbols_file", "data/universe/initial_universe.csv")
        symbols_path = Path(symbols_file)

        if not symbols_path.exists():
            logger.warning(f"Universe file {symbols_file} not found, returning empty list")
            return []

        symbols = []
        with open(symbols_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    symbols.append(line.upper())

        logger.info(f"Loaded {len(symbols)} symbols from {symbols_file}")
        return symbols

    # Reddit API credentials
    @property
    def reddit_client_id(self) -> str:
        return os.getenv("REDDIT_CLIENT_ID", "")

    @property
    def reddit_client_secret(self) -> str:
        return os.getenv("REDDIT_CLIENT_SECRET", "")

    @property
    def reddit_user_agent(self) -> str:
        return os.getenv("REDDIT_USER_AGENT", "QuantumAlphaHunter/1.0")

    # Twitter API credentials (optional)
    @property
    def twitter_bearer_token(self) -> str:
        return os.getenv("TWITTER_BEARER_TOKEN", "")

    # Rate limiting
    @property
    def api_rate_limit_delay(self) -> float:
        return float(os.getenv("API_RATE_LIMIT_DELAY", "1.0"))

    @property
    def max_retries(self) -> int:
        return int(os.getenv("MAX_RETRIES", "3"))


# Global config instance
_config = None


def get_config() -> ConfigManager:
    """Get global config instance"""
    global _config
    if _config is None:
        _config = ConfigManager()
    return _config
