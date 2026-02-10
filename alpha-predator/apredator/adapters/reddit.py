"""
Reddit adapter.
Scrapes mention counts and author diversity for symbols across relevant
subreddits via PRAW. Sourced from QAHT reddit_praw.py.
"""
import logging
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union

import pandas as pd

from ..config import get_config
from ..db import session_scope
from ..schemas import SocialMentions
from ..utils.retry import retry_with_backoff

logger = logging.getLogger("apredator.adapters.reddit")

# ---------------------------------------------------------------------------
# Subreddit lists
# ---------------------------------------------------------------------------

EQUITY_SUBREDDITS = [
    "wallstreetbets",
    "stocks",
    "investing",
    "pennystocks",
    "Shortsqueeze",
]

CRYPTO_SUBREDDITS = [
    "CryptoCurrency",
    "CryptoMarkets",
    "SatoshiStreetBets",
]


# ---------------------------------------------------------------------------
# Client setup
# ---------------------------------------------------------------------------

def get_reddit_client():
    """Create and return a PRAW Reddit client using credentials from config.

    Returns
    -------
    praw.Reddit
        Authenticated Reddit instance.

    Raises
    ------
    ImportError
        If ``praw`` is not installed.
    RuntimeError
        If Reddit credentials are not configured.
    """
    try:
        import praw
    except ImportError:
        raise ImportError(
            "praw is required for Reddit data. Install with: pip install praw"
        )

    config = get_config()

    client_id = config.reddit_client_id
    client_secret = config.reddit_client_secret
    user_agent = config.reddit_user_agent

    if not client_id or not client_secret:
        raise RuntimeError(
            "Reddit credentials not configured. Set REDDIT_CLIENT_ID and "
            "REDDIT_CLIENT_SECRET environment variables."
        )

    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
    )

    logger.info("Reddit client initialized (read-only)")
    return reddit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_author_entropy(authors: List[str]) -> float:
    """Compute Shannon entropy of the author distribution.

    Higher entropy means more diverse set of unique authors (less likely to
    be a single-person pump campaign).

    Parameters
    ----------
    authors : list[str]
        List of author usernames (may contain duplicates).

    Returns
    -------
    float
        Shannon entropy in bits. Returns 0.0 if authors list is empty.
    """
    if not authors:
        return 0.0

    counts = Counter(authors)
    total = len(authors)
    entropy = 0.0

    for count in counts.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log2(p)

    return round(entropy, 4)


# ---------------------------------------------------------------------------
# Mention scraping
# ---------------------------------------------------------------------------

@retry_with_backoff(max_retries=2, initial_delay=3.0)
def fetch_reddit_mentions(
    symbols: Union[str, List[str]],
    asset_type: str = "stock",
    time_filter: str = "week",
    limit: int = 100,
) -> pd.DataFrame:
    """Count mentions of symbols across relevant subreddits.

    Parameters
    ----------
    symbols : str or list[str]
        Ticker symbols to search for.
    asset_type : str
        ``"stock"`` or ``"crypto"`` -- determines which subreddits to scan.
    time_filter : str
        Reddit time filter: ``"day"``, ``"week"``, ``"month"``, ``"year"``.
    limit : int
        Maximum number of submissions to scan per subreddit.

    Returns
    -------
    pd.DataFrame
        Columns: ``symbol, date, reddit_count, author_entropy``.
    """
    if isinstance(symbols, str):
        symbols = [symbols]

    symbols = [s.strip().upper() for s in symbols if s.strip()]
    if not symbols:
        logger.warning("fetch_reddit_mentions called with empty symbol list")
        return pd.DataFrame()

    reddit = get_reddit_client()

    subreddits = EQUITY_SUBREDDITS if asset_type == "stock" else CRYPTO_SUBREDDITS

    # Build regex patterns for each symbol (word boundary matching)
    patterns = {}
    for sym in symbols:
        patterns[sym] = re.compile(rf"\b{re.escape(sym)}\b", re.IGNORECASE)

    # Accumulators
    mention_counts: Dict[str, int] = defaultdict(int)
    mention_authors: Dict[str, List[str]] = defaultdict(list)

    for sub_name in subreddits:
        try:
            subreddit = reddit.subreddit(sub_name)
            submissions = subreddit.top(time_filter=time_filter, limit=limit)

            for submission in submissions:
                title = submission.title or ""
                selftext = submission.selftext or ""
                combined_text = f"{title} {selftext}"
                author = str(submission.author) if submission.author else "unknown"

                for sym, pattern in patterns.items():
                    if pattern.search(combined_text):
                        mention_counts[sym] += 1
                        mention_authors[sym].append(author)

            logger.debug(f"Scanned r/{sub_name}: {limit} submissions")

        except Exception as exc:
            logger.warning(f"Error scanning r/{sub_name}: {exc}")

    # Build result DataFrame
    today = datetime.utcnow().strftime("%Y-%m-%d")
    rows = []

    for sym in symbols:
        count = mention_counts.get(sym, 0)
        authors = mention_authors.get(sym, [])
        entropy = _compute_author_entropy(authors)

        rows.append({
            "symbol": sym,
            "date": today,
            "reddit_count": count,
            "author_entropy": entropy,
        })

    df = pd.DataFrame(rows)
    total_mentions = df["reddit_count"].sum()
    logger.info(
        f"Reddit mentions: {total_mentions} total across {len(symbols)} symbols "
        f"({len(subreddits)} subreddits, time_filter='{time_filter}')"
    )
    return df


# ---------------------------------------------------------------------------
# Upsert to DB
# ---------------------------------------------------------------------------

def upsert_social_mentions(df: pd.DataFrame) -> int:
    """Upsert a DataFrame of Reddit mentions into the SocialMentions table.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain columns: ``symbol, date, reddit_count, author_entropy``.

    Returns
    -------
    int
        Number of rows upserted.
    """
    if df.empty:
        return 0

    count = 0
    with session_scope() as session:
        for _, row in df.iterrows():
            obj = SocialMentions(
                symbol=row["symbol"],
                date=row["date"],
                reddit_count=int(row.get("reddit_count", 0)),
                twitter_count=0,
                author_entropy=float(row["author_entropy"]) if pd.notna(row.get("author_entropy")) else None,
                engagement_ratio=None,
            )
            session.merge(obj)
            count += 1

    logger.info(f"Upserted {count} social mention rows")
    return count
