"""
Feature registry -- single source of truth for all feature names used in Alpha Predator.

Every list here must match the column names produced by the feature-computation
modules (technical.py, explosive.py, social.py, crypto.py, institutional.py)
and consumed by the scoring pipeline.
"""
import logging
from typing import List

import pandas as pd

logger = logging.getLogger("apredator.features.registry")

# ---------------------------------------------------------------------------
# Equities feature set (26 features)
# ---------------------------------------------------------------------------
FEATURES_EQUITIES: List[str] = [
    # Technical (from technical.py)
    "bb_width_pct",
    "bb_position",
    "ma_spread_pct",
    "ma_alignment_score",
    "atr_pct",
    "volatility_20d",
    "volume_ratio_20d",
    "obv_trend_5d",
    # Social (from social.py)
    "social_delta_7d",
    "author_entropy_7d",
    "engagement_ratio_7d",
    # Momentum / oscillators
    "rsi_14",
    "macd",
    # Explosive signals (from explosive.py)
    "vol_zscore",
    "gap_up",
    "vol_spike_count",
    "vol_accel",
    "range_20d",
    "rejection_wick",
    "selling_pressure",
    "low_in_range",
    "momentum_10d",
    "pullback_pct",
    "drawdown_60d",
    # Institutional (from institutional.py)
    "call_oi_ratio",
    "short_pct_float",
    "order_flow_score",
    "smart_money_score",
]

# ---------------------------------------------------------------------------
# Crypto feature set (14 features)
# ---------------------------------------------------------------------------
FEATURES_CRYPTO: List[str] = [
    "bb_width_pct",
    "ma_spread_pct",
    "atr_pct",
    "volatility_20d",
    "volume_ratio_20d",
    # Social (from social.py)
    "social_delta_7d",
    "author_entropy_7d",
    # Crypto derivatives (from crypto.py)
    "funding_rate_delta_7d",
    "oi_delta_7d",
    "btc_decoupling",
    "vol_compression",
    # Explosive / momentum
    "vol_zscore",
    "momentum_10d",
    "rsi_14",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_features_for_asset_type(asset_type: str) -> List[str]:
    """Return the canonical feature list for *asset_type* ('stock' or 'crypto')."""
    asset_type = asset_type.lower().strip()
    if asset_type in ("crypto", "token"):
        return list(FEATURES_CRYPTO)
    return list(FEATURES_EQUITIES)


def validate_features(
    df: pd.DataFrame,
    features: List[str],
    raise_on_missing: bool = False,
) -> pd.DataFrame:
    """Return *df* filtered to only the columns present in *features*.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe (e.g. from the Factors table or feature computation).
    features : list[str]
        Desired feature names.
    raise_on_missing : bool
        If *True*, raise ``KeyError`` when any feature is absent.
        Otherwise just log a warning and continue with the available subset.

    Returns
    -------
    pd.DataFrame
        Subset of *df* containing only the available features.
    """
    available = get_available_features(df, features)
    missing = set(features) - set(available)
    if missing:
        msg = f"Missing features in dataframe: {sorted(missing)}"
        if raise_on_missing:
            raise KeyError(msg)
        logger.warning(msg)
    return df[available]


def get_available_features(df: pd.DataFrame, features: List[str]) -> List[str]:
    """Return the intersection of *df.columns* and *features*, preserving order."""
    col_set = set(df.columns)
    return [f for f in features if f in col_set]
