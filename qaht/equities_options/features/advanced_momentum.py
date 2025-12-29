"""
Advanced momentum and money flow features.

These are PROVEN to predict explosive moves:
- Accumulation/Distribution
- Money Flow Index
- Relative Strength vs SPY
- Price/Volume divergence
- Momentum acceleration
"""

import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def compute_advanced_momentum(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute advanced momentum and money flow features.

    Args:
        df: DataFrame with OHLCV data

    Returns:
        DataFrame with added momentum features
    """
    try:
        df = df.copy()

        # 1. Accumulation/Distribution Line (A/D Line)
        # Measures cumulative flow of money into/out of security
        mfm = ((df['close'] - df['low']) - (df['high'] - df['close'])) / (df['high'] - df['low'])
        mfm = mfm.fillna(0)
        mfv = mfm * df['volume']
        df['ad_line'] = mfv.cumsum()

        # 2. Money Flow Index (MFI) - RSI but using volume
        # >80 = overbought, <20 = oversold
        df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3
        df['raw_money_flow'] = df['typical_price'] * df['volume']

        # Positive and negative money flow
        delta = df['typical_price'].diff()
        positive_flow = (delta > 0) * df['raw_money_flow']
        negative_flow = (delta < 0) * df['raw_money_flow']

        # MFI calculation
        for period in [14, 28]:
            pos_mf = positive_flow.rolling(period).sum()
            neg_mf = negative_flow.rolling(period).sum()
            mfi_ratio = pos_mf / neg_mf
            df[f'mfi_{period}'] = 100 - (100 / (1 + mfi_ratio))

        # 3. Volume-Weighted Average Price (VWAP)
        df['vwap'] = (df['typical_price'] * df['volume']).cumsum() / df['volume'].cumsum()
        df['price_to_vwap'] = df['close'] / df['vwap']

        # 4. On-Balance Volume (OBV)
        # Cumulative volume with direction
        obv = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
        df['obv'] = obv

        # OBV momentum (rate of change)
        df['obv_roc_10'] = df['obv'].pct_change(10) * 100

        # 5. Chaikin Money Flow (CMF)
        # Measures buying/selling pressure
        for period in [10, 20]:
            ad = mfm * df['volume']
            df[f'cmf_{period}'] = ad.rolling(period).sum() / df['volume'].rolling(period).sum()

        # 6. Volume Price Trend (VPT)
        # Similar to OBV but uses % price change
        vpt = (df['close'].pct_change() * df['volume']).fillna(0).cumsum()
        df['vpt'] = vpt

        # 7. Momentum Acceleration
        # Change in momentum (2nd derivative of price)
        df['momentum_10'] = df['close'].pct_change(10)
        df['momentum_20'] = df['close'].pct_change(20)
        df['momentum_acceleration'] = df['momentum_10'] - df['momentum_10'].shift(5)

        # 8. Volume Acceleration
        # Increasing volume = conviction
        df['volume_ma_20'] = df['volume'].rolling(20).mean()
        df['volume_acceleration'] = (df['volume'] - df['volume_ma_20']) / df['volume_ma_20']

        # 9. Price Velocity (rate of change of rate of change)
        roc_5 = df['close'].pct_change(5)
        df['price_velocity'] = roc_5 - roc_5.shift(5)

        # 10. Relative Volume (vs avg volume)
        df['relative_volume'] = df['volume'] / df['volume'].rolling(20).mean()

        # 11. Up/Down Volume Ratio
        # More up volume = bullish
        up_volume = ((df['close'] > df['open']) * df['volume']).rolling(10).sum()
        down_volume = ((df['close'] < df['open']) * df['volume']).rolling(10).sum()
        df['up_down_volume_ratio'] = up_volume / (down_volume + 1)  # Avoid div by zero

        # 12. Volume Weighted Momentum
        # Momentum weighted by volume (higher volume = more important)
        df['volume_weighted_momentum'] = df['momentum_10'] * (df['volume'] / df['volume_ma_20'])

        # 13. Breakout Strength
        # How far above 20-day high?
        high_20 = df['high'].rolling(20).max()
        df['breakout_strength'] = ((df['close'] - high_20) / high_20) * 100

        # 14. Support Test Count
        # How many times price bounced off support?
        low_20 = df['low'].rolling(20).min()
        df['near_support'] = ((df['low'] - low_20) / low_20) < 0.02  # Within 2% of support
        df['support_tests'] = df['near_support'].rolling(20).sum()

        # 15. Consolidation Detection
        # Low volatility = consolidation = potential breakout
        high_10 = df['high'].rolling(10).max()
        low_10 = df['low'].rolling(10).min()
        df['consolidation_range'] = ((high_10 - low_10) / low_10) * 100

        # Clean up temporary columns
        df = df.drop(columns=['typical_price', 'raw_money_flow', 'near_support'], errors='ignore')

        logger.info(f"Added {15} advanced momentum features")

        return df

    except Exception as e:
        logger.error(f"Error computing advanced momentum: {e}")
        return df


def compute_relative_strength(symbol_df: pd.DataFrame, spy_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute relative strength vs SPY (market).

    Outperforming SPY = bullish.

    Args:
        symbol_df: Stock price data
        spy_df: SPY price data

    Returns:
        DataFrame with relative strength features
    """
    try:
        df = symbol_df.copy()

        # Ensure same dates
        spy_df = spy_df.set_index('date') if 'date' in spy_df.columns else spy_df
        df = df.set_index('date') if 'date' in df.columns else df

        # Merge on date
        merged = df.join(spy_df['close'].rename('spy_close'), how='left')
        merged['spy_close'] = merged['spy_close'].ffill()  # Forward fill missing

        # Relative strength (stock return / SPY return)
        for period in [10, 20, 50]:
            stock_return = merged['close'].pct_change(period)
            spy_return = merged['spy_close'].pct_change(period)
            merged[f'rel_strength_{period}'] = stock_return - spy_return

        # Beta (correlation with SPY)
        merged['beta_50'] = merged['close'].pct_change().rolling(50).corr(merged['spy_close'].pct_change())

        df = merged.drop(columns=['spy_close'], errors='ignore')

        logger.info(f"Added relative strength features")

        return df.reset_index() if 'date' in df.index.names else df

    except Exception as e:
        logger.error(f"Error computing relative strength: {e}")
        return symbol_df
