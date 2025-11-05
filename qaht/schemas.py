"""
Database schemas for Quantum Alpha Hunter
Shared tables + vertical-specific tables (equities/options + crypto)
"""
from sqlalchemy import String, Float, Integer, Boolean, JSON, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from datetime import date


class Base(DeclarativeBase):
    pass


# ============================================================================
# SHARED TABLES (both equities and crypto)
# ============================================================================

class PriceOHLC(Base):
    """Price data - works for both stocks and crypto"""
    __tablename__ = "price_ohlc"

    symbol: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    date: Mapped[str] = mapped_column(String, primary_key=True)  # ISO format YYYY-MM-DD
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    asset_type: Mapped[str] = mapped_column(String, default="stock")  # 'stock' or 'crypto'


class SocialMentions(Base):
    """Social sentiment data from Reddit/Twitter"""
    __tablename__ = "social_mentions"

    symbol: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    date: Mapped[str] = mapped_column(String, primary_key=True)
    reddit_count: Mapped[int] = mapped_column(Integer, default=0)
    twitter_count: Mapped[int] = mapped_column(Integer, default=0)
    author_entropy: Mapped[float] = mapped_column(Float, nullable=True)  # Diversity of posters
    engagement_ratio: Mapped[float] = mapped_column(Float, nullable=True)  # Comments/posts


class Factors(Base):
    """
    Feature storage - STABLE SCHEMA
    Only add new columns via explicit migrations after validation
    """
    __tablename__ = "factors"

    symbol: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    date: Mapped[str] = mapped_column(String, primary_key=True)

    # Technical features (Phase 1 - minimal viable set)
    bb_width_pct: Mapped[float] = mapped_column(Float, nullable=True)
    bb_position: Mapped[float] = mapped_column(Float, nullable=True)
    ma_spread_pct: Mapped[float] = mapped_column(Float, nullable=True)
    ma_alignment_score: Mapped[float] = mapped_column(Float, nullable=True)
    atr_pct: Mapped[float] = mapped_column(Float, nullable=True)
    volatility_20d: Mapped[float] = mapped_column(Float, nullable=True)

    # Volume/flow features
    volume_ratio_20d: Mapped[float] = mapped_column(Float, nullable=True)
    obv_trend_5d: Mapped[float] = mapped_column(Float, nullable=True)

    # Social/attention features
    social_delta_7d: Mapped[float] = mapped_column(Float, nullable=True)
    author_entropy_7d: Mapped[float] = mapped_column(Float, nullable=True)
    engagement_ratio_7d: Mapped[float] = mapped_column(Float, nullable=True)
    trends_delta_7d: Mapped[float] = mapped_column(Float, nullable=True)

    # Momentum indicators
    rsi_14: Mapped[float] = mapped_column(Float, nullable=True)
    macd: Mapped[float] = mapped_column(Float, nullable=True)
    macd_signal: Mapped[float] = mapped_column(Float, nullable=True)


class Labels(Base):
    """Event labels for training"""
    __tablename__ = "labels"

    symbol: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    date: Mapped[str] = mapped_column(String, primary_key=True)

    # Forward returns
    fwd_ret_10d: Mapped[float] = mapped_column(Float, nullable=True)
    fwd_ret_30d: Mapped[float] = mapped_column(Float, nullable=True)

    # Explosion labels
    explosive_10d: Mapped[bool] = mapped_column(Boolean, default=False)
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=True)

    # Triple-barrier method
    tb_label: Mapped[int] = mapped_column(Integer, nullable=True)  # 1=up, 0=time, -1=down
    tb_time: Mapped[int] = mapped_column(Integer, nullable=True)  # Days to hit barrier


class Predictions(Base):
    """Model predictions and scores"""
    __tablename__ = "predictions"

    symbol: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    date: Mapped[str] = mapped_column(String, primary_key=True)

    quantum_score: Mapped[int] = mapped_column(Integer)  # 0-100
    prob_hit_10d: Mapped[float] = mapped_column(Float, nullable=True)  # Calibrated probability
    pred_lo: Mapped[float] = mapped_column(Float, nullable=True)  # Conformal lower bound
    pred_hi: Mapped[float] = mapped_column(Float, nullable=True)  # Conformal upper bound

    # Feature attribution (JSON of top contributing features)
    components: Mapped[str] = mapped_column(String, nullable=True)  # JSON string

    conviction_level: Mapped[str] = mapped_column(String, nullable=True)  # MAX/HIGH/MED/LOW


class Regime(Base):
    """Market regime indicators"""
    __tablename__ = "regime"

    date: Mapped[str] = mapped_column(String, primary_key=True)

    # Equities regime
    spy_above_200ma: Mapped[bool] = mapped_column(Boolean, default=True)
    vix_level: Mapped[float] = mapped_column(Float, nullable=True)
    risk_on_equities: Mapped[bool] = mapped_column(Boolean, default=True)

    # Crypto regime
    btc_above_200ma: Mapped[bool] = mapped_column(Boolean, default=True)
    btc_dominance: Mapped[float] = mapped_column(Float, nullable=True)
    risk_on_crypto: Mapped[bool] = mapped_column(Boolean, default=True)


# ============================================================================
# EQUITIES/OPTIONS SPECIFIC TABLES
# ============================================================================

class OptionsChain(Base):
    """Options data from Yahoo Finance"""
    __tablename__ = "options_chain"

    symbol: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    date: Mapped[str] = mapped_column(String, primary_key=True)
    expiry: Mapped[str] = mapped_column(String, primary_key=True)
    strike: Mapped[float] = mapped_column(Float, primary_key=True)
    option_type: Mapped[str] = mapped_column(String, primary_key=True)  # 'call' or 'put'

    last: Mapped[float] = mapped_column(Float, nullable=True)
    bid: Mapped[float] = mapped_column(Float, nullable=True)
    ask: Mapped[float] = mapped_column(Float, nullable=True)
    iv: Mapped[float] = mapped_column(Float, nullable=True)  # Implied volatility
    delta: Mapped[float] = mapped_column(Float, nullable=True)
    gamma: Mapped[float] = mapped_column(Float, nullable=True)
    vega: Mapped[float] = mapped_column(Float, nullable=True)
    theta: Mapped[float] = mapped_column(Float, nullable=True)
    oi: Mapped[int] = mapped_column(Integer, nullable=True)  # Open interest
    volume: Mapped[int] = mapped_column(Integer, nullable=True)


class SECEvents(Base):
    """SEC filings (8-K, 13D/G, Form 4)"""
    __tablename__ = "sec_events"

    symbol: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    filing_date: Mapped[str] = mapped_column(String, primary_key=True)
    form: Mapped[str] = mapped_column(String, primary_key=True)

    # Store additional metadata as JSON
    meta: Mapped[str] = mapped_column(String, nullable=True)  # JSON string


class ShortVolume(Base):
    """FINRA daily short volume"""
    __tablename__ = "short_volume"

    symbol: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    date: Mapped[str] = mapped_column(String, primary_key=True)

    short_vol: Mapped[int] = mapped_column(Integer)
    total_vol: Mapped[int] = mapped_column(Integer)
    short_pct: Mapped[float] = mapped_column(Float)


class NewsEvents(Base):
    """News/RSS events for equities"""
    __tablename__ = "news_events"

    symbol: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    date: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String, primary_key=True)
    headline: Mapped[str] = mapped_column(String, primary_key=True)


# ============================================================================
# CRYPTO SPECIFIC TABLES
# ============================================================================

class FuturesMetrics(Base):
    """Crypto futures data (funding rate, open interest)"""
    __tablename__ = "futures_metrics"

    symbol: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    date: Mapped[str] = mapped_column(String, primary_key=True)

    funding_rate: Mapped[float] = mapped_column(Float, nullable=True)
    oi: Mapped[float] = mapped_column(Float, nullable=True)  # Open interest in contracts
    oi_usd: Mapped[float] = mapped_column(Float, nullable=True)  # Open interest in USD
    basis_pct: Mapped[float] = mapped_column(Float, nullable=True)  # Futures vs spot


class ExchangeMeta(Base):
    """Exchange-specific metadata for crypto"""
    __tablename__ = "exchange_meta"

    symbol: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    venue: Mapped[str] = mapped_column(String, primary_key=True)

    min_notional: Mapped[float] = mapped_column(Float)
    fee_bps: Mapped[float] = mapped_column(Float)
    tick_size: Mapped[float] = mapped_column(Float)
    lot_size: Mapped[float] = mapped_column(Float)


class ProjectSignals(Base):
    """Crypto project development signals"""
    __tablename__ = "project_signals"

    symbol: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    date: Mapped[str] = mapped_column(String, primary_key=True)

    github_stars_30d: Mapped[int] = mapped_column(Integer, nullable=True)
    commits_14d: Mapped[int] = mapped_column(Integer, nullable=True)


class NewsEventsCrypto(Base):
    """News/RSS events for crypto"""
    __tablename__ = "news_events_crypto"

    symbol: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    date: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String, primary_key=True)
    headline: Mapped[str] = mapped_column(String, primary_key=True)
