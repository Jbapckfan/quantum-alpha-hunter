"""
Event labeling - identify explosions and create training labels
This tells the model what a multi-bagger looks like
"""
import pandas as pd
import numpy as np
from typing import Optional
import logging

from ..db import session_scope
from ..schemas import PriceOHLC, Labels
from ..config import get_config
from sqlalchemy import select

logger = logging.getLogger("qaht.backtest.labeler")
config = get_config()


def label_explosions(symbol: str, horizon: int = 10, threshold: Optional[float] = None):
    """
    Label explosive moves in historical data

    Args:
        symbol: Ticker symbol
        horizon: Forward-looking window (days)
        threshold: Return threshold for explosion (None = use config)
    """
    with session_scope() as session:
        # Get price data
        prices = session.execute(
            select(PriceOHLC)
            .where(PriceOHLC.symbol == symbol)
            .order_by(PriceOHLC.date)
        ).scalars().all()

        if len(prices) < horizon + 10:
            logger.warning(f"Insufficient data for labeling {symbol}")
            return

        # Convert to DataFrame
        df = pd.DataFrame([{
            'date': p.date,
            'close': p.close,
            'asset_type': p.asset_type
        } for p in prices])

        df = df.sort_values('date').reset_index(drop=True)

        # Determine threshold based on asset type
        if threshold is None:
            if df['asset_type'].iloc[0] == 'crypto':
                threshold = config.backtest.explosion_threshold_crypto  # 30%
            else:
                threshold = config.backtest.explosion_threshold_equity  # 50%

        # Calculate forward returns
        df['fwd_ret_10d'] = (df['close'].shift(-horizon) / df['close']) - 1
        df['fwd_ret_30d'] = (df['close'].shift(-30) / df['close']) - 1

        # Mark explosions
        df['explosive_10d'] = df['fwd_ret_10d'] >= threshold

        # Calculate lead time (days until explosion)
        df['lead_time_days'] = None

        for idx in df[df['explosive_10d']].index:
            # Find when the price actually moved
            if idx + horizon < len(df):
                prices_forward = df['close'].iloc[idx:idx+horizon+1].values
                entry_price = prices_forward[0]

                for day, price in enumerate(prices_forward[1:], 1):
                    if (price / entry_price - 1) >= threshold:
                        df.loc[idx, 'lead_time_days'] = day
                        break

        # Upsert labels
        inserted = 0
        updated = 0

        for _, row in df.iterrows():
            if pd.isna(row['fwd_ret_10d']):
                continue

            existing = session.get(Labels, (symbol, row['date']))

            if existing:
                existing.fwd_ret_10d = float(row['fwd_ret_10d'])
                existing.fwd_ret_30d = float(row['fwd_ret_30d']) if pd.notna(row['fwd_ret_30d']) else None
                existing.explosive_10d = bool(row['explosive_10d'])
                existing.lead_time_days = int(row['lead_time_days']) if pd.notna(row['lead_time_days']) else None
                updated += 1
            else:
                label = Labels(
                    symbol=symbol,
                    date=row['date'],
                    fwd_ret_10d=float(row['fwd_ret_10d']),
                    fwd_ret_30d=float(row['fwd_ret_30d']) if pd.notna(row['fwd_ret_30d']) else None,
                    explosive_10d=bool(row['explosive_10d']),
                    lead_time_days=int(row['lead_time_days']) if pd.notna(row['lead_time_days']) else None
                )
                session.add(label)
                inserted += 1

        explosions = df['explosive_10d'].sum()
        logger.info(f"Labeled {symbol}: {explosions} explosions found ({inserted} inserted, {updated} updated)")


def label_triple_barrier(symbol: str, upper_mult: float = 2.0, lower_mult: float = 1.0, time_limit: int = 10):
    """
    Triple-barrier method for labeling
    More nuanced than simple explosion labels

    Args:
        symbol: Ticker symbol
        upper_mult: Upper barrier (ATR multiplier)
        lower_mult: Lower barrier (ATR multiplier)
        time_limit: Max days to hit barrier
    """
    with session_scope() as session:
        prices = session.execute(
            select(PriceOHLC)
            .where(PriceOHLC.symbol == symbol)
            .order_by(PriceOHLC.date)
        ).scalars().all()

        if len(prices) < 50:
            return

        df = pd.DataFrame([{
            'date': p.date,
            'close': p.close,
            'high': p.high,
            'low': p.low
        } for p in prices])

        # Calculate ATR
        df['tr'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift(1)),
                abs(df['low'] - df['close'].shift(1))
            )
        )
        df['atr'] = df['tr'].rolling(window=14).mean()

        results = []

        for idx in range(len(df) - time_limit):
            entry_price = df['close'].iloc[idx]
            atr = df['atr'].iloc[idx]

            if pd.isna(atr) or atr == 0:
                continue

            upper_barrier = entry_price + (upper_mult * atr)
            lower_barrier = entry_price - (lower_mult * atr)

            # Check forward prices
            label = 0  # 0 = time stop
            time_to_hit = time_limit

            for day in range(1, time_limit + 1):
                if idx + day >= len(df):
                    break

                future_high = df['high'].iloc[idx + day]
                future_low = df['low'].iloc[idx + day]

                if future_high >= upper_barrier:
                    label = 1  # Upper barrier hit
                    time_to_hit = day
                    break
                elif future_low <= lower_barrier:
                    label = -1  # Lower barrier hit
                    time_to_hit = day
                    break

            results.append({
                'date': df['date'].iloc[idx],
                'tb_label': label,
                'tb_time': time_to_hit
            })

        # Update labels table
        for result in results:
            existing = session.get(Labels, (symbol, result['date']))

            if existing:
                existing.tb_label = result['tb_label']
                existing.tb_time = result['tb_time']
            else:
                label = Labels(
                    symbol=symbol,
                    date=result['date'],
                    fwd_ret_10d=None,
                    explosive_10d=False,
                    tb_label=result['tb_label'],
                    tb_time=result['tb_time']
                )
                session.add(label)

        logger.info(f"Triple-barrier labeled {len(results)} events for {symbol}")


def get_explosion_stats(symbols: Optional[list] = None):
    """
    Get statistics on historical explosions

    Args:
        symbols: List of symbols to analyze (None = all)

    Returns:
        DataFrame with explosion statistics
    """
    with session_scope() as session:
        query = select(Labels).where(Labels.explosive_10d == True)

        if symbols:
            query = query.where(Labels.symbol.in_(symbols))

        explosions = session.execute(query).scalars().all()

        if not explosions:
            logger.info("No explosions found")
            return pd.DataFrame()

        df = pd.DataFrame([{
            'symbol': e.symbol,
            'date': e.date,
            'return_10d': e.fwd_ret_10d,
            'return_30d': e.fwd_ret_30d,
            'lead_time_days': e.lead_time_days
        } for e in explosions])

        stats = df.groupby('symbol').agg({
            'return_10d': ['count', 'mean', 'max'],
            'lead_time_days': 'mean'
        }).round(2)

        logger.info(f"\nExplosion stats:\n{stats}")

        return df
