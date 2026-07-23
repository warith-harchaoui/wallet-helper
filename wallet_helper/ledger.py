"""Content-addressed ledger — remember results so a paid call runs once.

Module summary
--------------
The caching half of wallet-helper. A billable call is identified by a **key**
derived from a namespace plus a payload (the arguments / file / bytes that
determine the result). The ledger stores the result JSON keyed by that content
hash, so the same call never runs — and never bills — twice. It also records the
declared cost of each entry and counts cache hits, so it can report how much
money the cache has saved.

The store is a directory of one JSON file per entry (local-first, no server,
human-inspectable). It is provider-agnostic: HTTP APIs, a local paid binary, a
metered function — anything with a cost.

Author
------
Warith HARCHAOUI — https://linkedin.com/in/warith-harchaoui
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

# Default store location — outside any repo so results (which may hold sensitive
# payloads) are never accidentally committed. Overridable per call or via env.
_DEFAULT_DIR = Path(os.environ.get("WALLET_HELPER_DIR", str(Path.home() / ".cache" / "wallet-helper")))


@runtime_checkable
class LedgerLike(Protocol):
    """The storage contract every ledger backend fulfils.

    :class:`Ledger` (a directory of JSON files) is the default, zero-dependency
    implementation; :class:`wallet_helper.sqlite_ledger.SqliteLedger` is an
    interchangeable single-file backend for a concurrency-safe shared store.
    :class:`wallet_helper.guard.Wallet` and every CLI / surface accept either —
    anything satisfying this protocol works.
    """

    @property
    def location(self) -> str:
        """A human-readable pointer to where entries live (dir or file path)."""
        ...

    def has(self, key: str) -> bool:
        """Return ``True`` if a result is already stored for ``key``."""
        ...

    def get(self, key: str) -> Any | None:
        """Return the stored result for ``key``, or ``None`` if absent."""
        ...

    def get_record(self, key: str) -> dict | None:
        """Return the full stored record (result + cost + hits), or ``None``."""
        ...

    def put(self, key: str, result: Any, *, cost: float = 0.0, currency: str = "USD") -> None:
        """Store ``result`` for ``key`` with its declared cost (overwrites)."""
        ...

    def register_hit(self, key: str) -> None:
        """Increment the reuse counter for ``key`` (no-op if absent)."""
        ...

    def stats(self, namespace: str | None = None) -> dict:
        """Aggregate spend + savings across entries (optionally one namespace)."""
        ...

    def clear(self, namespace: str | None = None) -> None:
        """Remove entries (all, or just one namespace); irreversible."""
        ...


def _digest(payload: Any) -> str:
    """Return a stable sha256 hex for a key payload, content-addressed.

    Parameters
    ----------
    payload : Any
        ``bytes`` (hashed directly), a path to an existing file (hashed by its
        content, in chunks), or any JSON-serialisable value (hashed by its
        canonical, key-sorted JSON).

    Returns
    -------
    str
        64-char hex sha256.
    """
    h = hashlib.sha256()
    if isinstance(payload, (bytes, bytearray)):
        h.update(payload)
    elif isinstance(payload, (str, Path)) and Path(payload).is_file():
        # Content-address a file so a rename still hits and two files never clash.
        with open(payload, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    else:
        # Everything else: canonical JSON (order-independent, tolerant of enums).
        h.update(json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8"))
    return h.hexdigest()


def make_key(namespace: str, payload: Any) -> str:
    """Build a ledger key from a ``namespace`` and a content ``payload``.

    Parameters
    ----------
    namespace : str
        A scope for the call, e.g. ``"gladia"`` or ``"openai.chat"`` — keeps
        unrelated calls from colliding even if their payloads hash alike.
    payload : Any
        See :func:`_digest`.

    Returns
    -------
    str
        ``"<namespace>_<sha256>"`` — safe as a filename.

    Examples
    --------
    >>> make_key("demo", {"b": 2, "a": 1}) == make_key("demo", {"a": 1, "b": 2})
    True
    """
    return f"{namespace}_{_digest(payload)}"


class Ledger:
    """A directory-backed store of results for billable calls.

    Parameters
    ----------
    cache_dir : str or pathlib.Path, optional
        Where entries live. Defaults to ``$WALLET_HELPER_DIR`` then
        ``~/.cache/wallet-helper``.

    Examples
    --------
    >>> import tempfile
    >>> lg = Ledger(tempfile.mkdtemp())
    >>> lg.has("demo_x")
    False
    """

    def __init__(self, cache_dir: str | Path | None = None) -> None:
        self.dir = Path(cache_dir) if cache_dir is not None else _DEFAULT_DIR

    @property
    def location(self) -> str:
        """The directory that holds the JSON entries (for display)."""
        return str(self.dir)

    def _path(self, key: str) -> Path:
        """Absolute path of the JSON entry for ``key``."""
        return self.dir / f"{key}.json"

    def has(self, key: str) -> bool:
        """Return ``True`` if a result is already stored for ``key``."""
        return self._path(key).exists()

    def get_record(self, key: str) -> dict | None:
        """Return the full stored record (result + cost + hits), or ``None``."""
        path = self._path(key)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def get(self, key: str) -> Any | None:
        """Return just the stored result for ``key``, or ``None`` if absent."""
        record = self.get_record(key)
        return None if record is None else record["result"]

    def put(self, key: str, result: Any, *, cost: float = 0.0, currency: str = "USD") -> None:
        """Store ``result`` for ``key`` with its declared cost (overwrites).

        Parameters
        ----------
        key : str
            The ledger key (see :func:`make_key`).
        result : Any
            The JSON-serialisable result of the paid call.
        cost, currency : float, str
            What this call cost — recorded for spend reporting.
        """
        self.dir.mkdir(parents=True, exist_ok=True)
        record = {
            "key": key,
            "result": result,
            "cost": cost,
            "currency": currency,
            "created_at": time.time(),
            "hits": 0,  # incremented every time the cached result is reused
        }
        self._path(key).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    def register_hit(self, key: str) -> None:
        """Increment the reuse counter for ``key`` (best-effort, no-op if absent)."""
        record = self.get_record(key)
        if record is None:
            return
        record["hits"] = int(record.get("hits", 0)) + 1
        self._path(key).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    def clear(self, namespace: str | None = None) -> None:
        """Delete entries — all of them, or just one ``namespace`` (irreversible).

        Parameters
        ----------
        namespace : str, optional
            When given, only entries under this namespace are removed (used by a
            memoized function's ``cache_clear()``). When ``None``, the whole
            store directory is removed and recreated lazily on the next
            :meth:`put`.
        """
        if namespace is None:
            if self.dir.exists():
                shutil.rmtree(self.dir)
            return
        # Keys are "<namespace>_<sha256>", one file each — unlink the matches.
        for path in self.dir.glob(f"{namespace}_*.json"):
            path.unlink()

    def stats(self, namespace: str | None = None) -> dict:
        """Aggregate spend + savings across entries (optionally one namespace).

        Parameters
        ----------
        namespace : str, optional
            Restrict the aggregation to entries under this namespace; ``None``
            (default) aggregates the whole ledger.

        Returns
        -------
        dict
            ``{entries, spent, saved, hits, by_currency}`` where ``spent`` is the
            sum of entry costs (money actually paid, once each) and ``saved`` is
            the sum of ``cost * hits`` (money the cache avoided re-paying), both
            broken down ``by_currency``.
        """
        entries = spent = saved = hits = 0
        by_currency: dict[str, dict[str, float]] = {}
        pattern = "*.json" if namespace is None else f"{namespace}_*.json"
        for path in self.dir.glob(pattern):
            record = json.loads(path.read_text(encoding="utf-8"))
            cur = record.get("currency", "USD")
            cost = float(record.get("cost", 0.0))
            n_hits = int(record.get("hits", 0))
            entries += 1
            hits += n_hits
            spent += cost
            saved += cost * n_hits
            slot = by_currency.setdefault(cur, {"spent": 0.0, "saved": 0.0})
            slot["spent"] += cost
            slot["saved"] += cost * n_hits
        return {"entries": entries, "spent": spent, "saved": saved, "hits": hits, "by_currency": by_currency}
