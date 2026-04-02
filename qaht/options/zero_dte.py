"""
0DTE direction engine -- ported from the SPY Options Engine frontend JS.

Computes call and put scores (0-100) from five weighted signal components,
classifies the intraday regime, and generates play-suggestion text.

Score Components (weighted)
---------------------------
1. **Trend (30 %)** -- price change, VWAP vs price, EMA9 vs EMA21, ES
   lead/lag.
2. **Flow (25 %)** -- CVD trend * strength, call/put flow bias, divergences.
3. **Volatility (20 %)** -- IV/RV ratio, intraday range vs ATR20.
4. **Gamma & Liquidity (15 %)** -- negative/positive gamma regime, liquidity
   weights.
5. **Breadth / Macro (10 %)** -- advance/decline, NYSE tick, VIX change.

Regime classifications
----------------------
``High-Vol Trend`` | ``Low-Vol Range`` | ``Trend-Up Bias``
| ``Trend-Down Bias`` | ``Event Risk Day`` | ``Neutral / Range``
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger("qaht.options.zero_dte")


# ------------------------------------------------------------------
# Snapshot data structure
# ------------------------------------------------------------------

@dataclass
class MarketSnapshot:
    """All inputs required by the 0DTE scoring engine.

    Fields with defaults of ``None`` are optional enrichment data.  The
    scoring engine degrades gracefully when they are absent.
    """

    price: float
    prev_close: float
    open: float = 0.0
    vwap: float = 0.0
    ema9: float = 0.0
    ema21: float = 0.0

    # E-mini S&P 500 futures
    es_price: Optional[float] = None
    es_prev_close: Optional[float] = None

    # Intraday range
    overnight_range_pct: Optional[float] = None
    intraday_range_pct: Optional[float] = None
    atr20: Optional[float] = None

    # Market breadth
    adv_decl_ratio: Optional[float] = None   # 0-1 normalised
    tick: Optional[int] = None               # NYSE tick

    # VIX
    vix: Optional[float] = None
    vix_change: Optional[float] = None

    # Options vol surface
    iv_atm_0dte: Optional[float] = None      # 0DTE ATM implied vol (decimal)
    realized_vol_5d: Optional[float] = None  # 5-day realized vol (decimal)

    # Gamma
    gamma_regime: Optional[str] = None       # "negative", "positive", or None
    gamma_magnitude: Optional[float] = None  # 0-1

    # Liquidity
    liquidity_up: Optional[float] = None     # 0-1
    liquidity_down: Optional[float] = None   # 0-1

    # Cumulative Volume Delta
    cvd_trend: Optional[float] = None        # -1 to +1
    cvd_strength: Optional[float] = None     # 0 to 1
    cvd_divergence_bullish: Optional[bool] = None
    cvd_divergence_bearish: Optional[bool] = None

    # Order flow
    call_flow_bias: Optional[float] = None   # 0-1
    put_flow_bias: Optional[float] = None    # 0-1

    # Calendar
    event_risk: Optional[bool] = None

    # Optional ML model probs (0-1)
    model_call_prob: Optional[float] = None
    model_put_prob: Optional[float] = None
    model_no_trade_prob: Optional[float] = None


# ------------------------------------------------------------------
# Score output
# ------------------------------------------------------------------

@dataclass
class ZeroDTEScores:
    """Output of :func:`compute_scores`."""

    call_score: int                       # 0-100
    put_score: int                        # 0-100
    regime: str
    regime_description: str

    # Sub-component values (0-1 scale)
    trend_up: float = 0.0
    trend_down: float = 0.0
    flow_up: float = 0.0
    flow_down: float = 0.0
    movement_score: float = 0.0
    gamma_up: float = 0.0
    gamma_down: float = 0.0
    macro_up: float = 0.0
    macro_down: float = 0.0

    expected_move_pct: float = 0.0

    no_trade: bool = False
    no_trade_reason: str = ""

    call_label: str = ""
    put_label: str = ""
    call_play: str = ""
    put_play: str = ""
    suggestions: List[str] = field(default_factory=list)


# ------------------------------------------------------------------
# Technical helpers (ported from backend main.py)
# ------------------------------------------------------------------

def ema(series: List[float], period: int) -> Optional[float]:
    """Compute exponential moving average over *series* for given *period*.

    Returns ``None`` if the series is shorter than *period*.
    """
    if len(series) < period:
        return None
    k = 2.0 / (period + 1)
    e = series[0]
    for v in series[1:]:
        e = v * k + e * (1 - k)
    return e


def atr(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 20,
) -> Optional[float]:
    """Average True Range over last *period* bars.

    Requires at least ``period + 1`` bars.
    """
    if len(highs) < period + 1 or len(lows) < period + 1 or len(closes) < period + 1:
        return None
    trs: List[float] = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


def realized_vol(prices: List[float], window: int = 5) -> Optional[float]:
    """Annualised realised volatility from log returns over *window* days."""
    if len(prices) < window + 1:
        return None
    rets = []
    for i in range(-window, 0):
        p0 = prices[i - 1]
        p1 = prices[i]
        if p0 <= 0:
            continue
        rets.append(math.log(p1 / p0))
    if not rets:
        return None
    mean = sum(rets) / len(rets)
    var = sum((x - mean) ** 2 for x in rets) / len(rets)
    return math.sqrt(var) * math.sqrt(252.0)


# ------------------------------------------------------------------
# Core scoring engine
# ------------------------------------------------------------------

def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _norm(value: float, lo: float, hi: float) -> float:
    """Normalise *value* from [lo, hi] into [0, 1]."""
    if hi == lo:
        return 0.5
    return _clamp((value - lo) / (hi - lo))


def compute_scores(s: MarketSnapshot) -> ZeroDTEScores:
    """Run the full 0DTE direction scoring engine.

    Faithfully ports the ``computeScores()`` JS function from the SPY
    Options Engine frontend.
    """
    # Day change percentages
    day_change_pct = ((s.price - s.prev_close) / s.prev_close * 100) if s.prev_close else 0.0

    es_change_pct = 0.0
    if s.es_price is not None and s.es_prev_close is not None and s.es_prev_close > 0:
        es_change_pct = ((s.es_price - s.es_prev_close) / s.es_prev_close * 100)

    above_vwap = s.price > s.vwap if s.vwap else False
    ema_bull = s.ema9 > s.ema21 if (s.ema9 and s.ema21) else False
    ema_bear = s.ema9 < s.ema21 if (s.ema9 and s.ema21) else False

    # ----------------------------------------------------------------
    # 1. Trend (30 %)
    # ----------------------------------------------------------------
    day_up_norm = _norm(day_change_pct, -1, 1)
    es_lead_norm = _norm(es_change_pct, -1, 1)

    trend_up = 0.0
    trend_down = 0.0

    if above_vwap:
        trend_up += 0.25
    if ema_bull:
        trend_up += 0.25
    trend_up += 0.25 * day_up_norm
    trend_up += 0.25 * es_lead_norm

    if not above_vwap:
        trend_down += 0.25
    if ema_bear:
        trend_down += 0.25
    trend_down += 0.25 * (1 - day_up_norm)
    trend_down += 0.25 * (1 - es_lead_norm)

    trend_up = _clamp(trend_up)
    trend_down = _clamp(trend_down)

    # ----------------------------------------------------------------
    # 2. Flow (25 %)
    # ----------------------------------------------------------------
    cvd_trend_val = s.cvd_trend if s.cvd_trend is not None else 0.0
    cvd_strength_val = s.cvd_strength if s.cvd_strength is not None else 0.5

    cvd_bull = _norm(cvd_trend_val, -1, 1) * cvd_strength_val
    cvd_bear = (1 - _norm(cvd_trend_val, -1, 1)) * cvd_strength_val

    flow_up = 0.5 * cvd_bull + 0.5 * (s.call_flow_bias if s.call_flow_bias is not None else 0.5)
    flow_down = 0.5 * cvd_bear + 0.5 * (s.put_flow_bias if s.put_flow_bias is not None else 0.5)

    if s.cvd_divergence_bullish:
        flow_up = _clamp(flow_up + 0.15)
        flow_down = _clamp(flow_down - 0.15)
    if s.cvd_divergence_bearish:
        flow_up = _clamp(flow_up - 0.15)
        flow_down = _clamp(flow_down + 0.15)

    # ----------------------------------------------------------------
    # 3. Volatility / movement (20 %)
    # ----------------------------------------------------------------
    iv = s.iv_atm_0dte if s.iv_atm_0dte is not None else 0.0
    rv = s.realized_vol_5d if s.realized_vol_5d is not None else 0.0
    iv_to_rv = iv / rv if rv > 0 else 1.0
    iv_ratio_score = _clamp(1 - abs(iv_to_rv - 1) / 0.7)

    atr20 = s.atr20 if s.atr20 is not None else 0.0
    intraday_range = s.intraday_range_pct if s.intraday_range_pct is not None else 0.0
    range_rel = intraday_range / atr20 if atr20 > 0 else 0.5
    range_score = _clamp(range_rel, 0, 1.5)

    movement_score = _clamp(0.6 * iv_ratio_score + 0.4 * range_score)

    # ----------------------------------------------------------------
    # 4. Gamma & liquidity (15 %)
    # ----------------------------------------------------------------
    liq_up = s.liquidity_up if s.liquidity_up is not None else 0.5
    liq_down = s.liquidity_down if s.liquidity_down is not None else 0.5
    g_mag = s.gamma_magnitude if s.gamma_magnitude is not None else 0.5

    if s.gamma_regime == "negative":
        gamma_up = 0.5 + 0.25 * liq_up + 0.25 * g_mag
        gamma_down = 0.5 + 0.25 * liq_down + 0.25 * g_mag
    elif s.gamma_regime == "positive":
        gamma_up = 0.5 - 0.3 * g_mag + 0.25 * liq_up
        gamma_down = 0.5 - 0.3 * g_mag + 0.25 * liq_down
    else:
        gamma_up = 0.5 + 0.25 * liq_up
        gamma_down = 0.5 + 0.25 * liq_down

    gamma_up = _clamp(gamma_up)
    gamma_down = _clamp(gamma_down)

    # ----------------------------------------------------------------
    # 5. Breadth / macro (10 %)
    # ----------------------------------------------------------------
    breadth = s.adv_decl_ratio if s.adv_decl_ratio is not None else 0.5
    tick_norm = _norm(s.tick if s.tick is not None else 0, -600, 600)
    vix_trend_norm = _norm(s.vix_change if s.vix_change is not None else 0, -1, 1)

    breadth_up = _clamp(0.6 * breadth + 0.4 * tick_norm)
    breadth_down = 1 - breadth_up

    vix_help_calls = _clamp(1 - vix_trend_norm)
    vix_help_puts = vix_trend_norm

    macro_up = _clamp(0.7 * breadth_up + 0.3 * vix_help_calls)
    macro_down = _clamp(0.7 * breadth_down + 0.3 * vix_help_puts)

    # ----------------------------------------------------------------
    # Composite heuristic scores
    # ----------------------------------------------------------------
    heuristic_call = (
        0.30 * trend_up
        + 0.25 * flow_up
        + 0.20 * movement_score
        + 0.15 * gamma_up
        + 0.10 * macro_up
    )
    heuristic_put = (
        0.30 * trend_down
        + 0.25 * flow_down
        + 0.20 * movement_score
        + 0.15 * gamma_down
        + 0.10 * macro_down
    )

    # Blend with optional ML model probabilities
    ml_call = _clamp(s.model_call_prob) if s.model_call_prob is not None else None
    ml_put = _clamp(s.model_put_prob) if s.model_put_prob is not None else None
    ml_no = _clamp(s.model_no_trade_prob) if s.model_no_trade_prob is not None else None

    call_01 = heuristic_call
    put_01 = heuristic_put

    if ml_call is not None and ml_put is not None and ml_no is not None:
        call_01 = _clamp(0.5 * heuristic_call + 0.5 * ml_call)
        put_01 = _clamp(0.5 * heuristic_put + 0.5 * ml_put)

    call_score = round(call_01 * 100)
    put_score = round(put_01 * 100)

    # ----------------------------------------------------------------
    # Regime classification
    # ----------------------------------------------------------------
    regime = "Neutral / Range"
    regime_desc = "No clear dominant intraday trend yet."

    if movement_score > 0.7 and s.gamma_regime == "negative":
        regime = "High-Vol Trend"
        regime_desc = (
            "Negative gamma & elevated movement potential -- explosive "
            "moves likely."
        )
    elif movement_score < 0.4 and s.gamma_regime == "positive":
        regime = "Low-Vol Range"
        regime_desc = (
            "Positive gamma & muted vol -- mean reversion / chop likely."
        )
    else:
        if trend_up > 0.6:
            regime = "Trend-Up Bias"
            regime_desc = "Price, ES, and EMAs favor upside continuation."
        elif trend_down > 0.6:
            regime = "Trend-Down Bias"
            regime_desc = "Price, ES, and EMAs favor downside continuation."

    if s.event_risk:
        regime = "Event Risk Day"
        regime_desc = (
            "Macro event (CPI/FOMC/etc). Expect fakeouts, volatility "
            "spikes, and regime shifts."
        )

    # ----------------------------------------------------------------
    # No-trade logic
    # ----------------------------------------------------------------
    no_trade = False
    no_trade_reason = ""
    best_score = max(call_score, put_score)

    if ml_no is not None and ml_no > 0.5 and best_score < 65:
        no_trade = True
        no_trade_reason = (
            "Historical outcomes suggest negative expectancy here; sit out."
        )
    elif best_score < 50:
        no_trade = True
        no_trade_reason = (
            "Edge is weak for both calls and puts; risk/reward not compelling."
        )

    # ----------------------------------------------------------------
    # Labels and suggestions
    # ----------------------------------------------------------------
    call_label = _label_from_score(call_score)
    put_label = _label_from_score(put_score)
    call_play = _play_suggestion("call", call_score)
    put_play = _play_suggestion("put", put_score)

    suggestions: List[str] = []
    if no_trade:
        suggestions.append(f"NO TRADE: {no_trade_reason}")
    else:
        if call_score >= 65:
            suggestions.append(call_play)
        if put_score >= 65:
            suggestions.append(put_play)
        if not suggestions:
            suggestions.append(
                "Mixed conditions -- reduce size, tighten stops, or stand aside."
            )

    return ZeroDTEScores(
        call_score=call_score,
        put_score=put_score,
        regime=regime,
        regime_description=regime_desc,
        trend_up=round(trend_up, 3),
        trend_down=round(trend_down, 3),
        flow_up=round(flow_up, 3),
        flow_down=round(flow_down, 3),
        movement_score=round(movement_score, 3),
        gamma_up=round(gamma_up, 3),
        gamma_down=round(gamma_down, 3),
        macro_up=round(macro_up, 3),
        macro_down=round(macro_down, 3),
        expected_move_pct=round(atr20, 2) if atr20 else 1.0,
        no_trade=no_trade,
        no_trade_reason=no_trade_reason,
        call_label=call_label,
        put_label=put_label,
        call_play=call_play,
        put_play=put_play,
        suggestions=suggestions,
    )


# ------------------------------------------------------------------
# Convenience: build snapshot from Polygon adapter data
# ------------------------------------------------------------------

async def build_snapshot_from_polygon(
    adapter,  # PolygonAdapter
    ticker: str = "SPY",
) -> MarketSnapshot:
    """Build a :class:`MarketSnapshot` using live Polygon data.

    Only populates fields that Polygon can supply (price, VWAP, EMAs,
    ATR, intraday range, overnight range).  Fields that require external
    data (breadth, tick, CVD, flow, gamma, VIX) are left as ``None``.
    """
    snap = await adapter.get_snapshot(ticker)
    bars_df = await adapter.get_daily_bars(ticker, days=60)

    vwap = snap.get("vwap", 0.0)
    price = snap["price"]
    prev_close = snap["prev_close"]
    open_price = snap["open"]
    high = snap.get("high", 0.0)
    low = snap.get("low", 0.0)

    ema9_val = None
    ema21_val = None
    atr20_val = None
    intraday_range_pct = None
    overnight_range_pct = None

    if not bars_df.empty:
        closes = bars_df["close"].dropna().tolist()
        highs = bars_df["high"].dropna().tolist()
        lows = bars_df["low"].dropna().tolist()

        ema9_val = ema(closes[-30:], 9) if len(closes) >= 9 else None
        ema21_val = ema(closes[-60:], 21) if len(closes) >= 21 else None
        atr20_val = atr(highs, lows, closes, 20)

    if high > 0 and low > 0 and price > 0:
        intraday_range_pct = (high - low) / price * 100.0

    if prev_close and open_price:
        overnight_range_pct = abs(open_price - prev_close) / prev_close * 100.0

    return MarketSnapshot(
        price=price,
        prev_close=prev_close,
        open=open_price,
        vwap=vwap,
        ema9=round(ema9_val, 2) if ema9_val else 0.0,
        ema21=round(ema21_val, 2) if ema21_val else 0.0,
        intraday_range_pct=round(intraday_range_pct, 2) if intraday_range_pct else None,
        overnight_range_pct=round(overnight_range_pct, 2) if overnight_range_pct else None,
        atr20=round(atr20_val, 2) if atr20_val else None,
    )


# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------

def _label_from_score(score: int) -> str:
    if score >= 80:
        return "High conviction"
    if score >= 65:
        return "Favorable"
    if score >= 50:
        return "Meh / marginal"
    if score >= 35:
        return "Low edge"
    return "Avoid"


def _play_suggestion(side: str, score: int) -> str:
    if side == "call":
        if score >= 80:
            return (
                "Strong long-call environment: focus on 0DTE call scalps in "
                "the direction of trend only (above VWAP, EMA9>EMA21). Enter "
                "on pullbacks into VWAP/EMAs with strong CVD and bullish "
                "order flow."
            )
        if score >= 65:
            return (
                "Upside bias: 0DTE calls are viable on clean pullbacks. "
                "Avoid chasing breakouts; demand trend + flow alignment "
                "before entries."
            )
        if score >= 50:
            return (
                "Mixed conditions: only consider very tight, quick call "
                "scalps at key support levels; no hero holds."
            )
        return (
            "Environment does not favor long calls. Prefer no trade, "
            "spreads, or different product."
        )
    else:
        if score >= 80:
            return (
                "Strong long-put environment: focus on 0DTE put scalps in "
                "the downside trend (below VWAP, EMA9<EMA21). Enter on "
                "bounces into resistance with heavy selling flow and weak "
                "breadth."
            )
        if score >= 65:
            return (
                "Downside bias: 0DTE puts are viable on clean bounces into "
                "resistance. Avoid chasing extended flushes unless volatility "
                "+ gamma strongly support it."
            )
        if score >= 50:
            return (
                "Mixed conditions: only consider very short-duration put "
                "scalps from clear resistance levels."
            )
        return (
            "Environment does not favor long puts. Prefer no trade, "
            "spreads, or different strategy."
        )
