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
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Protocol, runtime_checkable

import os_helper as osh

try:
    import fcntl  # POSIX advisory file locks (macOS, Linux)
except ImportError:  # pragma: no cover - Windows has no fcntl
    fcntl = None  # type: ignore[assignment]

# Default store location, outside any repo so cached results are not committed by
# accident. Overridable per instance or through the environment variable.
_DEFAULT_DIR = Path(os.environ.get("WALLET_HELPER_DIR", str(Path.home() / ".cache" / "wallet-helper")))

# One in-process lock per store directory, shared across Ledger instances, so
# threads in the same process never interleave a read-modify-write of an entry.
_DIR_LOCKS: dict[str, threading.Lock] = {}
_DIR_LOCKS_GUARD = threading.Lock()


def _atomic_write(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically, so a reader never sees a half file.

    The data goes to a temporary file in the same directory, then ``os.replace``
    swaps it into place in one step (atomic on POSIX and Windows). A concurrent
    writer or a crash mid-write can never leave a truncated or corrupt entry.
    """
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        # Never leave the temporary file behind if the swap did not happen.
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


@contextmanager
def _entry_lock(directory: Path) -> Iterator[None]:
    """Serialize read-modify-write on a store directory, within and across processes.

    Holds a per-directory :class:`threading.Lock` (so threads in this process
    take turns) and, where available, an exclusive advisory lock on a small lock
    file (so separate processes take turns too). On platforms without ``fcntl``
    the cross-process guard is skipped and only the in-process lock applies.
    """
    key = str(directory)
    with _DIR_LOCKS_GUARD:
        lock = _DIR_LOCKS.setdefault(key, threading.Lock())
    with lock:
        if fcntl is None:
            yield  # Windows: in-process lock only (documented on register_hit)
            return
        directory.mkdir(parents=True, exist_ok=True)
        handle = open(directory / ".wallet-helper.lock", "a+")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()


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

    def put(self, key: str, result: Any, *, ttl: float | None = None) -> None:
        """Store ``result`` for ``key`` (overwrites), expiring after ``ttl`` seconds."""
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

    def evict(self, *, max_entries: int | None = None, older_than: float | None = None) -> int:
        """Prune entries and return how many were removed (see :meth:`Ledger.evict`)."""
        ...


# Markers standing in for a content hash inside a canonicalised payload. The
# leading NUL means a real path or argument string never begins this way, and any
# user string that somehow does is escaped (see _canonical) so it can never be
# mistaken for a marker. Order matters: _ESC is checked first when escaping.
_ESC = "\x00wallet_helper.esc:"
_FILE_MARK = "\x00wallet_helper.file:"
_BYTES_MARK = "\x00wallet_helper.bytes:"
_SET_MARK = "\x00wallet_helper.set:"
_KEY_MARK = "\x00wallet_helper.key:"
_MARKS = (_ESC, _FILE_MARK, _BYTES_MARK, _SET_MARK, _KEY_MARK)


def _json_default(value: Any) -> str:
    """Stable JSON fallback for a value :func:`json.dumps` cannot serialise.

    Objects with a meaningful ``str`` (``enum``, ``Decimal``, ``datetime``,
    ``uuid``, numpy scalars, and so on) are keyed by that text. An object that
    carries only the default ``object`` representation would otherwise leak its
    heap address into the key, so the same argument would hash differently on
    every run and the cache would never hit. Rather than key on an address (a
    silent miss) or on the type alone (a false hit that aliases distinct
    instances), we raise and point at the tools meant for volatile handles.
    """
    if type(value).__str__ is object.__str__ and type(value).__repr__ is object.__repr__:
        name = f"{type(value).__module__}.{type(value).__qualname__}"
        raise TypeError(
            f"wallet-helper cannot build a stable cache key from a {name} instance: "
            f"it has no content-bearing repr, so its key would embed a memory address "
            f"and change every run. Exclude it with ignore=(...) or supply a key=... builder."
        )
    return str(value)


def _file_path(value: Any) -> str | None:
    """Return the string path if ``value`` names an existing file, else ``None``.

    A path reaches us in several forms: a plain ``str``, a :class:`pathlib.Path`,
    or any other :class:`os.PathLike` (``__fspath__``). All are accepted and
    resolved with :func:`os.fspath`. ``bytes`` are excluded on purpose: they are
    hashed as raw content, not treated as a filesystem path. Never raises: a value
    that cannot be resolved to an existing file (a bad ``__fspath__``, an embedded
    NUL, an over-long string) is simply reported as not a file.
    """
    if isinstance(value, (bytes, bytearray)) or not isinstance(value, (str, os.PathLike)):
        return None
    try:
        path = os.fspath(value)
        if isinstance(path, bytes):
            path = path.decode()
        return path if osh.file_exists(path) else None
    except Exception:
        # Any failure resolving or stat-ing the value means it is not a file leaf;
        # key construction must never crash before the wrapped call even runs.
        return None


def _canonical(value: Any) -> Any:
    """Replace file-path and ``bytes`` leaves with content-hash markers.

    A path argument is usually one item inside a call's
    ``{"args": ..., "kwargs": ...}`` payload, not the whole payload. Walking the
    structure lets us key such a path by the file's *bytes* rather than its text,
    so two identical files at different paths (or one file later renamed) share a
    single cache entry, and two different files never collide even when their
    paths look alike. Leaves that are neither paths nor ``bytes`` pass through
    untouched, so a payload with no file leaves serialises exactly as before.

    A user string that itself begins with a marker prefix is escaped, so a crafted
    argument can never forge a file or bytes marker and collide with a real one.
    Dict *keys* are normalised through :func:`_canonical_key`: a plain ``str`` key
    keeps its text (kwarg names, the common case), while any other key type is
    encoded structurally. Keys are normally plain identifiers, so this is rarely
    visible.
    """
    if isinstance(value, (bytes, bytearray, memoryview)):
        # Every byte-like type is keyed by its content, and hashes the same
        # whatever wrapper it arrived in. latin-1 maps bytes to text losslessly.
        return _BYTES_MARK + osh.hash_string(bytes(value).decode("latin-1"))
    path = _file_path(value)
    if path is not None:
        return _FILE_MARK + osh.hashfile(path)
    if isinstance(value, str) and value.startswith(_MARKS):
        # Keep user data and synthesised markers in disjoint spaces.
        return _ESC + value
    if isinstance(value, dict):
        return {_canonical_key(k): _canonical(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if isinstance(value, (set, frozenset)):
        # Unordered: canonicalise members then sort by their JSON form so the same
        # set always hashes the same, and a file inside a set is content-addressed.
        # The _SET_MARK sentinel keeps a set distinct from a list of equal members
        # (a user list starting with _SET_MARK is escaped, so it cannot forge one).
        members = sorted((_canonical(v) for v in value), key=_dumps)
        return [_SET_MARK, members]
    return value


def _canonical_key(key: Any) -> str:
    """Return a stable string form of a dict key so the dict always serialises.

    A plain string key is kept as is (and escaped only if it resembles a marker),
    so the common payload hashes exactly as a plain ``json.dumps`` would. A
    non-string key (a tuple, ``bytes``, an enum, or one of several mixed with
    strings) would otherwise make ``json.dumps`` raise or fail to sort; it is
    encoded as the JSON of its canonical form under a distinct ``_KEY_MARK`` so it
    never collides with a string key of the same text (``{1: v}`` vs ``{"1": v}``).
    """
    if isinstance(key, str):
        return _ESC + key if key.startswith(_MARKS) else key
    return _KEY_MARK + _dumps(_canonical(key))


def _dumps(obj: Any) -> str:
    """Serialise an already-canonical object to a stable, key-sorted JSON string."""
    return json.dumps(obj, sort_keys=True, default=_json_default, ensure_ascii=False)


def _digest(payload: Any) -> str:
    """Return a stable content hash for a key payload.

    Delegates to os_helper's hashing, so wallet-helper reuses the suite's tested
    content-addressing instead of rolling its own. The payload is first
    canonicalised (:func:`_canonical`), which resolves every file-path and
    ``bytes`` leaf to its content hash *wherever it sits* (top level or nested in
    the arguments), then the whole canonical form is hashed as key-sorted JSON. So
    a file reached by a different path still hits the cache, and one rule governs
    top-level and nested values alike.

    Parameters
    ----------
    payload : Any
        A path to an existing file as a ``str`` or any :class:`os.PathLike`, raw
        ``bytes``, or any JSON-serialisable value, at any depth. Files and
        ``bytes`` are keyed by content (in disjoint spaces: a path and equal raw
        bytes do not alias); everything else by its canonical JSON.

    Returns
    -------
    str
        A fixed-length hex digest.
    """
    # One rule for every depth: canonicalise (files and bytes -> content markers),
    # then hash the key-sorted JSON. Order-independent and enum-tolerant.
    return osh.hash_string(_dumps(_canonical(payload)))


def is_fresh(record: dict, *, now: float | None = None) -> bool:
    """Return ``True`` if a record has not expired.

    Parameters
    ----------
    record : dict
        A stored record, which may carry an ``expires_at`` timestamp.
    now : float, optional
        The current time; defaults to :func:`time.time`. Passing it lets a caller
        judge many records against one instant.

    Returns
    -------
    bool
        ``True`` when there is no expiry, or the expiry is still in the future.
    """
    expires_at = record.get("expires_at")
    if expires_at is None:
        return True
    return (now if now is not None else time.time()) < expires_at


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

    Notes
    -----
    A ``str`` or :class:`os.PathLike` argument that names an existing file is
    keyed by the file's content, by design, so the same file reached by a
    different path still hits (this applies to a path used as an argument or as a
    value; a plain ``str`` used as a dict *key* keeps its text). Two consequences
    worth knowing:

    - A string you meant as plain data (a title, an id) that *happens* to match an
      existing file in the working directory is content-addressed too. If that is
      not what you want, wrap the value so it is not a bare path, or exclude the
      argument with ``ignore=`` / a ``key=`` builder.
    - If a file is deleted in the brief moment between detection and hashing, the
      key falls back to the path text for that call. The wrapped function would
      fail to read the missing file anyway, so no stale result is served.

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
    max_entries : int, optional
        A size cap. When set, each :meth:`put` also evicts down to the newest
        ``max_entries`` entries, so the store cannot grow without bound. ``None``
        (default) means no automatic bound; call :meth:`evict` yourself.

    Examples
    --------
    >>> import os_helper as osh
    >>> with osh.temporary_folder() as tmp:
    ...     Ledger(tmp).has("demo_x")
    False
    """

    def __init__(self, cache_dir: str | Path | None = None, max_entries: int | None = None) -> None:
        self.dir = Path(cache_dir) if cache_dir is not None else _DEFAULT_DIR
        self.max_entries = max_entries

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

    def put(self, key: str, result: Any, *, ttl: float | None = None) -> None:
        """Store ``result`` for ``key`` (overwrites any previous entry).

        Parameters
        ----------
        key : str
            The ledger key (see :func:`make_key`).
        result : Any
            The JSON-serialisable result to store.
        ttl : float, optional
            Seconds until the entry is considered stale. ``None`` (default) means
            it never expires. A stale entry is treated as a miss on the next call
            and is removed by :meth:`evict`.
        """
        osh.make_directory(str(self.dir))
        now = time.time()
        record = {
            "key": key,
            "result": result,
            "created_at": now,
            "expires_at": now + ttl if ttl is not None else None,
            "hits": 0,  # incremented every time the cached result is reused
        }
        # Atomic swap: overwriting an entry never exposes a partial file, so a
        # concurrent writer or a crash cannot corrupt it.
        _atomic_write(self._path(key), json.dumps(record, ensure_ascii=False, indent=2))
        if self.max_entries is not None:
            self.evict(max_entries=self.max_entries)

    def register_hit(self, key: str) -> None:
        """Count one reuse of the cached result for ``key`` (no-op if absent).

        The read-modify-write runs under a lock so concurrent hits do not lose a
        count: threads in this process take turns, and separate processes take
        turns too where advisory file locks are available (POSIX). On Windows the
        cross-process count is best-effort; use :class:`SqliteLedger` for an exact
        count under heavy multi-process concurrency.
        """
        with _entry_lock(self.dir):
            record = self.get_record(key)
            if record is None:
                return
            record["hits"] = int(record.get("hits", 0)) + 1
            _atomic_write(self._path(key), json.dumps(record, ensure_ascii=False, indent=2))

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

    def evict(self, *, max_entries: int | None = None, older_than: float | None = None) -> int:
        """Prune entries and return how many were removed.

        Expired entries (past their ``ttl``) are always removed. In addition:

        Parameters
        ----------
        max_entries : int, optional
            Keep only the newest ``max_entries`` by creation time; remove the
            rest. This is a simple size cap.
        older_than : float, optional
            Remove entries created more than this many seconds ago.

        Returns
        -------
        int
            The number of entries removed.
        """
        now = time.time()
        # Read every entry once, with its creation time, so we can rank and prune.
        items = []
        for path in self.dir.glob("*.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            items.append((path, float(record.get("created_at", 0.0)), record))

        doomed: set[Path] = set()
        for path, created_at, record in items:
            if not is_fresh(record, now=now):
                doomed.add(path)  # expired entries always go
            elif older_than is not None and (now - created_at) > older_than:
                doomed.add(path)
        if max_entries is not None:
            survivors = sorted((it for it in items if it[0] not in doomed), key=lambda it: it[1], reverse=True)
            for path, _created_at, _record in survivors[max_entries:]:
                doomed.add(path)  # keep the newest max_entries, drop the older tail

        osh.remove_files([str(p) for p in doomed])
        return len(doomed)
