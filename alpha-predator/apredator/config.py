"""
Configuration management with type safety and environment variable support.
Expanded from QAHT with alert, universe, and self-learning configs.
"""
import os
import configparser
from pathlib import Path
from typing import List, Dict
from dataclasses import dataclass, field
import logging

logger = logging.getLogger("apredator.config")


@dataclass
class PipelineConfig:
    """Pipeline execution configuration."""
    lookback_days: int = 400
    intraday: bool = False
    max_concurrent: int = 5
    scan_interval_minutes: int = 60


@dataclass
class FeatureConfig:
    """Feature computation configuration."""
    bb_window: int = 20
    ma_windows: List[int] = None
    atr_window: int = 14
    social_delta_window: int = 7
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9

    def __post_init__(self):
        if self.ma_windows is None:
            self.ma_windows = [20, 50, 200]


@dataclass
class BacktestConfig:
    """Backtesting configuration."""
    initial_capital: float = 100000.0
    risk_per_trade: float = 0.02
    max_positions: int = 10
    horizon_days: int = 10
    explosion_threshold_equity: float = 0.50
    explosion_threshold_crypto: float = 0.30
    profit_target: float = 0.50
    stop_loss: float = -0.15
    max_hold_days: int = 14


@dataclass
class ScoringConfig:
    """Model scoring configuration."""
    min_samples: int = 200
    cv_folds: int = 5
    calibration_method: str = "isotonic"


@dataclass
class AlertConfig:
    """Alert delivery configuration."""
    discord_webhook_url: str = ""
    cooldown_hours: int = 4
    min_confidence: float = 0.7
    educational_disclaimer: bool = True


@dataclass
class UniverseConfig:
    """Universe selection configuration."""
    symbols_file: str = "data/universe/initial_universe.csv"
    max_price: float = 50.0
    min_volume_20d: float = 100_000
    min_market_cap: float = 50_000_000
    max_market_cap: float = 50_000_000_000
    crypto_min_market_cap: float = 100_000_000


@dataclass
class LearningConfig:
    """Self-learning and adaptive threshold configuration."""
    enabled: bool = True
    retrain_interval_days: int = 30
    min_outcome_samples: int = 50
    fp_rate_threshold: float = 0.40
    signal_decay_halflife_days: int = 90
    weight_update_method: str = "bayesian"


class ConfigManager:
    """Central configuration manager. Reads from apredator.cfg and .env files."""

    def __init__(self, config_path: str = "apredator.cfg", env_path: str = ".env"):
        self.config_path = Path(config_path)
        self.env_path = Path(env_path)
        self._config = configparser.ConfigParser()

        if self.config_path.exists():
            self._config.read(config_path)
        else:
            logger.warning(f"Config file {config_path} not found, using defaults")

        self._load_env()

    def _load_env(self):
        if self.env_path.exists():
            try:
                from dotenv import load_dotenv
                load_dotenv(self.env_path)
                logger.info(f"Loaded environment from {self.env_path}")
            except ImportError:
                logger.warning("python-dotenv not installed, skipping .env loading")

    @property
    def db_url(self) -> str:
        return os.getenv("APREDATOR_DB_URL", "sqlite:///data/apredator.db")

    @property
    def log_level(self) -> str:
        return os.getenv("LOG_LEVEL", "INFO")

    @property
    def log_file(self) -> str:
        return os.getenv("LOG_FILE", "logs/apredator.log")

    @property
    def pipeline(self) -> PipelineConfig:
        if "pipeline" not in self._config:
            return PipelineConfig()
        s = self._config["pipeline"]
        return PipelineConfig(
            lookback_days=s.getint("lookback_days", 400),
            intraday=s.getboolean("intraday", False),
            max_concurrent=s.getint("max_concurrent", 5),
            scan_interval_minutes=s.getint("scan_interval_minutes", 60),
        )

    @property
    def features(self) -> FeatureConfig:
        if "features" not in self._config:
            return FeatureConfig()
        s = self._config["features"]
        ma_windows_str = s.get("ma_windows", "20,50,200")
        ma_windows = [int(x.strip()) for x in ma_windows_str.split(",")]
        return FeatureConfig(
            bb_window=s.getint("bb_window", 20),
            ma_windows=ma_windows,
            atr_window=s.getint("atr_window", 14),
            social_delta_window=s.getint("social_delta_window", 7),
        )

    @property
    def backtest(self) -> BacktestConfig:
        if "backtest" not in self._config:
            return BacktestConfig()
        s = self._config["backtest"]
        return BacktestConfig(
            initial_capital=s.getfloat("initial_capital", 100000.0),
            risk_per_trade=s.getfloat("risk_per_trade", 0.02),
            max_positions=s.getint("max_positions", 10),
            horizon_days=s.getint("horizon_days", 10),
            explosion_threshold_equity=s.getfloat("explosion_threshold_equity", 0.50),
            explosion_threshold_crypto=s.getfloat("explosion_threshold_crypto", 0.30),
            profit_target=s.getfloat("profit_target", 0.50),
            stop_loss=s.getfloat("stop_loss", -0.15),
            max_hold_days=s.getint("max_hold_days", 14),
        )

    @property
    def scoring(self) -> ScoringConfig:
        if "scoring" not in self._config:
            return ScoringConfig()
        s = self._config["scoring"]
        return ScoringConfig(
            min_samples=s.getint("min_samples", 200),
            cv_folds=s.getint("cv_folds", 5),
            calibration_method=s.get("calibration_method", "isotonic"),
        )

    @property
    def alerts(self) -> AlertConfig:
        if "alerts" not in self._config:
            return AlertConfig()
        s = self._config["alerts"]
        return AlertConfig(
            discord_webhook_url=s.get("discord_webhook_url", ""),
            cooldown_hours=s.getint("cooldown_hours", 4),
            min_confidence=s.getfloat("min_confidence", 0.7),
            educational_disclaimer=s.getboolean("educational_disclaimer", True),
        )

    @property
    def universe(self) -> UniverseConfig:
        if "universe" not in self._config:
            return UniverseConfig()
        s = self._config["universe"]
        return UniverseConfig(
            symbols_file=s.get("symbols_file", "data/universe/initial_universe.csv"),
            max_price=s.getfloat("max_price", 50.0),
            min_volume_20d=s.getfloat("min_volume_20d", 100_000),
            min_market_cap=s.getfloat("min_market_cap", 50_000_000),
            max_market_cap=s.getfloat("max_market_cap", 50_000_000_000),
            crypto_min_market_cap=s.getfloat("crypto_min_market_cap", 100_000_000),
        )

    @property
    def learning(self) -> LearningConfig:
        if "learning" not in self._config:
            return LearningConfig()
        s = self._config["learning"]
        return LearningConfig(
            enabled=s.getboolean("enabled", True),
            retrain_interval_days=s.getint("retrain_interval_days", 30),
            min_outcome_samples=s.getint("min_outcome_samples", 50),
            fp_rate_threshold=s.getfloat("fp_rate_threshold", 0.40),
            signal_decay_halflife_days=s.getint("signal_decay_halflife_days", 90),
            weight_update_method=s.get("weight_update_method", "bayesian"),
        )

    def get_universe_symbols(self) -> List[str]:
        symbols_file = self.universe.symbols_file
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

    # API credentials
    @property
    def reddit_client_id(self) -> str:
        return os.getenv("REDDIT_CLIENT_ID", "")

    @property
    def reddit_client_secret(self) -> str:
        return os.getenv("REDDIT_CLIENT_SECRET", "")

    @property
    def reddit_user_agent(self) -> str:
        return os.getenv("REDDIT_USER_AGENT", "AlphaPredator/1.0")

    @property
    def discord_webhook_url(self) -> str:
        return os.getenv("DISCORD_WEBHOOK_URL", self.alerts.discord_webhook_url)

    @property
    def api_rate_limit_delay(self) -> float:
        return float(os.getenv("API_RATE_LIMIT_DELAY", "1.0"))

    @property
    def max_retries(self) -> int:
        return int(os.getenv("MAX_RETRIES", "3"))


# Global config instance
_config = None


def get_config() -> ConfigManager:
    """Get global config instance."""
    global _config
    if _config is None:
        _config = ConfigManager()
    return _config
