"""SQLite-backed ledger — one file, concurrency-safe, still stdlib-only.

Module summary
--------------
An interchangeable backend for :class:`wallet_helper.ledger.Ledger`. Where the
default keeps one JSON file per entry (delightfully inspectable, ideal for a
single process), :class:`SqliteLedger` keeps everything in **one** SQLite file
with write-ahead logging — so many processes or threads can share and update one
ledger without the last writer clobbering a hit counter. It satisfies the same
:class:`~wallet_helper.ledger.LedgerLike` protocol, so :class:`Wallet`, the CLIs
and the HTTP / MCP surfaces accept it wherever a ``Ledger`` fits.

``sqlite3`` ships with CPython, so this stays a zero-third-party-dependency
backend — the concurrency-safe "shared ledger" without pulling in a server.

Author
------
Warith HARCHAOUI — https://linkedin.com/in/warith-harchaoui
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from wallet_helper.ledger import _DEFAULT_DIR


class SqliteLedger:
    """A single-file SQLite store of results for billable calls.

    Parameters
    ----------
    db_path : str or pathlib.Path, optional
        The database file. Defaults to ``<default ledger dir>/ledger.db`` (the
        same base as :class:`~wallet_helper.ledger.Ledger`, honouring
        ``$WALLET_HELPER_DIR``). Parent directories are created on demand.

    Examples
    --------
    >>> import tempfile
    >>> lg = SqliteLedger(tempfile.mkdtemp() + "/ledger.db")
    >>> lg.has("demo_x")
    False
    >>> lg.put("demo_x", {"ok": True}, cost=0.5, currency="EUR")
    >>> lg.get("demo_x")
    {'ok': True}
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.path = Path(db_path) if db_path is not None else _DEFAULT_DIR / "ledger.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # WAL lets readers and a writer proceed concurrently — the whole point of
        # choosing SQLite over the one-file-per-entry backend for shared use.
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS entries ("
                "  key TEXT PRIMARY KEY,"
                "  result TEXT NOT NULL,"      # the paid result, stored as JSON
                "  cost REAL NOT NULL,"
                "  currency TEXT NOT NULL,"
                "  created_at REAL NOT NULL,"
                "  hits INTEGER NOT NULL DEFAULT 0"
                ")"
            )

    @property
    def location(self) -> str:
        """The database file that holds the entries (for display)."""
        return str(self.path)

    def _connect(self) -> sqlite3.Connection:
        """Open a short-lived connection (timeout lets writers wait, not fail)."""
        # A generous busy timeout means concurrent writers queue rather than raise
        # "database is locked" under contention.
        return sqlite3.connect(self.path, timeout=30.0)

    def has(self, key: str) -> bool:
        """Return ``True`` if a result is already stored for ``key``."""
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM entries WHERE key = ?", (key,)).fetchone()
        return row is not None

    def get_record(self, key: str) -> dict | None:
        """Return the full stored record (result + cost + hits), or ``None``."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT key, result, cost, currency, created_at, hits FROM entries WHERE key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        # Re-hydrate the JSON result; the rest are already native column types.
        return {
            "key": row[0],
            "result": json.loads(row[1]),
            "cost": row[2],
            "currency": row[3],
            "created_at": row[4],
            "hits": row[5],
        }

    def get(self, key: str) -> Any | None:
        """Return just the stored result for ``key``, or ``None`` if absent."""
        record = self.get_record(key)
        return None if record is None else record["result"]

    def put(self, key: str, result: Any, *, cost: float = 0.0, currency: str = "USD") -> None:
        """Store ``result`` for ``key`` with its declared cost (overwrites).

        Overwriting resets the hit counter to 0, matching the JSON backend: a
        re-``put`` is a fresh entry, not a continuation of the old one.
        """
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO entries (key, result, cost, currency, created_at, hits) "
                "VALUES (?, ?, ?, ?, ?, 0) "
                "ON CONFLICT(key) DO UPDATE SET "
                "  result=excluded.result, cost=excluded.cost,"
                "  currency=excluded.currency, created_at=excluded.created_at, hits=0",
                (key, json.dumps(result, ensure_ascii=False), float(cost), currency, time.time()),
            )

    def register_hit(self, key: str) -> None:
        """Atomically increment the reuse counter for ``key`` (no-op if absent).

        The ``UPDATE ... hits = hits + 1`` is a single atomic statement, so
        concurrent hits never lose a count — the reason to prefer this backend
        over the read-modify-write of the JSON one under real concurrency.
        """
        with self._connect() as conn:
            conn.execute("UPDATE entries SET hits = hits + 1 WHERE key = ?", (key,))

    def stats(self, namespace: str | None = None) -> dict:
        """Aggregate spend + savings across entries (optionally one namespace).

        Same return shape as :meth:`wallet_helper.ledger.Ledger.stats`.
        """
        by_currency: dict[str, dict[str, float]] = {}
        entries = spent = saved = hits = 0
        with self._connect() as conn:
            if namespace is None:
                rows = conn.execute("SELECT currency, cost, hits FROM entries").fetchall()
            else:
                # Keys are "<namespace>_<sha256>"; match that prefix. '_' is a LIKE
                # wildcard, so escape it to anchor on the literal separator.
                rows = conn.execute(
                    r"SELECT currency, cost, hits FROM entries WHERE key LIKE ? ESCAPE '\'",
                    (namespace.replace("_", r"\_") + r"\_%",),
                ).fetchall()
        for currency, cost, n_hits in rows:
            entries += 1
            hits += n_hits
            spent += cost
            saved += cost * n_hits
            slot = by_currency.setdefault(currency, {"spent": 0.0, "saved": 0.0})
            slot["spent"] += cost
            slot["saved"] += cost * n_hits
        return {"entries": entries, "spent": spent, "saved": saved, "hits": hits, "by_currency": by_currency}

    def clear(self, namespace: str | None = None) -> None:
        """Delete entries — all, or just one ``namespace`` (irreversible).

        The database file itself remains; only rows are removed.
        """
        with self._connect() as conn:
            if namespace is None:
                conn.execute("DELETE FROM entries")
            else:
                conn.execute(
                    r"DELETE FROM entries WHERE key LIKE ? ESCAPE '\'",
                    (namespace.replace("_", r"\_") + r"\_%",),
                )

