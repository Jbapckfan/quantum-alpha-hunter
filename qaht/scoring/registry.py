"""
Feature registry - single source of truth for model features
CRITICAL: Only add features here after validation in pipeline
Prevents schema/model misalignment issues
"""
import pandas as pd
from typing import List, Optional
import logging

logger = logging.getLogger("qaht.registry")

# ============================================================================
# PHASE 1: Minimal Viable Feature Set
# ============================================================================

FEATURES_EQUITIES = [
    # Technical compression signals
    "bb_width_pct",
    "bb_position",
    "ma_spread_pct",
    "ma_alignment_score",
    "atr_pct",
    "volatility_20d",

    # Volume/flow
    "volume_ratio_20d",
    "obv_trend_5d",

    # Social/attention
    "social_delta_7d",
    "trends_delta_7d",

    # Momentum
    "rsi_14",
    "macd",
]

FEATURES_CRYPTO = [
    # Technical (same as equities)
    "bb_width_pct",
    "ma_spread_pct",
    "atr_pct",
    "volatility_20d",

    # Volume
    "volume_ratio_20d",

    # Social/attention
    "social_delta_7d",
    "trends_delta_7d",

    # Crypto-specific derivatives
    "funding_rate_delta_7d",
    "oi_delta_7d",
]

# Default to equities for backward compatibility
FEATURES = FEATURES_EQUITIES


def get_features_for_asset_type(asset_type: str = "stock") -> List[str]:
    """
    Get feature list for specific asset type

    Args:
        asset_type: 'stock' or 'crypto'

    Returns:
        List of feature column names
    """
    if asset_type.lower() == "crypto":
        return FEATURES_CRYPTO.copy()
    else:
        return FEATURES_EQUITIES.copy()


def validate_features(
    df: pd.DataFrame,
    features: Optional[List[str]] = None,
    raise_on_missing: bool = True
) -> pd.DataFrame:
    """
    Ensure required features exist in dataframe

    CRITICAL: Use this before training/scoring to catch schema mismatches

    Args:
        df: DataFrame to validate
        features: List of required features (defaults to FEATURES)
        raise_on_missing: If True, raise ValueError on missing features

    Returns:
        DataFrame with only the required features

    Raises:
        ValueError: If required features are missing and raise_on_missing=True
    """
    features = features or FEATURES
    missing = [f for f in features if f not in df.columns]

    if missing:
        error_msg = f"Missing features in dataframe: {missing}"
        if raise_on_missing:
            logger.error(error_msg)
            raise ValueError(error_msg)
        else:
            logger.warning(error_msg)
            # Return only available features
            available = [f for f in features if f in df.columns]
            return df[available]

    return df[features]


def get_available_features(df: pd.DataFrame, features: Optional[List[str]] = None) -> List[str]:
    """
    Get list of features that are actually available in the dataframe

    Args:
        df: DataFrame to check
        features: List of desired features (defaults to FEATURES)

    Returns:
        List of available feature names
    """
    features = features or FEATURES
    return [f for f in features if f in df.columns]


def add_feature(feature_name: str, asset_type: str = "stock"):
    """
    Add a new feature to the registry (after validation!)

    Args:
        feature_name: Name of the feature column
        asset_type: 'stock', 'crypto', or 'both'
    """
    if asset_type in ["stock", "both"]:
        if feature_name not in FEATURES_EQUITIES:
            FEATURES_EQUITIES.append(feature_name)
            logger.info(f"Added feature '{feature_name}' to equities registry")

    if asset_type in ["crypto", "both"]:
        if feature_name not in FEATURES_CRYPTO:
            FEATURES_CRYPTO.append(feature_name)
            logger.info(f"Added feature '{feature_name}' to crypto registry")
