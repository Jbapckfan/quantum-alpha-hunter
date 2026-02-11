"""
Options Max Pain and Gamma Exposure (GEX) calculator.

Computes the options max pain price (the strike at which option writers pay
out the least) and net gamma exposure for the nearest expiration.  GEX
polarity determines whether the underlying is likely to mean-revert (positive
gamma, dealer hedging dampens moves) or trend (negative gamma, dealer hedging
amplifies moves).

Dependencies: yfinance, numpy, scipy.
"""

import logging
import math
from datetime import datetime
from typing import Any, Dict, Optional

import numpy as np

logger = logging.getLogger("apredator.features.max_pain")

# ---------------------------------------------------------------------------
# Default / empty return
# ---------------------------------------------------------------------------

_EMPTY: Dict[str, Any] = {
    "max_pain_price": None,
    "max_pain_distance_pct": 0.0,
    "net_gex": 0.0,
    "gex_flip_strike": None,
    "gex_signal": "N/A",
    "expiration_date": None,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_max_pain_gex(
    symbol: str,
    current_price: float,
) -> Dict[str, Any]:
    """Compute options max pain price and net gamma exposure for *symbol*.

    Parameters
    ----------
    symbol : str
        Ticker symbol (e.g. ``"AAPL"``).
    current_price : float
        Current underlying price used for GEX gamma calculations and
        distance-to-max-pain.

    Returns
    -------
    dict
        ``max_pain_price``        -- strike that minimises total option writer
                                     payout (float or None)
        ``max_pain_distance_pct`` -- % distance from *current_price* to max
                                     pain (positive = above, negative = below)
        ``net_gex``               -- net gamma exposure in dollar-gamma terms
        ``gex_flip_strike``       -- strike where cumulative GEX crosses zero
                                     (float or None)
        ``gex_signal``            -- ``"Mean-Reverting"`` (positive GEX) or
                                     ``"Trending"`` (negative GEX)
        ``expiration_date``       -- ISO date string of the nearest expiry used
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance is not installed -- cannot compute max pain / GEX")
        return dict(_EMPTY)

    try:
        ticker = yf.Ticker(symbol)
        expirations = ticker.options
        if not expirations:
            logger.warning("No option expirations found for %s", symbol)
            return dict(_EMPTY)

        # Pick the nearest expiry date -------------------------------------------
        nearest_expiry = _pick_nearest_expiry(expirations)
        if nearest_expiry is None:
            logger.warning("Could not determine nearest expiry for %s", symbol)
            return dict(_EMPTY)

        chain = ticker.option_chain(nearest_expiry)
        calls = chain.calls
        puts = chain.puts

        if calls.empty and puts.empty:
            logger.warning("Empty option chain for %s (%s)", symbol, nearest_expiry)
            return dict(_EMPTY)

        # -----------------------------------------------------------------------
        # Max Pain
        # -----------------------------------------------------------------------
        max_pain_price = _calculate_max_pain(calls, puts)

        if max_pain_price is not None and max_pain_price != 0:
            max_pain_distance_pct = round(
                (current_price - max_pain_price) / max_pain_price * 100, 2
            )
        else:
            max_pain_distance_pct = 0.0

        # -----------------------------------------------------------------------
        # GEX (Gamma Exposure)
        # -----------------------------------------------------------------------
        days_to_expiry = _days_to_expiry(nearest_expiry)
        T = max(days_to_expiry / 365.0, 1.0 / 365.0)

        net_gex, gex_flip_strike = _calculate_gex(
            calls, puts, current_price, T
        )

        gex_signal = "Mean-Reverting" if net_gex > 0 else "Trending"

        logger.info(
            "%s max_pain=%.2f (dist=%.2f%%), net_gex=%.0f, signal=%s, expiry=%s",
            symbol,
            max_pain_price if max_pain_price is not None else 0,
            max_pain_distance_pct,
            net_gex,
            gex_signal,
            nearest_expiry,
        )

        return {
            "max_pain_price": round(max_pain_price, 2) if max_pain_price is not None else None,
            "max_pain_distance_pct": max_pain_distance_pct,
            "net_gex": round(net_gex, 2),
            "gex_flip_strike": round(gex_flip_strike, 2) if gex_flip_strike is not None else None,
            "gex_signal": gex_signal,
            "expiration_date": nearest_expiry,
        }

    except Exception:
        logger.exception("Max pain / GEX computation failed for %s", symbol)
        return dict(_EMPTY)


def compute_max_pain_gex_from_chain(
    calls,
    puts,
    current_price: float,
    nearest_expiry: str,
) -> Dict[str, Any]:
    """Compute max pain / GEX from pre-fetched option chain DataFrames.

    Parameters
    ----------
    calls : pd.DataFrame
        Calls DataFrame (must have ``strike``, ``openInterest``, ``impliedVolatility``).
    puts : pd.DataFrame
        Puts DataFrame (same columns).
    current_price : float
        Current underlying price.
    nearest_expiry : str
        Expiry date string (``"YYYY-MM-DD"``).

    Returns same dict as ``compute_max_pain_gex()``.
    """
    try:
        if (calls is None or calls.empty) and (puts is None or puts.empty):
            return dict(_EMPTY)

        import pandas as pd
        if calls is None:
            calls = pd.DataFrame(columns=["strike", "openInterest", "impliedVolatility"])
        if puts is None:
            puts = pd.DataFrame(columns=["strike", "openInterest", "impliedVolatility"])

        max_pain_price = _calculate_max_pain(calls, puts)

        if max_pain_price is not None and max_pain_price != 0:
            max_pain_distance_pct = round(
                (current_price - max_pain_price) / max_pain_price * 100, 2
            )
        else:
            max_pain_distance_pct = 0.0

        days = _days_to_expiry(nearest_expiry)
        T = max(days / 365.0, 1.0 / 365.0)

        net_gex, gex_flip_strike = _calculate_gex(calls, puts, current_price, T)
        gex_signal = "Mean-Reverting" if net_gex > 0 else "Trending"

        return {
            "max_pain_price": round(max_pain_price, 2) if max_pain_price is not None else None,
            "max_pain_distance_pct": max_pain_distance_pct,
            "net_gex": round(net_gex, 2),
            "gex_flip_strike": round(gex_flip_strike, 2) if gex_flip_strike is not None else None,
            "gex_signal": gex_signal,
            "expiration_date": nearest_expiry,
        }
    except Exception:
        logger.exception("compute_max_pain_gex_from_chain failed")
        return dict(_EMPTY)


# ---------------------------------------------------------------------------
# Max Pain calculation
# ---------------------------------------------------------------------------

def _calculate_max_pain(calls, puts) -> Optional[float]:
    """Find the strike price that minimises total ITM payout to option writers.

    For each candidate settlement price *K*:
      - Each call with strike *S* where K > S contributes (K - S) * OI * 100
      - Each put  with strike *S* where K < S contributes (S - K) * OI * 100
      - total[K] = sum of all such contributions
    Max pain = *K* that **minimises** total[K].
    """
    call_strikes = calls["strike"].values.astype(float)
    call_oi = calls["openInterest"].fillna(0).values.astype(float)
    put_strikes = puts["strike"].values.astype(float)
    put_oi = puts["openInterest"].fillna(0).values.astype(float)

    # Candidate settlement prices = union of all strikes
    all_strikes = np.unique(np.concatenate([call_strikes, put_strikes]))
    if len(all_strikes) == 0:
        return None

    best_strike: Optional[float] = None
    best_total: float = float("inf")

    for K in all_strikes:
        # ITM calls: calls with strike < K
        call_itm_mask = call_strikes < K
        call_pain = np.sum((K - call_strikes[call_itm_mask]) * call_oi[call_itm_mask] * 100)

        # ITM puts: puts with strike > K
        put_itm_mask = put_strikes > K
        put_pain = np.sum((put_strikes[put_itm_mask] - K) * put_oi[put_itm_mask] * 100)

        total = call_pain + put_pain
        if total < best_total:
            best_total = total
            best_strike = float(K)

    return best_strike


# ---------------------------------------------------------------------------
# GEX calculation
# ---------------------------------------------------------------------------

_RISK_FREE_RATE: float = 0.04
_DEFAULT_IV: float = 0.30


def _bs_gamma(S: float, K: float, T: float, sigma: float) -> float:
    """Black-Scholes gamma for a single option.

    Parameters
    ----------
    S : float   Current underlying price.
    K : float   Strike price.
    T : float   Time to expiry in years (>0).
    sigma : float  Implied volatility (annualised, >0).

    Returns
    -------
    float  Gamma value.
    """
    from scipy.stats import norm

    if sigma <= 0 or T <= 0 or S <= 0 or K <= 0:
        return 0.0

    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (_RISK_FREE_RATE + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
    gamma = norm.pdf(d1) / (S * sigma * sqrt_T)
    return gamma


def _calculate_gex(calls, puts, S: float, T: float):
    """Compute net gamma exposure and the GEX flip strike.

    Net GEX = sum(call_gamma * call_OI * 100 * S)
            - sum(put_gamma  * put_OI  * 100 * S)

    The flip strike is the strike at which cumulative GEX (sorted by
    ascending strike) changes sign, indicating the transition between
    positive-gamma and negative-gamma territory.

    Returns
    -------
    tuple[float, Optional[float]]
        ``(net_gex, gex_flip_strike)``
    """
    # --- Call GEX per strike ---
    call_strikes = calls["strike"].values.astype(float)
    call_oi = calls["openInterest"].fillna(0).values.astype(float)
    call_iv = calls["impliedVolatility"].values.astype(float)
    call_iv = np.where(np.isnan(call_iv) | (call_iv <= 0), _DEFAULT_IV, call_iv)

    call_gex_per_strike = np.zeros(len(call_strikes))
    for i in range(len(call_strikes)):
        gamma = _bs_gamma(S, call_strikes[i], T, call_iv[i])
        call_gex_per_strike[i] = gamma * call_oi[i] * 100 * S

    # --- Put GEX per strike ---
    put_strikes = puts["strike"].values.astype(float)
    put_oi = puts["openInterest"].fillna(0).values.astype(float)
    put_iv = puts["impliedVolatility"].values.astype(float)
    put_iv = np.where(np.isnan(put_iv) | (put_iv <= 0), _DEFAULT_IV, put_iv)

    put_gex_per_strike = np.zeros(len(put_strikes))
    for i in range(len(put_strikes)):
        gamma = _bs_gamma(S, put_strikes[i], T, put_iv[i])
        put_gex_per_strike[i] = gamma * put_oi[i] * 100 * S

    # --- Net GEX ---
    net_gex = float(np.sum(call_gex_per_strike) - np.sum(put_gex_per_strike))

    # --- GEX flip strike ---
    # Build per-strike net GEX: positive for calls, negative for puts
    # Merge onto a common sorted strike grid
    gex_flip_strike = _find_gex_flip(
        call_strikes, call_gex_per_strike,
        put_strikes, put_gex_per_strike,
    )

    return net_gex, gex_flip_strike


def _find_gex_flip(
    call_strikes: np.ndarray,
    call_gex: np.ndarray,
    put_strikes: np.ndarray,
    put_gex: np.ndarray,
) -> Optional[float]:
    """Find the strike where cumulative GEX changes sign.

    We assign +gex for calls and -gex for puts at each strike, sort by
    strike, and scan for a sign change in the running cumulative sum.
    """
    all_strikes = np.unique(np.concatenate([call_strikes, put_strikes]))
    if len(all_strikes) == 0:
        return None

    # Map strikes to net GEX contribution at each strike
    strike_gex: Dict[float, float] = {}
    for s, g in zip(call_strikes, call_gex):
        strike_gex[float(s)] = strike_gex.get(float(s), 0.0) + g
    for s, g in zip(put_strikes, put_gex):
        strike_gex[float(s)] = strike_gex.get(float(s), 0.0) - g

    sorted_strikes = sorted(strike_gex.keys())
    cumulative = 0.0
    prev_sign: Optional[int] = None

    for strike in sorted_strikes:
        cumulative += strike_gex[strike]
        current_sign = 1 if cumulative >= 0 else -1

        if prev_sign is not None and current_sign != prev_sign:
            return float(strike)

        prev_sign = current_sign

    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pick_nearest_expiry(expirations) -> Optional[str]:
    """Return the expiry date string closest to today (but not in the past)."""
    today = datetime.utcnow().date()
    best: Optional[str] = None
    best_delta: Optional[int] = None

    for exp_str in expirations:
        try:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        delta = (exp_date - today).days
        if delta < 0:
            continue  # skip expired
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best = exp_str

    # If all expirations are in the past (unusual), just take the latest one
    if best is None and expirations:
        best = expirations[-1]

    return best


def _days_to_expiry(expiry_str: str) -> int:
    """Return the number of calendar days from today to *expiry_str*."""
    try:
        exp_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
        today = datetime.utcnow().date()
        return max((exp_date - today).days, 1)
    except ValueError:
        return 1
