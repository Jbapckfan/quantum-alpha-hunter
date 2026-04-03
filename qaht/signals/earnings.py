"""Earnings calendar context and pre-earnings play detection."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger("qaht.signals.earnings")


@dataclass
class UpcomingEarnings:
    """Upcoming earnings event summary."""

    ticker: str
    earnings_date: str
    days_until: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EarningsContext:
    """Computed earnings context for a ticker."""

    ticker: str
    earnings_date: Optional[str]
    days_until: Optional[int]
    avg_abs_move_pct: Optional[float]
    current_atm_iv: Optional[float]
    historical_pre_earnings_iv: Optional[float]
    iv_expansion: Optional[bool]
    pre_earnings_drift: Optional[float]
    post_earnings_drift: Optional[float]
    iv_implied_move_pct: Optional[float]
    iv_crush_signal: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EarningsAnalyzer:
    """Analyze upcoming and historical earnings behavior."""

    def get_upcoming_earnings(self, tickers: List[str], days_ahead: int = 14) -> List[Dict[str, Any]]:
        """Return upcoming earnings within the requested horizon."""
        rows: List[Dict[str, Any]] = []
        for ticker in tickers:
            try:
                stock = yf.Ticker(ticker.upper())
                earnings_date = self._next_earnings_date(stock)
                if earnings_date is None:
                    continue
                days_until = (earnings_date.date() - date.today()).days
                if 0 <= days_until <= days_ahead:
                    rows.append(
                        UpcomingEarnings(
                            ticker=ticker.upper(),
                            earnings_date=earnings_date.date().isoformat(),
                            days_until=days_until,
                        ).to_dict()
                    )
            except Exception:
                logger.warning("Failed to fetch upcoming earnings for %s", ticker, exc_info=True)
        rows.sort(key=lambda row: (row["days_until"], row["ticker"]))
        return rows

    def compute_earnings_context(self, ticker: str) -> EarningsContext:
        """Compute upcoming earnings context and recent earnings behavior."""
        ticker = ticker.upper()
        stock = yf.Ticker(ticker)
        earnings_date = self._next_earnings_date(stock)
        days_until = (earnings_date.date() - date.today()).days if earnings_date is not None else None
        history = stock.history(period="2y", interval="1d")
        history = history.sort_index()

        historical_dates = self._historical_earnings_dates(stock, limit=4)
        avg_abs_move_pct = self._average_earnings_move(history, historical_dates)
        pre_drift = self._average_drift(history, historical_dates, before=True)
        post_drift = self._average_drift(history, historical_dates, before=False)

        atm_iv = self._current_atm_iv(stock, earnings_date)
        crush = self.estimate_iv_crush(ticker, context_inputs={
            "avg_abs_move_pct": avg_abs_move_pct,
            "current_atm_iv": atm_iv,
            "earnings_date": earnings_date,
            "stock": stock,
        })
        historical_iv_proxy = avg_abs_move_pct / 100.0 if avg_abs_move_pct is not None else None
        iv_expansion = bool(atm_iv is not None and historical_iv_proxy is not None and atm_iv > historical_iv_proxy)

        return EarningsContext(
            ticker=ticker,
            earnings_date=earnings_date.date().isoformat() if earnings_date is not None else None,
            days_until=days_until,
            avg_abs_move_pct=round(avg_abs_move_pct, 4) if avg_abs_move_pct is not None else None,
            current_atm_iv=round(atm_iv, 4) if atm_iv is not None else None,
            historical_pre_earnings_iv=round(historical_iv_proxy, 4) if historical_iv_proxy is not None else None,
            iv_expansion=iv_expansion if atm_iv is not None and historical_iv_proxy is not None else None,
            pre_earnings_drift=round(pre_drift, 4) if pre_drift is not None else None,
            post_earnings_drift=round(post_drift, 4) if post_drift is not None else None,
            iv_implied_move_pct=crush.get("iv_implied_move_pct"),
            iv_crush_signal=crush.get("signal"),
        )

    def flag_earnings_plays(self, scan_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Mutate scan results with earnings catalyst and imminent warning flags."""
        enriched: List[Dict[str, Any]] = []
        for result in scan_results:
            context = self.compute_earnings_context(str(result.get("ticker", "")))
            payload = dict(result)
            payload["earnings_context"] = context.to_dict()
            days_until = context.days_until
            flags = list(payload.get("flags", []))
            breakdown = payload.setdefault("signal_breakdown", {})
            score = float(payload.get("score", 0.0))

            if (
                days_until is not None
                and 5 <= days_until <= 14
                and score > 100
                and payload.get("stage") in {"EARLY", "MID"}
            ):
                payload["score"] = int(round(score + 15))
                breakdown["earnings_catalyst"] = 15
                flags.append("EARNINGS CATALYST")

            if days_until is not None and 0 <= days_until <= 2:
                payload["score"] = int(round(float(payload["score"]) - 5))
                breakdown["earnings_imminent_warning"] = -5
                flags.append("EARNINGS IMMINENT")

            payload["flags"] = list(dict.fromkeys(flags))
            enriched.append(payload)
        return enriched

    def estimate_iv_crush(
        self,
        ticker: str,
        context_inputs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Compare implied move versus historical earnings move."""
        context_inputs = context_inputs or {}
        stock = context_inputs.get("stock") or yf.Ticker(ticker.upper())
        earnings_date = context_inputs.get("earnings_date") or self._next_earnings_date(stock)
        avg_abs_move_pct = context_inputs.get("avg_abs_move_pct")
        if avg_abs_move_pct is None:
            history = stock.history(period="2y", interval="1d")
            avg_abs_move_pct = self._average_earnings_move(history, self._historical_earnings_dates(stock, limit=4))

        current_atm_iv = context_inputs.get("current_atm_iv")
        if current_atm_iv is None:
            current_atm_iv = self._current_atm_iv(stock, earnings_date)

        if current_atm_iv is None or avg_abs_move_pct is None:
            return {"signal": None, "iv_implied_move_pct": None, "historical_move_pct": avg_abs_move_pct}

        expiry_date = self._nearest_expiry_after(stock, earnings_date)
        days_to_expiry = max(1, (expiry_date - date.today()).days) if expiry_date is not None else 7
        iv_implied_move_pct = float(current_atm_iv * ((days_to_expiry / 365.0) ** 0.5) * 100.0)

        if iv_implied_move_pct >= avg_abs_move_pct * 1.5:
            signal = "IV_RICH_AVOID_LONG_OPTIONS"
        elif iv_implied_move_pct <= avg_abs_move_pct * 0.75:
            signal = "IV_CHEAP_BUY_STRADDLES"
        else:
            signal = "IV_FAIR"

        return {
            "signal": signal,
            "iv_implied_move_pct": round(iv_implied_move_pct, 4),
            "historical_move_pct": round(avg_abs_move_pct, 4),
        }

    @staticmethod
    def _next_earnings_date(stock: Any) -> Optional[pd.Timestamp]:
        calendar = getattr(stock, "calendar", None)
        if calendar is None:
            return None

        if isinstance(calendar, pd.DataFrame):
            values = calendar.values.flatten().tolist()
        elif isinstance(calendar, pd.Series):
            values = calendar.tolist()
        elif isinstance(calendar, dict):
            values = list(calendar.values())
        else:
            values = []

        for value in values:
            try:
                timestamp = pd.Timestamp(value)
            except Exception:
                continue
            if pd.isna(timestamp):
                continue
            if timestamp.date() >= date.today():
                return timestamp
        return None

    @staticmethod
    def _historical_earnings_dates(stock: Any, limit: int = 4) -> List[pd.Timestamp]:
        getter = getattr(stock, "get_earnings_dates", None)
        if getter is None:
            return []
        try:
            frame = getter(limit=limit + 4)
        except Exception:
            logger.debug("Failed to fetch historical earnings dates", exc_info=True)
            return []
        if frame is None or getattr(frame, "empty", True):
            return []
        if isinstance(frame.index, pd.DatetimeIndex):
            dates = [ts for ts in frame.index if ts.date() < date.today()]
        else:
            dates = [pd.Timestamp(value) for value in frame.iloc[:, 0].tolist()]
        dates = sorted([ts for ts in dates if ts.date() < date.today()], reverse=True)
        return dates[:limit]

    @staticmethod
    def _average_earnings_move(history: pd.DataFrame, earnings_dates: List[pd.Timestamp]) -> Optional[float]:
        moves: List[float] = []
        for earnings_date in earnings_dates:
            window = history.loc[earnings_date - timedelta(days=3): earnings_date + timedelta(days=3)]
            if len(window) < 2:
                continue
            prev_close = float(window["Close"].iloc[0])
            post_close = float(window["Close"].iloc[-1])
            if prev_close > 0:
                moves.append(abs((post_close / prev_close) - 1.0) * 100.0)
        if not moves:
            return None
        return sum(moves) / len(moves)

    @staticmethod
    def _average_drift(history: pd.DataFrame, earnings_dates: List[pd.Timestamp], before: bool) -> Optional[float]:
        drifts: List[float] = []
        for earnings_date in earnings_dates:
            window = history.loc[earnings_date - timedelta(days=15): earnings_date + timedelta(days=7)]
            if window.empty:
                continue
            if before and len(window) >= 11:
                start_price = float(window["Close"].iloc[0])
                end_price = float(window["Close"].iloc[min(9, len(window) - 1)])
            elif not before and len(window) >= 6:
                start_index = max(0, len(window) - 6)
                start_price = float(window["Close"].iloc[start_index])
                end_price = float(window["Close"].iloc[-1])
            else:
                continue
            if start_price > 0:
                drifts.append((end_price / start_price) - 1.0)
        if not drifts:
            return None
        return sum(drifts) / len(drifts)

    @staticmethod
    def _current_atm_iv(stock: Any, earnings_date: Optional[pd.Timestamp]) -> Optional[float]:
        try:
            expirations = list(getattr(stock, "options", []) or [])
        except Exception:
            return None
        if not expirations:
            return None

        expiry = EarningsAnalyzer._nearest_expiry_from_list(expirations, earnings_date)
        if expiry is None:
            return None

        try:
            chain = stock.option_chain(expiry)
            history = stock.history(period="10d", interval="1d")
        except Exception:
            logger.debug("Failed to fetch option chain for ATM IV", exc_info=True)
            return None
        if history.empty:
            return None

        spot = float(history["Close"].iloc[-1])
        candidates = []
        for frame in [chain.calls, chain.puts]:
            if frame is None or frame.empty or "strike" not in frame or "impliedVolatility" not in frame:
                continue
            temp = frame.copy()
            temp["distance"] = (temp["strike"] - spot).abs()
            candidates.append(temp.sort_values("distance").iloc[0])

        if not candidates:
            return None
        values = [float(row["impliedVolatility"]) for row in candidates if row.get("impliedVolatility") is not None]
        return sum(values) / len(values) if values else None

    @staticmethod
    def _nearest_expiry_after(stock: Any, earnings_date: Optional[pd.Timestamp]) -> Optional[date]:
        try:
            expirations = list(getattr(stock, "options", []) or [])
        except Exception:
            return None
        expiry = EarningsAnalyzer._nearest_expiry_from_list(expirations, earnings_date)
        return date.fromisoformat(expiry) if expiry is not None else None

    @staticmethod
    def _nearest_expiry_from_list(expirations: List[str], earnings_date: Optional[pd.Timestamp]) -> Optional[str]:
        if not expirations:
            return None
        if earnings_date is None:
            return expirations[0]

        target = earnings_date.date()
        for expiry in expirations:
            try:
                expiry_date = date.fromisoformat(expiry)
            except ValueError:
                continue
            if expiry_date >= target:
                return expiry
        return expirations[-1]
