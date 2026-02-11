"""
SEC EDGAR Insider Transactions Fetcher
======================================

Retrieves Form 4 insider transaction filings directly from the SEC EDGAR
system for a given ticker symbol.  Computes insider sentiment, cluster
buying detection, and a composite insider score.

Falls back to yfinance ``insider_transactions`` when EDGAR is unavailable.

Dependencies: requests, yfinance (already in the project).
"""

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any, Dict, List

import requests

logger = logging.getLogger("apredator.features.edgar_insider")

# Module-level cache for CIK lookups (ticker -> CIK string).
_cik_cache: Dict[str, str] = {}

# SEC requires a descriptive User-Agent header for programmatic access.
_SEC_HEADERS = {
    "User-Agent": "AlphaPredator Research/1.0 (research@example.com)",
    "Accept-Encoding": "gzip, deflate",
}

_REQUEST_TIMEOUT = 15  # seconds


# ---------------------------------------------------------------------------
# Default empty return value
# ---------------------------------------------------------------------------

def _empty_result() -> Dict[str, Any]:
    """Return the neutral default result when no data is available."""
    return {
        "insider_buys_90d": 0,
        "insider_sells_90d": 0,
        "insider_net_90d": 0,
        "cluster_buying": False,
        "insider_sentiment": "Neutral",
        "insider_score": 0,
        "recent_filings": [],
        "data_source": "EDGAR",
    }


# ---------------------------------------------------------------------------
# CIK Lookup
# ---------------------------------------------------------------------------

def _lookup_cik(symbol: str) -> str | None:
    """Resolve a ticker symbol to a SEC Central Index Key (CIK).

    Uses the SEC company_tickers.json endpoint and caches the result in
    the module-level ``_cik_cache`` dict.

    Returns
    -------
    str or None
        The CIK string (zero-padded to 10 digits), or *None* if not found.
    """
    ticker_upper = symbol.upper()

    if ticker_upper in _cik_cache:
        return _cik_cache[ticker_upper]

    try:
        resp = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=_SEC_HEADERS,
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        # The JSON maps string indices ("0", "1", ...) to dicts with
        # keys: cik_str, ticker, title.
        for entry in data.values():
            entry_ticker = str(entry.get("ticker", "")).upper()
            if entry_ticker == ticker_upper:
                cik = str(entry["cik_str"]).zfill(10)
                _cik_cache[ticker_upper] = cik
                return cik

    except Exception:
        logger.exception("CIK lookup failed for %s", symbol)

    return None


# ---------------------------------------------------------------------------
# Form 4 Fetch & Parse
# ---------------------------------------------------------------------------

def _fetch_form4_filings(cik: str, days_back: int) -> List[Dict[str, Any]]:
    """Fetch Form 4 filings from EDGAR for the given CIK.

    Parameters
    ----------
    cik : str
        The SEC Central Index Key.
    days_back : int
        Only filings within this many days from today are returned.

    Returns
    -------
    list of dict
        Each dict has keys: ``title``, ``filing_date``, ``link``, ``summary``.
    """
    url = (
        f"https://www.sec.gov/cgi-bin/browse-edgar"
        f"?action=getcompany&CIK={cik}&type=4&owner=include"
        f"&count=100&output=atom"
    )

    try:
        resp = requests.get(url, headers=_SEC_HEADERS, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception:
        logger.exception("Form 4 fetch failed for CIK %s", cik)
        return []

    # Strip the Atom namespace to simplify element access.
    xml_text = resp.text.replace('xmlns="http://www.w3.org/2005/Atom"', "")

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.exception("Failed to parse EDGAR XML for CIK %s", cik)
        return []

    cutoff_date = datetime.utcnow() - timedelta(days=days_back)
    filings: List[Dict[str, Any]] = []

    for entry in root.findall(".//entry"):
        title_el = entry.find("title")
        title = title_el.text.strip() if title_el is not None and title_el.text else ""

        # Filing date may appear as <filing-date> or <updated>.
        date_el = entry.find("filing-date")
        if date_el is None:
            date_el = entry.find("updated")
        date_str = date_el.text.strip() if date_el is not None and date_el.text else ""

        # Parse the date -- handle both "YYYY-MM-DD" and ISO-8601 with time.
        filing_date = _parse_date(date_str)
        if filing_date is None or filing_date < cutoff_date:
            continue

        # Extract alternate link.
        link = ""
        for link_el in entry.findall("link"):
            if link_el.get("rel") == "alternate":
                link = link_el.get("href", "")
                break
        if not link:
            # Fallback: use the first link element's href.
            link_el = entry.find("link")
            if link_el is not None:
                link = link_el.get("href", "")

        summary_el = entry.find("summary")
        summary = summary_el.text.strip() if summary_el is not None and summary_el.text else ""

        filings.append({
            "title": title,
            "filing_date": filing_date.strftime("%Y-%m-%d"),
            "link": link,
            "summary": summary,
        })

    return filings


def _parse_date(date_str: str) -> datetime | None:
    """Parse a date string in common EDGAR formats."""
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(date_str[:len(fmt) + 5], fmt)
        except (ValueError, IndexError):
            continue
    # Last resort: try just the first 10 chars as YYYY-MM-DD.
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d")
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Transaction Classification
# ---------------------------------------------------------------------------

_BUY_KEYWORDS = ("purchase", "buy", "acquired")
_SELL_KEYWORDS = ("sale", "sell", "disposed")


def _classify_transaction(title: str) -> str:
    """Classify a filing title as 'buy', 'sell', or 'unknown'."""
    title_lower = title.lower()
    if any(kw in title_lower for kw in _BUY_KEYWORDS):
        return "buy"
    if any(kw in title_lower for kw in _SELL_KEYWORDS):
        return "sell"
    return "unknown"


def _extract_filer_name(title: str) -> str:
    """Extract the filer name from a Form 4 title string.

    Typical title format: ``"4 - Smith John A (0001234567) (Issuer)"``
    or ``"4 - SMITH JOHN A"``.  We take the portion after the first
    ``" - "`` delimiter, stripping any trailing parenthetical CIK/role.
    """
    if " - " in title:
        name_part = title.split(" - ", 1)[1]
    else:
        name_part = title
    # Remove parenthetical suffixes like "(0001234567)" or "(Issuer)".
    while "(" in name_part:
        idx = name_part.index("(")
        name_part = name_part[:idx]
    return name_part.strip().upper()


# ---------------------------------------------------------------------------
# Scoring & Sentiment
# ---------------------------------------------------------------------------

def _compute_score(
    buys: int,
    sells: int,
    cluster_buying: bool,
    recent_30d_buyers: int,
) -> int:
    """Compute the insider score (0-100).

    Algorithm
    ---------
    - Base: buy_ratio * 50  (where buy_ratio = buys / (buys + sells))
    - +30 if cluster_buying  (3+ unique buyers in last 30 days)
    - +min(recent_30d_buyers * 5, 20) for recent activity
    - Capped at 100
    """
    total = buys + sells
    if total == 0:
        return 0

    buy_ratio = buys / total
    score = buy_ratio * 50

    if cluster_buying:
        score += 30

    score += min(recent_30d_buyers * 5, 20)

    return min(int(round(score)), 100)


def _score_to_sentiment(score: int) -> str:
    """Convert a numeric insider score to a sentiment label."""
    if score >= 70:
        return "Strong Buy"
    if score >= 40:
        return "Buy"
    if score >= 20:
        return "Neutral"
    return "Sell"


# ---------------------------------------------------------------------------
# yfinance Fallback
# ---------------------------------------------------------------------------

def _fallback_yfinance(symbol: str, days_back: int) -> Dict[str, Any]:
    """Attempt to gather insider data via yfinance as a fallback.

    Mirrors the classification logic used by the existing
    ``fetch_insider_activity()`` function in the intelligence module.
    """
    result = _empty_result()
    result["data_source"] = "yfinance"

    try:
        import yfinance as yf  # noqa: E402 -- deferred import

        ticker = yf.Ticker(symbol)
        txns = ticker.insider_transactions

        if txns is None or (hasattr(txns, "empty") and txns.empty):
            return result

        txns.columns = [c.lower().replace(" ", "_") for c in txns.columns]

        cutoff = datetime.utcnow() - timedelta(days=days_back)
        cutoff_30 = datetime.utcnow() - timedelta(days=30)
        buys = 0
        sells = 0
        recent_buyers: set = set()

        for _, row in txns.iterrows():
            # Determine the transaction date.
            raw_date = row.get("start_date", row.get("date", None))
            if raw_date is not None:
                try:
                    txn_date = datetime.strptime(str(raw_date)[:10], "%Y-%m-%d")
                except ValueError:
                    txn_date = None
            else:
                txn_date = None

            if txn_date is not None and txn_date < cutoff:
                continue

            text = str(row.get("text", "") or row.get("transaction", "")).lower()
            insider_name = str(row.get("insider", "") or row.get("name", "")).upper()

            if any(kw in text for kw in ("purchase", "buy", "acquisition")):
                buys += 1
                if txn_date is not None and txn_date >= cutoff_30 and insider_name:
                    recent_buyers.add(insider_name)
            elif any(kw in text for kw in ("sale", "sell", "disposition")):
                sells += 1

        cluster_buying = len(recent_buyers) >= 3
        score = _compute_score(buys, sells, cluster_buying, len(recent_buyers))

        result.update({
            "insider_buys_90d": buys,
            "insider_sells_90d": sells,
            "insider_net_90d": buys - sells,
            "cluster_buying": cluster_buying,
            "insider_sentiment": _score_to_sentiment(score),
            "insider_score": score,
        })

    except Exception:
        logger.exception("yfinance insider fallback failed for %s", symbol)

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_edgar_insider(symbol: str, days_back: int = 90) -> Dict[str, Any]:
    """Fetch insider transaction data from SEC EDGAR for *symbol*.

    Retrieves Form 4 filings, classifies buy/sell activity, detects cluster
    buying (3+ distinct buyers within 30 days), and computes a composite
    insider score (0-100) with a sentiment label.

    If the EDGAR lookup fails entirely the function falls back to yfinance
    ``insider_transactions``.

    Parameters
    ----------
    symbol : str
        Ticker symbol (e.g. ``"AAPL"``).
    days_back : int, optional
        Look-back window in days (default 90).

    Returns
    -------
    dict
        Keys:

        * ``insider_buys_90d`` -- number of insider buy filings
        * ``insider_sells_90d`` -- number of insider sell filings
        * ``insider_net_90d`` -- buys minus sells
        * ``cluster_buying`` -- *True* when 3+ distinct buyers in last 30 days
        * ``insider_sentiment`` -- ``"Strong Buy"`` | ``"Buy"`` | ``"Neutral"``
          | ``"Sell"``
        * ``insider_score`` -- composite score 0-100
        * ``recent_filings`` -- list of dicts (``title``, ``filing_date``,
          ``link``)
        * ``data_source`` -- ``"EDGAR"`` or ``"yfinance"``
    """
    result = _empty_result()

    # Step 1 -- Resolve ticker to CIK.
    cik = _lookup_cik(symbol)
    if cik is None:
        logger.warning(
            "CIK not found for %s; falling back to yfinance", symbol
        )
        return _fallback_yfinance(symbol, days_back)

    # Step 2 -- Fetch Form 4 filings from EDGAR.
    try:
        filings = _fetch_form4_filings(cik, days_back)
    except Exception:
        logger.exception(
            "EDGAR Form 4 fetch failed for %s; falling back to yfinance",
            symbol,
        )
        return _fallback_yfinance(symbol, days_back)

    if not filings:
        # No filings found -- may be legitimate (no insider activity) or an
        # EDGAR issue.  Return an empty result with EDGAR as source.
        return result

    # Step 3 -- Classify filings and detect cluster buying.
    buys = 0
    sells = 0
    cutoff_30 = datetime.utcnow() - timedelta(days=30)
    recent_buyers: set = set()

    for filing in filings:
        txn_type = _classify_transaction(filing["title"])

        if txn_type == "buy":
            buys += 1
            # Track unique buyers in the last 30 days for cluster detection.
            filing_date = _parse_date(filing["filing_date"])
            if filing_date is not None and filing_date >= cutoff_30:
                filer = _extract_filer_name(filing["title"])
                if filer:
                    recent_buyers.add(filer)
        elif txn_type == "sell":
            sells += 1

    cluster_buying = len(recent_buyers) >= 3

    # Step 4 -- Compute score.
    score = _compute_score(buys, sells, cluster_buying, len(recent_buyers))

    # Step 5 -- Derive sentiment.
    sentiment = _score_to_sentiment(score)

    # Build the recent_filings list (title, filing_date, link only).
    recent_filings_out: List[Dict[str, str]] = [
        {
            "title": f["title"],
            "filing_date": f["filing_date"],
            "link": f["link"],
        }
        for f in filings
    ]

    result.update({
        "insider_buys_90d": buys,
        "insider_sells_90d": sells,
        "insider_net_90d": buys - sells,
        "cluster_buying": cluster_buying,
        "insider_sentiment": sentiment,
        "insider_score": score,
        "recent_filings": recent_filings_out,
        "data_source": "EDGAR",
    })

    return result
