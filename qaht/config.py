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


@dataclass
class SignalsConfig:
    """RZLV signal detection defaults"""
    min_stock_score: int = 35
    min_crypto_score: int = 15
    high_confidence_score: int = 70
    price_min: float = 0.50
    price_max: float = 50.0
    market_cap_min: int = 50_000_000
    market_cap_max: int = 30_000_000_000
    min_drawdown_pct: int = 40
    min_rally_pct: int = 15
    max_workers: int = 8


@dataclass
class OptionsConfig:
    """Polygon.io options integration configuration"""
    polygon_api_key_env: str = "MARKET_API_KEY"
    default_universe: List[str] = None
    min_leaps_dte: int = 270
    leaps_min_trend: float = 0.6
    zero_dte_refresh_seconds: int = 15

    def __post_init__(self):
        if self.default_universe is None:
            self.default_universe = ["SPY", "QQQ", "AAPL", "MSFT", "TSLA", "SMH", "XLF"]


@dataclass
class EmpiricalConfig:
    """Hedge Fund research-validated settings"""
    vol_zscore_threshold: float = 2.0
    tier1_min_score: int = 13
    tier1_min_drawdown_60d: int = 55
    tier1_max_rsi: int = 35
    fake_out_max_vol: float = 4.0
    falling_knife_max_dd20: int = 50
    kelly_fraction: float = 0.25
    max_position_pct: int = 10
    min_position_pct: int = 2
    stop_loss_pct: int = 15
    target1_pct: int = 30
    target2_pct: int = 50
    target3_pct: int = 100


@dataclass
class ApiConfig:
    """API server configuration"""
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "*"


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

    @property
    def signals(self) -> SignalsConfig:
        """RZLV signal detection configuration"""
        if "signals" not in self._config:
            return SignalsConfig()

        section = self._config["signals"]
        return SignalsConfig(
            min_stock_score=section.getint("min_stock_score", 35),
            min_crypto_score=section.getint("min_crypto_score", 15),
            high_confidence_score=section.getint("high_confidence_score", 70),
            price_min=section.getfloat("price_min", 0.50),
            price_max=section.getfloat("price_max", 50.0),
            market_cap_min=section.getint("market_cap_min", 50_000_000),
            market_cap_max=section.getint("market_cap_max", 30_000_000_000),
            min_drawdown_pct=section.getint("min_drawdown_pct", 40),
            min_rally_pct=section.getint("min_rally_pct", 15),
            max_workers=section.getint("max_workers", 8),
        )

    @property
    def options(self) -> OptionsConfig:
        """Options engine configuration"""
        if "options" not in self._config:
            return OptionsConfig()

        section = self._config["options"]
        universe_str = section.get("default_universe", "SPY,QQQ,AAPL,MSFT,TSLA,SMH,XLF")
        universe = [s.strip() for s in universe_str.split(",")]

        return OptionsConfig(
            polygon_api_key_env=section.get("polygon_api_key_env", "MARKET_API_KEY"),
            default_universe=universe,
            min_leaps_dte=section.getint("min_leaps_dte", 270),
            leaps_min_trend=section.getfloat("leaps_min_trend", 0.6),
            zero_dte_refresh_seconds=section.getint("zero_dte_refresh_seconds", 15),
        )

    @property
    def empirical(self) -> EmpiricalConfig:
        """Empirical combo engine configuration"""
        if "empirical" not in self._config:
            return EmpiricalConfig()

        section = self._config["empirical"]
        return EmpiricalConfig(
            vol_zscore_threshold=section.getfloat("vol_zscore_threshold", 2.0),
            tier1_min_score=section.getint("tier1_min_score", 13),
            tier1_min_drawdown_60d=section.getint("tier1_min_drawdown_60d", 55),
            tier1_max_rsi=section.getint("tier1_max_rsi", 35),
            fake_out_max_vol=section.getfloat("fake_out_max_vol", 4.0),
            falling_knife_max_dd20=section.getint("falling_knife_max_dd20", 50),
            kelly_fraction=section.getfloat("kelly_fraction", 0.25),
            max_position_pct=section.getint("max_position_pct", 10),
            min_position_pct=section.getint("min_position_pct", 2),
            stop_loss_pct=section.getint("stop_loss_pct", 15),
            target1_pct=section.getint("target1_pct", 30),
            target2_pct=section.getint("target2_pct", 50),
            target3_pct=section.getint("target3_pct", 100),
        )

    @property
    def api(self) -> ApiConfig:
        """API server configuration"""
        if "api" not in self._config:
            return ApiConfig()

        section = self._config["api"]
        return ApiConfig(
            host=section.get("host", "0.0.0.0"),
            port=section.getint("port", 8000),
            cors_origins=section.get("cors_origins", "*"),
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
