"""
Stock universe builder.
Combines curated momentum, sector, and high-interest lists into a deduplicated
tradable universe.  No S&P 500 / NASDAQ-100 mega-caps — this app targets
small-to-mid-cap momentum names.
"""
import logging
from typing import List, Optional

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
    "tech_growth": ["SOFI", "HOOD", "AFRM", "UPST", "DKNG", "HIMS"],
}

# ---------------------------------------------------------------------------
# Momentum / high-interest stocks (the core universe)
# ---------------------------------------------------------------------------
_FALLBACK_MOMENTUM = [
    # Meme / High Beta
    "AMC", "GME", "SOFI", "HOOD", "AFRM", "UPST", "DKNG", "CLOV", "RBLX", "CVNA",
    "HIMS", "DJT", "RDDT", "MNDY", "CELH", "SNAP", "PINS", "SE", "GRAB",
    # Crypto-Adjacent
    "RIOT", "MARA", "COIN", "BITF", "HUT", "CIFR", "MSTR", "CLSK",
    # Biotech
    "SAVA", "SRNE", "OCGN", "VXRT", "IBRX", "APLS", "CRSP", "BEAM", "NTLA", "DNA",
    "IONS", "EXAS", "FATE", "EDIT", "FOLD", "DAWN",
    # EV / Clean Energy
    "LCID", "RIVN", "QS", "CHPT", "BLNK", "PLUG", "FCEL", "BE", "RUN", "STEM",
    "GOEV", "WKHS", "NKLA", "PTRA", "EVGO",
    # Tech Growth
    "SNOW", "NET", "DDOG", "ZS", "MDB", "CFLT", "SHOP", "ROKU", "TTD", "TWLO",
    "DOCN", "BILL", "PCOR", "TOST", "BRZE",
    # Chinese ADR
    "BABA", "JD", "PDD", "NIO", "XPEV", "LI", "BIDU", "FUTU", "TAL", "BILI",
    # Quantum / Space / AI
    "IONQ", "RGTI", "QBTS", "QUBT", "LUNR", "RKLB", "ASTS", "JOBY", "SMCI", "ARM",
    "AI", "BBAI", "SOUN", "VNET",
    # Nuclear / Energy
    "OKLO", "SMR", "NNE", "VST", "CEG", "CCJ", "LEU",
    # Cannabis
    "TLRY", "SNDL", "ACB", "CGC",
    # Misc Momentum / Popular
    "BARK", "WULF", "SQ", "OPEN", "WISH", "SKLZ",
    "INDI", "LAZR", "LIDR", "VLDR", "OUST", "AEVA",
    # Mid-cap value / under-followed
    "CROX", "DINO", "TGTX", "RXRX", "SMMT", "ACHR", "GENI", "BTBT",
    # SPACs / De-SPACs that are actively traded
    "MVST", "PAYO", "OPAD", "IRNT", "VLD",
]


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

def _is_tradable(symbol: str) -> bool:
    """Return True if the symbol looks like a regular equity ticker.

    Excludes warrants (W), units (U), and rights (R) that are suffixed to
    tickers on exchanges (e.g. "ACAHW", "BRPMU", "IRNTR").
    Short tickers like "W" (Wayfair) or "U" (Unity) are kept.
    """
    if not symbol or not isinstance(symbol, str):
        return False
    sym = symbol.strip().upper()
    if len(sym) >= 4 and sym[-1] in ("W", "U", "R"):
        return False
    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_stock_universe(config=None) -> List[str]:
    """Build the full stock universe from curated momentum + sector lists.

    No S&P 500 / NASDAQ-100 mega-caps — this app focuses on small-to-mid-cap
    momentum names.

    Parameters
    ----------
    config : ConfigManager, optional
        If provided, additional symbols from a config universe file are merged in.

    Returns
    -------
    list[str]
        Sorted, deduplicated list of tradable stock symbols.
    """
    all_symbols: set = set()

    # 1. Momentum / high-interest stocks (core universe)
    all_symbols.update(_FALLBACK_MOMENTUM)

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
