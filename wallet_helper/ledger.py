"""Content-addressed ledger, so a heavy call runs once and is remembered.

The storage half of wallet-helper. A call is identified by a key built from a
namespace plus a payload (the arguments, file, or bytes that determine the
result). The ledger stores the result under that key, so an identical call is
served from disk instead of running again, across process restarts.

The default store is a directory with one JSON file per entry: local, no server,
easy to inspect and to delete. It is content-addressed, so a renamed input file
still hits and two different inputs never collide.

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import os_helper as osh

# Default store location, outside any repo so cached results are not committed by
# accident. Overridable per instance or through the environment variable.
_DEFAULT_DIR = Path(os.environ.get("WALLET_HELPER_DIR", str(Path.home() / ".cache" / "wallet-helper")))


@runtime_checkable
class LedgerLike(Protocol):
    """The storage contract every ledger backend fulfils.

    The default :class:`Ledger` keeps one JSON file per entry, which is ideal for
    a single process. :class:`wallet_helper.sqlite_ledger.SqliteLedger` keeps
    everything in one SQLite file for a shared, concurrency-safe store. A
    :class:`wallet_helper.guard.Wallet` and the command-line tools accept either.
    """

    @property
    def location(self) -> str:
        """A readable pointer to where entries live (a directory or a file)."""
        ...

    def has(self, key: str) -> bool:
        """Return ``True`` if a result is already stored for ``key``."""
        ...

    def get(self, key: str) -> Any | None:
        """Return the stored result for ``key``, or ``None`` if absent."""
        ...

    def get_record(self, key: str) -> dict | None:
        """Return the full stored record, or ``None`` if absent."""
        ...

    def put(self, key: str, result: Any) -> None:
        """Store ``result`` for ``key`` (overwrites any previous entry)."""
        ...

    def register_hit(self, key: str) -> None:
        """Count one reuse of the cached result for ``key`` (no-op if absent)."""
        ...

    def stats(self, namespace: str | None = None) -> dict:
        """Return ``{entries, hits}`` for the whole store or one namespace."""
        ...

    def clear(self, namespace: str | None = None) -> None:
        """Remove entries, all of them or just one namespace (irreversible)."""
        ...


def _digest(payload: Any) -> str:
    """Return a stable content hash for a key payload.

    Delegates to os_helper's hashing, so wallet-helper reuses the suite's tested
    content-addressing instead of rolling its own.

    Parameters
    ----------
    payload : Any
        A path to an existing file (hashed by its bytes), raw ``bytes``, or any
        JSON-serialisable value (hashed by its canonical key-sorted JSON).

    Returns
    -------
    str
        A fixed-length hex digest.
    """
    if isinstance(payload, (bytes, bytearray)):
        # latin-1 is a lossless byte to text mapping, so any bytes hash stably.
        return osh.hash_string(bytes(payload).decode("latin-1"))
    if isinstance(payload, (str, Path)) and osh.file_exists(str(payload)):
        # Hash the file by content, so a rename still hits and two files differ.
        return osh.hashfile(str(payload))
    # Everything else: canonical JSON, order-independent and enum-tolerant.
    return osh.hash_string(json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False))


def make_key(namespace: str, payload: Any) -> str:
    """Build a ledger key from a ``namespace`` and a content ``payload``.

    Parameters
    ----------
    namespace : str
        A scope for the call, for example ``"transcribe"`` or ``"openai.chat"``,
        so unrelated calls do not collide even if their payloads hash alike.
    payload : Any
        See :func:`_digest`.

    Returns
    -------
    str
        ``"<namespace>_<hash>"``, safe to use as a filename.

    Examples
    --------
    >>> make_key("demo", {"b": 2, "a": 1}) == make_key("demo", {"a": 1, "b": 2})
    True
    """
    return f"{namespace}_{_digest(payload)}"


class Ledger:
    """A directory-backed store of results, one JSON file per entry.

    Parameters
    ----------
    cache_dir : str or pathlib.Path, optional
        Where entries live. Defaults to ``$WALLET_HELPER_DIR`` then
        ``~/.cache/wallet-helper``.

    Examples
    --------
    >>> import os_helper as osh
    >>> with osh.temporary_folder() as tmp:
    ...     Ledger(tmp).has("demo_x")
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
        return osh.file_exists(str(self._path(key)))

    def get_record(self, key: str) -> dict | None:
        """Return the full stored record, or ``None`` if absent."""
        path = self._path(key)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def get(self, key: str) -> Any | None:
        """Return just the stored result for ``key``, or ``None`` if absent."""
        record = self.get_record(key)
        return None if record is None else record["result"]

    def put(self, key: str, result: Any) -> None:
        """Store ``result`` for ``key`` (overwrites any previous entry)."""
        osh.make_directory(str(self.dir))
        record = {
            "key": key,
            "result": result,
            "created_at": time.time(),
            "hits": 0,  # incremented every time the cached result is reused
        }
        self._path(key).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    def register_hit(self, key: str) -> None:
        """Count one reuse of the cached result for ``key`` (no-op if absent)."""
        record = self.get_record(key)
        if record is None:
            return
        record["hits"] = int(record.get("hits", 0)) + 1
        self._path(key).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    def clear(self, namespace: str | None = None) -> None:
        """Delete entries, all or just one ``namespace`` (irreversible).

        With a namespace, only its entries are removed (this is what a memoized
        function's ``cache_clear()`` calls). Without one, the whole directory is
        removed and recreated lazily on the next :meth:`put`.
        """
        if namespace is None:
            osh.remove_directory(str(self.dir))
            return
        # Keys are "<namespace>_<hash>", one file each; unlink the matches.
        osh.remove_files([str(p) for p in self.dir.glob(f"{namespace}_*.json")])

    def stats(self, namespace: str | None = None) -> dict:
        """Count stored entries and their reuses, for the store or one namespace.

        Parameters
        ----------
        namespace : str, optional
            Restrict the count to entries under this namespace. ``None`` (default)
            counts the whole ledger.

        Returns
        -------
        dict
            ``{"entries": int, "hits": int}`` where ``hits`` is how many times a
            cached result was reused, that is, how many real calls were saved.
        """
        entries = hits = 0
        pattern = "*.json" if namespace is None else f"{namespace}_*.json"
        for path in self.dir.glob(pattern):
            record = json.loads(path.read_text(encoding="utf-8"))
            entries += 1
            hits += int(record.get("hits", 0))
        return {"entries": entries, "hits": hits}
