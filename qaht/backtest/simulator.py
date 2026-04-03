"""Walk-forward backtesting engine without lookahead bias."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
import yfinance as yf

from qaht.backtest.metrics import BacktestMetrics
from qaht.db import init_db, session_scope
from qaht.schemas import BacktestRun
from qaht.scoring.empirical_combos import EmpiricalScorer
from qaht.signals.detector import StockSignalDetector

logger = logging.getLogger("qaht.backtest.simulator")


@dataclass
class SimulatedTrade:
    """Completed trade summary."""

    ticker: str
    sector: str
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    return_pct: float
    days_held: int
    combo_used: Optional[str]
    exit_reason: str
    size_pct: float
    pnl: float
    score: float


@dataclass
class OpenPosition:
    """Internal position state with partial exits."""

    ticker: str
    sector: str
    entry_date: str
    entry_price: float
    size_pct: float
    score: float
    combo_used: Optional[str]
    initial_shares: float
    remaining_shares: float
    stop_price: float
    t1_price: float
    t2_price: float
    t3_price: float
    realized_cash: float = 0.0
    sold_shares: float = 0.0
    targets_hit: set[str] = field(default_factory=set)


class BacktestSimulator:
    """Daily walk-forward simulator using the stock detector plus empirical combos."""

    def __init__(self, score_threshold: int = 70) -> None:
        init_db()
        self.score_threshold = score_threshold
        self.detector = StockSignalDetector()
        self.empirical = EmpiricalScorer()

    def run(
        self,
        tickers: List[str],
        start_date: str,
        end_date: str,
        initial_capital: float = 100000.0,
    ) -> Dict[str, Any]:
        """Run a no-lookahead walk-forward simulation."""
        tickers = [ticker.upper() for ticker in tickers]
        histories = self._fetch_histories(tickers, start_date, end_date)
        if not histories:
            raise ValueError("No historical data available for requested tickers")

        trading_days = self._build_calendar(histories, start_date, end_date)
        if not trading_days:
            raise ValueError("No trading days found in requested window")

        sector_map = self._fetch_sectors(tickers)
        cash = float(initial_capital)
        open_positions: Dict[str, OpenPosition] = {}
        trades: List[Dict[str, Any]] = []
        equity_curve: List[Dict[str, Any]] = []

        for current_dt in trading_days:
            current_date = current_dt.date().isoformat()

            for ticker, position in list(open_positions.items()):
                bar = self._bar_on_or_before(histories[ticker], current_dt)
                if bar is None:
                    continue
                closed = self._process_exits(position, bar, current_date)
                if closed is not None:
                    cash += closed["cash_delta"]
                    trades.append(closed["trade"])
                    open_positions.pop(ticker, None)

            portfolio_value = cash + self._positions_value(open_positions, histories, current_dt)
            exposure_ratio = self._positions_value(open_positions, histories, current_dt) / portfolio_value if portfolio_value > 0 else 0.0

            if exposure_ratio < 0.30:
                candidates = self._entry_candidates(histories, current_dt)
                for candidate in candidates:
                    ticker = candidate["ticker"]
                    if ticker in open_positions:
                        continue

                    sector = sector_map.get(ticker, "Unknown")
                    sector_count = sum(1 for pos in open_positions.values() if pos.sector == sector)
                    if sector_count >= 3:
                        continue

                    portfolio_value = cash + self._positions_value(open_positions, histories, current_dt)
                    if portfolio_value <= 0:
                        break
                    current_exposure = self._positions_value(open_positions, histories, current_dt) / portfolio_value
                    remaining_capacity = max(0.0, 0.30 - current_exposure)
                    if remaining_capacity <= 0:
                        break

                    weight = min(candidate["weight"], remaining_capacity, 0.30)
                    allocation = min(cash, portfolio_value * weight)
                    if allocation <= 0:
                        continue

                    price = float(candidate["price"])
                    shares = allocation / price if price > 0 else 0.0
                    if shares <= 0:
                        continue

                    cash -= allocation
                    open_positions[ticker] = OpenPosition(
                        ticker=ticker,
                        sector=sector,
                        entry_date=current_date,
                        entry_price=price,
                        size_pct=weight,
                        score=float(candidate["score"]),
                        combo_used=candidate["combo_used"],
                        initial_shares=shares,
                        remaining_shares=shares,
                        stop_price=float(candidate["stop"]),
                        t1_price=float(candidate["t1"]),
                        t2_price=float(candidate["t2"]),
                        t3_price=float(candidate["t3"]),
                    )

            equity_curve.append(
                {
                    "date": current_date,
                    "cash": round(cash, 4),
                    "positions_value": round(self._positions_value(open_positions, histories, current_dt), 4),
                    "equity": round(cash + self._positions_value(open_positions, histories, current_dt), 4),
                    "open_positions": len(open_positions),
                }
            )

        final_dt = trading_days[-1]
        final_date = final_dt.date().isoformat()
        for ticker, position in list(open_positions.items()):
            bar = self._bar_on_or_before(histories[ticker], final_dt)
            if bar is None:
                continue
            closed = self._close_position(position, float(bar["Close"]), final_date, "end_of_test")
            cash += closed["cash_delta"]
            trades.append(closed["trade"])
            open_positions.pop(ticker, None)

        metrics = BacktestMetrics.compute(equity_curve=equity_curve, trades=trades).to_dict()
        payload = {
            "tickers": tickers,
            "start_date": start_date,
            "end_date": end_date,
            "initial_capital": initial_capital,
            "metrics": metrics,
            "equity_curve": equity_curve,
            "trades": trades,
        }
        payload["run_id"] = self._store_run(payload)
        return payload

    def _fetch_histories(self, tickers: List[str], start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
        warmup_start = (pd.Timestamp(start_date) - timedelta(days=400)).date().isoformat()
        end_plus_one = (pd.Timestamp(end_date) + timedelta(days=1)).date().isoformat()
        histories: Dict[str, pd.DataFrame] = {}

        for ticker in tickers:
            history = yf.Ticker(ticker).history(start=warmup_start, end=end_plus_one, interval="1d")
            if history.empty:
                logger.warning("No history returned for %s", ticker)
                continue
            columns = [col for col in ("Open", "High", "Low", "Close", "Volume") if col in history.columns]
            history = history[columns].dropna(how="any")
            if isinstance(history.index, pd.DatetimeIndex) and history.index.tz is not None:
                history.index = history.index.tz_convert(None)
            histories[ticker] = history

        return histories

    def _build_calendar(self, histories: Dict[str, pd.DataFrame], start_date: str, end_date: str) -> List[pd.Timestamp]:
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
        all_days = set()
        for history in histories.values():
            for idx in history.index:
                ts = pd.Timestamp(idx)
                if start <= ts <= end:
                    all_days.add(ts)
        return sorted(all_days)

    def _fetch_sectors(self, tickers: List[str]) -> Dict[str, str]:
        sectors: Dict[str, str] = {}
        for ticker in tickers:
            try:
                sectors[ticker] = str((yf.Ticker(ticker).info or {}).get("sector", "Unknown"))
            except Exception:
                sectors[ticker] = "Unknown"
        return sectors

    def _entry_candidates(self, histories: Dict[str, pd.DataFrame], current_dt: pd.Timestamp) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for ticker, history in histories.items():
            available = history[history.index <= current_dt]
            if len(available) < 60:
                continue

            scan = self.detector.scan(
                ticker,
                data=available,
                info={},
                timeframe="1d",
                include_multiframe=False,
                apply_earnings=False,
            )
            if scan is None or float(scan.get("score", 0.0)) < self.score_threshold:
                continue

            empirical = self.empirical.score_symbol(
                symbol=ticker,
                df=available.rename(columns=str.lower),
                quantum_score=int(scan["score"]),
                entry_price=float(scan["price"]),
                max_drawdown_60d=self._max_drawdown(available, 60),
                max_drawdown_20d=self._max_drawdown(available, 20),
            )
            if not empirical.matched_combos:
                continue

            weight = empirical.kelly.clamped_size if empirical.kelly else 0.05
            rows.append(
                {
                    "ticker": ticker,
                    "price": float(scan["price"]),
                    "score": float(scan["score"]),
                    "stop": float(scan["stop"]),
                    "t1": float(scan["t1"]),
                    "t2": float(scan["t2"]),
                    "t3": float(scan["t3"]),
                    "weight": float(weight),
                    "combo_used": empirical.matched_combos[0].name,
                }
            )

        rows.sort(key=lambda row: row["score"], reverse=True)
        return rows

    def _process_exits(self, position: OpenPosition, bar: pd.Series, current_date: str) -> Optional[Dict[str, Any]]:
        low = float(bar["Low"])
        high = float(bar["High"])

        if low <= position.stop_price:
            return self._close_position(position, position.stop_price, current_date, "stop")

        for label, target_price, fraction in (
            ("T1", position.t1_price, 0.25),
            ("T2", position.t2_price, 0.25),
            ("T3", position.t3_price, 1.0),
        ):
            if label in position.targets_hit:
                continue
            if high < target_price:
                continue

            shares_to_sell = position.remaining_shares if fraction >= 1.0 else position.remaining_shares * fraction
            proceeds = shares_to_sell * target_price
            position.realized_cash += proceeds
            position.remaining_shares -= shares_to_sell
            position.sold_shares += shares_to_sell
            position.targets_hit.add(label)

            if label == "T3" or position.remaining_shares <= 1e-8:
                return self._close_position(position, target_price, current_date, label.lower(), already_booked=True)

        return None

    def _close_position(
        self,
        position: OpenPosition,
        exit_price: float,
        exit_date: str,
        exit_reason: str,
        already_booked: bool = False,
    ) -> Dict[str, Any]:
        if not already_booked and position.remaining_shares > 0:
            proceeds = position.remaining_shares * exit_price
            position.realized_cash += proceeds
            position.sold_shares += position.remaining_shares
            position.remaining_shares = 0.0

        invested = position.initial_shares * position.entry_price
        pnl = position.realized_cash - invested
        avg_exit = position.realized_cash / position.initial_shares if position.initial_shares else exit_price
        trade = SimulatedTrade(
            ticker=position.ticker,
            sector=position.sector,
            entry_date=position.entry_date,
            entry_price=round(position.entry_price, 4),
            exit_date=exit_date,
            exit_price=round(avg_exit, 4),
            return_pct=round(position.realized_cash / invested - 1.0, 4) if invested else 0.0,
            days_held=max(0, (pd.Timestamp(exit_date) - pd.Timestamp(position.entry_date)).days),
            combo_used=position.combo_used,
            exit_reason=exit_reason,
            size_pct=round(position.size_pct, 4),
            pnl=round(pnl, 4),
            score=round(position.score, 2),
        )
        return {"cash_delta": position.realized_cash, "trade": asdict(trade)}

    def _positions_value(
        self,
        positions: Dict[str, OpenPosition],
        histories: Dict[str, pd.DataFrame],
        current_dt: pd.Timestamp,
    ) -> float:
        total = 0.0
        for ticker, position in positions.items():
            bar = self._bar_on_or_before(histories[ticker], current_dt)
            if bar is None:
                continue
            total += position.remaining_shares * float(bar["Close"])
        return total

    def _bar_on_or_before(self, history: pd.DataFrame, current_dt: pd.Timestamp) -> Optional[pd.Series]:
        subset = history[history.index <= current_dt]
        if subset.empty:
            return None
        return subset.iloc[-1]

    def _max_drawdown(self, history: pd.DataFrame, window: int) -> float:
        recent = history.tail(window)
        if recent.empty:
            return 0.0
        peak = float(recent["High"].max())
        trough = float(recent["Low"].min())
        if peak <= 0:
            return 0.0
        return max(0.0, (peak - trough) / peak)

    def _store_run(self, payload: Dict[str, Any]) -> int:
        with session_scope() as session:
            run = BacktestRun(
                created_at=pd.Timestamp.utcnow().isoformat(),
                start_date=payload["start_date"],
                end_date=payload["end_date"],
                initial_capital=float(payload["initial_capital"]),
                tickers=payload["tickers"],
                metrics=payload["metrics"],
                equity_curve=payload["equity_curve"],
                trades=payload["trades"],
            )
            session.add(run)
            session.flush()
            return int(run.id)
