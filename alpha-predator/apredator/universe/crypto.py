"""
Crypto universe builder.
Combines CoinGecko market data and Binance futures listings into a
deduplicated tradable universe. Sourced from QAHT + Destroyer.
"""
import logging
import time
from typing import Dict, List, Optional, Set

import requests

from ..config import get_config
from ..utils.retry import retry_with_backoff

logger = logging.getLogger("apredator.universe.crypto")

# ---------------------------------------------------------------------------
# CoinGecko ID -> Ticker mapping
# ---------------------------------------------------------------------------

SYMBOL_MAP: Dict[str, str] = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
    "cardano": "ADA",
    "avalanche-2": "AVAX",
    "polkadot": "DOT",
    "chainlink": "LINK",
    "polygon": "MATIC",
    "near": "NEAR",
    "arbitrum": "ARB",
    "optimism": "OP",
    "celestia": "TIA",
    "injective-protocol": "INJ",
    "sui": "SUI",
    "sei-network": "SEI",
    "jupiter-exchange-solana": "JUP",
    "render-token": "RNDR",
    "the-graph": "GRT",
    "aptos": "APT",
    "stacks": "STX",
    "internet-computer": "ICP",
    "filecoin": "FIL",
    "hedera": "HBAR",
    "cosmos": "ATOM",
    "algorand": "ALGO",
    "fantom": "FTM",
    "toncoin": "TON",
    "litecoin": "LTC",
    "dogecoin": "DOGE",
    "shiba-inu": "SHIB",
    "pepe": "PEPE",
    "bonk": "BONK",
    "floki": "FLOKI",
    "worldcoin": "WLD",
    "fetch-ai": "FET",
}

# ---------------------------------------------------------------------------
# Stablecoins to exclude
# ---------------------------------------------------------------------------

STABLECOINS: Set[str] = {
    "USDT", "USDC", "BUSD", "TUSD", "DAI", "USDP", "FDUSD", "USDD", "FRAX",
}

# ---------------------------------------------------------------------------
# Binance futures pair mapping (ticker -> USDT perpetual pair)
# ---------------------------------------------------------------------------

BINANCE_FUTURES_MAP: Dict[str, str] = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
    "ADA": "ADAUSDT",
    "AVAX": "AVAXUSDT",
    "DOT": "DOTUSDT",
    "LINK": "LINKUSDT",
    "MATIC": "MATICUSDT",
    "NEAR": "NEARUSDT",
    "ARB": "ARBUSDT",
    "OP": "OPUSDT",
    "TIA": "TIAUSDT",
    "INJ": "INJUSDT",
    "SUI": "SUIUSDT",
    "SEI": "SEIUSDT",
    "JUP": "JUPUSDT",
    "RNDR": "RNDRUSDT",
    "GRT": "GRTUSDT",
    "APT": "APTUSDT",
    "STX": "STXUSDT",
    "ICP": "ICPUSDT",
    "FIL": "FILUSDT",
    "HBAR": "HBARUSDT",
    "ATOM": "ATOMUSDT",
    "ALGO": "ALGOUSDT",
    "FTM": "FTMUSDT",
    "TON": "TONUSDT",
    "LTC": "LTCUSDT",
    "DOGE": "DOGEUSDT",
    "SHIB": "SHIBUSDT",
    "PEPE": "PEPEUSDT",
    "BONK": "BONKUSDT",
    "FLOKI": "FLOKIUSDT",
    "WLD": "WLDUSDT",
    "FET": "FETUSDT",
}


# ---------------------------------------------------------------------------
# CoinGecko universe
# ---------------------------------------------------------------------------

@retry_with_backoff(max_retries=3, initial_delay=2.0)
def get_coingecko_universe(min_market_cap: int = 100_000_000) -> List[str]:
    """Fetch top coins from CoinGecko by market cap.

    Parameters
    ----------
    min_market_cap : int
        Minimum market capitalisation in USD to include a coin.

    Returns
    -------
    list[str]
        Ticker symbols (upper-case) that meet the criteria.
    """
    config = get_config()

    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 250,
        "page": 1,
        "sparkline": "false",
    }

    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        time.sleep(config.api_rate_limit_delay)

        tickers: List[str] = []
        for coin in data:
            mcap = coin.get("market_cap") or 0
            symbol = (coin.get("symbol") or "").upper()
            if mcap >= min_market_cap and symbol not in STABLECOINS:
                tickers.append(symbol)

        logger.info(
            f"CoinGecko universe: {len(tickers)} coins with market cap >= "
            f"${min_market_cap:,.0f}"
        )
        return tickers

    except Exception as exc:
        logger.warning(
            f"CoinGecko API call failed: {exc}. Falling back to SYMBOL_MAP values."
        )
        fallback = [t for t in SYMBOL_MAP.values() if t not in STABLECOINS]
        logger.info(f"Fallback crypto universe: {len(fallback)} symbols from SYMBOL_MAP")
        return fallback


# ---------------------------------------------------------------------------
# Binance futures universe
# ---------------------------------------------------------------------------

def get_binance_futures_symbols() -> List[str]:
    """Return the list of tickers that have Binance USDT perpetual futures."""
    return list(BINANCE_FUTURES_MAP.keys())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_crypto_universe(config=None) -> List[str]:
    """Build the full crypto universe by combining CoinGecko listings and
    Binance futures availability.

    Parameters
    ----------
    config : ConfigManager, optional
        If provided, ``config.universe.crypto_min_market_cap`` is used as the
        market-cap floor.

    Returns
    -------
    list[str]
        Sorted, deduplicated list of crypto ticker symbols.
    """
    min_mcap = 100_000_000
    if config is not None:
        try:
            min_mcap = int(config.universe.crypto_min_market_cap)
        except Exception:
            pass

    all_symbols: set = set()

    # 1. CoinGecko top coins
    cg_symbols = get_coingecko_universe(min_market_cap=min_mcap)
    all_symbols.update(cg_symbols)

    # 2. Binance futures tickers
    futures_symbols = get_binance_futures_symbols()
    all_symbols.update(futures_symbols)

    # 3. Always include SYMBOL_MAP values (curated core list)
    all_symbols.update(SYMBOL_MAP.values())

    # 4. Remove stablecoins
    all_symbols -= STABLECOINS

    universe = sorted(all_symbols)
    logger.info(f"Crypto universe built: {len(universe)} unique symbols")
    return universe
