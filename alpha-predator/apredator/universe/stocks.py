"""
Stock universe builder.
Combines S&P 500, NASDAQ 100, and curated sector lists into a deduplicated
tradable universe. Sourced from Hedge Fund master_system.py.
"""
import logging
import re
from typing import List, Optional

import pandas as pd

from ..config import get_config

logger = logging.getLogger("apredator.universe.stocks")

# ---------------------------------------------------------------------------
# Curated sector lists
# ---------------------------------------------------------------------------

SECTOR_LISTS = {
    "biotech": ["SAVA", "SRNE", "OCGN", "VXRT", "ATOS", "IBRX", "APLS"],
    "ev": ["GOEV", "WKHS", "RIDE", "LCID", "RIVN", "FSR", "NKLA"],
    "crypto_related": ["RIOT", "MARA", "COIN", "BITF", "HUT", "CIFR"],
    "cannabis": ["TLRY", "SNDL", "ACB", "CGC", "HEXO"],
    "chinese_adr": ["BABA", "JD", "PDD", "NIO", "XPEV", "LI", "BIDU"],
    "tech_growth": ["PLTR", "SOFI", "HOOD", "AFRM", "UPST", "DKNG"],
}

# Hardcoded fallback in case Wikipedia scraping fails
_FALLBACK_SP500 = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "BRK.B",
    "UNH", "XOM", "JNJ", "JPM", "V", "PG", "AVGO", "HD", "MA", "CVX",
    "MRK", "ABBV", "LLY", "PEP", "COST", "KO", "ADBE", "WMT", "MCD",
    "CRM", "CSCO", "TMO", "ACN", "ABT", "DHR", "LIN", "NKE", "CMCSA",
    "VZ", "TXN", "NEE", "PM", "BMY", "UNP", "ORCL", "RTX", "INTC",
    "AMD", "QCOM", "HON", "LOW", "COP", "AMGN",
]

_FALLBACK_NASDAQ100 = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "AVGO",
    "ADBE", "COST", "PEP", "CSCO", "CMCSA", "INTC", "AMD", "TXN",
    "QCOM", "AMGN", "INTU", "NFLX", "HON", "SBUX", "ISRG", "AMAT",
    "BKNG", "GILD", "ADP", "MDLZ", "ADI", "VRTX", "REGN", "LRCX",
    "PYPL", "MU", "PANW", "SNPS", "KLAC", "CDNS", "MELI", "CHTR",
    "ABNB", "MAR", "MNST", "FTNT", "CRWD", "KDP", "CTAS", "AEP",
    "DXCM", "ORLY",
]


# ---------------------------------------------------------------------------
# Wikipedia scrapers
# ---------------------------------------------------------------------------

def get_sp500() -> List[str]:
    """Scrape S&P 500 constituents from Wikipedia.

    Falls back to a hardcoded list of top-50 symbols on failure.
    """
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        tables = pd.read_html(url)
        df = tables[0]
        symbols = df["Symbol"].str.strip().str.replace(".", "-", regex=False).tolist()
        logger.info(f"Scraped {len(symbols)} S&P 500 symbols from Wikipedia")
        return symbols
    except Exception as exc:
        logger.warning(f"Failed to scrape S&P 500 from Wikipedia: {exc}. Using fallback list.")
        return list(_FALLBACK_SP500)


def get_nasdaq100() -> List[str]:
    """Scrape NASDAQ-100 constituents from Wikipedia.

    Falls back to a hardcoded list of top-50 symbols on failure.
    """
    try:
        url = "https://en.wikipedia.org/wiki/Nasdaq-100"
        tables = pd.read_html(url)
        # The constituents table usually contains a 'Ticker' or 'Symbol' column
        for table in tables:
            for col in ("Ticker", "Symbol"):
                if col in table.columns:
                    symbols = table[col].str.strip().tolist()
                    logger.info(f"Scraped {len(symbols)} NASDAQ-100 symbols from Wikipedia")
                    return symbols
        # If we reach here, none of the tables had the expected column
        logger.warning("Could not find Ticker/Symbol column in NASDAQ-100 Wikipedia tables. Using fallback.")
        return list(_FALLBACK_NASDAQ100)
    except Exception as exc:
        logger.warning(f"Failed to scrape NASDAQ-100 from Wikipedia: {exc}. Using fallback list.")
        return list(_FALLBACK_NASDAQ100)


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

_EXCLUDED_SUFFIX_RE = re.compile(r"[WUR]$")


def _is_tradable(symbol: str) -> bool:
    """Return True if the symbol looks like a regular equity ticker.

    Excludes warrants (W), units (U), and rights (R) that are suffixed to
    tickers on exchanges.
    """
    if not symbol or not isinstance(symbol, str):
        return False
    sym = symbol.strip().upper()
    if _EXCLUDED_SUFFIX_RE.search(sym) and len(sym) > 1:
        return True  # single-char check below
    # More precise: exclude if the last character is W, U, or R and it looks
    # like a multi-part ticker (e.g., "ACAHW")
    if len(sym) >= 4 and sym[-1] in ("W", "U", "R"):
        return False
    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_stock_universe(config=None) -> List[str]:
    """Build the full stock universe by combining index constituents and
    curated sector lists.

    Parameters
    ----------
    config : ConfigManager, optional
        If provided, additional filtering criteria (max_price, min_volume, etc.)
        can be applied downstream. Currently only used for logging context.

    Returns
    -------
    list[str]
        Sorted, deduplicated list of tradable stock symbols.
    """
    all_symbols: set = set()

    # 1. Index constituents
    sp500 = get_sp500()
    nasdaq100 = get_nasdaq100()
    all_symbols.update(sp500)
    all_symbols.update(nasdaq100)

    # 2. Curated sector lists
    for sector_name, tickers in SECTOR_LISTS.items():
        all_symbols.update(tickers)
        logger.debug(f"Added {len(tickers)} symbols from sector '{sector_name}'")

    # 3. Config-based symbols (if any)
    if config is not None:
        try:
            cfg_symbols = config.get_universe_symbols()
            if cfg_symbols:
                all_symbols.update(cfg_symbols)
                logger.info(f"Added {len(cfg_symbols)} symbols from config universe file")
        except Exception as exc:
            logger.warning(f"Could not load config universe symbols: {exc}")

    # 4. Normalize and filter
    cleaned = set()
    for sym in all_symbols:
        sym = str(sym).strip().upper()
        if sym and _is_tradable(sym):
            cleaned.add(sym)

    universe = sorted(cleaned)
    logger.info(f"Stock universe built: {len(universe)} unique tradable symbols")
    return universe
