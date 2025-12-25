"""
Data validation framework - catches bad data before it corrupts the model
Critical for production reliability
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("qaht.validation")


class DataValidator:
    """Validates data quality and freshness"""

    def __init__(self):
        self.errors = []
        self.warnings = []

    def validate_price_data(self, df: pd.DataFrame) -> Tuple[bool, List[str]]:
        """
        Validate OHLCV data quality

        Args:
            df: DataFrame with columns: open, high, low, close, volume, date

        Returns:
            (is_valid, list_of_issues)
        """
        issues = []

        # Check required columns
        required = ['open', 'high', 'low', 'close', 'volume', 'date']
        missing = [col for col in required if col not in df.columns]
        if missing:
            issues.append(f"Missing required columns: {missing}")
            return False, issues

        # Check for nulls
        null_counts = df[required].isnull().sum()
        if null_counts.any():
            issues.append(f"Null values found: {null_counts[null_counts > 0].to_dict()}")

        # Check for negative prices
        price_cols = ['open', 'high', 'low', 'close']
        for col in price_cols:
            negative = (df[col] <= 0).sum()
            if negative > 0:
                issues.append(f"{negative} negative/zero values in {col}")

        # Check OHLC relationships
        invalid_ohlc = (
            (df['high'] < df['low']) |
            (df['high'] < df['open']) |
            (df['high'] < df['close']) |
            (df['low'] > df['open']) |
            (df['low'] > df['close'])
        ).sum()
        if invalid_ohlc > 0:
            issues.append(f"{invalid_ohlc} rows with invalid OHLC relationships")

        # Check for unrealistic price movements (>100% in one day)
        if len(df) > 1:
            df_sorted = df.sort_values('date')
            price_change = (df_sorted['close'].pct_change().abs() * 100)
            extreme_moves = (price_change > 100).sum()
            if extreme_moves > 0:
                issues.append(f"{extreme_moves} days with >100% price change (possible split)")

        # Check for zero volume
        zero_volume = (df['volume'] == 0).sum()
        if zero_volume > 0:
            issues.append(f"{zero_volume} days with zero volume (market closed?)")

        # Check for outliers using IQR method
        for col in price_cols:
            Q1 = df[col].quantile(0.25)
            Q3 = df[col].quantile(0.75)
            IQR = Q3 - Q1
            outliers = ((df[col] < Q1 - 3*IQR) | (df[col] > Q3 + 3*IQR)).sum()
            if outliers > 0:
                issues.append(f"{outliers} outliers detected in {col}")

        is_valid = len(issues) == 0
        return is_valid, issues

    def validate_features(self, df: pd.DataFrame, feature_names: List[str]) -> Tuple[bool, List[str]]:
        """
        Validate computed features

        Args:
            df: DataFrame with feature columns
            feature_names: List of expected feature names

        Returns:
            (is_valid, list_of_issues)
        """
        issues = []

        # Check all features exist
        missing = [f for f in feature_names if f not in df.columns]
        if missing:
            issues.append(f"Missing features: {missing}")
            return False, issues

        # Check for excessive nulls (>50% null = feature broken)
        for feature in feature_names:
            null_pct = df[feature].isnull().sum() / len(df) * 100
            if null_pct > 50:
                issues.append(f"{feature}: {null_pct:.1f}% null values (feature broken?)")

        # Check for inf values
        for feature in feature_names:
            inf_count = np.isinf(df[feature]).sum()
            if inf_count > 0:
                issues.append(f"{feature}: {inf_count} inf values")

        # Check for constant features (no variance)
        for feature in feature_names:
            if df[feature].std() == 0:
                issues.append(f"{feature}: constant value (no variance)")

        is_valid = len([i for i in issues if 'broken' in i or 'inf' in i]) == 0
        return is_valid, issues

    def check_data_freshness(self, last_date: str, max_age_hours: int = 48) -> Tuple[bool, str]:
        """
        Check if data is fresh enough

        Args:
            last_date: Most recent date in data (YYYY-MM-DD)
            max_age_hours: Maximum acceptable age in hours

        Returns:
            (is_fresh, message)
        """
        try:
            last_dt = datetime.strptime(last_date, "%Y-%m-%d")
            age_hours = (datetime.now() - last_dt).total_seconds() / 3600

            if age_hours > max_age_hours:
                return False, f"Data is {age_hours:.1f} hours old (max: {max_age_hours})"
            else:
                return True, f"Data is fresh ({age_hours:.1f} hours old)"
        except Exception as e:
            return False, f"Invalid date format: {e}"

    def detect_look_ahead_bias(self, predictions_df: pd.DataFrame, labels_df: pd.DataFrame) -> List[str]:
        """
        Detect if predictions were made using future data

        CRITICAL: Predictions must be made BEFORE labels

        Args:
            predictions_df: DataFrame with columns: symbol, date, quantum_score
            labels_df: DataFrame with columns: symbol, date, explosive_10d

        Returns:
            List of violations (empty = no bias detected)
        """
        violations = []

        # Merge predictions and labels
        merged = predictions_df.merge(
            labels_df,
            on=['symbol', 'date'],
            how='inner',
            suffixes=('_pred', '_label')
        )

        if len(merged) == 0:
            return []

        # Check: prediction date should be < label date + horizon
        # For 10-day forward labels, prediction on date D uses label from D+10
        # This is WRONG if we predicted on date D using label from D+10

        # More simply: Count predictions that have same-date labels
        # This indicates we might have used the label to make the prediction
        same_date_predictions = len(merged)

        if same_date_predictions > 0:
            violations.append(
                f"WARNING: {same_date_predictions} predictions have same-date labels. "
                f"Ensure predictions are made BEFORE computing labels to avoid look-ahead bias."
            )

        return violations

    def validate_symbol_eligibility(
        self,
        symbol: str,
        market_cap: Optional[float] = None,
        min_price: float = 5.0,
        max_price: float = 500.0,
        min_volume: float = 1_000_000,
        max_market_cap: float = 10_000_000_000  # $10B max
    ) -> Tuple[bool, str]:
        """
        Validate if symbol is eligible for multi-bagger detection

        CRITICAL: No mega-caps (AAPL, TSLA, NVDA) - they can't 10x

        Args:
            symbol: Ticker symbol
            market_cap: Market capitalization in USD
            min_price: Minimum price (avoid penny stocks)
            max_price: Maximum price
            min_volume: Minimum daily volume
            max_market_cap: Maximum market cap ($10B = real opportunity)

        Returns:
            (is_eligible, reason)
        """
        # Block mega-cap behemoths explicitly
        MEGA_CAPS_BLOCKLIST = {
            'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'NVDA', 'META',
            'TSLA', 'BRK.A', 'BRK.B', 'V', 'JPM', 'JNJ', 'WMT', 'PG',
            'MA', 'HD', 'CVX', 'MRK', 'ABBV', 'KO', 'PEP', 'COST',
            'AVGO', 'TMO', 'ORCL', 'NKE', 'ACN', 'DIS', 'CSCO', 'ABT',
            'CRM', 'VZ', 'ADBE', 'TXN', 'INTC', 'AMD', 'QCOM', 'UNH'
        }

        if symbol in MEGA_CAPS_BLOCKLIST:
            return False, f"{symbol} is a mega-cap ($1T+) - no multi-bagger potential"

        # Check market cap
        if market_cap is not None and market_cap > max_market_cap:
            return False, f"Market cap ${market_cap/1e9:.1f}B > max ${max_market_cap/1e9:.1f}B"

        return True, "Eligible"

    def validate_pipeline_output(
        self,
        symbols_in: int,
        symbols_fetched: int,
        symbols_scored: int,
        min_success_rate: float = 0.7
    ) -> Tuple[bool, str]:
        """
        Validate pipeline success rates

        Args:
            symbols_in: Number of symbols requested
            symbols_fetched: Number successfully fetched
            symbols_scored: Number successfully scored
            min_success_rate: Minimum acceptable success rate

        Returns:
            (is_healthy, message)
        """
        if symbols_in == 0:
            return False, "No symbols provided"

        fetch_rate = symbols_fetched / symbols_in
        score_rate = symbols_scored / symbols_in if symbols_in > 0 else 0

        issues = []
        if fetch_rate < min_success_rate:
            issues.append(f"Low fetch rate: {fetch_rate:.1%}")
        if score_rate < min_success_rate:
            issues.append(f"Low score rate: {score_rate:.1%}")

        if issues:
            return False, "; ".join(issues)

        return True, f"Pipeline healthy: {score_rate:.1%} success rate"


# Convenience functions
def validate_dataframe(df: pd.DataFrame, df_type: str = "price") -> bool:
    """Quick validation wrapper"""
    validator = DataValidator()

    if df_type == "price":
        is_valid, issues = validator.validate_price_data(df)
    else:
        is_valid, issues = True, []

    if not is_valid:
        logger.error(f"Validation failed for {df_type} data:")
        for issue in issues:
            logger.error(f"  - {issue}")
    elif issues:
        logger.warning(f"Warnings for {df_type} data:")
        for issue in issues:
            logger.warning(f"  - {issue}")

    return is_valid


def check_for_look_ahead_bias(session) -> List[str]:
    """Check entire database for look-ahead bias"""
    from sqlalchemy import select
    from .schemas import Predictions, Labels

    predictions = session.execute(select(Predictions)).scalars().all()
    labels = session.execute(select(Labels)).scalars().all()

    pred_df = pd.DataFrame([{
        'symbol': p.symbol,
        'date': p.date,
        'quantum_score': p.quantum_score
    } for p in predictions])

    label_df = pd.DataFrame([{
        'symbol': l.symbol,
        'date': l.date,
        'explosive_10d': l.explosive_10d
    } for l in labels])

    validator = DataValidator()
    violations = validator.detect_look_ahead_bias(pred_df, label_df)

    for violation in violations:
        logger.critical(violation)

    return violations
