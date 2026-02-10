"""
Watchlist & Position Tracker
=============================

SQLite-backed persistent watchlist and position tracker.  Designed to work
standalone (no dependency on the project's SQLAlchemy ``db.py``) so it can
be imported from CLI scripts, notebooks, or the dashboard without pulling in
the full ORM stack.

Usage::

    from apredator.features.watchlist import Watchlist

    wl = Watchlist()                       # default DB in data/watchlist.db
    wl.add_to_watchlist("AAPL", notes="Breakout candidate", entry_price=175.0)
    wl.open_position("AAPL", entry_price=174.50, shares=100, target=200.0)
    wl.close_position("AAPL", exit_price=195.0)
    print(wl.get_pnl_summary())

Dependencies: standard library only (sqlite3, pathlib, datetime).
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("apredator.features.watchlist")


class Watchlist:
    """SQLite-backed watchlist and position tracker.

    Parameters
    ----------
    db_path : str or Path, optional
        Path to the SQLite database file.  Defaults to
        ``<project_root>/data/watchlist.db``.
    """

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            self._db_path = (
                Path(__file__).resolve().parent.parent.parent / "data" / "watchlist.db"
            )
        else:
            self._db_path = Path(db_path)

        # Ensure the parent directory exists.
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_tables()
        logger.info("Watchlist DB initialised at %s", self._db_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        """Return a new connection with row-factory set to ``sqlite3.Row``."""
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_tables(self) -> None:
        """Create the ``watchlist`` and ``positions`` tables if they do not
        already exist."""
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS watchlist (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol       TEXT    NOT NULL,
                    added_date   TEXT    DEFAULT CURRENT_TIMESTAMP,
                    notes        TEXT,
                    entry_price  REAL,
                    target_price REAL,
                    stop_loss    REAL,
                    status       TEXT    DEFAULT 'watching'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS positions (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol       TEXT    NOT NULL,
                    entry_date   TEXT,
                    entry_price  REAL    NOT NULL,
                    shares       REAL    DEFAULT 0,
                    target_price REAL,
                    stop_loss    REAL,
                    exit_date    TEXT,
                    exit_price   REAL,
                    pnl_pct      REAL,
                    status       TEXT    DEFAULT 'open',
                    notes        TEXT,
                    created_at   TEXT    DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    @staticmethod
    def _rows_to_dicts(rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
        """Convert a list of ``sqlite3.Row`` objects to plain dicts."""
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Watchlist CRUD
    # ------------------------------------------------------------------

    def add_to_watchlist(
        self,
        symbol: str,
        notes: str = "",
        entry_price: Optional[float] = None,
        target: Optional[float] = None,
        stop_loss: Optional[float] = None,
    ) -> bool:
        """Add *symbol* to the watchlist.

        If the symbol already exists with status ``watching`` or ``entered``,
        the call is silently skipped and returns *False*.

        Parameters
        ----------
        symbol : str
            Ticker symbol (stored upper-cased).
        notes : str
            Free-text notes.
        entry_price : float, optional
            Target entry price.
        target : float, optional
            Profit target price.
        stop_loss : float, optional
            Stop-loss price.

        Returns
        -------
        bool
            *True* if the symbol was added, *False* if it already existed.
        """
        symbol = symbol.upper().strip()
        try:
            with self._connect() as conn:
                existing = conn.execute(
                    "SELECT id FROM watchlist WHERE symbol = ? AND status IN ('watching', 'entered')",
                    (symbol,),
                ).fetchone()
                if existing:
                    logger.debug("%s already on watchlist (id=%s)", symbol, existing["id"])
                    return False

                conn.execute(
                    """
                    INSERT INTO watchlist (symbol, notes, entry_price, target_price, stop_loss)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (symbol, notes, entry_price, target, stop_loss),
                )
                conn.commit()
                logger.info("Added %s to watchlist", symbol)
                return True
        except Exception:
            logger.exception("Failed to add %s to watchlist", symbol)
            return False

    def remove_from_watchlist(self, symbol: str) -> bool:
        """Remove *symbol* from the watchlist.

        Returns
        -------
        bool
            *True* if a row was deleted, *False* otherwise.
        """
        symbol = symbol.upper().strip()
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    "DELETE FROM watchlist WHERE symbol = ?", (symbol,)
                )
                conn.commit()
                deleted = cursor.rowcount > 0
                if deleted:
                    logger.info("Removed %s from watchlist", symbol)
                return deleted
        except Exception:
            logger.exception("Failed to remove %s from watchlist", symbol)
            return False

    def get_watchlist(self) -> List[Dict[str, Any]]:
        """Return all watchlist entries as a list of dicts."""
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM watchlist ORDER BY added_date DESC"
                ).fetchall()
                return self._rows_to_dicts(rows)
        except Exception:
            logger.exception("Failed to retrieve watchlist")
            return []

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------

    def open_position(
        self,
        symbol: str,
        entry_price: float,
        shares: float = 0,
        target: Optional[float] = None,
        stop_loss: Optional[float] = None,
        notes: str = "",
    ) -> bool:
        """Open a new position and mark the watchlist entry as *entered*.

        Parameters
        ----------
        symbol : str
            Ticker symbol.
        entry_price : float
            Actual entry price.
        shares : float
            Number of shares (or contracts).
        target : float, optional
            Profit target.
        stop_loss : float, optional
            Stop-loss level.
        notes : str
            Free-text notes.

        Returns
        -------
        bool
            *True* on success.
        """
        symbol = symbol.upper().strip()
        entry_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO positions
                        (symbol, entry_date, entry_price, shares,
                         target_price, stop_loss, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (symbol, entry_date, entry_price, shares, target, stop_loss, notes),
                )
                # Update watchlist status.
                conn.execute(
                    "UPDATE watchlist SET status = 'entered' WHERE symbol = ? AND status = 'watching'",
                    (symbol,),
                )
                conn.commit()
                logger.info(
                    "Opened position: %s @ %.2f x %s", symbol, entry_price, shares
                )
                return True
        except Exception:
            logger.exception("Failed to open position for %s", symbol)
            return False

    def close_position(
        self,
        symbol: str,
        exit_price: float,
        notes: str = "",
    ) -> bool:
        """Close the oldest open position for *symbol*.

        Computes realised P&L percentage and updates both the ``positions``
        and ``watchlist`` tables.

        Parameters
        ----------
        symbol : str
            Ticker symbol.
        exit_price : float
            Actual exit price.
        notes : str
            Free-text notes.

        Returns
        -------
        bool
            *True* on success, *False* if no open position was found.
        """
        symbol = symbol.upper().strip()
        exit_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with self._connect() as conn:
                # Find the oldest open position for this symbol.
                row = conn.execute(
                    "SELECT id, entry_price FROM positions WHERE symbol = ? AND status = 'open' ORDER BY entry_date ASC LIMIT 1",
                    (symbol,),
                ).fetchone()
                if row is None:
                    logger.warning("No open position found for %s", symbol)
                    return False

                pos_id = row["id"]
                entry_price = row["entry_price"]
                pnl_pct = (
                    round((exit_price - entry_price) / entry_price * 100, 2)
                    if entry_price
                    else 0.0
                )

                conn.execute(
                    """
                    UPDATE positions
                       SET exit_date  = ?,
                           exit_price = ?,
                           pnl_pct    = ?,
                           status     = 'closed',
                           notes      = CASE WHEN notes IS NULL OR notes = '' THEN ? ELSE notes || ' | ' || ? END
                     WHERE id = ?
                    """,
                    (exit_date, exit_price, pnl_pct, notes, notes, pos_id),
                )
                # Mark watchlist entry as closed (if all positions for symbol
                # are now closed).
                still_open = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM positions WHERE symbol = ? AND status = 'open'",
                    (symbol,),
                ).fetchone()["cnt"]
                if still_open == 0:
                    conn.execute(
                        "UPDATE watchlist SET status = 'closed' WHERE symbol = ? AND status = 'entered'",
                        (symbol,),
                    )
                conn.commit()
                logger.info(
                    "Closed position %s (id=%s): exit=%.2f  pnl=%.2f%%",
                    symbol, pos_id, exit_price, pnl_pct,
                )
                return True
        except Exception:
            logger.exception("Failed to close position for %s", symbol)
            return False

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_open_positions(self) -> List[Dict[str, Any]]:
        """Return all open positions as a list of dicts."""
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM positions WHERE status = 'open' ORDER BY entry_date DESC"
                ).fetchall()
                return self._rows_to_dicts(rows)
        except Exception:
            logger.exception("Failed to retrieve open positions")
            return []

    def get_closed_positions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return closed positions, most recent first.

        Parameters
        ----------
        limit : int
            Maximum number of rows to return (default 50).
        """
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM positions WHERE status = 'closed' ORDER BY exit_date DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return self._rows_to_dicts(rows)
        except Exception:
            logger.exception("Failed to retrieve closed positions")
            return []

    def get_pnl_summary(self) -> Dict[str, Any]:
        """Compute aggregate P&L statistics across all closed positions.

        Returns
        -------
        dict
            Keys: ``total_trades``, ``wins``, ``losses``, ``win_rate``,
            ``avg_pnl``, ``total_pnl``, ``best_trade``, ``worst_trade``.
        """
        empty: Dict[str, Any] = {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "avg_pnl": 0.0,
            "total_pnl": 0.0,
            "best_trade": 0.0,
            "worst_trade": 0.0,
        }
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT pnl_pct FROM positions WHERE status = 'closed' AND pnl_pct IS NOT NULL"
                ).fetchall()
                if not rows:
                    return empty

                pnls = [r["pnl_pct"] for r in rows]
                total_trades = len(pnls)
                wins = sum(1 for p in pnls if p > 0)
                losses = sum(1 for p in pnls if p <= 0)

                return {
                    "total_trades": total_trades,
                    "wins": wins,
                    "losses": losses,
                    "win_rate": round(wins / total_trades * 100, 2) if total_trades else 0.0,
                    "avg_pnl": round(sum(pnls) / total_trades, 2) if total_trades else 0.0,
                    "total_pnl": round(sum(pnls), 2),
                    "best_trade": round(max(pnls), 2),
                    "worst_trade": round(min(pnls), 2),
                }
        except Exception:
            logger.exception("Failed to compute P&L summary")
            return empty

    def update_current_prices(
        self, price_dict: Dict[str, float]
    ) -> List[Dict[str, Any]]:
        """Enrich open positions with live unrealised P&L.

        Parameters
        ----------
        price_dict : dict
            Mapping of ``{symbol: current_price}``.

        Returns
        -------
        list[dict]
            Open positions with two extra keys per row:

            * ``current_price`` -- the price from *price_dict* (or *None*).
            * ``unrealized_pnl_pct`` -- ``(current - entry) / entry * 100``.
        """
        positions = self.get_open_positions()
        enriched: List[Dict[str, Any]] = []
        for pos in positions:
            symbol = pos["symbol"]
            current = price_dict.get(symbol)
            pos["current_price"] = current
            if current is not None and pos["entry_price"]:
                pos["unrealized_pnl_pct"] = round(
                    (current - pos["entry_price"]) / pos["entry_price"] * 100, 2
                )
            else:
                pos["unrealized_pnl_pct"] = None
            enriched.append(pos)
        return enriched
