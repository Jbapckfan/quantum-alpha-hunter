"""
Social feature engineering - delta tracking and quality metrics
The key is RATE OF CHANGE, not absolute levels
"""
import pandas as pd
import numpy as np
from typing import Optional
import logging

from ...db import session_scope
from ...schemas import SocialMentions, Factors
from ...config import get_config
from sqlalchemy import select

logger = logging.getLogger("qaht.features.social")
config = get_config()


def compute_social_delta(symbol: str, window: int = 7):
    """
    Compute social attention delta (7-day vs 30-day average)

    CRITICAL INSIGHT: Volume delta > 5x = explosion incoming
    GME went from 100 daily mentions → 5000+ in 3 days

    Args:
        symbol: Ticker symbol
        window: Rolling window for delta calculation
    """
    with session_scope() as session:
        # Get all social mention history
        mentions = session.execute(
            select(SocialMentions)
            .where(SocialMentions.symbol == symbol)
            .order_by(SocialMentions.date)
        ).scalars().all()

        if len(mentions) < 30:  # Need 30 days for baseline
            logger.debug(f"Insufficient social history for {symbol}: {len(mentions)} days")
            return

        # Convert to DataFrame
        df = pd.DataFrame([{
            'date': m.date,
            'reddit_count': m.reddit_count,
            'twitter_count': m.twitter_count,
            'author_entropy': m.author_entropy,
            'engagement_ratio': m.engagement_ratio
        } for m in mentions])

        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')

        # Total mentions
        df['total_mentions'] = df['reddit_count'] + df['twitter_count']

        # Rolling averages
        df['mentions_7d'] = df['total_mentions'].rolling(window=window, min_periods=window).mean()
        df['mentions_30d'] = df['total_mentions'].rolling(window=30, min_periods=30).mean()

        # Delta calculation
        df['social_delta_7d'] = (
            (df['mentions_7d'] - df['mentions_30d']) / df['mentions_30d'].replace(0, 1)
        )

        # Author entropy delta (more unique voices = organic growth)
        df['author_entropy_7d'] = df['author_entropy'].rolling(window=window, min_periods=window).mean()

        # Engagement quality
        df['engagement_ratio_7d'] = df['engagement_ratio'].rolling(window=window, min_periods=window).mean()

        # Update Factors table
        for _, row in df.dropna(subset=['social_delta_7d']).iterrows():
            date_str = row['date'].strftime('%Y-%m-%d')

            # CRITICAL FIX: Use tuple for composite PK
            factor = session.get(Factors, (symbol, date_str))

            if not factor:
                # Create new factor row if it doesn't exist (happens if social data comes before price)
                factor = Factors(
                    symbol=symbol,
                    date=date_str,
                    bb_width_pct=None,
                    ma_spread_pct=None,
                    social_delta_7d=float(row['social_delta_7d']),
                    author_entropy_7d=float(row['author_entropy_7d']) if pd.notna(row['author_entropy_7d']) else None,
                    engagement_ratio_7d=float(row['engagement_ratio_7d']) if pd.notna(row['engagement_ratio_7d']) else None
                )
                session.add(factor)
            else:
                # Update existing
                factor.social_delta_7d = float(row['social_delta_7d'])
                if pd.notna(row['author_entropy_7d']):
                    factor.author_entropy_7d = float(row['author_entropy_7d'])
                if pd.notna(row['engagement_ratio_7d']):
                    factor.engagement_ratio_7d = float(row['engagement_ratio_7d'])

        logger.debug(f"Updated social deltas for {symbol}")


def detect_sustained_attention(symbol: str, threshold_sigma: float = 1.0) -> bool:
    """
    Detect if social attention is sustained (3+ days above baseline)
    Sustained attention > spike = real signal

    Args:
        symbol: Ticker symbol
        threshold_sigma: Standard deviations above mean

    Returns:
        True if sustained attention detected
    """
    with session_scope() as session:
        mentions = session.execute(
            select(SocialMentions)
            .where(SocialMentions.symbol == symbol)
            .order_by(SocialMentions.date.desc())
            .limit(30)
        ).scalars().all()

        if len(mentions) < 7:
            return False

        df = pd.DataFrame([{
            'date': m.date,
            'reddit_count': m.reddit_count,
            'twitter_count': m.twitter_count
        } for m in mentions])

        df['total_mentions'] = df['reddit_count'] + df['twitter_count']

        # Calculate baseline (exclude last 7 days)
        baseline_mean = df['total_mentions'].iloc[7:].mean()
        baseline_std = df['total_mentions'].iloc[7:].std()

        if baseline_std == 0:
            return False

        # Check last 3 days
        recent_mentions = df['total_mentions'].iloc[:3]
        threshold = baseline_mean + (threshold_sigma * baseline_std)

        sustained = (recent_mentions > threshold).sum() >= 3

        if sustained:
            logger.info(f"Sustained attention detected for {symbol}")

        return sustained


def compute_social_quality_score(symbol: str) -> Optional[float]:
    """
    Quality score: author diversity + engagement ratio
    High quality = diverse authors + high engagement

    Args:
        symbol: Ticker symbol

    Returns:
        Quality score 0-1 (higher = better)
    """
    with session_scope() as session:
        latest = session.execute(
            select(SocialMentions)
            .where(SocialMentions.symbol == symbol)
            .order_by(SocialMentions.date.desc())
            .limit(1)
        ).scalar_one_or_none()

        if not latest:
            return None

        # Normalize metrics (rough heuristics)
        author_score = min(latest.author_entropy / 50.0, 1.0) if latest.author_entropy else 0
        engagement_score = min(latest.engagement_ratio / 10.0, 1.0) if latest.engagement_ratio else 0

        quality = (author_score + engagement_score) / 2

        return float(quality)
