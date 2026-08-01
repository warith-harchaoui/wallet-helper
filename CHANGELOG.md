# Changelog

All notable changes to wallet-helper are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to
semantic versioning.

## [0.3.1] - 2026-08-01

### Fixed
- **`SqliteLedger` leaked a connection (and a file descriptor) on every call.**
  `sqlite3.Connection` used as its own context manager commits or rolls back,
  but it never closes the connection; every `has`, `get`, `get_record`, `put`,
  `register_hit`, `stats`, `clear`, and `evict` opened one that was then never
  released. A long-running process backed by `SqliteLedger` (a memoized
  function hit repeatedly, or the HTTP dedup server) would accumulate open
  file descriptors without bound and eventually fail with "too many open
  files". Every call now goes through a session helper that closes its
  connection when it is done.
- **An opaque object's key silently dropped state inherited from a base
  class.** Keying an object with only the default `repr` (see 0.3.0) reads
  `__slots__` to find its state; a subclass's `__slots__` only lists the
  names *it* adds, not what a base class contributes, so any state held in an
  inherited slot was missing from the key. Two instances that differed only
  in that inherited slot then hashed identically — a real cache collision (a
  wrong cached result served for a different logical input), not merely a
  missed hit. `__slots__` is now collected across the whole MRO.
  `__weakref__`, a runtime plumbing slot rather than user state, is skipped
  like `__dict__`.
- **A namespace containing a glob or SQL `LIKE` metacharacter leaked into an
  unrelated namespace.** `Ledger.stats("a*b")` / `.clear("a*b")` used the
  namespace directly in a glob pattern, so `*` (or `?`, `[`) matched more than
  the literal namespace name; `SqliteLedger.stats("a%")` / `.clear("a%")` had
  the same problem with SQL `LIKE`'s `%`. Namespaces are normally a
  `module.qualname` and never hit this, but a custom namespace could. Both
  backends now escape the namespace before building the pattern.
- **`RemoteLedger` / the HTTP server could not address a key whose namespace
  contains a `/`.** `GET /result/{key}` only matched the first path segment,
  so a non-default namespace with a slash silently 404'd instead of finding
  its result (a known, documented limitation of 0.3.0). The route now uses a
  path converter that matches the whole key.

### Testing
- Every self-contained code block in `EXAMPLES.md` (the ones using
  `osh.temporary_folder`, per that file's own convention) is now executed as
  a real test (`tests/test_examples_md.py`), so a future change that breaks
  the cookbook fails CI instead of only being noticed by a reader.
- The `fcntl`-less lock fallback (the Windows path, where `register_hit` is
  guarded only by the in-process lock) now has a dedicated test that simulates
  a missing `fcntl` on any OS and proves concurrent hits are still not lost.

### CI
- **Verify the install procedure on all three target OSes.** A new `smoke`
  job installs the package and its extras on Linux (🐧), macOS (🍎), and
  Windows (🪟), then proves a fresh install works: it imports, both
  command-line entry points respond, and a memoize round-trip runs the work
  exactly once (`scripts/smoke_install.py`). This is what makes Windows a
  first-class install target again without paying for the whole suite on that
  runner: the exhaustive `pytest` suite still runs on Linux (full version
  range) and macOS (newest), where it is fast and reliable. The reason the
  full suite is not run on Windows is the cross-process test, whose driver is
  a `spawn`-based `multiprocessing.Pool` that is minutes-slow on Windows
  runners; the guarantee it proves rides on SQLite's atomic lease, which is
  OS-independent. That test is also marked to skip on Windows for anyone who
  runs the suite on a Windows dev machine.

## [0.3.0] - 2026-07-24

### Added
- **Content-address file arguments wherever they appear.** A file path is now
  keyed by the file's bytes even when it is one argument among several, not only
  when it is the whole payload. Two identical files reached by different paths
  (a rename, or a byte-for-byte copy in another folder) share a single cache
  entry, and two different files never collide even if their names look alike.
  The key builder walks the call's `{"args", "kwargs"}` structure and replaces
  each file-path or `bytes` leaf with its os-helper content hash.
- Path arguments are recognised as a `str` or any `os.PathLike`
  (`pathlib.Path` and friends), resolved through `os.fspath`. `bytes` stay raw
  content, never treated as a filesystem path. Non-file strings are untouched,
  so a payload with no file leaves hashes exactly as before.

### Changed
- **One key rule at every depth.** Top-level and nested values now go through the
  same canonicaliser, so a file path and equal raw `bytes` are consistently kept
  in **distinct key spaces** for text and binary content alike (previously they
  aliased only for ASCII, at the top level). This changes the computed key for a
  payload that is a bare `bytes` object or that carries nested `bytes`; such
  entries recompute once after upgrading.
- Sets and frozensets are canonicalised (members content-addressed, order
  independent) and kept distinct from a list of the same members.

### Hardened
- Key construction never raises: a misbehaving `os.PathLike` whose `__fspath__`
  throws is treated as plain data instead of crashing the wrapped call.
- A crafted argument string can no longer forge an internal content marker and
  collide with a real file or bytes key (markers are NUL-prefixed and any
  user string that resembles one is escaped).
- Every byte-like argument (`bytes`, `bytearray`, `memoryview`) is content
  addressed and keys deterministically, the same whatever wrapper it arrived in.
- An argument that has only the default object representation (whose `str` would
  embed a memory address) is now **keyed by its own state** (`__dict__` or
  `__slots__`), canonicalised, instead of by that address. So the same object
  hits across processes, two objects with different state never collide, and a
  file path held in an object's state is content-addressed like any other. This
  replaces the previous behavior of keying on the address (silent cross-process
  misses and a store that filled with duplicates). Volatile handles held inside
  such an object should still be dropped with `ignore=(...)` or a `key=...`
  builder. Values with a content-bearing `str` (`enum`, `Decimal`, `datetime`,
  `uuid`, numpy scalars, ...) are keyed by that text, as before.
- A function, method, class, or builtin passed as an argument (a callback or
  strategy) is keyed by its stable `(module, qualified name)` rather than the
  address in its repr, so it dedups across processes instead of never hitting. A
  `functools.partial` is keyed structurally (wrapped callable plus bound args).
- Key construction no longer crashes on a self-referential argument graph (a
  cycle resolves to a stable marker) or on an object whose `__getattr__` raises
  something other than `AttributeError`.
- Dicts with non-string keys (a tuple, `bytes`, an enum, or a mix of `int` and
  `str`) no longer crash key construction; keys are normalised so the payload
  always serialises and distinct keys never alias (`{1: v}` and `{"1": v}` stay
  separate).

## [0.2.2] - 2026-07-23

### Documentation
- Added a hosted **Documentation** link (Sphinx API docs on the AI Helpers site)
  to the README and LISEZMOI, matching the other suite helpers.
- Refreshed `LANDSCAPE.md` against the current ecosystem: added the async-first
  decorator caches `cashews` and `cacheme` (both with built-in stampede/single-
  flight protection but redis-bound for the cross-process case), and the
  semantic LLM cache GPTCache; added a "Two things wallet-helper is not" section
  distinguishing exact content-addressed reuse from semantic matching and from
  HTTP-protocol caches (`requests-cache`, `hishel`). Docs-only; no code change.

## [0.2.1] - 2026-07-23

### Documentation
- Use **absolute URLs** for the logo image and the LICENSE link in the README
  and LISEZMOI, so they render on the PyPI project page (PyPI does not resolve
  repo-relative paths, unlike GitHub). Docs-only; no code change.

## [0.2.0] - 2026-07-23

This release refocuses wallet-helper on one job: never run the same heavy call
twice. The cost, currency, and budget features were removed; the project is now
persistent, content-addressed memoization plus single-flight deduplication.

### Added
- **Single-flight**: two identical calls made at the same time collapse into
  one, for sync and async callers. In-process coalescing is built into `Wallet`;
  cross-process coalescing uses the claim lease. `Wallet` routes to the lease
  automatically for any claim-capable backend, so `Wallet(SqliteLedger(...))` and
  `Wallet(RemoteLedger(...))` get cross-process dedup with no extra code. Covered
  by a real multi-process test.
- **Async support**: `@memoize` on an `async def` caches the awaited result (not
  the coroutine) and coalesces concurrent awaits, via `Wallet.acall`.
- **Fencing token**: `claim` issues an owner token that `submit`, `release`, and
  `extend` require, so a revived stale leader cannot disturb a new leader's lease.
  Combined with the lease timeout and heartbeat, duplicates coalesce as long as
  the leader finishes within its lease or keeps a heartbeat (a leader that
  silently overruns its lease can still be run twice, as with any time lease).
- **`SqliteLedger`**: a single shared file with write-ahead logging, atomic reuse
  counters, and the fenced in-flight lease (`claim` / `submit` / `release`), plus
  `extend` and a `heartbeat` context manager to keep a long job's lease alive.
- **Concurrency-safe JSON store**: atomic writes (temp file plus `os.replace`)
  and a locked read-modify-write hit counter, so concurrent writers cannot
  corrupt an entry or lose a count.
- **Automatic eviction**: a `max_entries` size cap on both stores, enforced on
  every write, alongside the manual `evict(max_entries=, older_than=)`.
- **Time-to-live and eviction**: a per-entry `ttl`, an optional
  `stale_while_revalidate` that serves a stale result and refreshes in the
  background, and `evict(max_entries=, older_than=)` (which always drops expired
  entries) on every backend and both CLIs.
- **`RemoteLedger`**: a `LedgerLike` that talks to the server over `urllib`
  (standard library only), so `Wallet(RemoteLedger(url))` dedups across a fleet.
- **`@memoize`** decorator with a shared default store, plus `ignore=` to drop a
  volatile argument, `ttl=`, and `cache_info()` / `cache_clear()` on the wrapper.
- **HTTP dedup server** (`wallet_helper.api`, the `[api]` extra): `claim`,
  `submit`, `release`, `extend`, `clear`, `evict`, and a long-polling
  `GET /result/{key}?wait=` whose SQLite reads run in a worker thread so the poll
  never blocks the event loop. Every endpoint takes a ready key or a namespace
  and payload.
- `LANDSCAPE.md` comparing related caching, single-flight, and idempotency tools.

### Changed
- Built on [os-helper](https://github.com/warith-harchaoui/os-helper) for
  content-addressed hashing, temporary folders, path helpers, and logging.
- `Ledger.stats()` now reports `{entries, hits}` (results cached and calls saved).

### Removed
- The cost, currency, and budget model (`Cost`, `Budget`, `BudgetExceeded`, and
  all `cost=` / `currency=` arguments).
- The GUI and the MCP tool set. wallet-helper is a small toolbox, close in
  spirit to os-helper: a library plus two CLIs and an optional HTTP dedup
  server, with no agent surface.

### Documentation
- A **The Promise** / **La promesse** section and a `local-first` badge in the
  README and LISEZMOI, stating the honest, case-by-case privacy reality
  (guaranteed-local store; the optional dedup server as the one by-design
  network path; a cloud store as your own decision), mirroring the suite.
- Default branch renamed to `main` for consistency with the rest of the AI
  Helpers suite (the in-repo `blob/main` documentation links now resolve).

### CI
- Dropped the Windows job from the test matrix for now (slow runners; the
  `fcntl`-less lock fallback is low priority today). CI keeps Linux 3.10–3.13
  plus macOS on the newest version. Windows can be re-added later.

## [0.1.0] - 2026-07-22

### Added
- Content-addressed `Ledger` for idempotent results, and a `Wallet` front door.
- argparse CLI: `stats`, `path`, `clear`.
