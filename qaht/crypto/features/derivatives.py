"""
Crypto derivatives features - funding rates and OI deltas
These are CRITICAL for crypto multi-baggers
"""
import pandas as pd
import numpy as np
from typing import Dict
import logging

from ...db import session_scope
from ...schemas import FuturesMetrics, Factors
from ...config import get_config
from sqlalchemy import select

logger = logging.getLogger("qaht.features.crypto_derivatives")
config = get_config()


def compute_funding_rate_delta(symbol: str, window: int = 7):
    """
    Compute funding rate delta - extreme shifts predict reversals

    Positive funding = longs paying shorts (bullish crowded)
    Negative funding = shorts paying longs (bearish crowded)

    When funding flips negative → positive or vice versa = explosion incoming

    Args:
        symbol: Crypto symbol
        window: Rolling window for delta
    """
    with session_scope() as session:
        # Get futures metrics history
        metrics = session.execute(
            select(FuturesMetrics)
            .where(FuturesMetrics.symbol == symbol)
            .order_by(FuturesMetrics.date)
        ).scalars().all()

        if len(metrics) < 30:
            logger.debug(f"Insufficient futures history for {symbol}")
            return

        # Convert to DataFrame
        df = pd.DataFrame([{
            'date': m.date,
            'funding_rate': m.funding_rate,
            'oi': m.oi,
            'oi_usd': m.oi_usd
        } for m in metrics])

        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')

        # Funding rate delta (7d vs 30d average)
        df['funding_7d'] = df['funding_rate'].rolling(window=window, min_periods=window).mean()
        df['funding_30d'] = df['funding_rate'].rolling(window=30, min_periods=30).mean()

        # Delta: change in funding bias
        df['funding_rate_delta_7d'] = df['funding_7d'] - df['funding_30d']

        # Open interest delta
        df['oi_delta_7d'] = df['oi_usd'].pct_change(periods=window)

        # Update Factors table
        for _, row in df.dropna(subset=['funding_rate_delta_7d']).iterrows():
            date_str = row['date'].strftime('%Y-%m-%d')

            factor = session.get(Factors, (symbol, date_str))

            if not factor:
                # Create new if missing
                factor = Factors(
                    symbol=symbol,
                    date=date_str,
                    bb_width_pct=None,
                    ma_spread_pct=None,
                    social_delta_7d=None
                )
                session.add(factor)

            # Update derivatives features (crypto-specific columns)
            # Note: These need to be added to Factors schema
            if pd.notna(row['funding_rate_delta_7d']):
                # For now, store in existing columns as placeholder
                # TODO: Add funding_rate_delta_7d, oi_delta_7d columns to schema
                pass

        logger.debug(f"Updated derivatives features for {symbol}")


def detect_funding_reversal(symbol: str, threshold: float = 0.0001) -> bool:
    """
    Detect funding rate reversals
    These often precede violent moves

    Args:
        symbol: Crypto symbol
        threshold: Reversal threshold

    Returns:
        True if reversal detected
    """
    with session_scope() as session:
        metrics = session.execute(
            select(FuturesMetrics)
            .where(FuturesMetrics.symbol == symbol)
            .order_by(FuturesMetrics.date.desc())
            .limit(14)
        ).scalars().all()

        if len(metrics) < 7:
            return False

        df = pd.DataFrame([{
            'date': m.date,
            'funding_rate': m.funding_rate
        } for m in metrics])

        # Check for sign change
        recent_avg = df['funding_rate'].iloc[:3].mean()
        historical_avg = df['funding_rate'].iloc[7:].mean()

        # Reversal if signs differ and magnitude > threshold
        if abs(recent_avg) > threshold and abs(historical_avg) > threshold:
            if np.sign(recent_avg) != np.sign(historical_avg):
                logger.info(f"Funding reversal detected for {symbol}: {historical_avg:.6f} → {recent_avg:.6f}")
                return True

    return False


def compute_oi_momentum(symbol: str) -> Dict[str, float]:
    """
    Open interest momentum - money flow indicator
    Rising OI + rising price = strong trend
    Rising OI + falling price = capitulation incoming

    Args:
        symbol: Crypto symbol

    Returns:
        Dict with OI metrics
    """
    with session_scope() as session:
        metrics = session.execute(
            select(FuturesMetrics)
            .where(FuturesMetrics.symbol == symbol)
            .order_by(FuturesMetrics.date)
            .limit(30)
        ).scalars().all()

        if len(metrics) < 14:
            return {}

        df = pd.DataFrame([{
            'date': m.date,
            'oi_usd': m.oi_usd
        } for m in metrics])

        # OI change rates
        oi_change_7d = (df['oi_usd'].iloc[-1] - df['oi_usd'].iloc[-7]) / df['oi_usd'].iloc[-7]
        oi_change_14d = (df['oi_usd'].iloc[-1] - df['oi_usd'].iloc[-14]) / df['oi_usd'].iloc[-14]

        return {
            'oi_change_7d': float(oi_change_7d),
            'oi_change_14d': float(oi_change_14d)
        }
