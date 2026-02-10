"""
Social-sentiment features -- mention velocity, author entropy, engagement.
Ported from QAHT features/social.py.
"""
import logging
import math
from collections import Counter
from datetime import datetime, timedelta
from typing import Dict

from ..db import session_scope
from ..schemas import SocialMentions

logger = logging.getLogger("apredator.features.social")


def compute_social_features(
    symbol: str,
    asset_type: str = "stock",
) -> Dict[str, float]:
    """Compute social-sentiment features for *symbol*.

    Queries the ``social_mentions`` table for the last 30 days and derives:

    - **social_delta_7d** -- ratio of 7-day average mentions to 30-day average.
      Values > 1 indicate rising buzz; < 1 indicates fading interest.
    - **author_entropy_7d** -- Shannon entropy of author distribution in the
      last 7 days.  Higher entropy = more organic (many distinct authors).
    - **engagement_ratio_7d** -- average engagement (comments) per post in
      the last 7 days.

    Parameters
    ----------
    symbol : str
        Ticker or token symbol.
    asset_type : str
        ``"stock"`` or ``"crypto"`` (currently unused but reserved for
        platform-specific weighting).

    Returns
    -------
    dict
        Feature dict with keys ``social_delta_7d``, ``author_entropy_7d``,
        ``engagement_ratio_7d``.
    """
    defaults = {
        "social_delta_7d": 0.0,
        "author_entropy_7d": 0.0,
        "engagement_ratio_7d": 0.0,
    }

    try:
        today = datetime.utcnow().date()
        date_30d_ago = (today - timedelta(days=30)).isoformat()
        date_7d_ago = (today - timedelta(days=7)).isoformat()

        with session_scope() as session:
            rows = (
                session.query(SocialMentions)
                .filter(
                    SocialMentions.symbol == symbol.upper(),
                    SocialMentions.date >= date_30d_ago,
                )
                .all()
            )

        if not rows:
            logger.debug("No social data found for %s in last 30 days", symbol)
            return defaults

        # Split into 7-day and 30-day windows
        mentions_30d = []
        mentions_7d = []
        engagement_7d = []

        for row in rows:
            total_mentions = (row.reddit_count or 0) + (row.twitter_count or 0)
            mentions_30d.append(total_mentions)
            if row.date >= date_7d_ago:
                mentions_7d.append(total_mentions)
                if row.engagement_ratio is not None:
                    engagement_7d.append(row.engagement_ratio)

        # --- social_delta_7d ---
        avg_30d = sum(mentions_30d) / len(mentions_30d) if mentions_30d else 0
        avg_7d = sum(mentions_7d) / len(mentions_7d) if mentions_7d else 0
        social_delta = avg_7d / avg_30d if avg_30d > 0 else 0.0

        # --- author_entropy_7d ---
        # Use stored entropy if available, otherwise compute from mention counts
        entropy_values = [
            row.author_entropy
            for row in rows
            if row.date >= date_7d_ago and row.author_entropy is not None
        ]
        if entropy_values:
            author_entropy = sum(entropy_values) / len(entropy_values)
        else:
            # Fallback: estimate entropy from mention distribution across days
            if mentions_7d and sum(mentions_7d) > 0:
                total = sum(mentions_7d)
                author_entropy = _shannon_entropy(
                    [m / total for m in mentions_7d if m > 0]
                )
            else:
                author_entropy = 0.0

        # --- engagement_ratio_7d ---
        engagement_ratio = (
            sum(engagement_7d) / len(engagement_7d) if engagement_7d else 0.0
        )

        return {
            "social_delta_7d": round(social_delta, 4),
            "author_entropy_7d": round(author_entropy, 4),
            "engagement_ratio_7d": round(engagement_ratio, 4),
        }

    except Exception:
        logger.exception("Failed to compute social features for %s", symbol)
        return defaults


def _shannon_entropy(probabilities: list) -> float:
    """Compute Shannon entropy: -sum(p * log2(p)) for *probabilities*."""
    entropy = 0.0
    for p in probabilities:
        if p > 0:
            entropy -= p * math.log2(p)
    return entropy
