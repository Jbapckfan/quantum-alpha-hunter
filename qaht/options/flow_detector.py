"""Unusual options activity detection."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from .chain import ParsedChain, fetch_and_parse
from .polygon_adapter import PolygonAdapter

logger = logging.getLogger("qaht.options.flow")


@dataclass
class FlowContract:
    """Ranked unusual contract details."""

    contract_type: str
    strike: float
    expiration: str
    dte: int
    mid_price: float
    volume: int
    open_interest: int
    vol_oi_ratio: float
    dollar_volume: float
    iv_percentile: float
    otm_pct: float
    score: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FlowAlert:
    """Ticker-level unusual flow summary."""

    ticker: str
    direction: str
    score: int
    top_contracts: List[Dict[str, Any]]
    total_dollar_volume: float
    dominant_expiry: Optional[str]
    iv_skew_anomaly: bool
    block_trades: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FlowDetector:
    """Detect unusual options flow from Polygon chain snapshots."""

    _SKEW_CACHE: Dict[str, tuple[datetime, float]] = {}

    def __init__(self, adapter: Optional[PolygonAdapter] = None) -> None:
        self.adapter = adapter or PolygonAdapter()

    async def scan_unusual_activity(
        self,
        tickers: List[str],
        min_score: int = 3,
    ) -> List[FlowAlert]:
        """Scan a ticker set and return ranked unusual-flow alerts."""
        tasks = [self._scan_ticker(ticker.upper(), min_score=min_score) for ticker in tickers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        alerts: List[FlowAlert] = []

        for ticker, result in zip(tickers, results, strict=False):
            if isinstance(result, Exception):
                logger.warning("Flow scan failed for %s: %s", ticker, result)
                continue
            if result is not None:
                alerts.append(result)

        alerts.sort(key=lambda alert: (alert.score, alert.total_dollar_volume), reverse=True)
        return alerts

    async def detect_iv_skew_anomaly(
        self,
        ticker: str,
        chain: Optional[ParsedChain] = None,
    ) -> bool:
        """Flag large changes in 25-delta skew versus the prior cached reading."""
        chain = chain or await fetch_and_parse(self.adapter, ticker.upper())
        put_leg = self._nearest_delta(chain, option_type="put", target_delta=0.25)
        call_leg = self._nearest_delta(chain, option_type="call", target_delta=0.25)
        if put_leg is None or call_leg is None or put_leg.iv is None or call_leg.iv is None:
            return False

        current_skew = float(put_leg.iv - call_leg.iv)
        now = datetime.utcnow()
        previous = self._SKEW_CACHE.get(chain.underlying)
        self._SKEW_CACHE[chain.underlying] = (now, current_skew)
        if previous is None:
            return False

        _, prior_skew = previous
        return abs(current_skew - prior_skew) > 0.05

    async def detect_block_trades(
        self,
        ticker: str,
        chain: Optional[ParsedChain] = None,
    ) -> List[Dict[str, Any]]:
        """Flag contracts trading at 10x the chain's average volume."""
        chain = chain or await fetch_and_parse(self.adapter, ticker.upper())
        volumes = [int(leg.volume or 0) for leg in chain.legs if (leg.volume or 0) > 0]
        average_volume = sum(volumes) / len(volumes) if volumes else 0.0
        if average_volume <= 0:
            return []

        blocks: List[Dict[str, Any]] = []
        for leg in chain.legs:
            volume = int(leg.volume or 0)
            if volume > average_volume * 10:
                blocks.append(
                    {
                        "contract_type": leg.contract_type,
                        "strike": leg.strike,
                        "expiration": leg.expiration,
                        "volume": volume,
                        "avg_chain_volume": round(average_volume, 2),
                    }
                )
        return blocks

    async def _scan_ticker(self, ticker: str, min_score: int) -> Optional[FlowAlert]:
        chain = await fetch_and_parse(self.adapter, ticker)
        if not chain.legs:
            return None

        iv_values = [float(leg.iv) for leg in chain.legs if leg.iv is not None and leg.iv > 0]
        scored_contracts: List[FlowContract] = []
        call_dollar_volume = 0.0
        put_dollar_volume = 0.0
        expiry_buckets: Dict[str, float] = {}

        for leg in chain.legs:
            summary = self._score_contract(chain, leg, iv_values)
            if summary.score <= 0:
                continue
            scored_contracts.append(summary)
            expiry_buckets[summary.expiration] = expiry_buckets.get(summary.expiration, 0.0) + summary.dollar_volume
            if summary.contract_type == "call":
                call_dollar_volume += summary.dollar_volume
            else:
                put_dollar_volume += summary.dollar_volume

        if not scored_contracts:
            return None

        scored_contracts.sort(key=lambda contract: (contract.score, contract.dollar_volume), reverse=True)
        top_contracts = scored_contracts[:3]
        total_score = sum(contract.score for contract in top_contracts)
        if total_score < min_score:
            return None

        iv_skew_anomaly = await self.detect_iv_skew_anomaly(ticker, chain=chain)
        block_trades = await self.detect_block_trades(ticker, chain=chain)
        if iv_skew_anomaly:
            total_score += 1
        if block_trades:
            total_score += 1

        direction = "bullish" if call_dollar_volume >= put_dollar_volume else "bearish"
        dominant_expiry = max(expiry_buckets.items(), key=lambda item: item[1])[0] if expiry_buckets else None

        return FlowAlert(
            ticker=ticker,
            direction=direction,
            score=total_score,
            top_contracts=[contract.to_dict() for contract in top_contracts],
            total_dollar_volume=round(call_dollar_volume + put_dollar_volume, 2),
            dominant_expiry=dominant_expiry,
            iv_skew_anomaly=iv_skew_anomaly,
            block_trades=block_trades,
        )

    @staticmethod
    def _score_contract(chain: ParsedChain, leg: Any, iv_values: List[float]) -> FlowContract:
        volume = int(leg.volume or 0)
        open_interest = int(leg.open_interest or 0)
        mid_price = float(leg.mid or 0.0)
        dollar_volume = volume * mid_price * 100.0
        vol_oi_ratio = float(volume / open_interest) if open_interest > 0 else float(volume if volume > 0 else 0.0)
        iv = float(leg.iv or 0.0)
        iv_percentile = FlowDetector._percentile(iv, iv_values)
        otm_pct = FlowDetector._otm_pct(
            contract_type=leg.contract_type,
            strike=float(leg.strike),
            underlying_price=float(chain.underlying_price or 0.0),
        )

        score = 0
        if vol_oi_ratio > 5:
            score += 3
        if dollar_volume > 1_000_000:
            score += 2
        elif dollar_volume > 500_000:
            score += 1
        if iv_percentile > 80:
            score += 2
        if otm_pct > 15:
            score += 2
        elif otm_pct > 10:
            score += 1
        if int(leg.dte) < 14:
            score += 1

        return FlowContract(
            contract_type=str(leg.contract_type),
            strike=float(leg.strike),
            expiration=str(leg.expiration),
            dte=int(leg.dte),
            mid_price=round(mid_price, 4),
            volume=volume,
            open_interest=open_interest,
            vol_oi_ratio=round(vol_oi_ratio, 4),
            dollar_volume=round(dollar_volume, 2),
            iv_percentile=round(iv_percentile, 2),
            otm_pct=round(otm_pct, 2),
            score=score,
        )

    @staticmethod
    def _nearest_delta(chain: ParsedChain, option_type: str, target_delta: float) -> Any | None:
        candidates = [leg for leg in chain.legs if leg.contract_type == option_type and leg.delta is not None and leg.iv is not None]
        if not candidates:
            return None
        if option_type == "put":
            return min(candidates, key=lambda leg: abs(abs(float(leg.delta)) - target_delta))
        return min(candidates, key=lambda leg: abs(float(leg.delta) - target_delta))

    @staticmethod
    def _otm_pct(contract_type: str, strike: float, underlying_price: float) -> float:
        if underlying_price <= 0:
            return 0.0
        if contract_type == "call":
            return max(0.0, ((strike - underlying_price) / underlying_price) * 100.0)
        return max(0.0, ((underlying_price - strike) / underlying_price) * 100.0)

    @staticmethod
    def _percentile(value: float, values: List[float]) -> float:
        clean_values = sorted(v for v in values if v > 0)
        if not clean_values or value <= 0:
            return 0.0
        below = sum(1 for current in clean_values if current <= value)
        return (below / len(clean_values)) * 100.0
