"""
Ridge regression ML scorer -- trains a calibrated model on historical factors and
labels, then scores live symbols.

Pipeline: StandardScaler -> RidgeCV -> IsotonicRegression calibration.
Ported from QAHT scoring/ridge_model.py with adaptations for Alpha Predator
schemas and feature registry.
"""
import json
import logging
import pickle
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ..config import get_config
from ..db import session_scope
from ..features.registry import get_features_for_asset_type, validate_features
from ..schemas import Factors, Labels, Predictions

logger = logging.getLogger("apredator.scoring.ml_scorer")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_training_data(
    symbols: Optional[List[str]] = None,
    asset_type: str = "stock",
) -> pd.DataFrame:
    """Load joined factors + labels where ``fwd_ret_10d`` is not null.

    Parameters
    ----------
    symbols : list[str] or None
        Restrict to these symbols.  ``None`` means load all.
    asset_type : str
        ``'stock'`` or ``'crypto'`` -- determines which feature columns to select.

    Returns
    -------
    pd.DataFrame
        Rows with features, ``fwd_ret_10d``, and ``explosive_10d`` columns.
    """
    features = get_features_for_asset_type(asset_type)

    with session_scope() as session:
        query = (
            session.query(Factors, Labels)
            .join(Labels, (Factors.symbol == Labels.symbol) & (Factors.date == Labels.date))
            .filter(Labels.fwd_ret_10d.isnot(None))
        )

        if symbols:
            query = query.filter(Factors.symbol.in_(symbols))

        rows = query.all()

    if not rows:
        logger.warning("No training data found")
        return pd.DataFrame()

    records = []
    for factor_row, label_row in rows:
        rec = {
            "symbol": factor_row.symbol,
            "date": factor_row.date,
        }
        for feat in features:
            rec[feat] = getattr(factor_row, feat, None)
        rec["fwd_ret_10d"] = label_row.fwd_ret_10d
        rec["explosive_10d"] = label_row.explosive_10d
        records.append(rec)

    df = pd.DataFrame(records)
    logger.info(
        "Loaded %d training samples (%s, %d features)",
        len(df),
        asset_type,
        len(features),
    )
    return df


# ---------------------------------------------------------------------------
# Model training
# ---------------------------------------------------------------------------

def train_model(
    symbols: Optional[List[str]] = None,
    asset_type: str = "stock",
) -> Optional[Dict]:
    """Train a RidgeCV model with isotonic calibration.

    Returns
    -------
    dict or None
        ``{"pipeline", "calibrator", "features", "feature_importance",
        "n_samples"}`` or ``None`` if insufficient data.
    """
    config = get_config()
    min_samples = config.scoring.min_samples

    df = load_training_data(symbols=symbols, asset_type=asset_type)
    if df.empty or len(df) < min_samples:
        logger.warning(
            "Insufficient training data: %d samples (need %d)",
            len(df),
            min_samples,
        )
        return None

    features = get_features_for_asset_type(asset_type)
    df_features = validate_features(df, features)

    # Drop rows with all-NaN feature vectors
    valid_mask = df_features.notna().any(axis=1)
    df = df.loc[valid_mask].copy()
    df_features = df_features.loc[valid_mask].copy()

    if len(df) < min_samples:
        logger.warning("Too few valid rows after NaN filtering: %d", len(df))
        return None

    # Fill remaining NaN with column medians
    X = df_features.fillna(df_features.median())
    y = df["fwd_ret_10d"].values

    # Build pipeline: StandardScaler + RidgeCV
    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("ridge", RidgeCV(alphas=[0.1, 1.0, 10.0, 100.0])),
    ])
    pipeline.fit(X, y)

    ridge_model = pipeline.named_steps["ridge"]
    chosen_alpha = ridge_model.alpha_
    logger.info("RidgeCV selected alpha=%.2f", chosen_alpha)

    # Feature importance from ridge coefficients
    feature_importance = dict(zip(
        X.columns.tolist(),
        ridge_model.coef_.tolist(),
    ))

    # Calibrate with IsotonicRegression on the explosive_10d binary target
    y_pred_train = pipeline.predict(X)
    y_binary = df["explosive_10d"].astype(int).values

    calibrator = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip")
    calibrator.fit(y_pred_train, y_binary)

    model_dict = {
        "pipeline": pipeline,
        "calibrator": calibrator,
        "features": X.columns.tolist(),
        "feature_importance": feature_importance,
        "n_samples": len(df),
        "alpha": chosen_alpha,
        "asset_type": asset_type,
        "trained_at": datetime.utcnow().isoformat(),
    }
    logger.info(
        "Model trained: %d samples, %d features, alpha=%.2f",
        len(df),
        len(model_dict["features"]),
        chosen_alpha,
    )
    return model_dict


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_symbols(
    symbols: List[str],
    model_dict: Dict,
    asset_type: str = "stock",
) -> pd.DataFrame:
    """Score a list of symbols using the trained model.

    Parameters
    ----------
    symbols : list[str]
        Symbols to score.
    model_dict : dict
        Output from :func:`train_model`.
    asset_type : str
        ``'stock'`` or ``'crypto'``.

    Returns
    -------
    pd.DataFrame
        Columns: symbol, date, quantum_score, prob_hit_10d, conviction_level,
        components (JSON string).
    """
    pipeline = model_dict["pipeline"]
    calibrator = model_dict["calibrator"]
    model_features = model_dict["features"]

    # Load latest factors for each symbol
    with session_scope() as session:
        from sqlalchemy import func

        # Sub-query: latest date per symbol
        latest_dates = (
            session.query(
                Factors.symbol,
                func.max(Factors.date).label("max_date"),
            )
            .filter(Factors.symbol.in_(symbols))
            .group_by(Factors.symbol)
            .subquery()
        )

        rows = (
            session.query(Factors)
            .join(
                latest_dates,
                (Factors.symbol == latest_dates.c.symbol)
                & (Factors.date == latest_dates.c.max_date),
            )
            .all()
        )

    if not rows:
        logger.warning("No factor rows found for scoring")
        return pd.DataFrame()

    records = []
    for row in rows:
        rec = {"symbol": row.symbol, "date": row.date}
        for feat in model_features:
            rec[feat] = getattr(row, feat, None)
        records.append(rec)

    df = pd.DataFrame(records)
    df_features = df[model_features].fillna(df[model_features].median())

    # Predict and calibrate
    raw_preds = pipeline.predict(df_features)
    probs = calibrator.predict(raw_preds)
    probs = np.clip(probs, 0.0, 1.0)

    df["prob_hit_10d"] = probs
    df["quantum_score"] = (probs * 100).astype(int)

    # Conviction levels
    df["conviction_level"] = df["quantum_score"].apply(_conviction_from_score)

    # Components JSON
    df["components"] = df.apply(
        lambda row: json.dumps({
            feat: round(float(row.get(feat, 0) or 0), 4)
            for feat in model_features[:10]  # top 10 for brevity
        }),
        axis=1,
    )

    logger.info("Scored %d symbols", len(df))
    return df[["symbol", "date", "quantum_score", "prob_hit_10d", "conviction_level", "components"]]


def _conviction_from_score(score: int) -> str:
    """Map quantum_score to conviction level."""
    if score >= 90:
        return "MAX"
    if score >= 80:
        return "HIGH"
    if score >= 70:
        return "MED"
    return "LOW"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def upsert_predictions(df: pd.DataFrame) -> None:
    """Save scored predictions to the Predictions table.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain: symbol, date, quantum_score, prob_hit_10d,
        conviction_level, components.
    """
    if df.empty:
        return

    with session_scope() as session:
        for _, row in df.iterrows():
            existing = (
                session.query(Predictions)
                .filter_by(symbol=row["symbol"], date=row["date"])
                .first()
            )
            if existing:
                existing.quantum_score = int(row["quantum_score"])
                existing.prob_hit_10d = float(row["prob_hit_10d"])
                existing.conviction_level = row["conviction_level"]
                existing.components = row.get("components")
            else:
                pred = Predictions(
                    symbol=row["symbol"],
                    date=row["date"],
                    quantum_score=int(row["quantum_score"]),
                    prob_hit_10d=float(row["prob_hit_10d"]),
                    conviction_level=row["conviction_level"],
                    components=row.get("components"),
                )
                session.add(pred)

    logger.info("Upserted %d predictions", len(df))


def save_model(model_dict: Dict, filepath: str) -> None:
    """Persist a trained model to disk via pickle.

    Parameters
    ----------
    model_dict : dict
        Output from :func:`train_model`.
    filepath : str
        Destination path (e.g. ``models/ridge_stock_v1.pkl``).
    """
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(model_dict, f, protocol=pickle.HIGHEST_PROTOCOL)
    logger.info("Model saved to %s", filepath)


def load_model(filepath: Optional[str] = None) -> Dict:
    """Load a previously saved model from disk.

    Parameters
    ----------
    filepath : str or None
        Path to the pickled model dict.  If ``None``, attempts to find the
        most recent model in the ``models/`` directory.

    Returns
    -------
    dict
        The model dict (same structure as :func:`train_model` output).

    Raises
    ------
    FileNotFoundError
        If no model file is found.
    """
    if filepath is None:
        # Auto-discover most recent model file
        models_dir = Path("models")
        if models_dir.exists():
            pkl_files = sorted(models_dir.glob("*.pkl"), key=lambda p: p.stat().st_mtime, reverse=True)
            if pkl_files:
                filepath = str(pkl_files[0])
                logger.info("Auto-discovered model: %s", filepath)
            else:
                raise FileNotFoundError("No model files found in models/ directory")
        else:
            raise FileNotFoundError("models/ directory does not exist")

    with open(filepath, "rb") as f:
        model_dict = pickle.load(f)
    logger.info(
        "Model loaded from %s (%d features, %d samples)",
        filepath,
        len(model_dict.get("features", [])),
        model_dict.get("n_samples", 0),
    )
    return model_dict


# ---------------------------------------------------------------------------
# End-to-end workflow
# ---------------------------------------------------------------------------

def train_and_score(
    symbols: List[str],
    asset_type: str = "stock",
) -> Optional[pd.DataFrame]:
    """Train a model and immediately score the given symbols.

    Parameters
    ----------
    symbols : list[str]
        Symbols to train on and score.
    asset_type : str
        ``'stock'`` or ``'crypto'``.

    Returns
    -------
    pd.DataFrame or None
        Scored predictions, or ``None`` if training failed.
    """
    model_dict = train_model(symbols=symbols, asset_type=asset_type)
    if model_dict is None:
        return None

    df = score_symbols(symbols, model_dict, asset_type=asset_type)
    if not df.empty:
        upsert_predictions(df)

    return df
