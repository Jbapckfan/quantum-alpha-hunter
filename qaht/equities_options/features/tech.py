"""
Technical feature engineering - compression, momentum, volatility
This is where we detect the "coiled spring" before it uncoils
"""
import pandas as pd
import numpy as np
from typing import Dict, Optional
import logging

try:
    import talib
    HAS_TALIB = True
except ImportError:
    HAS_TALIB = False
    logging.warning("TA-Lib not available, using pandas fallbacks")

from ...db import session_scope
from ...schemas import PriceOHLC, Factors
from ...config import get_config
from sqlalchemy import select

logger = logging.getLogger("qaht.features.tech")
config = get_config()


def compute_bollinger_compression(df: pd.DataFrame) -> Dict[str, float]:
    """
    Bollinger Band compression - key signal for explosive moves
    When BB width < 20th percentile, the spring is coiled

    Args:
        df: DataFrame with OHLCV data

    Returns:
        Dict with bb_width_pct and bb_position
    """
    window = config.features.bb_window

    if len(df) < window:
        return {}

    close = df['close'].values

    if HAS_TALIB:
        upper, middle, lower = talib.BBANDS(close, timeperiod=window, nbdevup=2, nbdevdn=2)
    else:
        # Pandas fallback
        middle = df['close'].rolling(window=window).mean()
        std = df['close'].rolling(window=window).std()
        upper = middle + (2 * std)
        lower = middle - (2 * std)
        upper = upper.values
        middle = middle.values
        lower = lower.values

    if np.isnan(upper[-1]) or np.isnan(lower[-1]):
        return {}

    # BB width as % of price
    bb_width = (upper[-1] - lower[-1]) / middle[-1]

    # Where price sits in the band (0 = at lower, 1 = at upper)
    bb_position = (close[-1] - lower[-1]) / (upper[-1] - lower[-1]) if (upper[-1] - lower[-1]) > 0 else 0.5

    return {
        'bb_width_pct': float(bb_width),
        'bb_position': float(bb_position)
    }


def compute_ma_compression(df: pd.DataFrame) -> Dict[str, float]:
    """
    Moving average compression - GME had 20/50/200 within 5% before squeeze
    Tight MA spread = compression, alignment score = trend readiness

    Args:
        df: DataFrame with close prices

    Returns:
        Dict with ma_spread_pct and ma_alignment_score
    """
    ma_windows = config.features.ma_windows
    close = df['close'].values

    ma_values = {}
    for window in ma_windows:
        if len(df) >= window:
            if HAS_TALIB:
                ma = talib.SMA(close, timeperiod=window)[-1]
            else:
                ma = df['close'].rolling(window=window).mean().iloc[-1]

            if not np.isnan(ma):
                ma_values[window] = ma

    if len(ma_values) < 2:
        return {}

    # Spread: how far apart are the MAs?
    ma_list = list(ma_values.values())
    ma_spread = (max(ma_list) - min(ma_list)) / close[-1]

    # Alignment: are shorter MAs above longer MAs? (bullish setup)
    windows_sorted = sorted(ma_windows)
    alignment_score = 0
    comparisons = 0

    for i in range(1, len(windows_sorted)):
        if windows_sorted[i] in ma_values and windows_sorted[i-1] in ma_values:
            if ma_values[windows_sorted[i-1]] > ma_values[windows_sorted[i]]:
                alignment_score += 1
            comparisons += 1

    ma_alignment = alignment_score / max(1, comparisons)

    return {
        'ma_spread_pct': float(ma_spread),
        'ma_alignment_score': float(ma_alignment)
    }


def compute_volatility_metrics(df: pd.DataFrame) -> Dict[str, float]:
    """
    Volatility compression detection
    Low volatility precedes high volatility (mean reversion)

    Args:
        df: DataFrame with OHLC data

    Returns:
        Dict with atr_pct and volatility_20d
    """
    atr_window = config.features.atr_window

    if len(df) < max(atr_window, 20):
        return {}

    high = df['high'].values
    low = df['low'].values
    close = df['close'].values

    # ATR (Average True Range)
    if HAS_TALIB:
        atr = talib.ATR(high, low, close, timeperiod=atr_window)[-1]
    else:
        tr1 = high - low
        tr2 = np.abs(high - np.roll(close, 1))
        tr3 = np.abs(low - np.roll(close, 1))
        tr = np.maximum(tr1, np.maximum(tr2, tr3))
        atr = pd.Series(tr).rolling(window=atr_window).mean().iloc[-1]

    atr_pct = atr / close[-1] if close[-1] > 0 else 0

    # Historical volatility (20-day)
    returns = np.diff(np.log(close))
    if len(returns) >= 20:
        vol_20d = np.std(returns[-20:]) * np.sqrt(252)  # Annualized
    else:
        vol_20d = 0

    return {
        'atr_pct': float(atr_pct),
        'volatility_20d': float(vol_20d)
    }


def compute_volume_features(df: pd.DataFrame) -> Dict[str, float]:
    """
    Volume analysis - accumulation detection
    Rising volume + flat price = smart money accumulating

    Args:
        df: DataFrame with volume data

    Returns:
        Dict with volume_ratio_20d and obv_trend_5d
    """
    volume = df['volume'].values
    close = df['close'].values

    if len(df) < 20:
        return {}

    # Volume ratio: current vs 20-day average
    volume_sma_20 = np.mean(volume[-20:])
    volume_ratio = volume[-1] / volume_sma_20 if volume_sma_20 > 0 else 1.0

    # OBV (On-Balance Volume) trend
    if HAS_TALIB:
        obv = talib.OBV(close, volume)
        obv_trend = (obv[-1] - obv[-5]) / abs(obv[-5]) if len(obv) >= 5 and obv[-5] != 0 else 0
    else:
        obv_direction = np.where(close > np.roll(close, 1), volume, -volume)
        obv = np.cumsum(obv_direction)
        obv_trend = (obv[-1] - obv[-5]) / abs(obv[-5]) if len(obv) >= 5 and obv[-5] != 0 else 0

    return {
        'volume_ratio_20d': float(volume_ratio),
        'obv_trend_5d': float(obv_trend)
    }


def compute_momentum_features(df: pd.DataFrame) -> Dict[str, float]:
    """
    Momentum indicators - RSI, MACD
    Neutral RSI (40-60) + MACD crossover = setup forming

    Args:
        df: DataFrame with price data

    Returns:
        Dict with rsi_14, macd, macd_signal
    """
    close = df['close'].values

    features = {}

    # RSI
    if len(close) >= 14:
        if HAS_TALIB:
            rsi = talib.RSI(close, timeperiod=14)[-1]
        else:
            delta = np.diff(close)
            gains = np.where(delta > 0, delta, 0)
            losses = np.where(delta < 0, -delta, 0)
            avg_gain = pd.Series(gains).rolling(window=14).mean().iloc[-1]
            avg_loss = pd.Series(losses).rolling(window=14).mean().iloc[-1]
            rs = avg_gain / avg_loss if avg_loss > 0 else 0
            rsi = 100 - (100 / (1 + rs))

        if not np.isnan(rsi):
            features['rsi_14'] = float(rsi)

    # MACD
    if len(close) >= 26:
        if HAS_TALIB:
            macd, macd_signal, macd_hist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
            if not np.isnan(macd[-1]):
                features['macd'] = float(macd[-1])
                features['macd_signal'] = float(macd_signal[-1]) if not np.isnan(macd_signal[-1]) else 0.0
        else:
            ema_12 = pd.Series(close).ewm(span=12, adjust=False).mean()
            ema_26 = pd.Series(close).ewm(span=26, adjust=False).mean()
            macd_line = ema_12 - ema_26
            macd_signal_line = macd_line.ewm(span=9, adjust=False).mean()
            features['macd'] = float(macd_line.iloc[-1])
            features['macd_signal'] = float(macd_signal_line.iloc[-1])

    return features


def compute_all_technical_features(df: pd.DataFrame) -> Dict[str, float]:
    """
    Compute all technical features for a symbol

    Args:
        df: DataFrame with OHLCV data (sorted by date)

    Returns:
        Dict with all feature values
    """
    features = {}

    features.update(compute_bollinger_compression(df))
    features.update(compute_ma_compression(df))
    features.update(compute_volatility_metrics(df))
    features.update(compute_volume_features(df))
    features.update(compute_momentum_features(df))

    return features


def upsert_factors_for_symbol(symbol: str):
    """
    Compute and store technical features for a symbol

    Args:
        symbol: Ticker symbol
    """
    with session_scope() as session:
        # Get price data
        prices = session.execute(
            select(PriceOHLC)
            .where(PriceOHLC.symbol == symbol)
            .order_by(PriceOHLC.date)
        ).scalars().all()

        if not prices or len(prices) < 50:
            logger.warning(f"Insufficient data for {symbol}: {len(prices) if prices else 0} rows")
            return

        # Convert to DataFrame
        df = pd.DataFrame([{
            'date': p.date,
            'open': p.open,
            'high': p.high,
            'low': p.low,
            'close': p.close,
            'volume': p.volume
        } for p in prices])

        # Compute features for latest date
        features = compute_all_technical_features(df)

        if not features:
            logger.warning(f"No features computed for {symbol}")
            return

        latest_date = df['date'].iloc[-1]

        # CRITICAL FIX: Use tuple for composite primary key
        existing = session.get(Factors, (symbol, latest_date))

        if existing:
            # Update existing
            for key, value in features.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
        else:
            # Create new (with null social features initially)
            factor = Factors(
                symbol=symbol,
                date=latest_date,
                social_delta_7d=None,
                author_entropy_7d=None,
                engagement_ratio_7d=None,
                trends_delta_7d=None,
                **features
            )
            session.add(factor)

        logger.debug(f"Upserted features for {symbol} on {latest_date}")
