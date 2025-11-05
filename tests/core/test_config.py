"""
Tests for Configuration Management
"""
import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from qaht.config import (
    PipelineConfig,
    FeatureConfig,
    BacktestConfig,
    ScoringConfig,
    ConfigManager,
    get_config
)


class TestDataclasses:
    """Test configuration dataclasses"""

    def test_pipeline_config_defaults(self):
        """Test PipelineConfig default values"""
        config = PipelineConfig()

        assert config.lookback_days == 400
        assert config.intraday is False
        assert config.max_concurrent == 5

    def test_pipeline_config_custom(self):
        """Test PipelineConfig with custom values"""
        config = PipelineConfig(lookback_days=200, intraday=True, max_concurrent=10)

        assert config.lookback_days == 200
        assert config.intraday is True
        assert config.max_concurrent == 10

    def test_feature_config_defaults(self):
        """Test FeatureConfig default values"""
        config = FeatureConfig()

        assert config.bb_window == 20
        assert config.ma_windows == [20, 50, 200]
        assert config.atr_window == 14
        assert config.social_delta_window == 7

    def test_feature_config_custom_ma_windows(self):
        """Test FeatureConfig with custom MA windows"""
        config = FeatureConfig(ma_windows=[10, 30, 60])

        assert config.ma_windows == [10, 30, 60]

    def test_backtest_config_defaults(self):
        """Test BacktestConfig default values"""
        config = BacktestConfig()

        assert config.initial_capital == 100000.0
        assert config.risk_per_trade == 0.02
        assert config.max_positions == 10
        assert config.horizon_days == 10
        assert config.explosion_threshold_equity == 0.50
        assert config.explosion_threshold_crypto == 0.30

    def test_scoring_config_defaults(self):
        """Test ScoringConfig default values"""
        config = ScoringConfig()

        assert config.min_samples == 200
        assert config.cv_folds == 5
        assert config.calibration_method == "isotonic"


class TestConfigManagerInitialization:
    """Test ConfigManager initialization"""

    def test_initialization_without_files(self, tmp_path):
        """Test initialization when config files don't exist"""
        config_path = tmp_path / "nonexistent.cfg"
        env_path = tmp_path / "nonexistent.env"

        manager = ConfigManager(str(config_path), str(env_path))

        assert manager.config_path == config_path
        assert manager.env_path == env_path

    def test_initialization_with_config_file(self, tmp_path):
        """Test initialization with existing config file"""
        config_file = tmp_path / "test.cfg"
        config_file.write_text("""
[pipeline]
lookback_days = 300
intraday = true
max_concurrent = 3
""")

        manager = ConfigManager(str(config_file), "nonexistent.env")

        assert manager.config_path.exists()
        # Check it loads the config
        pipeline = manager.pipeline
        assert pipeline.lookback_days == 300
        assert pipeline.intraday is True


class TestEnvironmentVariables:
    """Test environment variable loading"""

    def test_db_url_from_env(self, monkeypatch):
        """Test db_url loads from environment"""
        monkeypatch.setenv("QAHT_DB_URL", "postgresql://localhost/test")

        manager = ConfigManager()

        assert manager.db_url == "postgresql://localhost/test"

    def test_db_url_default(self):
        """Test db_url default value"""
        # Remove env var if it exists
        if "QAHT_DB_URL" in os.environ:
            del os.environ["QAHT_DB_URL"]

        manager = ConfigManager()

        assert manager.db_url == "sqlite:///data/qaht.db"

    def test_log_level_from_env(self, monkeypatch):
        """Test log_level loads from environment"""
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")

        manager = ConfigManager()

        assert manager.log_level == "DEBUG"

    def test_log_level_default(self):
        """Test log_level default value"""
        if "LOG_LEVEL" in os.environ:
            del os.environ["LOG_LEVEL"]

        manager = ConfigManager()

        assert manager.log_level == "INFO"

    def test_log_file_from_env(self, monkeypatch):
        """Test log_file loads from environment"""
        monkeypatch.setenv("LOG_FILE", "/var/log/custom.log")

        manager = ConfigManager()

        assert manager.log_file == "/var/log/custom.log"

    def test_api_rate_limit_delay(self, monkeypatch):
        """Test api_rate_limit_delay loads from environment"""
        monkeypatch.setenv("API_RATE_LIMIT_DELAY", "2.5")

        manager = ConfigManager()

        assert manager.api_rate_limit_delay == 2.5

    def test_max_retries(self, monkeypatch):
        """Test max_retries loads from environment"""
        monkeypatch.setenv("MAX_RETRIES", "5")

        manager = ConfigManager()

        assert manager.max_retries == 5


class TestPipelineConfiguration:
    """Test pipeline configuration loading"""

    def test_pipeline_from_config_file(self, tmp_path):
        """Test loading pipeline config from file"""
        config_file = tmp_path / "test.cfg"
        config_file.write_text("""
[pipeline]
lookback_days = 500
intraday = yes
max_concurrent = 8
""")

        manager = ConfigManager(str(config_file))
        pipeline = manager.pipeline

        assert pipeline.lookback_days == 500
        assert pipeline.intraday is True
        assert pipeline.max_concurrent == 8

    def test_pipeline_defaults_when_missing(self):
        """Test pipeline uses defaults when section missing"""
        manager = ConfigManager("nonexistent.cfg")
        pipeline = manager.pipeline

        assert pipeline.lookback_days == 400
        assert pipeline.intraday is False
        assert pipeline.max_concurrent == 5


class TestFeatureConfiguration:
    """Test feature configuration loading"""

    def test_features_from_config_file(self, tmp_path):
        """Test loading features config from file"""
        config_file = tmp_path / "test.cfg"
        config_file.write_text("""
[features]
bb_window = 15
ma_windows = 10,30,90
atr_window = 10
social_delta_window = 5
""")

        manager = ConfigManager(str(config_file))
        features = manager.features

        assert features.bb_window == 15
        assert features.ma_windows == [10, 30, 90]
        assert features.atr_window == 10
        assert features.social_delta_window == 5

    def test_features_defaults_when_missing(self):
        """Test features uses defaults when section missing"""
        manager = ConfigManager("nonexistent.cfg")
        features = manager.features

        assert features.bb_window == 20
        assert features.ma_windows == [20, 50, 200]


class TestBacktestConfiguration:
    """Test backtest configuration loading"""

    def test_backtest_from_config_file(self, tmp_path):
        """Test loading backtest config from file"""
        config_file = tmp_path / "test.cfg"
        config_file.write_text("""
[backtest]
initial_capital = 50000.0
risk_per_trade = 0.01
max_positions = 5
horizon_days = 20
explosion_threshold_equity = 0.40
explosion_threshold_crypto = 0.25
""")

        manager = ConfigManager(str(config_file))
        backtest = manager.backtest

        assert backtest.initial_capital == 50000.0
        assert backtest.risk_per_trade == 0.01
        assert backtest.max_positions == 5
        assert backtest.horizon_days == 20
        assert backtest.explosion_threshold_equity == 0.40
        assert backtest.explosion_threshold_crypto == 0.25

    def test_backtest_defaults_when_missing(self):
        """Test backtest uses defaults when section missing"""
        manager = ConfigManager("nonexistent.cfg")
        backtest = manager.backtest

        assert backtest.initial_capital == 100000.0
        assert backtest.risk_per_trade == 0.02


class TestScoringConfiguration:
    """Test scoring configuration loading"""

    def test_scoring_from_config_file(self, tmp_path):
        """Test loading scoring config from file"""
        config_file = tmp_path / "test.cfg"
        config_file.write_text("""
[scoring]
min_samples = 300
cv_folds = 3
calibration_method = sigmoid
""")

        manager = ConfigManager(str(config_file))
        scoring = manager.scoring

        assert scoring.min_samples == 300
        assert scoring.cv_folds == 3
        assert scoring.calibration_method == "sigmoid"

    def test_scoring_defaults_when_missing(self):
        """Test scoring uses defaults when section missing"""
        manager = ConfigManager("nonexistent.cfg")
        scoring = manager.scoring

        assert scoring.min_samples == 200
        assert scoring.cv_folds == 5
        assert scoring.calibration_method == "isotonic"


class TestUniverseLoading:
    """Test universe symbol loading"""

    def test_load_universe_from_file(self, tmp_path):
        """Test loading universe symbols from file"""
        config_file = tmp_path / "test.cfg"
        symbols_file = tmp_path / "symbols.csv"

        # Create symbols file
        symbols_file.write_text("""AAPL
TSLA
NVDA
# Comment line
MSFT
""")

        # Create config pointing to symbols file
        config_file.write_text(f"""
[universe]
symbols_file = {symbols_file}
""")

        manager = ConfigManager(str(config_file))
        symbols = manager.get_universe_symbols()

        assert len(symbols) == 4
        assert "AAPL" in symbols
        assert "TSLA" in symbols
        assert "NVDA" in symbols
        assert "MSFT" in symbols

    def test_universe_symbols_uppercase(self, tmp_path):
        """Test symbols are converted to uppercase"""
        config_file = tmp_path / "test.cfg"
        symbols_file = tmp_path / "symbols.csv"

        symbols_file.write_text("aapl\ntsla\n")

        config_file.write_text(f"""
[universe]
symbols_file = {symbols_file}
""")

        manager = ConfigManager(str(config_file))
        symbols = manager.get_universe_symbols()

        assert symbols == ["AAPL", "TSLA"]

    def test_universe_file_not_found(self, tmp_path):
        """Test returns empty list when universe file not found"""
        config_file = tmp_path / "test.cfg"

        config_file.write_text("""
[universe]
symbols_file = nonexistent.csv
""")

        manager = ConfigManager(str(config_file))
        symbols = manager.get_universe_symbols()

        assert symbols == []

    def test_universe_section_missing(self):
        """Test returns empty list when universe section missing"""
        manager = ConfigManager("nonexistent.cfg")
        symbols = manager.get_universe_symbols()

        assert symbols == []


class TestAPICredentials:
    """Test API credential loading"""

    def test_reddit_credentials(self, monkeypatch):
        """Test Reddit API credentials"""
        monkeypatch.setenv("REDDIT_CLIENT_ID", "test_id")
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "test_secret")
        monkeypatch.setenv("REDDIT_USER_AGENT", "TestAgent/1.0")

        manager = ConfigManager()

        assert manager.reddit_client_id == "test_id"
        assert manager.reddit_client_secret == "test_secret"
        assert manager.reddit_user_agent == "TestAgent/1.0"

    def test_reddit_defaults(self):
        """Test Reddit credential defaults"""
        # Clear env vars
        for key in ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"]:
            if key in os.environ:
                del os.environ[key]

        manager = ConfigManager()

        assert manager.reddit_client_id == ""
        assert manager.reddit_client_secret == ""
        assert manager.reddit_user_agent == "QuantumAlphaHunter/1.0"

    def test_twitter_bearer_token(self, monkeypatch):
        """Test Twitter API token"""
        monkeypatch.setenv("TWITTER_BEARER_TOKEN", "test_token")

        manager = ConfigManager()

        assert manager.twitter_bearer_token == "test_token"


class TestGlobalConfigInstance:
    """Test global config singleton"""

    def test_get_config_returns_instance(self):
        """Test get_config returns ConfigManager instance"""
        config = get_config()

        assert isinstance(config, ConfigManager)

    def test_get_config_returns_same_instance(self):
        """Test get_config returns same instance (singleton)"""
        config1 = get_config()
        config2 = get_config()

        assert config1 is config2


@pytest.mark.integration
class TestConfigIntegration:
    """Integration tests for configuration"""

    def test_full_config_loading(self, tmp_path):
        """Test loading complete configuration"""
        config_file = tmp_path / "full.cfg"
        config_file.write_text("""
[pipeline]
lookback_days = 250
intraday = yes
max_concurrent = 10

[features]
bb_window = 15
ma_windows = 10,20,30
atr_window = 12
social_delta_window = 3

[backtest]
initial_capital = 75000.0
risk_per_trade = 0.015
max_positions = 8
horizon_days = 15

[scoring]
min_samples = 250
cv_folds = 4
calibration_method = sigmoid
""")

        manager = ConfigManager(str(config_file))

        # Test all sections loaded correctly
        pipeline = manager.pipeline
        assert pipeline.lookback_days == 250

        features = manager.features
        assert features.bb_window == 15

        backtest = manager.backtest
        assert backtest.initial_capital == 75000.0

        scoring = manager.scoring
        assert scoring.min_samples == 250

    def test_mixed_config_and_env(self, tmp_path, monkeypatch):
        """Test configuration from both file and environment"""
        config_file = tmp_path / "mixed.cfg"
        config_file.write_text("""
[pipeline]
lookback_days = 300
""")

        monkeypatch.setenv("QAHT_DB_URL", "postgresql://localhost/testdb")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")

        manager = ConfigManager(str(config_file))

        # From config file
        assert manager.pipeline.lookback_days == 300

        # From environment
        assert manager.db_url == "postgresql://localhost/testdb"
        assert manager.log_level == "DEBUG"
