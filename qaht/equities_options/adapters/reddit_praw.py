"""
Reddit sentiment adapter using PRAW
Tracks mentions and engagement across finance subreddits
"""
import praw
import pandas as pd
from typing import List, Dict, Set
from datetime import datetime, timedelta
from collections import defaultdict
import logging
import os

from ...db import session_scope
from ...schemas import SocialMentions
from ...utils.retry import retry_with_backoff
from ...config import get_config

logger = logging.getLogger("qaht.adapters.reddit")
config = get_config()

# Subreddits to monitor
EQUITY_SUBREDDITS = [
    'wallstreetbets',
    'stocks',
    'investing',
    'StockMarket',
    'pennystocks',
    'Shortsqueeze',
    'smallstreetbets'
]

CRYPTO_SUBREDDITS = [
    'CryptoCurrency',
    'CryptoMarkets',
    'CryptoMoonShots',
    'SatoshiStreetBets'
]


def get_reddit_client() -> praw.Reddit:
    """
    Initialize Reddit API client

    Returns:
        Authenticated PRAW Reddit instance
    """
    client_id = config.reddit_client_id
    client_secret = config.reddit_client_secret
    user_agent = config.reddit_user_agent

    if not client_id or not client_secret:
        raise ValueError("Reddit API credentials not configured. Set in .env file.")

    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent
    )

    logger.info(f"Reddit client initialized: read_only={reddit.read_only}")
    return reddit


@retry_with_backoff(max_retries=2, initial_delay=3.0)
def search_symbol_mentions(
    reddit: praw.Reddit,
    symbol: str,
    subreddits: List[str],
    time_filter: str = "day",
    limit: int = 100
) -> Dict:
    """
    Search for symbol mentions across subreddits

    Args:
        reddit: PRAW Reddit instance
        symbol: Stock or crypto symbol
        subreddits: List of subreddit names
        time_filter: 'hour', 'day', 'week', 'month', 'year'
        limit: Max results per subreddit

    Returns:
        Dict with mention count, authors, engagement data
    """
    mentions = []
    authors = set()
    total_comments = 0
    total_score = 0

    # Search patterns
    search_queries = [f"${symbol}", f"#{symbol}", symbol]

    for sub_name in subreddits:
        try:
            subreddit = reddit.subreddit(sub_name)

            for query in search_queries:
                for submission in subreddit.search(query, time_filter=time_filter, limit=limit):
                    mentions.append({
                        'title': submission.title,
                        'author': str(submission.author) if submission.author else '[deleted]',
                        'score': submission.score,
                        'num_comments': submission.num_comments,
                        'created_utc': submission.created_utc
                    })

                    if submission.author:
                        authors.add(str(submission.author))

                    total_comments += submission.num_comments
                    total_score += submission.score

        except Exception as e:
            logger.warning(f"Error searching {sub_name} for {symbol}: {e}")

    # Calculate metrics
    mention_count = len(mentions)
    author_diversity = len(authors)  # More unique authors = more organic
    engagement_ratio = total_comments / max(1, mention_count)  # Comments per post

    return {
        'mention_count': mention_count,
        'author_diversity': author_diversity,
        'engagement_ratio': engagement_ratio,
        'total_score': total_score,
        'authors': authors
    }


def fetch_reddit_mentions(symbols: List[str], asset_type: str = 'stock') -> pd.DataFrame:
    """
    Fetch Reddit mentions for multiple symbols

    Args:
        symbols: List of symbols to track
        asset_type: 'stock' or 'crypto'

    Returns:
        DataFrame with social mention data
    """
    reddit = get_reddit_client()

    subreddits = EQUITY_SUBREDDITS if asset_type == 'stock' else CRYPTO_SUBREDDITS
    today = datetime.now().strftime('%Y-%m-%d')

    results = []

    for symbol in symbols:
        try:
            data = search_symbol_mentions(reddit, symbol, subreddits, time_filter="day", limit=50)

            results.append({
                'symbol': symbol.upper(),
                'date': today,
                'reddit_count': data['mention_count'],
                'author_entropy': data['author_diversity'],  # Higher = more diverse
                'engagement_ratio': data['engagement_ratio']
            })

            logger.info(f"{symbol}: {data['mention_count']} mentions, {data['author_diversity']} unique authors")

        except Exception as e:
            logger.error(f"Failed to fetch Reddit data for {symbol}: {e}")

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results)
    logger.info(f"Fetched Reddit mentions for {len(results)} symbols")

    return df


def upsert_social_mentions(df: pd.DataFrame):
    """
    Insert or update social mentions in database

    Args:
        df: DataFrame with social mention data
    """
    if df.empty:
        logger.warning("Empty DataFrame passed to upsert_social_mentions")
        return

    with session_scope() as session:
        inserted = 0
        updated = 0

        for _, row in df.iterrows():
            existing = session.get(SocialMentions, (row['symbol'], row['date']))

            if existing:
                existing.reddit_count = int(row['reddit_count'])
                existing.author_entropy = float(row['author_entropy'])
                existing.engagement_ratio = float(row['engagement_ratio'])
                updated += 1
            else:
                mention = SocialMentions(
                    symbol=row['symbol'],
                    date=row['date'],
                    reddit_count=int(row['reddit_count']),
                    twitter_count=0,  # Placeholder for Twitter integration
                    author_entropy=float(row['author_entropy']),
                    engagement_ratio=float(row['engagement_ratio'])
                )
                session.add(mention)
                inserted += 1

        logger.info(f"Upserted social mentions: {inserted} inserted, {updated} updated")


def fetch_and_upsert_reddit(symbols: List[str], asset_type: str = 'stock'):
    """
    Convenience function: fetch and upsert Reddit mentions

    Args:
        symbols: List of symbols
        asset_type: 'stock' or 'crypto'
    """
    df = fetch_reddit_mentions(symbols, asset_type)
    if not df.empty:
        upsert_social_mentions(df)
        return len(df)
    return 0
