"""
Ridge regression scoring model with isotonic calibration
Self-optimizing via monthly weight updates
"""
import pandas as pd
import numpy as np
from typing import Any, Optional, Dict, List
import logging
import pickle
from pathlib import Path

from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import TimeSeriesSplit
from sklearn.calibration import CalibratedClassifierCV
from sklearn.isotonic import IsotonicRegression

from ..db import session_scope
from ..schemas import Factors, Labels, Predictions, PriceOHLC
from ..config import get_config
from .registry import FEATURES, validate_features, get_features_for_asset_type
from .empirical_combos import EmpiricalScorer, RegimeState, RegimeType
from sqlalchemy import select, text

logger = logging.getLogger("qaht.scoring.ridge")
config = get_config()


def _conviction_from_score(score: float) -> str:
    """Map a 0-100 score to a conviction bucket."""
    if score >= 90:
        return "MAX"
    if score >= 80:
        return "HIGH"
    if score >= 70:
        return "MED"
    return "LOW"


def load_price_history(symbols: List[str], asset_type: str = 'stock') -> Dict[str, pd.DataFrame]:
    """Load OHLCV history for a batch of symbols from the database."""
    if not symbols:
        return {}

    with session_scope() as session:
        rows = session.execute(
            select(PriceOHLC)
            .where(PriceOHLC.symbol.in_(symbols))
            .where(PriceOHLC.asset_type == asset_type)
            .order_by(PriceOHLC.symbol, PriceOHLC.date)
        ).scalars().all()

    history: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        history.setdefault(row.symbol, []).append(
            {
                "date": row.date,
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "volume": row.volume,
            }
        )

    return {
        symbol: pd.DataFrame(records)
        for symbol, records in history.items()
        if records
    }


def _extract_triggered_empirical_signals(result: Any) -> List[str]:
    """Return boolean empirical signals that fired for a symbol."""
    return [
        name
        for name, value in vars(result.signals).items()
        if name != "symbol" and isinstance(value, bool) and value
    ]


def _build_conviction_reasons(
    ml_quantum_score: int,
    empirical_result: Optional[Any],
) -> List[str]:
    """Create a compact set of reasons behind a score."""
    reasons = [f"ML baseline score {ml_quantum_score}"]

    if empirical_result is None:
        reasons.append("Empirical combo score unavailable")
        return reasons

    reasons.append(f"Empirical combo score {empirical_result.combo_score:.1f}")

    for combo in empirical_result.matched_combos[:3]:
        reasons.append(f"Matched {combo.name} ({combo.hit_rate:.1%} hit rate)")

    triggered_signals = _extract_triggered_empirical_signals(empirical_result)
    if triggered_signals:
        reasons.append(
            "Signals fired: " + ", ".join(triggered_signals[:5])
        )

    return reasons


def load_training_data(symbols: Optional[List[str]] = None, asset_type: str = 'stock') -> pd.DataFrame:
    """
    Load features and labels for training

    Args:
        symbols: List of symbols (None = all)
        asset_type: 'stock' or 'crypto'

    Returns:
        DataFrame with features and target
    """
    with session_scope() as session:
        # SQL join to get features + labels
        query = text("""
            SELECT
                f.symbol,
                f.date,
                f.bb_width_pct,
                f.bb_position,
                f.ma_spread_pct,
                f.ma_alignment_score,
                f.atr_pct,
                f.volatility_20d,
                f.volume_ratio_20d,
                f.obv_trend_5d,
                f.social_delta_7d,
                f.author_entropy_7d,
                f.engagement_ratio_7d,
                f.rsi_14,
                f.macd,
                f.macd_signal,
                l.explosive_10d,
                l.fwd_ret_10d
            FROM factors f
            JOIN labels l ON f.symbol = l.symbol AND f.date = l.date
            WHERE l.fwd_ret_10d IS NOT NULL
        """)

        if symbols:
            placeholders = ','.join([f"'{s}'" for s in symbols])
            query = text(str(query) + f" AND f.symbol IN ({placeholders})")

        df = pd.read_sql(query, session.bind)

    if df.empty:
        logger.warning("No training data found")
        return pd.DataFrame()

    logger.info(f"Loaded {len(df)} training samples")
    return df


def train_model(symbols: Optional[List[str]] = None, asset_type: str = 'stock') -> Optional[Dict]:
    """
    Train Ridge regression model with cross-validation

    Args:
        symbols: Symbols to train on (None = all)
        asset_type: 'stock' or 'crypto'

    Returns:
        Dict with model, scaler, and metrics
    """
    # Load data
    df = load_training_data(symbols, asset_type)

    if len(df) < config.scoring.min_samples:
        logger.warning(f"Insufficient samples for training: {len(df)} < {config.scoring.min_samples}")
        return None

    # Get features for asset type
    features = get_features_for_asset_type(asset_type)

    # Validate and select features
    try:
        X = validate_features(df, features, raise_on_missing=False)
    except ValueError as e:
        logger.error(f"Feature validation failed: {e}")
        return None

    # Handle missing values
    X = X.fillna(0)

    # Target: forward return (continuous)
    y = df['fwd_ret_10d'].values

    # Build pipeline
    pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('ridge', RidgeCV(alphas=[0.1, 1.0, 10.0, 100.0], cv=config.scoring.cv_folds))
    ])

    # Train
    logger.info("Training Ridge model...")
    pipeline.fit(X, y)

    # Get best alpha
    best_alpha = pipeline.named_steps['ridge'].alpha_
    logger.info(f"Best alpha: {best_alpha}")

    # Calculate feature importance (coefficients)
    coef = pipeline.named_steps['ridge'].coef_
    feature_importance = dict(zip(X.columns, coef))

    # Sort by absolute value
    feature_importance = {k: v for k, v in sorted(feature_importance.items(), key=lambda x: abs(x[1]), reverse=True)}
    logger.info(f"Top features: {list(feature_importance.keys())[:5]}")

    # Calibrate predictions to probabilities
    y_pred = pipeline.predict(X)

    # Binary target for calibration (explosion yes/no)
    y_binary = df['explosive_10d'].values.astype(int)

    # Isotonic regression for calibration
    calibrator = IsotonicRegression(out_of_bounds='clip')
    calibrator.fit(y_pred, y_binary)

    logger.info("Model training complete")

    return {
        'pipeline': pipeline,
        'calibrator': calibrator,
        'features': list(X.columns),
        'feature_importance': feature_importance,
        'best_alpha': best_alpha,
        'n_samples': len(df)
    }


def score_symbols(symbols: List[str], model_dict: Dict, asset_type: str = 'stock') -> pd.DataFrame:
    """
    Score symbols using trained model

    Args:
        symbols: List of symbols to score
        model_dict: Trained model dictionary
        asset_type: 'stock' or 'crypto'

    Returns:
        DataFrame with scores
    """
    pipeline = model_dict['pipeline']
    calibrator = model_dict['calibrator']
    features = model_dict['features']

    with session_scope() as session:
        # Get latest factors for each symbol
        results = []

        for symbol in symbols:
            factor = session.execute(
                select(Factors)
                .where(Factors.symbol == symbol)
                .order_by(Factors.date.desc())
                .limit(1)
            ).scalar_one_or_none()

            if not factor:
                logger.warning(f"No factors found for {symbol}")
                continue

            # Extract feature values
            feature_values = {}
            for feat in features:
                value = getattr(factor, feat, None)
                feature_values[feat] = value if value is not None else 0.0

            # Create single-row DataFrame
            X = pd.DataFrame([feature_values])

            # Predict
            pred_return = pipeline.predict(X)[0]
            prob_explosion = calibrator.predict([pred_return])[0]

            # Quantum score (0-100 scale)
            quantum_score = int(prob_explosion * 100)

            results.append({
                'symbol': symbol,
                'date': factor.date,
                'quantum_score': quantum_score,
                'ml_quantum_score': quantum_score,
                'empirical_combo_score': None,
                'prob_hit_10d': prob_explosion,
                'pred_return': pred_return,
                'conviction_level': _conviction_from_score(quantum_score),
                'components': feature_values,
                'conviction_reasons': [],
            })

    df = pd.DataFrame(results)
    logger.info(f"Scored {len(df)} symbols")

    return df


def upsert_predictions(df: pd.DataFrame):
    """
    Save predictions to database

    Args:
        df: DataFrame with predictions
    """
    with session_scope() as session:
        for _, row in df.iterrows():
            existing = session.get(Predictions, (row['symbol'], row['date']))

            # Convert components dict to JSON string
            import json
            components_json = json.dumps(row['components'])

            if existing:
                existing.quantum_score = row['quantum_score']
                existing.prob_hit_10d = row['prob_hit_10d']
                existing.conviction_level = row['conviction_level']
                existing.components = components_json
            else:
                pred = Predictions(
                    symbol=row['symbol'],
                    date=row['date'],
                    quantum_score=row['quantum_score'],
                    prob_hit_10d=row['prob_hit_10d'],
                    pred_lo=None,  # Add conformal intervals later
                    pred_hi=None,
                    components=components_json,
                    conviction_level=row['conviction_level']
                )
                session.add(pred)

        logger.info(f"Upserted {len(df)} predictions")


def train_and_score(symbols: List[str], asset_type: str = 'stock'):
    """
    Complete workflow: train model and score symbols

    Args:
        symbols: List of symbols
        asset_type: 'stock' or 'crypto'
    """
    # Train model
    model_dict = train_model(symbols, asset_type)

    if not model_dict:
        logger.error("Model training failed")
        return

    # Score symbols
    scores = score_symbols(symbols, model_dict, asset_type)

    if not scores.empty:
        price_history = load_price_history(scores['symbol'].tolist(), asset_type=asset_type)
        empirical_scorer = EmpiricalScorer()
        neutral_regime = RegimeState(
            regime=RegimeType.NEUTRAL,
            ev_adjustment=0.0,
            position_size_mult=1.0,
        )

        for idx, row in scores.iterrows():
            symbol = row['symbol']
            ml_quantum_score = int(row['ml_quantum_score'])
            components = {'features': dict(row['components'])}
            empirical_df = price_history.get(symbol)
            empirical_result = None

            if empirical_df is not None and len(empirical_df) >= 30:
                empirical_result = empirical_scorer.score_symbol(
                    symbol=symbol,
                    df=empirical_df,
                    quantum_score=None,
                    entry_price=float(empirical_df['close'].iloc[-1]),
                    regime=neutral_regime,
                )
                empirical_combo_score = round(empirical_result.combo_score, 2)
                hybrid_score = int(round((0.4 * ml_quantum_score) + (0.6 * empirical_result.combo_score)))

                matched_combos = [combo.name for combo in empirical_result.matched_combos]
                triggered_signals = _extract_triggered_empirical_signals(empirical_result)

                components.update({
                    'ml_quantum_score': ml_quantum_score,
                    'empirical_combo_score': empirical_combo_score,
                    'matched_combos': matched_combos,
                    'triggered_empirical_signals': triggered_signals,
                })

                scores.at[idx, 'empirical_combo_score'] = empirical_combo_score
                scores.at[idx, 'quantum_score'] = hybrid_score
                scores.at[idx, 'conviction_level'] = _conviction_from_score(hybrid_score)
            else:
                components.update({
                    'ml_quantum_score': ml_quantum_score,
                    'empirical_combo_score': None,
                    'matched_combos': [],
                    'triggered_empirical_signals': [],
                })

            conviction_reasons = _build_conviction_reasons(ml_quantum_score, empirical_result)
            components['conviction_reasons'] = conviction_reasons
            scores.at[idx, 'conviction_reasons'] = conviction_reasons
            scores.at[idx, 'components'] = components

        # Save predictions
        upsert_predictions(scores)

        # Log top signals
        top_signals = scores.nlargest(10, 'quantum_score')[['symbol', 'quantum_score', 'conviction_level']]
        logger.info(f"\nTop 10 signals:\n{top_signals}")

    return scores


def save_model(model_dict: Dict, filepath: str):
    """
    Persist trained model to disk

    Args:
        model_dict: Model dictionary
        filepath: Path to save to
    """
    with open(filepath, 'wb') as f:
        pickle.dump(model_dict, f)

    logger.info(f"Model saved to {filepath}")


def load_model(filepath: str) -> Optional[Dict]:
    """
    Load persisted model

    Args:
        filepath: Path to model file

    Returns:
        Model dictionary or None
    """
    path = Path(filepath)

    if not path.exists():
        logger.warning(f"Model file not found: {filepath}")
        return None

    with open(filepath, 'rb') as f:
        model_dict = pickle.load(f)

    logger.info(f"Model loaded from {filepath}")
    return model_dict
