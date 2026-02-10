"""
Binance futures adapter.
Fetches funding rates, open interest, and other derivatives metrics from
the Binance USDT-M Futures API. Sourced from QAHT futures_binance.py.
"""
import logging
import time
from typing import Dict, List, Optional, Union

import pandas as pd
import requests

from ..config import get_config
from ..db import session_scope
from ..schemas import FuturesMetrics
from ..universe.crypto import BINANCE_FUTURES_MAP
from ..utils.retry import retry_with_backoff

logger = logging.getLogger("apredator.adapters.binance")

BASE_URL = "https://fapi.binance.com"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ticker_to_pair(symbol: str) -> Optional[str]:
    """Map a ticker symbol (e.g. ``BTC``) to the Binance USDT perpetual pair
    (e.g. ``BTCUSDT``).

    Returns ``None`` if the ticker is not in the futures map.
    """
    sym = symbol.strip().upper()
    pair = BINANCE_FUTURES_MAP.get(sym)
    if pair is None:
        # Try constructing it directly
        candidate = f"{sym}USDT"
        logger.debug(f"Ticker {sym} not in BINANCE_FUTURES_MAP, trying {candidate}")
        return candidate
    return pair


# ---------------------------------------------------------------------------
# Funding rate
# ---------------------------------------------------------------------------

@retry_with_backoff(max_retries=3, initial_delay=1.0)
def fetch_funding_rate(symbol: str) -> float:
    """Fetch the current funding rate for a symbol.

    Parameters
    ----------
    symbol : str
        Ticker symbol (e.g. ``"BTC"``, ``"ETH"``).

    Returns
    -------
    float
        The current funding rate (e.g. 0.0001 for 0.01%).
    """
    pair = _ticker_to_pair(symbol)
    if pair is None:
        logger.warning(f"Cannot map {symbol} to Binance futures pair")
        return 0.0

    url = f"{BASE_URL}/fapi/v1/premiumIndex"
    params = {"symbol": pair}

    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    funding_rate = float(data.get("lastFundingRate", 0.0))
    logger.debug(f"Funding rate for {symbol} ({pair}): {funding_rate}")
    return funding_rate


# ---------------------------------------------------------------------------
# Open interest
# ---------------------------------------------------------------------------

@retry_with_backoff(max_retries=3, initial_delay=1.0)
def fetch_open_interest(symbol: str) -> Dict:
    """Fetch the current open interest for a symbol.

    Parameters
    ----------
    symbol : str
        Ticker symbol (e.g. ``"BTC"``).

    Returns
    -------
    dict
        ``{"oi": <float>, "oi_usd": <float>}`` where ``oi`` is the open
        interest in contracts and ``oi_usd`` is the notional value in USD.
    """
    pair = _ticker_to_pair(symbol)
    if pair is None:
        logger.warning(f"Cannot map {symbol} to Binance futures pair")
        return {"oi": 0.0, "oi_usd": 0.0}

    url = f"{BASE_URL}/fapi/v1/openInterest"
    params = {"symbol": pair}

    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    oi = float(data.get("openInterest", 0.0))

    # Fetch mark price to compute USD notional
    oi_usd = 0.0
    try:
        mark_url = f"{BASE_URL}/fapi/v1/premiumIndex"
        mark_resp = requests.get(mark_url, params={"symbol": pair}, timeout=15)
        mark_resp.raise_for_status()
        mark_data = mark_resp.json()
        mark_price = float(mark_data.get("markPrice", 0.0))
        oi_usd = oi * mark_price
    except Exception as exc:
        logger.warning(f"Could not fetch mark price for {pair}: {exc}")

    logger.debug(f"Open interest for {symbol} ({pair}): oi={oi}, oi_usd={oi_usd:.2f}")
    return {"oi": oi, "oi_usd": oi_usd}


# ---------------------------------------------------------------------------
# Batch metrics
# ---------------------------------------------------------------------------

@retry_with_backoff(max_retries=3, initial_delay=1.0)
def fetch_futures_metrics(symbols: Union[str, List[str]]) -> pd.DataFrame:
    """Fetch funding rate and open interest for multiple symbols.

    Parameters
    ----------
    symbols : str or list[str]
        Ticker symbol(s).

    Returns
    -------
    pd.DataFrame
        Columns: ``symbol, funding_rate, oi, oi_usd``.
    """
    config = get_config()

    if isinstance(symbols, str):
        symbols = [symbols]

    rows = []
    for sym in symbols:
        try:
            fr = fetch_funding_rate(sym)
            oi_data = fetch_open_interest(sym)

            rows.append({
                "symbol": sym.upper(),
                "funding_rate": fr,
                "oi": oi_data["oi"],
                "oi_usd": oi_data["oi_usd"],
            })

            # Rate limiting between symbols
            time.sleep(config.api_rate_limit_delay)

        except Exception as exc:
            logger.warning(f"Failed to fetch futures metrics for {sym}: {exc}")

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    logger.info(f"Fetched futures metrics for {len(df)} symbols")
    return df


# ---------------------------------------------------------------------------
# Upsert to DB
# ---------------------------------------------------------------------------

def upsert_futures_metrics(df: pd.DataFrame) -> int:
    """Upsert a DataFrame of futures metrics into the FuturesMetrics table.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain columns: ``symbol, funding_rate, oi, oi_usd``.

    Returns
    -------
    int
        Number of rows upserted.
    """
    if df.empty:
        return 0

    from datetime import date as dt_date

    today = dt_date.today().isoformat()
    count = 0

    with session_scope() as session:
        for _, row in df.iterrows():
            obj = FuturesMetrics(
                symbol=row["symbol"],
                date=today,
                funding_rate=float(row.get("funding_rate", 0.0)),
                oi=float(row.get("oi", 0.0)),
                oi_usd=float(row.get("oi_usd", 0.0)),
                basis_pct=None,
            )
            session.merge(obj)
            count += 1

    logger.info(f"Upserted {count} futures metrics rows")
    return count
