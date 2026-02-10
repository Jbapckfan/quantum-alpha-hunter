"""
Database schemas for Alpha Predator.
Unified tables for stocks + crypto with new explosive signal and self-learning tables.
"""
from sqlalchemy import String, Float, Integer, Boolean, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# ============================================================================
# SHARED TABLES
# ============================================================================

class PriceOHLC(Base):
    """Price data for both stocks and crypto."""
    __tablename__ = "price_ohlc"

    symbol: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    date: Mapped[str] = mapped_column(String, primary_key=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    asset_type: Mapped[str] = mapped_column(String, default="stock")


class SocialMentions(Base):
    """Social sentiment data from Reddit/Twitter."""
    __tablename__ = "social_mentions"

    symbol: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    date: Mapped[str] = mapped_column(String, primary_key=True)
    reddit_count: Mapped[int] = mapped_column(Integer, default=0)
    twitter_count: Mapped[int] = mapped_column(Integer, default=0)
    author_entropy: Mapped[float] = mapped_column(Float, nullable=True)
    engagement_ratio: Mapped[float] = mapped_column(Float, nullable=True)


class Factors(Base):
    """Feature storage — all computed features for ML training and scoring."""
    __tablename__ = "factors"

    symbol: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    date: Mapped[str] = mapped_column(String, primary_key=True)

    # Technical features (from QAHT)
    bb_width_pct: Mapped[float] = mapped_column(Float, nullable=True)
    bb_position: Mapped[float] = mapped_column(Float, nullable=True)
    ma_spread_pct: Mapped[float] = mapped_column(Float, nullable=True)
    ma_alignment_score: Mapped[float] = mapped_column(Float, nullable=True)
    atr_pct: Mapped[float] = mapped_column(Float, nullable=True)
    volatility_20d: Mapped[float] = mapped_column(Float, nullable=True)
    volume_ratio_20d: Mapped[float] = mapped_column(Float, nullable=True)
    obv_trend_5d: Mapped[float] = mapped_column(Float, nullable=True)
    rsi_14: Mapped[float] = mapped_column(Float, nullable=True)
    macd: Mapped[float] = mapped_column(Float, nullable=True)
    macd_signal: Mapped[float] = mapped_column(Float, nullable=True)

    # Social features
    social_delta_7d: Mapped[float] = mapped_column(Float, nullable=True)
    author_entropy_7d: Mapped[float] = mapped_column(Float, nullable=True)
    engagement_ratio_7d: Mapped[float] = mapped_column(Float, nullable=True)
    trends_delta_7d: Mapped[float] = mapped_column(Float, nullable=True)

    # Crypto derivatives
    funding_rate_delta_7d: Mapped[float] = mapped_column(Float, nullable=True)
    oi_delta_7d: Mapped[float] = mapped_column(Float, nullable=True)

    # Explosive signals (from Hedge Fund)
    vol_zscore: Mapped[float] = mapped_column(Float, nullable=True)
    gap_up: Mapped[float] = mapped_column(Float, nullable=True)
    vol_spike_count: Mapped[float] = mapped_column(Float, nullable=True)
    vol_accel: Mapped[float] = mapped_column(Float, nullable=True)
    range_20d: Mapped[float] = mapped_column(Float, nullable=True)
    rejection_wick: Mapped[float] = mapped_column(Float, nullable=True)
    selling_pressure: Mapped[float] = mapped_column(Float, nullable=True)
    low_in_range: Mapped[float] = mapped_column(Float, nullable=True)
    momentum_10d: Mapped[float] = mapped_column(Float, nullable=True)
    pullback_pct: Mapped[float] = mapped_column(Float, nullable=True)
    drawdown_60d: Mapped[float] = mapped_column(Float, nullable=True)

    # Institutional signals (from Destroyer)
    call_oi_ratio: Mapped[float] = mapped_column(Float, nullable=True)
    short_pct_float: Mapped[float] = mapped_column(Float, nullable=True)
    days_to_cover: Mapped[float] = mapped_column(Float, nullable=True)
    order_flow_score: Mapped[float] = mapped_column(Float, nullable=True)
    smart_money_score: Mapped[float] = mapped_column(Float, nullable=True)

    # Crypto-specific (from Destroyer)
    btc_decoupling: Mapped[float] = mapped_column(Float, nullable=True)
    vol_compression: Mapped[float] = mapped_column(Float, nullable=True)

    # Regime
    regime_state: Mapped[str] = mapped_column(String, nullable=True)


class Labels(Base):
    """Event labels for training."""
    __tablename__ = "labels"

    symbol: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    date: Mapped[str] = mapped_column(String, primary_key=True)
    fwd_ret_10d: Mapped[float] = mapped_column(Float, nullable=True)
    fwd_ret_30d: Mapped[float] = mapped_column(Float, nullable=True)
    fwd_max_60d: Mapped[float] = mapped_column(Float, nullable=True)
    explosive_10d: Mapped[bool] = mapped_column(Boolean, default=False)
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=True)
    tb_label: Mapped[int] = mapped_column(Integer, nullable=True)
    tb_time: Mapped[int] = mapped_column(Integer, nullable=True)


class Predictions(Base):
    """Model predictions and scores."""
    __tablename__ = "predictions"

    symbol: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    date: Mapped[str] = mapped_column(String, primary_key=True)
    quantum_score: Mapped[int] = mapped_column(Integer)
    prob_hit_10d: Mapped[float] = mapped_column(Float, nullable=True)
    pred_lo: Mapped[float] = mapped_column(Float, nullable=True)
    pred_hi: Mapped[float] = mapped_column(Float, nullable=True)
    components: Mapped[str] = mapped_column(String, nullable=True)
    conviction_level: Mapped[str] = mapped_column(String, nullable=True)
    combo_match: Mapped[str] = mapped_column(String, nullable=True)
    tier: Mapped[int] = mapped_column(Integer, nullable=True)
    kelly_fraction: Mapped[float] = mapped_column(Float, nullable=True)
    ensemble_score: Mapped[float] = mapped_column(Float, nullable=True)


class Regime(Base):
    """Market regime indicators."""
    __tablename__ = "regime"

    date: Mapped[str] = mapped_column(String, primary_key=True)
    spy_above_200ma: Mapped[bool] = mapped_column(Boolean, default=True)
    vix_level: Mapped[float] = mapped_column(Float, nullable=True)
    risk_on_equities: Mapped[bool] = mapped_column(Boolean, default=True)
    btc_above_200ma: Mapped[bool] = mapped_column(Boolean, default=True)
    btc_dominance: Mapped[float] = mapped_column(Float, nullable=True)
    risk_on_crypto: Mapped[bool] = mapped_column(Boolean, default=True)
    regime_state: Mapped[str] = mapped_column(String, nullable=True)
    regime_confidence: Mapped[float] = mapped_column(Float, nullable=True)


# ============================================================================
# EQUITIES-SPECIFIC
# ============================================================================

class OptionsChain(Base):
    __tablename__ = "options_chain"
    symbol: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    date: Mapped[str] = mapped_column(String, primary_key=True)
    expiry: Mapped[str] = mapped_column(String, primary_key=True)
    strike: Mapped[float] = mapped_column(Float, primary_key=True)
    option_type: Mapped[str] = mapped_column(String, primary_key=True)
    last: Mapped[float] = mapped_column(Float, nullable=True)
    bid: Mapped[float] = mapped_column(Float, nullable=True)
    ask: Mapped[float] = mapped_column(Float, nullable=True)
    iv: Mapped[float] = mapped_column(Float, nullable=True)
    delta: Mapped[float] = mapped_column(Float, nullable=True)
    gamma: Mapped[float] = mapped_column(Float, nullable=True)
    oi: Mapped[int] = mapped_column(Integer, nullable=True)
    volume: Mapped[int] = mapped_column(Integer, nullable=True)


class SECEvents(Base):
    __tablename__ = "sec_events"
    symbol: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    filing_date: Mapped[str] = mapped_column(String, primary_key=True)
    form: Mapped[str] = mapped_column(String, primary_key=True)
    meta: Mapped[str] = mapped_column(String, nullable=True)


class ShortVolume(Base):
    __tablename__ = "short_volume"
    symbol: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    date: Mapped[str] = mapped_column(String, primary_key=True)
    short_vol: Mapped[int] = mapped_column(Integer)
    total_vol: Mapped[int] = mapped_column(Integer)
    short_pct: Mapped[float] = mapped_column(Float)


# ============================================================================
# CRYPTO-SPECIFIC
# ============================================================================

class FuturesMetrics(Base):
    __tablename__ = "futures_metrics"
    symbol: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    date: Mapped[str] = mapped_column(String, primary_key=True)
    funding_rate: Mapped[float] = mapped_column(Float, nullable=True)
    oi: Mapped[float] = mapped_column(Float, nullable=True)
    oi_usd: Mapped[float] = mapped_column(Float, nullable=True)
    basis_pct: Mapped[float] = mapped_column(Float, nullable=True)


class ExchangeMeta(Base):
    __tablename__ = "exchange_meta"
    symbol: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    venue: Mapped[str] = mapped_column(String, primary_key=True)
    min_notional: Mapped[float] = mapped_column(Float)
    fee_bps: Mapped[float] = mapped_column(Float)
    tick_size: Mapped[float] = mapped_column(Float)
    lot_size: Mapped[float] = mapped_column(Float)


# ============================================================================
# NEW: EXPLOSIVE SIGNALS & COMBOS
# ============================================================================

class ExplosiveSignals(Base):
    """Stores the 11 explosive signal values per (symbol, date)."""
    __tablename__ = "explosive_signals"

    symbol: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    date: Mapped[str] = mapped_column(String, primary_key=True)
    vol_zscore: Mapped[float] = mapped_column(Float, nullable=True)
    gap_up_pct: Mapped[float] = mapped_column(Float, nullable=True)
    vol_spike_count: Mapped[int] = mapped_column(Integer, nullable=True)
    vol_accel: Mapped[float] = mapped_column(Float, nullable=True)
    range_20d_pct: Mapped[float] = mapped_column(Float, nullable=True)
    rejection_wick_pct: Mapped[float] = mapped_column(Float, nullable=True)
    selling_pressure_score: Mapped[float] = mapped_column(Float, nullable=True)
    low_in_range_pct: Mapped[float] = mapped_column(Float, nullable=True)
    rsi_value: Mapped[float] = mapped_column(Float, nullable=True)
    momentum_10d: Mapped[float] = mapped_column(Float, nullable=True)
    drawdown_60d: Mapped[float] = mapped_column(Float, nullable=True)
    v1_score: Mapped[int] = mapped_column(Integer, nullable=True)
    v2_score: Mapped[float] = mapped_column(Float, nullable=True)
    matched_combos: Mapped[str] = mapped_column(String, nullable=True)
    tier: Mapped[int] = mapped_column(Integer, nullable=True)


class AlertLog(Base):
    """Stores sent alerts with outcome tracking for self-learning."""
    __tablename__ = "alert_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String, index=True)
    timestamp: Mapped[str] = mapped_column(String)
    channel: Mapped[str] = mapped_column(String, default="discord")
    conviction_level: Mapped[str] = mapped_column(String, nullable=True)
    quantum_score: Mapped[int] = mapped_column(Integer, nullable=True)
    combo_name: Mapped[str] = mapped_column(String, nullable=True)
    tier: Mapped[int] = mapped_column(Integer, nullable=True)
    entry_price: Mapped[float] = mapped_column(Float, nullable=True)
    # Outcome tracking (filled later by self-learning loop)
    outcome_5d: Mapped[float] = mapped_column(Float, nullable=True)
    outcome_10d: Mapped[float] = mapped_column(Float, nullable=True)
    outcome_30d: Mapped[float] = mapped_column(Float, nullable=True)
    max_gain_30d: Mapped[float] = mapped_column(Float, nullable=True)
    hit_target: Mapped[bool] = mapped_column(Boolean, nullable=True)


class SignalPerformance(Base):
    """Tracks rolling hit rates per signal/combo for adaptive learning."""
    __tablename__ = "signal_performance"

    signal_name: Mapped[str] = mapped_column(String, primary_key=True)
    period_start: Mapped[str] = mapped_column(String, primary_key=True)
    period_end: Mapped[str] = mapped_column(String, primary_key=True)
    total_signals: Mapped[int] = mapped_column(Integer, default=0)
    hits: Mapped[int] = mapped_column(Integer, default=0)
    hit_rate: Mapped[float] = mapped_column(Float, nullable=True)
    avg_return: Mapped[float] = mapped_column(Float, nullable=True)
    avg_max_gain: Mapped[float] = mapped_column(Float, nullable=True)
    lift_vs_baseline: Mapped[float] = mapped_column(Float, nullable=True)
    weight_adjustment: Mapped[float] = mapped_column(Float, default=1.0)


class ModelRegistry(Base):
    """Tracks trained models for versioning and self-retraining."""
    __tablename__ = "model_registry"

    model_id: Mapped[str] = mapped_column(String, primary_key=True)
    asset_type: Mapped[str] = mapped_column(String)
    trained_at: Mapped[str] = mapped_column(String)
    n_samples: Mapped[int] = mapped_column(Integer)
    n_features: Mapped[int] = mapped_column(Integer)
    oos_hit_rate: Mapped[float] = mapped_column(Float, nullable=True)
    oos_sharpe: Mapped[float] = mapped_column(Float, nullable=True)
    filepath: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(String, nullable=True)
