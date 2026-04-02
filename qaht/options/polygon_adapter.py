"""
Polygon.io market data adapter for options and equity snapshots.

Async adapter using httpx for all Polygon REST endpoints needed by the
options module: ticker snapshots, daily aggregates, and options chain
snapshots.  Designed to work both standalone (``MARKET_API_KEY`` env var)
and when wired into the broader QAH pipeline.
"""
from __future__ import annotations

import os
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import httpx
import pandas as pd

logger = logging.getLogger("qaht.options.polygon")

_DEFAULT_BASE = "https://api.polygon.io"
_HTTP_TIMEOUT = 10.0


class PolygonAPIError(Exception):
    """Raised when Polygon returns a non-OK response or upstream error."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")


class PolygonAdapter:
    """Polygon.io market data adapter.

    Parameters
    ----------
    api_key : str, optional
        Polygon API key.  Falls back to the ``MARKET_API_KEY`` environment
        variable when not supplied.
    base_url : str, optional
        Override the Polygon REST base URL (useful for proxy / Massive API
        setups).
    timeout : float, optional
        HTTP request timeout in seconds.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = _HTTP_TIMEOUT,
    ):
        self.api_key = (api_key or os.environ.get("MARKET_API_KEY", "")).strip()
        if not self.api_key:
            raise RuntimeError(
                "Polygon API key required.  Set MARKET_API_KEY env var or "
                "pass api_key= to PolygonAdapter."
            )
        self.base_url = (
            base_url or os.environ.get("MARKET_API_BASE", _DEFAULT_BASE)
        ).rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute an authenticated GET and return decoded JSON.

        Raises :class:`PolygonAPIError` on non-200 status or Polygon-level
        error payloads.
        """
        params = dict(params or {})
        params["apiKey"] = self.api_key

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url, params=params)

        if resp.status_code != 200:
            raise PolygonAPIError(
                status_code=resp.status_code,
                detail=f"Upstream error {resp.status_code}: {resp.text[:300]}",
            )

        data = resp.json()

        # Polygon wraps some errors inside a 200 response.
        if "status" in data and data["status"] not in ("OK", "ok", "success"):
            if "error" in data:
                raise PolygonAPIError(status_code=502, detail=data["error"])

        return data

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_snapshot(self, ticker: str) -> dict:
        """Fetch a single-ticker equity snapshot.

        Uses ``/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}``.

        Returns the raw ``ticker`` object from the Polygon response which
        contains ``lastTrade``, ``day``, ``prevDay``, ``min`` sub-dicts.
        """
        url = f"{self.base_url}/v2/snapshot/locale/us/markets/stocks/tickers/{ticker.upper()}"
        data = await self._get(url, {})

        t = data.get("ticker") or {}
        last_trade = t.get("lastTrade") or {}
        prev_day = t.get("prevDay") or {}
        day_bar = t.get("day") or {}

        price = float(
            last_trade.get("p")
            or day_bar.get("c")
            or prev_day.get("c")
            or 0.0
        )
        if price <= 0:
            raise PolygonAPIError(
                status_code=502,
                detail=f"Invalid price from snapshot for {ticker}",
            )

        return {
            "price": round(price, 2),
            "prev_close": round(float(prev_day.get("c") or 0.0), 2),
            "open": round(float(day_bar.get("o") or price), 2),
            "high": float(day_bar.get("h") or 0.0),
            "low": float(day_bar.get("l") or 0.0),
            "vwap": float(day_bar.get("vwap") or t.get("min", {}).get("vwap") or 0.0),
            "volume": float(day_bar.get("v") or 0.0),
            "raw": t,
        }

    async def get_daily_bars(
        self, ticker: str, days: int = 60
    ) -> pd.DataFrame:
        """Fetch adjusted daily OHLCV bars for *ticker*.

        Uses ``/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}``.

        Returns a DataFrame with columns
        ``[date, open, high, low, close, volume, vwap]`` sorted by date
        ascending.  Empty DataFrame on no data.
        """
        end = date.today()
        start = end - timedelta(days=days)
        url = (
            f"{self.base_url}/v2/aggs/ticker/{ticker.upper()}"
            f"/range/1/day/{start.isoformat()}/{end.isoformat()}"
        )
        data = await self._get(url, {"adjusted": "true", "sort": "asc", "limit": "50000"})
        results = data.get("results") or []

        if not results:
            logger.warning("No daily bars returned for %s", ticker)
            return pd.DataFrame()

        rows = []
        for r in results:
            rows.append(
                {
                    "date": pd.Timestamp(r["t"], unit="ms").strftime("%Y-%m-%d"),
                    "open": r.get("o"),
                    "high": r.get("h"),
                    "low": r.get("l"),
                    "close": r.get("c"),
                    "volume": r.get("v"),
                    "vwap": r.get("vw"),
                }
            )

        df = pd.DataFrame(rows)
        logger.info("Fetched %d daily bars for %s", len(df), ticker)
        return df

    async def get_options_chain(self, underlying: str) -> list[dict]:
        """Fetch the full options chain snapshot for *underlying*.

        Uses ``/v3/snapshot/options/{underlyingAsset}`` with pagination.

        Each returned dict contains::

            {
                "contract_type": "call" | "put",
                "strike": float,
                "expiration": "YYYY-MM-DD",
                "dte": int,
                "bid": float | None,
                "ask": float | None,
                "mid": float | None,
                "iv": float | None,
                "delta": float | None,
                "gamma": float | None,
                "vega": float | None,
                "theta": float | None,
                "open_interest": int | None,
                "volume": int | None,
                "underlying_price": float | None,
            }
        """
        url = f"{self.base_url}/v3/snapshot/options/{underlying.upper()}"
        data = await self._get(url, {"limit": "1000"})

        results = data.get("results") or []
        if not isinstance(results, list):
            raise PolygonAPIError(
                status_code=502,
                detail="Unexpected options snapshot format",
            )

        options: List[dict] = []
        underlying_price: Optional[float] = None
        today = date.today()

        for item in results:
            details = item.get("details") or {}
            day = item.get("day") or {}
            last_quote = item.get("last_quote") or item.get("lastQuote") or {}
            greeks = item.get("greeks") or {}

            contract_type = details.get("contract_type")
            strike = details.get("strike_price")
            expiration_str = details.get("expiration_date")

            if contract_type not in ("call", "put") or strike is None or not expiration_str:
                continue

            try:
                exp_date = date.fromisoformat(expiration_str)
            except (ValueError, TypeError):
                continue

            dte = (exp_date - today).days

            bid = last_quote.get("bid")
            ask = last_quote.get("ask")
            mid: Optional[float] = None
            if bid is not None and ask is not None and bid >= 0 and ask >= 0:
                mid = round((bid + ask) / 2.0, 4)
            elif "close" in day:
                mid = day["close"]

            iv = greeks.get("implied_volatility") or greeks.get("iv")
            oi = item.get("open_interest") or item.get("openInterest")

            # Try to capture underlying price
            raw_underlying = item.get("underlying_asset") or item.get("underlying") or {}
            if not underlying_price and isinstance(raw_underlying, dict):
                up = raw_underlying.get("price") or raw_underlying.get("last_price")
                if up:
                    underlying_price = float(up)

            options.append(
                {
                    "contract_type": contract_type.lower(),
                    "strike": float(strike),
                    "expiration": expiration_str,
                    "dte": dte,
                    "bid": float(bid) if bid is not None else None,
                    "ask": float(ask) if ask is not None else None,
                    "mid": float(mid) if mid is not None else None,
                    "iv": float(iv) if iv is not None else None,
                    "delta": _safe_float(greeks.get("delta")),
                    "gamma": _safe_float(greeks.get("gamma")),
                    "vega": _safe_float(greeks.get("vega")),
                    "theta": _safe_float(greeks.get("theta")),
                    "open_interest": int(oi) if oi is not None else None,
                    "volume": _safe_int(day.get("volume") or day.get("v")),
                    "underlying_price": underlying_price,
                }
            )

        logger.info(
            "Fetched %d option contracts for %s (underlying ~%s)",
            len(options),
            underlying,
            underlying_price,
        )
        return options


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _safe_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(val: Any) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None
