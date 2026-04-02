"""
Quantum Alpha Hunter -- Unified FastAPI Backend
================================================

Merges all verticals into a single API:
  - Stock scanning   (/api/scan)
  - Watchlist         (/api/watchlist)
  - Signal weights    (/api/weights)
  - Crypto scanning   (/api/crypto)
  - Options           (/api/options)
  - Empirical scoring (/api/scoring)

Delegates to qaht.signals, qaht.options, and qaht.scoring modules; the API
layer stays thin -- validation, serialization, routing.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Quantum Alpha Hunter API",
    description="Unified backend for equities scanning, crypto scanning, options, and empirical scoring.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger("qaht.api")

# ---------------------------------------------------------------------------
# Lazy imports -- keep startup fast, fail gracefully if optional deps missing
# ---------------------------------------------------------------------------

# Stock scanning
from qaht.signals.detector import StockSignalDetector
from qaht.signals.resistance import ResistanceAnalyzer
from qaht.signals.weights import (
    STOCK_WEIGHTS,
    CRYPTO_WEIGHTS,
    load_weights,
    save_weights,
    max_positive_score,
)

# Crypto scanning
from qaht.signals.crypto_detector import CryptoScanner, DEFAULT_CRYPTO_UNIVERSE

# Options (async -- uses Polygon adapter)
from qaht.options.polygon_adapter import PolygonAdapter
from qaht.options.chain import fetch_and_parse, ParsedChain
from qaht.options.zero_dte import (
    compute_scores as compute_0dte_scores,
    build_snapshot_from_polygon,
    MarketSnapshot,
)
from qaht.options.leaps_scanner import scan_leaps_candidates
from qaht.options.strategies import (
    target_price_strategies,
    build_leaps_strategies,
    find_covered_calls,
)

# Empirical scoring
from qaht.scoring.empirical_combos import EmpiricalScorer
from qaht.scoring.position_sizing import KellyPositionSizer

# ---------------------------------------------------------------------------
# Config paths
# ---------------------------------------------------------------------------

_WEIGHTS_DIR = Path(__file__).resolve().parent.parent / "signals"
_STOCK_WEIGHTS_FILE = _WEIGHTS_DIR / "stock_weights.json"
_CRYPTO_WEIGHTS_FILE = _WEIGHTS_DIR / "crypto_weights.json"
_WATCHLIST_FILE = Path(os.environ.get("QAHT_WATCHLIST_FILE", "")) or Path(__file__).resolve().parent.parent.parent / "watchlist.json"

# Default stock universe (mid-cap recovery / momentum names)
DEFAULT_STOCK_UNIVERSE: List[str] = [
    "SOFI", "PLTR", "IONQ", "RKLB", "LUNR", "JOBY", "DNA", "ACHR",
    "AFRM", "UPST", "LAZR", "LCID", "RIVN", "OPEN", "WISH", "CLOV",
    "STEM", "QS", "PLUG", "FCEL", "BLNK", "CHPT", "ENVX", "ASTS",
    "VUZI", "PSFE", "SKLZ", "DKNG", "NKLA", "SPCE", "RDW", "ARQQ",
    "SMCI", "NVDA", "AMD", "MU", "MARA", "RIOT", "COIN", "HOOD",
    "SNAP", "PINS", "TTWO", "RBLX", "U", "SHOP", "SQ", "PYPL",
]


# ═══════════════════════════════════════════════════════════════════════════
# Pydantic v2 request / response schemas
# ═══════════════════════════════════════════════════════════════════════════

# -- Scan ------------------------------------------------------------------

class CustomScanRequest(BaseModel):
    tickers: Optional[List[str]] = None
    min_score: int = Field(default=35, ge=0, le=200)


# -- Watchlist --------------------------------------------------------------

class WatchlistAddRequest(BaseModel):
    ticker: str
    entry_price: float
    score: int = 0
    flags: List[str] = Field(default_factory=list)
    target_price: Optional[float] = None
    stop_price: Optional[float] = None
    notes: Optional[str] = None


class WatchlistUpdateRequest(BaseModel):
    notes: Optional[str] = None
    target_price: Optional[float] = None
    stop_price: Optional[float] = None


# -- Weights ----------------------------------------------------------------

class WeightUpdateRequest(BaseModel):
    weights: Dict[str, int]


# -- Crypto -----------------------------------------------------------------

class CryptoCustomScanRequest(BaseModel):
    tickers: Optional[List[str]] = None
    min_score: int = Field(default=15, ge=0, le=200)


# -- Options ----------------------------------------------------------------

class StrategyRequest(BaseModel):
    ticker: str
    target_price: float
    target_date: str = Field(..., description="ISO date YYYY-MM-DD")
    view: str = Field(default="bull", pattern=r"^(bull|bear)$")
    capital: float = Field(default=1000.0, gt=0)


class LeapsStrategyRequest(BaseModel):
    ticker: str
    view: str = Field(default="bull", pattern=r"^(bull|bear)$")
    bull_target: Optional[float] = None
    bear_target: Optional[float] = None
    capital: float = Field(default=5000.0, gt=0)


class CoveredCallRequest(BaseModel):
    ticker: str
    strategy: str = Field(default="keep", pattern=r"^(keep|okay|max)$")
    min_dte: int = Field(default=3, ge=0)
    max_dte: int = Field(default=60, ge=1)


# -- Scoring ----------------------------------------------------------------

class PositionSizeRequest(BaseModel):
    win_prob: float = Field(..., ge=0.0, le=1.0)
    avg_win: float = Field(default=0.40, gt=0.0)
    avg_loss: float = Field(default=0.15, gt=0.0)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _load_watchlist() -> Dict[str, Any]:
    if _WATCHLIST_FILE.exists():
        with open(_WATCHLIST_FILE, "r") as f:
            return json.load(f)
    return {"items": [], "last_updated": None}


def _save_watchlist(data: Dict[str, Any]) -> None:
    data["last_updated"] = datetime.now().isoformat()
    _WATCHLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_WATCHLIST_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _get_polygon_adapter() -> PolygonAdapter:
    """Construct a PolygonAdapter from environment; raises 503 if unconfigured."""
    try:
        return PolygonAdapter()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


def _yf_quote(ticker: str) -> Dict[str, Any]:
    """Fetch a quick quote from yfinance.  Used by watchlist & stock quote."""
    import yfinance as yf  # noqa: local import to avoid top-level dep if unused

    stock = yf.Ticker(ticker.upper())
    hist = stock.history(period="5d")
    if hist.empty:
        raise HTTPException(status_code=404, detail=f"No data for {ticker}")

    info = stock.info or {}
    current = float(hist.iloc[-1]["Close"])
    prev_close = float(hist.iloc[-2]["Close"]) if len(hist) > 1 else current
    change = current - prev_close
    change_pct = (change / prev_close * 100) if prev_close else 0.0

    return {
        "ticker": ticker.upper(),
        "name": info.get("shortName", ticker.upper()),
        "price": round(current, 2),
        "change": round(change, 2),
        "change_pct": round(change_pct, 2),
        "volume": int(hist.iloc[-1]["Volume"]),
        "high": round(float(hist.iloc[-1]["High"]), 2),
        "low": round(float(hist.iloc[-1]["Low"]), 2),
        "market_cap": info.get("marketCap"),
        "target_mean": info.get("targetMeanPrice"),
        "target_high": info.get("targetHighPrice"),
        "recommendation": info.get("recommendationKey"),
        "num_analysts": info.get("numberOfAnalystOpinions", 0),
    }


def _dataclass_to_dict(obj: Any) -> Any:
    """Recursively convert dataclass instances to dicts for JSON serialization."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _dataclass_to_dict(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [_dataclass_to_dict(i) for i in obj]
    return obj


# ═══════════════════════════════════════════════════════════════════════════
# Root
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {
        "name": "Quantum Alpha Hunter API",
        "version": "2.0.0",
        "verticals": ["scan", "watchlist", "weights", "crypto", "options", "scoring"],
    }


# ═══════════════════════════════════════════════════════════════════════════
# STOCK SCANNER  /api/scan
# ═══════════════════════════════════════════════════════════════════════════

from fastapi import APIRouter

scan_router = APIRouter(prefix="/api/scan", tags=["Stock Scanner"])


@scan_router.get("")
async def scan_universe(min_score: int = Query(35, ge=0)):
    """Scan the default stock universe, returning results >= *min_score*."""
    try:
        detector = StockSignalDetector()
        results = detector.scan_universe(DEFAULT_STOCK_UNIVERSE, min_score=min_score)
        return {
            "scan_time": datetime.now().isoformat(),
            "total": len(results),
            "min_score": min_score,
            "results": results,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@scan_router.get("/high-confidence")
async def high_confidence_plays(min_score: int = Query(70, ge=0)):
    """High-confidence plays: score >= threshold, EARLY/MID stage, 3+ bullish signals."""
    try:
        detector = StockSignalDetector()
        results = detector.scan_universe(DEFAULT_STOCK_UNIVERSE, min_score=min_score)

        high_confidence = []
        for r in results:
            stage = r.get("stage", "")
            is_early = stage in ("EARLY", "MID")
            not_extended = "EXTENDED" not in r.get("flags", [])

            flags = r.get("flags", [])
            ema_bull = r.get("ema_bullish", False)
            macd_bull = r.get("macd_bullish", False)
            bullish_count = sum([
                ema_bull,
                macd_bull,
                "RSI_THRUST" in flags,
                "VOL_SURGE" in flags or "VOL_UP" in flags,
                "BIG_DAY" in flags or "MOMENTUM" in flags,
            ])

            if is_early and not_extended and bullish_count >= 3:
                has_upside = (r.get("upside_to_target") or 0) > 30
                r["confidence"] = "HIGH" if (has_upside and bullish_count >= 4) else "MEDIUM-HIGH"
                r["bullish_signals"] = bullish_count
                high_confidence.append(r)

        return {
            "scan_time": datetime.now().isoformat(),
            "total": len(high_confidence),
            "criteria": {
                "min_score": min_score,
                "stage": ["EARLY", "MID"],
                "min_bullish_signals": 3,
            },
            "results": high_confidence,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@scan_router.post("/custom")
async def scan_custom(request: CustomScanRequest):
    """Scan a custom list of tickers."""
    try:
        tickers = [t.upper() for t in (request.tickers or DEFAULT_STOCK_UNIVERSE)]
        detector = StockSignalDetector()
        results = detector.scan_universe(tickers, min_score=request.min_score)

        return {
            "scan_time": datetime.now().isoformat(),
            "total": len(results),
            "scanned": len(tickers),
            "results": results,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


app.include_router(scan_router)


@app.get("/api/analyze/{ticker}", tags=["Stock Scanner"])
async def analyze_ticker(ticker: str, days: int = Query(150, ge=30, le=500)):
    """Detailed analysis with resistance levels and chart for a single ticker."""
    try:
        ticker = ticker.upper()

        # Resistance analysis
        analyzer = ResistanceAnalyzer(ticker)
        levels = analyzer.find_all_levels()

        # Pattern / signal scan
        detector = StockSignalDetector()
        pattern = detector.scan(ticker)

        return {
            "ticker": ticker,
            "resistance_levels": levels,
            "pattern": pattern,
            "generated_at": datetime.now().isoformat(),
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/quote/{ticker}", tags=["Stock Scanner"])
async def stock_quote(ticker: str):
    """Current quote and basic info for a stock ticker."""
    try:
        return _yf_quote(ticker)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ═══════════════════════════════════════════════════════════════════════════
# WATCHLIST  /api/watchlist
# ═══════════════════════════════════════════════════════════════════════════

watchlist_router = APIRouter(prefix="/api/watchlist", tags=["Watchlist"])


@watchlist_router.get("")
async def get_watchlist():
    """Get the current watchlist with live P&L."""
    import yfinance as yf  # noqa

    try:
        watchlist = _load_watchlist()
        items = watchlist.get("items", [])

        for item in items:
            try:
                stock = yf.Ticker(item["ticker"])
                hist = stock.history(period="1d")
                if not hist.empty:
                    current = float(hist.iloc[-1]["Close"])
                    entry = item["entry_price"]
                    item["current_price"] = round(current, 2)
                    item["pnl"] = round(current - entry, 2)
                    item["pnl_pct"] = round((current - entry) / entry * 100, 2)

                    if item.get("target_price") and current >= item["target_price"]:
                        item["status"] = "TARGET_HIT"
                    elif item.get("stop_price") and current <= item["stop_price"]:
                        item["status"] = "STOPPED_OUT"
                    else:
                        item["status"] = "ACTIVE"
            except Exception:
                item["current_price"] = None
                item["pnl"] = None
                item["pnl_pct"] = None
                item["status"] = "ERROR"

        return {
            "items": items,
            "total": len(items),
            "last_updated": watchlist.get("last_updated"),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@watchlist_router.post("/add")
async def add_to_watchlist(item: WatchlistAddRequest):
    """Add a stock to the watchlist."""
    try:
        watchlist = _load_watchlist()
        ticker = item.ticker.upper()

        if any(i["ticker"] == ticker for i in watchlist["items"]):
            raise HTTPException(status_code=400, detail=f"{ticker} already in watchlist")

        new_item = {
            "ticker": ticker,
            "entry_price": item.entry_price,
            "score": item.score,
            "flags": item.flags,
            "target_price": item.target_price,
            "stop_price": item.stop_price,
            "notes": item.notes,
            "added_at": datetime.now().isoformat(),
            "status": "ACTIVE",
        }
        watchlist["items"].append(new_item)
        _save_watchlist(watchlist)

        return {"message": f"Added {ticker} to watchlist", "item": new_item}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@watchlist_router.post("/add-from-scan/{ticker}")
async def add_from_scan(ticker: str, notes: Optional[str] = Query(None)):
    """Auto-add a ticker from scan results (fills price, score, targets)."""
    import yfinance as yf  # noqa

    try:
        ticker = ticker.upper()
        detector = StockSignalDetector()
        result = detector.scan(ticker)

        if not result:
            raise HTTPException(status_code=404, detail=f"Could not analyze {ticker}")

        # Enrich with company info
        stock = yf.Ticker(ticker)
        info = stock.info or {}

        watchlist = _load_watchlist()
        if any(i["ticker"] == ticker for i in watchlist["items"]):
            raise HTTPException(status_code=400, detail=f"{ticker} already in watchlist")

        new_item = {
            "ticker": ticker,
            "company_name": info.get("longName") or info.get("shortName") or result.get("name", ticker),
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", "Unknown"),
            "entry_price": result["price"],
            "score": result["score"],
            "flags": result.get("flags", []),
            "target_price": result.get("t2"),
            "stop_price": result.get("stop"),
            "notes": notes or f"Score: {result['score']}, Stage: {result.get('stage', 'N/A')}",
            "added_at": datetime.now().isoformat(),
            "status": "ACTIVE",
            "pattern_data": {
                "drawdown": result.get("drawdown"),
                "rally_from_low": result.get("rally_from_low"),
                "stage": result.get("stage"),
                "t1": result.get("t1"),
                "t2": result.get("t2"),
                "t3": result.get("t3"),
                "t4": result.get("t4"),
            },
        }
        watchlist["items"].append(new_item)
        _save_watchlist(watchlist)

        return {"message": f"Added {ticker} to watchlist", "item": new_item}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@watchlist_router.delete("/{ticker}")
async def remove_from_watchlist(ticker: str):
    """Remove a stock from the watchlist."""
    try:
        ticker = ticker.upper()
        watchlist = _load_watchlist()
        original_len = len(watchlist["items"])
        watchlist["items"] = [i for i in watchlist["items"] if i["ticker"] != ticker]

        if len(watchlist["items"]) == original_len:
            raise HTTPException(status_code=404, detail=f"{ticker} not in watchlist")

        _save_watchlist(watchlist)
        return {"message": f"Removed {ticker} from watchlist"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@watchlist_router.put("/{ticker}")
async def update_watchlist_item(ticker: str, body: WatchlistUpdateRequest):
    """Update notes, target, or stop for a watchlist item."""
    try:
        ticker = ticker.upper()
        watchlist = _load_watchlist()

        found = False
        for item in watchlist["items"]:
            if item["ticker"] == ticker:
                if body.notes is not None:
                    item["notes"] = body.notes
                if body.target_price is not None:
                    item["target_price"] = body.target_price
                if body.stop_price is not None:
                    item["stop_price"] = body.stop_price
                found = True
                break

        if not found:
            raise HTTPException(status_code=404, detail=f"{ticker} not in watchlist")

        _save_watchlist(watchlist)
        return {"message": f"Updated {ticker}"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@watchlist_router.get("/performance")
async def watchlist_performance():
    """Aggregate performance summary of the watchlist."""
    import yfinance as yf  # noqa

    try:
        watchlist = _load_watchlist()
        items = watchlist.get("items", [])

        if not items:
            return {"message": "Watchlist is empty"}

        total_pnl = 0.0
        winners = losers = active = 0

        for item in items:
            try:
                stock = yf.Ticker(item["ticker"])
                hist = stock.history(period="1d")
                if not hist.empty:
                    current = float(hist.iloc[-1]["Close"])
                    pnl_pct = (current - item["entry_price"]) / item["entry_price"] * 100
                    total_pnl += pnl_pct
                    if pnl_pct > 0:
                        winners += 1
                    else:
                        losers += 1
                    active += 1
            except Exception:
                pass

        win_rate = (winners / active * 100) if active > 0 else 0
        avg_pnl = total_pnl / active if active > 0 else 0

        return {
            "total_positions": len(items),
            "active_positions": active,
            "winners": winners,
            "losers": losers,
            "win_rate": round(win_rate, 1),
            "avg_pnl_pct": round(avg_pnl, 2),
            "total_pnl_pct": round(total_pnl, 2),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


app.include_router(watchlist_router)


# ═══════════════════════════════════════════════════════════════════════════
# SIGNAL WEIGHTS  /api/weights
# ═══════════════════════════════════════════════════════════════════════════

weights_router = APIRouter(prefix="/api/weights", tags=["Signal Weights"])


@weights_router.get("")
async def get_weights():
    """Current stock signal weights and defaults."""
    try:
        current = load_weights(_STOCK_WEIGHTS_FILE, STOCK_WEIGHTS)
        return {
            "current": current,
            "defaults": STOCK_WEIGHTS,
            "total_signals": len(STOCK_WEIGHTS),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@weights_router.put("")
async def update_weights(body: WeightUpdateRequest):
    """Update stock signal weights (partial merge)."""
    try:
        current = load_weights(_STOCK_WEIGHTS_FILE, STOCK_WEIGHTS)
        invalid = [k for k in body.weights if k not in STOCK_WEIGHTS]
        if invalid:
            raise HTTPException(status_code=400, detail=f"Invalid weight keys: {invalid}")

        current.update(body.weights)
        save_weights(_STOCK_WEIGHTS_FILE, current)
        return {"message": f"Updated {len(body.weights)} weight(s)", "current": current}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@weights_router.post("/reset")
async def reset_weights():
    """Reset stock weights to defaults."""
    try:
        save_weights(_STOCK_WEIGHTS_FILE, STOCK_WEIGHTS.copy())
        return {"message": "Weights reset to defaults", "weights": STOCK_WEIGHTS}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@weights_router.get("/analyze/{ticker}")
async def analyze_weight_impact(ticker: str):
    """Signal breakdown: which signals fired and their weight contributions."""
    try:
        ticker = ticker.upper()
        detector = StockSignalDetector()
        result = detector.scan(ticker)

        if not result:
            raise HTTPException(status_code=404, detail=f"Could not analyze {ticker}")

        weights = load_weights(_STOCK_WEIGHTS_FILE, STOCK_WEIGHTS)
        signal_breakdown = result.get("signal_breakdown", {})

        contributions = []
        total_positive = total_negative = 0

        for signal, fired in signal_breakdown.items():
            if fired and signal in weights:
                w = weights[signal]
                contributions.append({"signal": signal, "weight": w, "fired": True})
                if w > 0:
                    total_positive += w
                else:
                    total_negative += w

        contributions.sort(key=lambda x: abs(x["weight"]), reverse=True)

        return {
            "ticker": ticker,
            "final_score": result["score"],
            "total_positive": total_positive,
            "total_negative": total_negative,
            "signals_fired": len(contributions),
            "contributions": contributions,
            "stage": result.get("stage"),
            "flags": result.get("flags", []),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


app.include_router(weights_router)


# ═══════════════════════════════════════════════════════════════════════════
# CRYPTO  /api/crypto
# ═══════════════════════════════════════════════════════════════════════════

crypto_router = APIRouter(prefix="/api/crypto", tags=["Crypto Scanner"])


def _normalize_crypto_ticker(ticker: str) -> str:
    """Ensure proper `-USD` suffix on crypto tickers."""
    t = ticker.upper()
    return t if t.endswith("-USD") else f"{t}-USD"


@crypto_router.get("/scan")
async def scan_crypto(min_score: int = Query(15, ge=0)):
    """Scan the default crypto universe."""
    try:
        scanner = CryptoScanner()
        results = scanner.scan(min_score=min_score)
        return {
            "scan_time": datetime.now().isoformat(),
            "total": len(results),
            "min_score": min_score,
            "universe_size": len(DEFAULT_CRYPTO_UNIVERSE),
            "results": results,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@crypto_router.post("/scan/custom")
async def scan_crypto_custom(request: CryptoCustomScanRequest):
    """Scan a custom list of crypto tickers."""
    try:
        tickers = [_normalize_crypto_ticker(t) for t in (request.tickers or DEFAULT_CRYPTO_UNIVERSE)]
        scanner = CryptoScanner(universe=tickers)
        results = scanner.scan(min_score=request.min_score)
        return {
            "scan_time": datetime.now().isoformat(),
            "total": len(results),
            "scanned": len(tickers),
            "results": results,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@crypto_router.get("/quote/{ticker}")
async def crypto_quote(ticker: str):
    """Current quote and 7d/30d change for a cryptocurrency."""
    import yfinance as yf  # noqa

    try:
        ticker = _normalize_crypto_ticker(ticker)
        crypto = yf.Ticker(ticker)
        hist = crypto.history(period="30d")

        if hist.empty:
            raise HTTPException(status_code=404, detail=f"No data for {ticker}")

        info = crypto.info or {}
        current = float(hist["Close"].iloc[-1])
        prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current
        decimals = 6 if current < 1 else 2

        change_24h = (current - prev_close) / prev_close * 100
        change_7d = (
            (current - float(hist["Close"].iloc[-7])) / float(hist["Close"].iloc[-7]) * 100
            if len(hist) >= 7
            else 0.0
        )
        change_30d = (current - float(hist["Close"].iloc[0])) / float(hist["Close"].iloc[0]) * 100

        return {
            "ticker": ticker,
            "name": info.get("name") or info.get("shortName") or ticker.replace("-USD", ""),
            "price": round(current, decimals),
            "change_24h": round(change_24h, 2),
            "change_7d": round(change_7d, 2),
            "change_30d": round(change_30d, 2),
            "volume_24h": int(hist["Volume"].iloc[-1] * current),
            "high_24h": round(float(hist["High"].iloc[-1]), decimals),
            "low_24h": round(float(hist["Low"].iloc[-1]), decimals),
            "high_30d": round(float(hist["High"].max()), decimals),
            "low_30d": round(float(hist["Low"].min()), decimals),
            "market_cap": info.get("marketCap"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@crypto_router.get("/weights")
async def get_crypto_weights():
    """Current crypto signal weights."""
    try:
        current = load_weights(_CRYPTO_WEIGHTS_FILE, CRYPTO_WEIGHTS)
        return {
            "current": current,
            "defaults": CRYPTO_WEIGHTS,
            "total_signals": len(CRYPTO_WEIGHTS),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@crypto_router.put("/weights")
async def update_crypto_weights(body: WeightUpdateRequest):
    """Update crypto signal weights (partial merge)."""
    try:
        current = load_weights(_CRYPTO_WEIGHTS_FILE, CRYPTO_WEIGHTS)
        invalid = [k for k in body.weights if k not in CRYPTO_WEIGHTS]
        if invalid:
            raise HTTPException(status_code=400, detail=f"Invalid weight keys: {invalid}")

        current.update(body.weights)
        save_weights(_CRYPTO_WEIGHTS_FILE, current)
        return {"message": f"Updated {len(body.weights)} crypto weight(s)", "current": current}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@crypto_router.post("/weights/reset")
async def reset_crypto_weights():
    """Reset crypto weights to defaults."""
    try:
        save_weights(_CRYPTO_WEIGHTS_FILE, CRYPTO_WEIGHTS.copy())
        return {"message": "Crypto weights reset to defaults", "weights": CRYPTO_WEIGHTS}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@crypto_router.get("/analyze/{ticker}")
async def analyze_crypto(ticker: str):
    """Signal breakdown for a single cryptocurrency."""
    try:
        ticker = _normalize_crypto_ticker(ticker)
        scanner = CryptoScanner(universe=[ticker])
        results = scanner.scan(min_score=0)

        if not results:
            raise HTTPException(status_code=404, detail=f"Could not analyze {ticker}")

        data = results[0]
        signal_breakdown = data.get("signal_breakdown", {})

        contributions = []
        total_positive = total_negative = 0

        for signal, weight in signal_breakdown.items():
            contributions.append({"signal": signal, "weight": weight, "fired": True})
            if weight > 0:
                total_positive += weight
            else:
                total_negative += weight

        contributions.sort(key=lambda x: abs(x["weight"]), reverse=True)

        return {
            "ticker": ticker,
            "name": data.get("name"),
            "price": data.get("price"),
            "final_score": data.get("score"),
            "max_score": data.get("max_score"),
            "total_positive": total_positive,
            "total_negative": total_negative,
            "signals_fired": len(contributions),
            "contributions": contributions,
            "trend": data.get("trend"),
            "flags": data.get("flags", []),
            "metrics": {
                "change_24h": data.get("change_24h"),
                "change_7d": data.get("change_7d"),
                "change_30d": data.get("change_30d"),
                "volume_ratio": data.get("volume_ratio"),
                "rsi": data.get("rsi"),
                "drawdown_from_ath": data.get("drawdown_from_ath"),
            },
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@crypto_router.get("/chart/{ticker}")
async def crypto_chart(ticker: str, days: int = Query(90, ge=7, le=365)):
    """Technical analysis chart (base64 PNG) for a cryptocurrency.

    Requires ``qaht.crypto.charts.CryptoChartGenerator`` -- returns 501 if
    that module has not been ported yet.
    """
    try:
        from qaht.crypto.charts import CryptoChartGenerator  # type: ignore[import-untyped]
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="Crypto chart module not yet available (qaht.crypto.charts).",
        )

    try:
        gen = CryptoChartGenerator(ticker)
        chart_base64 = gen.create_chart(days=days)
        chart_data = gen.get_chart_data()
        return {
            "ticker": gen.ticker,
            "chart": chart_base64,
            "indicators": chart_data,
            "days": days,
            "generated_at": datetime.now().isoformat(),
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@crypto_router.get("/sentiment/{ticker}")
async def crypto_sentiment(ticker: str):
    """Social sentiment and community metrics for a cryptocurrency.

    Requires ``qaht.crypto.sentiment.CryptoSentimentTracker`` -- returns 501
    if that module has not been ported yet.
    """
    try:
        from qaht.crypto.sentiment import CryptoSentimentTracker  # type: ignore[import-untyped]
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="Crypto sentiment module not yet available (qaht.crypto.sentiment).",
        )

    try:
        tracker = CryptoSentimentTracker()
        report = tracker.get_full_sentiment_report(ticker)
        if report.get("error"):
            raise HTTPException(status_code=404, detail=report["error"])
        return report
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@crypto_router.get("/fear-greed")
async def fear_greed_index():
    """Crypto Fear & Greed Index (0-100)."""
    try:
        from qaht.crypto.sentiment import get_market_fear_greed  # type: ignore[import-untyped]
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="Crypto sentiment module not yet available (qaht.crypto.sentiment).",
        )

    try:
        return get_market_fear_greed()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@crypto_router.get("/top-movers")
async def crypto_top_movers():
    """Top gaining / losing cryptos and volume leaders over the last 24h."""
    try:
        scanner = CryptoScanner()
        results = scanner.scan(min_score=0)

        gainers = sorted(results, key=lambda x: x.get("change_24h", 0), reverse=True)[:10]
        losers = sorted(results, key=lambda x: x.get("change_24h", 0))[:10]
        volume_leaders = sorted(results, key=lambda x: x.get("volume_ratio", 0), reverse=True)[:10]

        return {
            "scan_time": datetime.now().isoformat(),
            "top_gainers": gainers,
            "top_losers": losers,
            "volume_leaders": volume_leaders,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


app.include_router(crypto_router)


# ═══════════════════════════════════════════════════════════════════════════
# OPTIONS  /api/options
# ═══════════════════════════════════════════════════════════════════════════

options_router = APIRouter(prefix="/api/options", tags=["Options"])


@options_router.get("/chain")
async def options_chain(
    ticker: str = Query(..., description="Underlying ticker symbol"),
):
    """Full options chain with Greeks from Polygon.io."""
    adapter = _get_polygon_adapter()
    try:
        chain = await fetch_and_parse(adapter, ticker.upper())

        # Serialize OptionLeg dataclasses into dicts
        legs_dicts = [_dataclass_to_dict(leg) for leg in chain.legs]

        return {
            "ticker": chain.underlying,
            "currentPrice": chain.underlying_price,
            "expirations": chain.expirations,
            "total_contracts": len(chain.legs),
            "options": legs_dicts,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@options_router.get("/zero-dte")
async def zero_dte_scores(
    ticker: str = Query("SPY", description="Underlying ticker (default SPY)"),
):
    """0DTE direction scores (call/put 0-100) and regime classification."""
    adapter = _get_polygon_adapter()
    try:
        snapshot = await build_snapshot_from_polygon(adapter, ticker.upper())
        scores = compute_0dte_scores(snapshot)
        return _dataclass_to_dict(scores)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@options_router.get("/leaps")
async def leaps_candidates(
    view: str = Query("bull", pattern=r"^(bull|bear)$"),
    min_trend: float = Query(0.6, ge=0.0, le=1.0),
    limit: int = Query(10, ge=1, le=50),
    universe: Optional[str] = Query(
        None,
        description="Comma-separated tickers (e.g. 'SPY,QQQ,AAPL'). Uses default universe if omitted.",
    ),
    fetch_iv: bool = Query(True, description="Fetch 30-day IV from options chain (slower)."),
):
    """LEAPS candidates ranked by trend score."""
    adapter = _get_polygon_adapter()
    tickers = [t.strip().upper() for t in universe.split(",") if t.strip()] if universe else None

    try:
        candidates = await scan_leaps_candidates(
            adapter=adapter,
            view=view,
            universe=tickers,
            min_trend=min_trend,
            limit=limit,
            fetch_iv=fetch_iv,
        )
        return {
            "view": view,
            "candidates": [_dataclass_to_dict(c) for c in candidates],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@options_router.post("/strategy")
async def target_price_strategy(body: StrategyRequest):
    """Target-price strategy calculator (calls/puts/spreads ranked by ROI)."""
    adapter = _get_polygon_adapter()
    try:
        chain = await fetch_and_parse(adapter, body.ticker.upper())
        strategies = target_price_strategies(
            chain=chain,
            target_price=body.target_price,
            target_date=body.target_date,
            view=body.view,
            capital=body.capital,
        )
        return {
            "ticker": chain.underlying,
            "current_price": chain.underlying_price,
            "target_price": body.target_price,
            "target_date": body.target_date,
            "view": body.view,
            "strategies": [_dataclass_to_dict(s) for s in strategies],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@options_router.post("/leaps-strategy")
async def leaps_strategy(body: LeapsStrategyRequest):
    """Build LEAPS strategies (long LEAP, PMCC, diagonal) for a ticker."""
    adapter = _get_polygon_adapter()
    try:
        chain = await fetch_and_parse(adapter, body.ticker.upper())
        strategies = build_leaps_strategies(
            chain=chain,
            view=body.view,
            bull_target=body.bull_target,
            bear_target=body.bear_target,
            capital=body.capital,
        )
        return {
            "ticker": chain.underlying,
            "current_price": chain.underlying_price,
            "view": body.view,
            "strategies": [_dataclass_to_dict(s) for s in strategies],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@options_router.post("/covered-calls")
async def covered_calls(body: CoveredCallRequest):
    """Find covered-call candidates by delta profile (keep / okay / max)."""
    adapter = _get_polygon_adapter()
    try:
        chain = await fetch_and_parse(adapter, body.ticker.upper())
        results = find_covered_calls(
            chain=chain,
            strategy=body.strategy,
            min_dte=body.min_dte,
            max_dte=body.max_dte,
        )
        return {
            "ticker": chain.underlying,
            "current_price": chain.underlying_price,
            "strategy": body.strategy,
            "candidates": [_dataclass_to_dict(r) for r in results],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


app.include_router(options_router)


# ═══════════════════════════════════════════════════════════════════════════
# SCORING  /api/scoring
# ═══════════════════════════════════════════════════════════════════════════

scoring_router = APIRouter(prefix="/api/scoring", tags=["Scoring"])


@scoring_router.get("/empirical/{ticker}")
async def empirical_score(ticker: str):
    """Empirical combo score, trap detection, and conviction for a ticker.

    Uses the EmpiricalScorer which pulls OHLCV from the database.  Returns
    a 404 if there is insufficient data.
    """
    try:
        scorer = EmpiricalScorer()
        result = scorer.score_from_db(ticker.upper())

        if result is None:
            raise HTTPException(
                status_code=404,
                detail=f"Insufficient data for empirical scoring of {ticker.upper()}",
            )

        return {
            "symbol": result.symbol,
            "hybrid_score": round(result.hybrid_score, 2),
            "combo_score": round(result.combo_score, 2),
            "quantum_score": result.quantum_score,
            "conviction": result.conviction,
            "best_combo": result.matched_combos[0].name if result.matched_combos else None,
            "best_combo_hit_rate": round(result.best_combo_hit_rate, 3),
            "n_combos": len(result.matched_combos),
            "matched_combos": [
                {"name": c.name, "hit_rate": c.hit_rate, "signals": c.signals_present}
                for c in result.matched_combos
            ],
            "trap_warnings": [
                {"trap": t.trap_type, "severity": t.severity, "detail": t.detail}
                for t in result.trap_warnings
            ] if hasattr(result, "trap_warnings") and result.trap_warnings else [],
            "has_unmitigated_traps": result.has_unmitigated_traps,
            "regime": result.regime.label if result.regime else "UNKNOWN",
            "kelly": _dataclass_to_dict(result.kelly) if result.kelly else None,
            "exit_plan": _dataclass_to_dict(result.exit_plan) if result.exit_plan else None,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@scoring_router.get("/hybrid/{ticker}")
async def hybrid_score(ticker: str):
    """Combined ML (Ridge) + empirical score with regime adjustment.

    Same underlying scorer as /empirical but returns a simplified view
    focused on the blended hybrid_score and position guidance.
    """
    try:
        scorer = EmpiricalScorer()
        result = scorer.score_from_db(ticker.upper())

        if result is None:
            raise HTTPException(
                status_code=404,
                detail=f"Insufficient data for hybrid scoring of {ticker.upper()}",
            )

        return {
            "symbol": result.symbol,
            "hybrid_score": round(result.hybrid_score, 2),
            "conviction": result.conviction,
            "combo_score": round(result.combo_score, 2),
            "quantum_score": result.quantum_score,
            "regime": result.regime.label if result.regime else "UNKNOWN",
            "kelly_size": round(result.kelly.clamped_size, 4) if result.kelly else None,
            "n_combos": len(result.matched_combos),
            "has_traps": result.has_unmitigated_traps,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@scoring_router.get("/position-size")
async def position_size(
    win_prob: float = Query(..., ge=0.0, le=1.0, description="Estimated win probability"),
    avg_win: float = Query(0.40, gt=0.0, description="Average winner return (e.g. 0.40 = +40%)"),
    avg_loss: float = Query(0.15, gt=0.0, description="Average loser magnitude (e.g. 0.15 = -15%)"),
):
    """Kelly criterion position sizing."""
    try:
        sizer = KellyPositionSizer()
        result = sizer.compute(win_prob=win_prob, avg_win=avg_win, avg_loss=avg_loss)
        return _dataclass_to_dict(result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


app.include_router(scoring_router)


# ═══════════════════════════════════════════════════════════════════════════
# Entrypoint
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "qaht.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
