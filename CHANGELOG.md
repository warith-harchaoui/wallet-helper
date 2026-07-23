# Changelog

All notable changes to wallet-helper are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to
semantic versioning.

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
