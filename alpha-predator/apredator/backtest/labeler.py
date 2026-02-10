"""
Event labeling - identify explosions and create training labels.
Adapted from QAHT backtest/labeler.py for the Alpha Predator system.
"""
import pandas as pd
import numpy as np
from typing import Optional, List
import logging

from sqlalchemy import select

from ..db import session_scope
from ..schemas import PriceOHLC, Labels
from ..config import get_config

logger = logging.getLogger("apredator.backtest.labeler")
config = get_config()


def label_explosions(
    symbol: str,
    horizon: int = 10,
    threshold: Optional[float] = None,
) -> None:
    """
    Label explosive moves in historical price data.

    Queries PriceOHLC from the database, computes forward returns at multiple
    horizons, marks explosive events, and upserts results into the Labels table.

    Args:
        symbol: Ticker symbol (e.g. "AAPL" or "BTC-USD").
        horizon: Forward-looking window in trading days for the primary
                 explosion label (default 10).
        threshold: Minimum forward return to qualify as explosive.
                   If *None*, the config defaults are used:
                   0.50 for stocks, 0.30 for crypto.
    """
    with session_scope() as session:
        # Fetch price data sorted by date
        prices = session.execute(
            select(PriceOHLC)
            .where(PriceOHLC.symbol == symbol)
            .order_by(PriceOHLC.date)
        ).scalars().all()

        if len(prices) < horizon + 10:
            logger.warning(
                f"Insufficient data for labeling {symbol} "
                f"({len(prices)} bars, need >= {horizon + 10})"
            )
            return

        # Build a lightweight DataFrame
        df = pd.DataFrame([
            {
                "date": p.date,
                "close": p.close,
                "high": p.high,
                "asset_type": p.asset_type,
            }
            for p in prices
        ])
        df = df.sort_values("date").reset_index(drop=True)

        # Determine threshold based on asset type when not specified
        if threshold is None:
            if df["asset_type"].iloc[0] == "crypto":
                threshold = config.backtest.explosion_threshold_crypto  # 0.30
            else:
                threshold = config.backtest.explosion_threshold_equity  # 0.50

        # -----------------------------------------------------------------
        # Forward return calculations
        # -----------------------------------------------------------------
        df["fwd_ret_10d"] = (df["close"].shift(-horizon) / df["close"]) - 1
        df["fwd_ret_30d"] = (df["close"].shift(-30) / df["close"]) - 1

        # Maximum price in the next 60 trading days relative to entry close
        df["fwd_max_60d"] = (
            df["high"]
            .shift(-1)
            .rolling(window=60, min_periods=1)
            .max()
            .shift(-59)  # align: window starts at +1, ends at +60
            / df["close"]
            - 1
        )
        # For rows near the end we cannot compute a proper 60-day window,
        # so use a simpler expanding approach for partial windows.
        for idx in range(max(0, len(df) - 60), len(df)):
            future_highs = df["high"].iloc[idx + 1 : idx + 61]
            if len(future_highs) == 0:
                df.loc[idx, "fwd_max_60d"] = np.nan
            else:
                df.loc[idx, "fwd_max_60d"] = future_highs.max() / df["close"].iloc[idx] - 1

        # Mark explosive moves
        df["explosive_10d"] = df["fwd_ret_10d"] >= threshold

        # -----------------------------------------------------------------
        # Lead-time: first day the threshold was reached
        # -----------------------------------------------------------------
        df["lead_time_days"] = np.nan

        for idx in df[df["explosive_10d"]].index:
            if idx + horizon >= len(df):
                continue
            prices_forward = df["close"].iloc[idx : idx + horizon + 1].values
            entry_price = prices_forward[0]
            for day, price in enumerate(prices_forward[1:], 1):
                if (price / entry_price - 1) >= threshold:
                    df.at[idx, "lead_time_days"] = day
                    break

        # -----------------------------------------------------------------
        # Upsert into Labels table
        # -----------------------------------------------------------------
        inserted = 0
        updated = 0

        for _, row in df.iterrows():
            if pd.isna(row["fwd_ret_10d"]):
                continue

            existing = session.get(Labels, (symbol, row["date"]))

            fwd_30 = float(row["fwd_ret_30d"]) if pd.notna(row["fwd_ret_30d"]) else None
            fwd_max = float(row["fwd_max_60d"]) if pd.notna(row["fwd_max_60d"]) else None
            lead = int(row["lead_time_days"]) if pd.notna(row["lead_time_days"]) else None

            if existing:
                existing.fwd_ret_10d = float(row["fwd_ret_10d"])
                existing.fwd_ret_30d = fwd_30
                existing.fwd_max_60d = fwd_max
                existing.explosive_10d = bool(row["explosive_10d"])
                existing.lead_time_days = lead
                updated += 1
            else:
                label = Labels(
                    symbol=symbol,
                    date=row["date"],
                    fwd_ret_10d=float(row["fwd_ret_10d"]),
                    fwd_ret_30d=fwd_30,
                    fwd_max_60d=fwd_max,
                    explosive_10d=bool(row["explosive_10d"]),
                    lead_time_days=lead,
                )
                session.add(label)
                inserted += 1

        explosions = int(df["explosive_10d"].sum())
        logger.info(
            f"Labeled {symbol}: {explosions} explosions found "
            f"({inserted} inserted, {updated} updated)"
        )


def label_triple_barrier(
    symbol: str,
    upper_mult: float = 2.0,
    lower_mult: float = 1.0,
    time_limit: int = 10,
) -> None:
    """
    Triple-barrier labeling method.

    For each bar the method sets an upper profit barrier and a lower stop
    barrier (both expressed as multiples of ATR(14)), then walks forward
    up to *time_limit* days to see which barrier is hit first.

    Labels:
        +1  upper barrier hit first (winner)
        -1  lower barrier hit first (loser)
         0  neither barrier hit within *time_limit* (time-expired)

    Results are upserted into the ``tb_label`` and ``tb_time`` columns of the
    Labels table.

    Args:
        symbol: Ticker symbol.
        upper_mult: Upper barrier as a multiple of ATR.
        lower_mult: Lower barrier as a multiple of ATR.
        time_limit: Maximum days to wait for a barrier hit.
    """
    with session_scope() as session:
        prices = session.execute(
            select(PriceOHLC)
            .where(PriceOHLC.symbol == symbol)
            .order_by(PriceOHLC.date)
        ).scalars().all()

        if len(prices) < 50:
            logger.warning(
                f"Insufficient data for triple-barrier labeling {symbol} "
                f"({len(prices)} bars, need >= 50)"
            )
            return

        df = pd.DataFrame([
            {
                "date": p.date,
                "close": p.close,
                "high": p.high,
                "low": p.low,
            }
            for p in prices
        ])
        df = df.sort_values("date").reset_index(drop=True)

        # ATR(14) calculation
        df["tr"] = np.maximum(
            df["high"] - df["low"],
            np.maximum(
                abs(df["high"] - df["close"].shift(1)),
                abs(df["low"] - df["close"].shift(1)),
            ),
        )
        df["atr"] = df["tr"].rolling(window=14).mean()

        results = []

        for idx in range(len(df) - time_limit):
            entry_price = df["close"].iloc[idx]
            atr = df["atr"].iloc[idx]

            if pd.isna(atr) or atr == 0:
                continue

            upper_barrier = entry_price + (upper_mult * atr)
            lower_barrier = entry_price - (lower_mult * atr)

            label = 0  # default: time expired
            time_to_hit = time_limit

            for day in range(1, time_limit + 1):
                if idx + day >= len(df):
                    break

                future_high = df["high"].iloc[idx + day]
                future_low = df["low"].iloc[idx + day]

                if future_high >= upper_barrier:
                    label = 1
                    time_to_hit = day
                    break
                elif future_low <= lower_barrier:
                    label = -1
                    time_to_hit = day
                    break

            results.append(
                {
                    "date": df["date"].iloc[idx],
                    "tb_label": label,
                    "tb_time": time_to_hit,
                }
            )

        # Upsert into Labels
        for result in results:
            existing = session.get(Labels, (symbol, result["date"]))

            if existing:
                existing.tb_label = result["tb_label"]
                existing.tb_time = result["tb_time"]
            else:
                label_row = Labels(
                    symbol=symbol,
                    date=result["date"],
                    fwd_ret_10d=None,
                    explosive_10d=False,
                    tb_label=result["tb_label"],
                    tb_time=result["tb_time"],
                )
                session.add(label_row)

        logger.info(
            f"Triple-barrier labeled {len(results)} events for {symbol}"
        )


def get_explosion_stats(symbols: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Retrieve statistics on historical explosive moves.

    Args:
        symbols: List of symbols to analyse.  ``None`` returns all.

    Returns:
        DataFrame with explosion counts and average returns per symbol.
    """
    with session_scope() as session:
        query = select(Labels).where(Labels.explosive_10d == True)  # noqa: E712

        if symbols:
            query = query.where(Labels.symbol.in_(symbols))

        explosions = session.execute(query).scalars().all()

        if not explosions:
            logger.info("No explosions found in the database")
            return pd.DataFrame()

        df = pd.DataFrame([
            {
                "symbol": e.symbol,
                "date": e.date,
                "return_10d": e.fwd_ret_10d,
                "return_30d": e.fwd_ret_30d,
                "max_gain_60d": e.fwd_max_60d,
                "lead_time_days": e.lead_time_days,
            }
            for e in explosions
        ])

        stats = df.groupby("symbol").agg(
            explosion_count=("return_10d", "count"),
            avg_return_10d=("return_10d", "mean"),
            avg_return_30d=("return_30d", "mean"),
            avg_max_gain_60d=("max_gain_60d", "mean"),
            max_return_10d=("return_10d", "max"),
            avg_lead_time=("lead_time_days", "mean"),
        ).round(4)

        logger.info(f"Explosion stats across {len(stats)} symbols:\n{stats}")

        return stats
