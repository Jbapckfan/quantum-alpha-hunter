#!/usr/bin/env python
"""
Monthly model retraining and optimization script
Analyzes recent performance and adjusts feature weights

Usage:
    python scripts/monthly_retrain.py
    python scripts/monthly_retrain.py --lookback-months 3 --min-samples 50
"""
import argparse
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from qaht.db import session_scope
from qaht.schemas import Predictions, Labels, Factors
from qaht.scoring.ridge_model import train_model, save_model
from qaht.scoring.registry import get_features_for_asset_type
from sqlalchemy import select, and_
import pandas as pd
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def analyze_recent_performance(lookback_months: int = 3) -> pd.DataFrame:
    """
    Analyze model performance over recent period

    Args:
        lookback_months: Number of months to look back

    Returns:
        DataFrame with prediction vs actual comparison
    """
    cutoff_date = (datetime.now() - timedelta(days=lookback_months * 30)).strftime("%Y-%m-%d")

    with session_scope() as session:
        # Get predictions with corresponding labels
        query = select(
            Predictions.symbol,
            Predictions.date,
            Predictions.quantum_score,
            Predictions.conviction_level,
            Predictions.prob_hit_10d,
            Labels.fwd_ret_10d,
            Labels.explosive_10d
        ).join(
            Labels,
            and_(
                Predictions.symbol == Labels.symbol,
                Predictions.date == Labels.date
            )
        ).where(
            Predictions.date >= cutoff_date,
            Labels.fwd_ret_10d.isnot(None)
        )

        results = session.execute(query).all()

        if not results:
            logger.warning(f"No predictions with labels found since {cutoff_date}")
            return pd.DataFrame()

        df = pd.DataFrame([{
            'symbol': r.symbol,
            'date': r.date,
            'quantum_score': r.quantum_score,
            'conviction_level': r.conviction_level,
            'predicted_prob': r.prob_hit_10d,
            'actual_return': r.fwd_ret_10d,
            'actual_explosive': r.explosive_10d
        } for r in results])

        return df


def calculate_calibration_metrics(performance_df: pd.DataFrame) -> dict:
    """
    Calculate calibration and discrimination metrics

    Args:
        performance_df: DataFrame from analyze_recent_performance

    Returns:
        Dictionary of metrics
    """
    if performance_df.empty:
        return {}

    metrics = {}

    # Overall hit rate by conviction level
    for level in ['MAX', 'HIGH', 'MED', 'LOW']:
        level_df = performance_df[performance_df['conviction_level'] == level]
        if len(level_df) > 0:
            hit_rate = (level_df['actual_explosive'] == True).sum() / len(level_df)
            avg_return = level_df['actual_return'].mean()
            metrics[f'{level}_hit_rate'] = hit_rate
            metrics[f'{level}_avg_return'] = avg_return
            metrics[f'{level}_count'] = len(level_df)

    # Score bucket calibration
    bins = [0, 70, 80, 90, 100]
    labels = ['70-79', '80-89', '90-99', '100']
    performance_df['score_bucket'] = pd.cut(
        performance_df['quantum_score'],
        bins=bins,
        labels=labels,
        include_lowest=True
    )

    bucket_metrics = {}
    for bucket in labels:
        bucket_df = performance_df[performance_df['score_bucket'] == bucket]
        if len(bucket_df) > 0:
            bucket_metrics[bucket] = {
                'count': len(bucket_df),
                'hit_rate': (bucket_df['actual_explosive'] == True).sum() / len(bucket_df),
                'avg_return': bucket_df['actual_return'].mean()
            }

    metrics['by_score_bucket'] = bucket_metrics

    # Calibration error (predicted prob vs actual frequency)
    prob_bins = np.linspace(0, 1, 11)
    performance_df['prob_bucket'] = pd.cut(performance_df['predicted_prob'], bins=prob_bins)
    calibration_data = []

    for bucket in performance_df['prob_bucket'].unique():
        if pd.isna(bucket):
            continue
        bucket_df = performance_df[performance_df['prob_bucket'] == bucket]
        if len(bucket_df) > 5:  # Require at least 5 samples
            pred_prob = bucket_df['predicted_prob'].mean()
            actual_freq = (bucket_df['actual_explosive'] == True).sum() / len(bucket_df)
            calibration_data.append({
                'predicted_prob': pred_prob,
                'actual_frequency': actual_freq,
                'count': len(bucket_df)
            })

    if calibration_data:
        cal_df = pd.DataFrame(calibration_data)
        calibration_error = np.abs(cal_df['predicted_prob'] - cal_df['actual_frequency']).mean()
        metrics['calibration_error'] = calibration_error
    else:
        metrics['calibration_error'] = None

    return metrics


def analyze_feature_importance(asset_type: str = "stock", lookback_months: int = 6) -> pd.DataFrame:
    """
    Analyze which features are most predictive

    Args:
        asset_type: 'stock' or 'crypto'
        lookback_months: Months of data to analyze

    Returns:
        DataFrame with feature correlations to outcomes
    """
    cutoff_date = (datetime.now() - timedelta(days=lookback_months * 30)).strftime("%Y-%m-%d")
    features = get_features_for_asset_type(asset_type)

    with session_scope() as session:
        # Build query to join factors with labels
        query = select(Factors, Labels.explosive_10d, Labels.fwd_ret_10d).join(
            Labels,
            and_(
                Factors.symbol == Labels.symbol,
                Factors.date == Labels.date
            )
        ).where(
            Factors.date >= cutoff_date,
            Labels.explosive_10d.isnot(None)
        )

        results = session.execute(query).all()

        if not results:
            logger.warning(f"No factor data with labels found since {cutoff_date}")
            return pd.DataFrame()

        # Convert to DataFrame
        data = []
        for factor, explosive, fwd_ret in results:
            row = {'explosive': explosive, 'fwd_return': fwd_ret}
            for feat in features:
                row[feat] = getattr(factor, feat, None)
            data.append(row)

        df = pd.DataFrame(data)

        # Calculate correlations
        feature_stats = []
        for feat in features:
            if feat not in df.columns or df[feat].isna().all():
                continue

            # Correlation with explosive moves
            corr_explosive = df[[feat, 'explosive']].corr().iloc[0, 1]

            # Correlation with forward returns
            corr_returns = df[[feat, 'fwd_return']].corr().iloc[0, 1]

            # Mean difference between explosive vs non-explosive
            explosive_mean = df[df['explosive'] == True][feat].mean()
            non_explosive_mean = df[df['explosive'] == False][feat].mean()
            mean_diff = explosive_mean - non_explosive_mean

            feature_stats.append({
                'feature': feat,
                'corr_explosive': corr_explosive,
                'corr_returns': corr_returns,
                'mean_diff': mean_diff,
                'explosive_mean': explosive_mean,
                'non_explosive_mean': non_explosive_mean
            })

        importance_df = pd.DataFrame(feature_stats)
        importance_df = importance_df.sort_values('corr_explosive', ascending=False, key=abs)

        return importance_df


def retrain_models(min_samples: int = 100, save_old_model: bool = True):
    """
    Retrain models for both equities and crypto

    Args:
        min_samples: Minimum training samples required
        save_old_model: Whether to backup old model
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for asset_type in ['stock', 'crypto']:
        logger.info(f"\n{'='*60}")
        logger.info(f"Retraining {asset_type} model")
        logger.info(f"{'='*60}")

        # Get training data
        features = get_features_for_asset_type(asset_type)

        with session_scope() as session:
            # Join factors with labels
            query = select(Factors, Labels.explosive_10d).join(
                Labels,
                and_(
                    Factors.symbol == Labels.symbol,
                    Factors.date == Labels.date
                )
            ).where(
                Labels.explosive_10d.isnot(None)
            )

            results = session.execute(query).all()

            if len(results) < min_samples:
                logger.warning(
                    f"Insufficient training samples for {asset_type}: {len(results)} < {min_samples}"
                )
                continue

            # Build feature matrix
            X_data = []
            y_data = []

            for factor, label in results:
                row = []
                valid = True
                for feat in features:
                    val = getattr(factor, feat, None)
                    if val is None or pd.isna(val):
                        valid = False
                        break
                    row.append(val)

                if valid:
                    X_data.append(row)
                    y_data.append(1 if label else 0)

            if len(X_data) < min_samples:
                logger.warning(f"After filtering, only {len(X_data)} valid samples for {asset_type}")
                continue

            X = pd.DataFrame(X_data, columns=features)
            y = pd.Series(y_data)

            logger.info(f"Training with {len(X)} samples, {y.sum()} positive examples")

            # Train model
            model, scaler, calibrator, feature_importance = train_model(X, y)

            # Save model with timestamp backup
            if save_old_model:
                old_model_path = f"models/{asset_type}_model_{timestamp}.pkl"
                logger.info(f"Backing up old model to {old_model_path}")

            model_path = f"models/{asset_type}_model.pkl"
            save_model(model, scaler, calibrator, feature_importance, model_path)

            logger.info(f"✅ {asset_type} model retrained and saved to {model_path}")

            # Log top features
            top_features = sorted(
                feature_importance.items(),
                key=lambda x: abs(x[1]),
                reverse=True
            )[:5]

            logger.info(f"\nTop 5 features for {asset_type}:")
            for feat, importance in top_features:
                logger.info(f"  {feat:25s}: {importance:+.4f}")


def generate_performance_report(lookback_months: int = 3, output_file: str = None):
    """
    Generate comprehensive performance report

    Args:
        lookback_months: Months to analyze
        output_file: Optional file to save report
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"MONTHLY PERFORMANCE REPORT")
    logger.info(f"{'='*60}\n")

    # Get recent performance
    perf_df = analyze_recent_performance(lookback_months)

    if perf_df.empty:
        logger.warning("No performance data available")
        return

    # Calculate metrics
    metrics = calculate_calibration_metrics(perf_df)

    # Print report
    logger.info(f"Analysis Period: Last {lookback_months} months")
    logger.info(f"Total Predictions: {len(perf_df)}")
    logger.info(f"\nPerformance by Conviction Level:")
    logger.info("-" * 60)

    for level in ['MAX', 'HIGH', 'MED', 'LOW']:
        if f'{level}_count' in metrics:
            logger.info(
                f"{level:4s}: {metrics[f'{level}_count']:4d} predictions | "
                f"Hit Rate: {metrics[f'{level}_hit_rate']*100:5.1f}% | "
                f"Avg Return: {metrics[f'{level}_avg_return']*100:+6.2f}%"
            )

    if 'calibration_error' in metrics and metrics['calibration_error']:
        logger.info(f"\nCalibration Error: {metrics['calibration_error']:.4f}")
        logger.info("(Lower is better, <0.05 is well-calibrated)")

    if 'by_score_bucket' in metrics:
        logger.info(f"\nPerformance by Score Bucket:")
        logger.info("-" * 60)
        for bucket, stats in metrics['by_score_bucket'].items():
            logger.info(
                f"{bucket:6s}: {stats['count']:3d} predictions | "
                f"Hit Rate: {stats['hit_rate']*100:5.1f}% | "
                f"Avg Return: {stats['avg_return']*100:+6.2f}%"
            )

    # Feature importance
    logger.info(f"\n{'='*60}")
    logger.info("FEATURE IMPORTANCE ANALYSIS")
    logger.info(f"{'='*60}\n")

    for asset_type in ['stock', 'crypto']:
        logger.info(f"\n{asset_type.upper()} Features:")
        logger.info("-" * 60)

        importance_df = analyze_feature_importance(asset_type, lookback_months * 2)
        if not importance_df.empty:
            top_features = importance_df.head(10)
            for _, row in top_features.iterrows():
                logger.info(
                    f"{row['feature']:25s}: Corr={row['corr_explosive']:+.3f} | "
                    f"Explosive Avg={row['explosive_mean']:+.3f} | "
                    f"Normal Avg={row['non_explosive_mean']:+.3f}"
                )

    # Save report if requested
    if output_file:
        with open(output_file, 'w') as f:
            f.write(f"Quantum Alpha Hunter - Monthly Performance Report\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'='*60}\n\n")
            # Write metrics as JSON
            import json
            f.write(json.dumps(metrics, indent=2))

        logger.info(f"\nReport saved to {output_file}")


def main():
    parser = argparse.ArgumentParser(description='Monthly model retraining and performance analysis')
    parser.add_argument('--lookback-months', type=int, default=3, help='Months to analyze (default: 3)')
    parser.add_argument('--min-samples', type=int, default=100, help='Minimum training samples (default: 100)')
    parser.add_argument('--skip-retrain', action='store_true', help='Skip retraining, only generate report')
    parser.add_argument('--report-file', type=str, help='Save report to file')

    args = parser.parse_args()

    # Generate performance report
    generate_performance_report(args.lookback_months, args.report_file)

    # Retrain models unless skipped
    if not args.skip_retrain:
        logger.info(f"\n{'='*60}")
        logger.info("RETRAINING MODELS")
        logger.info(f"{'='*60}\n")
        retrain_models(args.min_samples, save_old_model=True)
    else:
        logger.info("\nSkipping model retraining (--skip-retrain flag set)")

    logger.info("\n✅ Monthly maintenance complete")


if __name__ == "__main__":
    main()
