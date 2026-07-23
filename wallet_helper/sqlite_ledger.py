"""SQLite-backed ledger: one file, concurrency-safe, with a cross-process lease.

An interchangeable backend for :class:`wallet_helper.ledger.Ledger`. The default
keeps one JSON file per entry, which is great for a single process. This backend
keeps everything in one SQLite file with write-ahead logging, so many processes
or hosts can share one store and update it without clobbering each other's reuse
counters.

It also adds a lease table (``claim`` / ``submit`` / ``release``) used for
cross-process single-flight: while one caller computes a key, others see it as
pending and wait, so the same heavy call is not run twice at the same time.

``sqlite3`` ships with Python, so this stays dependency-light: the shared,
concurrency-safe store without running a database server.

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from wallet_helper.ledger import _DEFAULT_DIR


class SqliteLedger:
    """A single-file SQLite store of results, with an in-flight lease table.

    Parameters
    ----------
    db_path : str or pathlib.Path, optional
        The database file. Defaults to ``<default ledger dir>/ledger.db`` (the
        same base as :class:`~wallet_helper.ledger.Ledger`, honouring
        ``$WALLET_HELPER_DIR``). Parent directories are created if missing.

    Examples
    --------
    >>> import os_helper as osh
    >>> with osh.temporary_folder() as tmp:
    ...     lg = SqliteLedger(tmp + "/ledger.db")
    ...     lg.put("demo_x", {"ok": True})
    ...     lg.get("demo_x")
    {'ok': True}
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.path = Path(db_path) if db_path is not None else _DEFAULT_DIR / "ledger.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            # WAL lets readers and one writer proceed at once, which is the point
            # of choosing SQLite over one-file-per-entry for shared use.
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS entries ("
                "  key TEXT PRIMARY KEY,"
                "  result TEXT NOT NULL,"      # the result, stored as JSON
                "  created_at REAL NOT NULL,"
                "  expires_at REAL,"           # NULL means the entry never expires
                "  hits INTEGER NOT NULL DEFAULT 0"
                ")"
            )
            # One row per key while a leader computes it, so concurrent callers
            # wait instead of running the same work.
            conn.execute(
                "CREATE TABLE IF NOT EXISTS pending ("
                "  key TEXT PRIMARY KEY,"
                "  leased_at REAL NOT NULL"
                ")"
            )

    @property
    def location(self) -> str:
        """The database file that holds the entries (for display)."""
        return str(self.path)

    def _connect(self) -> sqlite3.Connection:
        """Open a short-lived connection; the timeout makes writers wait, not fail."""
        return sqlite3.connect(self.path, timeout=30.0)

    def has(self, key: str) -> bool:
        """Return ``True`` if a result is already stored for ``key``."""
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM entries WHERE key = ?", (key,)).fetchone()
        return row is not None

    def get_record(self, key: str) -> dict | None:
        """Return the full stored record, or ``None`` if absent."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT key, result, created_at, expires_at, hits FROM entries WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        return {"key": row[0], "result": json.loads(row[1]), "created_at": row[2], "expires_at": row[3], "hits": row[4]}

    def get(self, key: str) -> Any | None:
        """Return just the stored result for ``key``, or ``None`` if absent."""
        record = self.get_record(key)
        return None if record is None else record["result"]

    def put(self, key: str, result: Any, *, ttl: float | None = None) -> None:
        """Store ``result`` for ``key`` (overwrites, resetting the hit counter).

        With ``ttl`` set, the entry expires that many seconds from now and is then
        treated as a miss on the next :meth:`claim` and removed by :meth:`evict`.
        """
        now = time.time()
        expires_at = now + ttl if ttl is not None else None
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO entries (key, result, created_at, expires_at, hits) VALUES (?, ?, ?, ?, 0) "
                "ON CONFLICT(key) DO UPDATE SET result=excluded.result, created_at=excluded.created_at, "
                "expires_at=excluded.expires_at, hits=0",
                (key, json.dumps(result, ensure_ascii=False), now, expires_at),
            )

    def register_hit(self, key: str) -> None:
        """Atomically count one reuse of ``key`` (no-op if absent).

        The ``hits = hits + 1`` runs as a single statement, so concurrent reuses
        never lose a count. This is the reason to prefer this backend over the
        read-modify-write of the JSON one under real concurrency.
        """
        with self._connect() as conn:
            conn.execute("UPDATE entries SET hits = hits + 1 WHERE key = ?", (key,))

    def stats(self, namespace: str | None = None) -> dict:
        """Count stored entries and their reuses, for the store or one namespace."""
        with self._connect() as conn:
            if namespace is None:
                row = conn.execute("SELECT COUNT(*), COALESCE(SUM(hits), 0) FROM entries").fetchone()
            else:
                like = (namespace.replace("_", r"\_") + r"\_%",)
                row = conn.execute(
                    r"SELECT COUNT(*), COALESCE(SUM(hits), 0) FROM entries WHERE key LIKE ? ESCAPE '\'", like
                ).fetchone()
        return {"entries": row[0], "hits": row[1]}

    def clear(self, namespace: str | None = None) -> None:
        """Delete entries, all or just one ``namespace`` (irreversible).

        The database file itself remains; only rows are removed.
        """
        with self._connect() as conn:
            if namespace is None:
                conn.execute("DELETE FROM entries")
                conn.execute("DELETE FROM pending")
            else:
                like = (namespace.replace("_", r"\_") + r"\_%",)
                conn.execute(r"DELETE FROM entries WHERE key LIKE ? ESCAPE '\'", like)
                conn.execute(r"DELETE FROM pending WHERE key LIKE ? ESCAPE '\'", like)

    # --- Cross-process single-flight (claim / submit / release) ---------------
    # One leader computes a key while others wait, so the same heavy call is not
    # run twice at once across processes or hosts sharing this file.

    def claim(self, key: str, lease_seconds: float = 300.0) -> dict:
        """Get the cached result, or lease the right to compute it.

        Parameters
        ----------
        key : str
            The ledger key (see :func:`wallet_helper.ledger.make_key`).
        lease_seconds : float, optional
            How long a lease is honoured before it counts as abandoned, so a
            crashed leader cannot block waiters forever. Defaults to 300 s.

        Returns
        -------
        dict
            ``{"status": "hit", "result": ...}`` if it is already computed,
            ``{"status": "leased"}`` if you are the leader (compute, then
            :meth:`submit`), or ``{"status": "pending"}`` if another caller is
            computing it (wait and claim again).
        """
        conn = self._connect()
        conn.isolation_level = None  # take explicit control of the transaction
        try:
            # BEGIN IMMEDIATE grabs the write lock now, so the check-then-lease
            # below cannot race another process doing the same.
            conn.execute("BEGIN IMMEDIATE")
            now = time.time()
            row = conn.execute("SELECT result, expires_at FROM entries WHERE key = ?", (key,)).fetchone()
            if row is not None and (row[1] is None or now < row[1]):
                # A fresh entry: reuse it. An expired one falls through to re-lease.
                conn.execute("UPDATE entries SET hits = hits + 1 WHERE key = ?", (key,))
                conn.execute("COMMIT")
                return {"status": "hit", "result": json.loads(row[0])}
            lease = conn.execute("SELECT leased_at FROM pending WHERE key = ?", (key,)).fetchone()
            if lease is not None and (now - lease[0]) < lease_seconds:
                conn.execute("COMMIT")
                return {"status": "pending"}
            # No fresh entry and no live lease: grant one, stealing a stale lease too.
            conn.execute(
                "INSERT INTO pending (key, leased_at) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET leased_at = excluded.leased_at",
                (key, now),
            )
            conn.execute("COMMIT")
            return {"status": "leased"}
        finally:
            conn.close()

    def submit(self, key: str, result: Any, *, ttl: float | None = None) -> dict:
        """Store a leader's result and release its lease; return the record."""
        self.put(key, result, ttl=ttl)
        with self._connect() as conn:
            conn.execute("DELETE FROM pending WHERE key = ?", (key,))
        return self.get_record(key)

    def release(self, key: str) -> None:
        """Drop a lease without storing a result, so a waiter can take over."""
        with self._connect() as conn:
            conn.execute("DELETE FROM pending WHERE key = ?", (key,))

    def extend(self, key: str) -> bool:
        """Renew a lease so a long job is not treated as abandoned.

        A leader running work longer than ``lease_seconds`` calls this (directly
        or through :meth:`heartbeat`) to reset the lease clock, so waiters do not
        steal leadership from a job that is still making progress.

        Returns
        -------
        bool
            ``True`` if a lease existed and was renewed, ``False`` otherwise.
        """
        with self._connect() as conn:
            cur = conn.execute("UPDATE pending SET leased_at = ? WHERE key = ?", (time.time(), key))
        return cur.rowcount > 0

    @contextmanager
    def heartbeat(self, key: str, *, interval: float = 60.0) -> Iterator[None]:
        """Renew ``key``'s lease every ``interval`` seconds for the duration of a block.

        Wrap a long computation in this so its lease never lapses:

        >>> import os_helper as osh
        >>> with osh.temporary_folder() as tmp:
        ...     lg = SqliteLedger(tmp + "/ledger.db")
        ...     _ = lg.claim("job_1")
        ...     with lg.heartbeat("job_1", interval=0.05):
        ...         result = 6 * 7            # a long job, kept alive meanwhile
        ...     _ = lg.submit("job_1", result)
        ...     lg.get("job_1")
        42
        """
        stop = threading.Event()

        def _renew() -> None:
            # Ping until the block exits; wait() returns True only when stopped.
            while not stop.wait(interval):
                self.extend(key)

        thread = threading.Thread(target=_renew, daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop.set()
            thread.join(timeout=interval)

    def evict(self, *, max_entries: int | None = None, older_than: float | None = None) -> int:
        """Prune entries and return how many were removed.

        Expired entries are always removed. With ``older_than``, entries created
        more than that many seconds ago go too. With ``max_entries``, only the
        newest ``max_entries`` by creation time are kept.
        """
        now = time.time()
        with self._connect() as conn:
            before = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
            conn.execute("DELETE FROM entries WHERE expires_at IS NOT NULL AND expires_at <= ?", (now,))
            if older_than is not None:
                conn.execute("DELETE FROM entries WHERE created_at < ?", (now - older_than,))
            if max_entries is not None:
                # Keep the newest max_entries; delete anything ranked below them.
                conn.execute(
                    "DELETE FROM entries WHERE key NOT IN ("
                    "  SELECT key FROM entries ORDER BY created_at DESC LIMIT ?"
                    ")",
                    (max_entries,),
                )
            after = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        return before - after
