# Changelog

All notable changes to wallet-helper are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to
semantic versioning.

## [1.2.0] - 2026-10-19

### Added

- **`lifetime_hits` and `lifetime_misses` in `stats()` / `cache_info()`.**

  `hits` is stored inside each record, so `stats()` sums it over the records
  that still exist — and evicting or expiring an entry therefore destroys the
  record of every call it ever saved. Measured on five entries with a hundred
  reuses each:

  ```
  avant eviction : {'entries': 5, 'hits': 500}
  evict(max_entries=2)
  apres eviction : {'entries': 2, 'hits': 200}
  ```

  500 calls genuinely saved, 200 reported. Sixty per cent of the evidence gone,
  with nothing raised. The docstring claimed `hits` was "how many real calls
  were saved", which was false for any cache that had ever evicted or expired
  anything — and eviction and TTL are this package's own features. **The better
  a cache housekept, the more it under-reported itself.** Someone tuning
  `max_entries` would watch the saved-call count fall and reasonably blame the
  eviction, when it was only the counter forgetting.

  `entries` and `hits` still describe what exists now. The lifetime tallies
  describe everything the store has ever done, and survive eviction and expiry.
  They do not survive `clear()`, which removes the store outright — that is an
  explicit instruction to forget, not automatic housekeeping.

  `lifetime_misses` is what makes the number mean something: a hit count alone
  cannot say whether a cache is earning its keep, since 500 hits is excellent
  against 520 calls and dismal against 50 000.

  Both backends, each by the mechanism it needs. The JSON ledger keeps a
  `_lifetime.tally` file — deliberately not `.json`, because entries are
  globbed as `*.json` and a `.json` tally would be counted as an entry by
  `stats()` then deleted by `evict()` as soon as the cache grew. SQLite keeps a
  `counters` table, which `DELETE FROM entries` cannot reach. A test pins that
  both backends return the same keys.

- **`register_miss()` on the ledger protocol.** Called at the two public seams
  (`call` / `acall`), which already returned `(value, hit)` — one site each
  rather than the four internal miss sites, since a miss counted in three paths
  out of four would be worse than none. `getattr`-guarded, so a third-party
  backend written against the older protocol stays valid.

### Changed

- **`stats()` and `cache_info()` return two extra keys.** Additive: any
  `stats()["hits"]`-style consumer is unaffected. Code comparing the whole dict
  with `==` will need updating — five of this package's own tests did, and they
  are better for asserting the fields they were actually about.

- **LANDSCAPE / PAYSAGE gain a `Hit-rate visible` axis**, both maps regenerated
  through `standpoint`. `functools.lru_cache` scores 4 on it and Redis 5:
  wallet-helper was behind the standard library here until this release, and
  the table says so.

## [1.1.4] - 2026-08-24

### Fixed

- **`cli_argparse.py`'s `clear` command deleted the whole ledger with no
  confirmation**, unlike `cli_click.py`'s `clear`, which prompts (or accepts
  `--yes`) before this irreversible action. Both surfaces are documented as
  offering the same features, and the argparse CLI is the dependency-free
  one, not a rarely-used fallback — a user relying on the click CLI's
  confirm-first behavior got silent, unconfirmed data loss on the other
  surface. `clear` now gains the same `--yes`-skippable `input()`
  confirmation prompt.
- **A narrow in-process single-flight race could re-run `fn` for a key that
  was already fresh.** `Wallet._call_local` checks the ledger for a fresh
  record, then calls `_compute_local`, which takes the in-flight lock and
  claims leadership. Between those two steps (no lock held), a concurrent
  leader for the same key could finish, store its result, and remove itself
  from the in-flight registry; a caller arriving in that gap then saw an
  empty registry, claimed leadership itself, and re-ran the heavy call even
  though a fresh result already existed in the ledger, defeating the
  library's "never twice" promise. `_compute_local` now re-checks the ledger
  for a fresh record atomically with the leadership claim, inside the same
  locked section, so a caller landing in that gap reuses the existing result
  instead of recomputing it. Regression test:
  `tests/test_guard.py::test_compute_local_skips_recompute_when_already_fresh`.

## [1.1.3] - 2026-08-17

### Fixed

- **`RemoteLedger` mis-routed a key or namespace containing a URL-reserved
  character.** `get_record` embedded the key straight into the request path
  (`f"/result/{key}"`) and `stats` embedded the namespace straight into the
  query string (`f"/stats?namespace={namespace}"`), un-encoded. A namespace
  is user-supplied text (or a nested function's `module.qualname`, which
  contains `<locals>`), so a `?`/`#` in it silently truncated the outgoing
  request into the wrong (or no) key, and a `&`/`=` in a namespace passed to
  `stats` silently split into extra query parameters, the same
  "namespace-as-untrusted-string" bug class already fixed once for the JSON
  and SQLite stores' `LIKE`/glob patterns. Both call sites now URL-encode via
  `urllib.parse`. The server side was already correct (`{key:path}`, and
  FastAPI decodes query params itself); only the client's request
  construction was missing the encode.

### Documentation

- **Glossed "fencing token"** in README.md/LISEZMOI.md, the one cross-process
  mechanism left unexplained while its siblings (lease timeout, heartbeat,
  stale-while-revalidate) already were. It is a random, unique value handed
  out with each lease; a new leader taking over a stale lease gets a fresh
  one, so a late write carrying the old value no longer matches and is
  rejected.
- Removed punctuation-dash asides from LANDSCAPE.md, PAYSAGE.md, and
  `mcp.py`'s module docstring, per this project's writing charter.

## [1.1.2] - 2026-08-15

### Fixed

- **`wallet-helper-click` leaked raw exceptions for plain usage errors, not
  just library errors.** `main()` calls click with `standalone_mode=False`
  (so it stays a plain callable returning an int, for testability), which
  also disables click's own exception handling — so even an unknown
  subcommand or a bad option raised a raw `ClickException`/`UsageError`
  instead of click's usual clean message. Both CLI twins now print one
  `Error: ...` line to stderr and return a non-zero exit code on any library
  exception (a locked/corrupted SQLite ledger, a permission error); the
  click twin additionally restores click's own formatted output for its own
  `ClickException`/`Abort`.

## [1.1.1] - 2026-08-09

### Changed

- **CI never enforced `ruff format --check`, only `ruff check`**, so
  formatting had drifted across 23 files (line wrapping, blank lines).
  Reformatted the tree and added the missing CI step so it can't drift
  again silently.

## [1.1.0] - 2026-08-06

### Added

- **MCP surface** (`wallet_helper.mcp`, `[mcp]` extra, entry point
  `wallet-helper-mcp`): exposes the existing FastAPI app (claim/submit/
  release/extend/result/stats/clear/evict) as MCP tools via `fastapi-mcp`,
  mirroring the pattern already shipped in `standpoint` / `vocal-helper` /
  `md2star` / `os-helper`. Closes the CLI/API/MCP surface gap for
  wallet-helper flagged in `ai-helpers/.private/do.md` §7.

## [1.0.1] - 2026-08-02

Documentation-only follow-up. The install commands now point at PyPI
(`pip install wallet-helper`) instead of a pinned git tag, so the rendered PyPI
project page never drifts to an old version.

### Fixed

- README / LISEZMOI install commands no longer self-pin to a git tag (`@v0.3.0`);
  they use `pip install wallet-helper`, which always resolves to the latest
  published release.

### Added

- `tests/test_readme_install_pin.py` guards against the stale git self-pin ever
  returning to any Markdown file.

### Changed

- CI pins `ruff==0.15.21` (was the unpinned `ruff>=0.6`), matching the rest of
  the suite so a surprise ruff upgrade cannot flip lint behaviour under the
  build.

## [1.0.0] - 2026-08-02

### Changed

- **Requires os-helper 2.x** (`os-helper>=2.0.0,<3`, was `>=1.7,<2`). The
  previous `<2` cap excluded the suite's new foundation, so this is a hard
  requirement bump. Logging and content-addressed hashing continue to route
  through os-helper, now on its stable 2.x contract.
- First stable release: classifier moved to `Development Status :: 5 -
  Production/Stable`. The memoize / single-flight API is considered stable.
- CI trimmed to a super-light single-Python test gate (ruff + pytest block); the
  fast cross-OS `smoke` job is kept because wallet-helper's file locking is
  OS-specific (POSIX `fcntl` vs Windows).

## [0.3.1] - 2026-08-01

### Fixed
- **The JSON `Ledger` crashed on Windows for a memoized closure or lambda.**
  It turned a cache key straight into a filename, and a default namespace is
  `module.qualname` -- which for a nested function or a lambda contains
  `<locals>` / `<lambda>`. `<` and `>` (and `: " / \ | ? *` and control
  characters) are illegal in a Windows filename, so `Ledger.put` raised
  `OSError: [Errno 22] Invalid argument` there. Those characters are now
  percent-encoded when building the filename (a no-op for a key that has none,
  so common filenames are unchanged and injective, so distinct keys never
  collide). The `SqliteLedger` was never affected (it stores the key as
  arbitrary text). Found by the new cross-OS install smoke test (see CI below).
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
  in that inherited slot then hashed identically: a real cache collision (a
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
