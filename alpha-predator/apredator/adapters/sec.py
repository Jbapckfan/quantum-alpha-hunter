"""
SEC EDGAR adapter (stub).
Fetches recent filings from the SEC full-text search API.
Placeholder for future expansion with more detailed filing analysis.
"""
import logging
from typing import Dict, List, Optional

import requests

from ..utils.retry import retry_with_backoff

logger = logging.getLogger("apredator.adapters.sec")

SEC_BASE = "https://efts.sec.gov/LATEST/search-index?q="

_HEADERS = {
    "User-Agent": "AlphaPredator/1.0 research@example.com",
    "Accept": "application/json",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@retry_with_backoff(max_retries=2, initial_delay=2.0)
def fetch_recent_filings(
    symbol: str,
    forms: Optional[List[str]] = None,
) -> List[Dict]:
    """Fetch recent SEC filings for a given stock symbol.

    This is a basic stub implementation that queries the EDGAR full-text
    search API. Results are best-effort and may not capture all filings.

    Parameters
    ----------
    symbol : str
        Stock ticker symbol (e.g. ``"AAPL"``).
    forms : list[str], optional
        SEC form types to filter for (e.g. ``["8-K", "13D"]``).
        Defaults to ``["8-K", "13D"]``.

    Returns
    -------
    list[dict]
        Each dict has keys: ``form``, ``date``, ``description``.
        Returns an empty list on failure.
    """
    if forms is None:
        forms = ["8-K", "13D"]

    try:
        # Build search query
        form_filter = " OR ".join(f'formType:"{f}"' for f in forms)
        query = f'"{symbol}" AND ({form_filter})'

        url = "https://efts.sec.gov/LATEST/search-index"
        params = {
            "q": query,
            "dateRange": "custom",
            "startdt": "",  # API uses recent filings by default
            "enddt": "",
            "forms": ",".join(forms),
        }

        # SEC EDGAR full-text search endpoint
        search_url = f"https://efts.sec.gov/LATEST/search-index?q={symbol}"
        resp = requests.get(
            search_url,
            headers=_HEADERS,
            timeout=15,
        )

        if resp.status_code != 200:
            logger.debug(f"SEC EDGAR returned status {resp.status_code} for {symbol}")
            return []

        data = resp.json()

        filings = []
        hits = data.get("hits", {}).get("hits", [])

        for hit in hits[:20]:  # Limit to 20 most recent
            source = hit.get("_source", {})
            form_type = source.get("form_type", "")
            filing_date = source.get("file_date", "")
            description = source.get("display_names", [""])[0] if source.get("display_names") else ""

            # Filter to requested form types
            if forms and form_type not in forms:
                continue

            filings.append({
                "form": form_type,
                "date": filing_date,
                "description": description,
            })

        logger.info(f"Found {len(filings)} SEC filings for {symbol}")
        return filings

    except Exception as exc:
        logger.warning(f"SEC EDGAR lookup failed for {symbol}: {exc}")
        return []
