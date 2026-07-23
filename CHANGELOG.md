# Changelog

All notable changes to wallet-helper are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to
semantic versioning.

## [0.2.0] - 2026-07-23

This release refocuses wallet-helper on one job: never run the same heavy call
twice. The cost, currency, and budget features were removed; the project is now
persistent, content-addressed memoization plus single-flight deduplication.

### Added
- **Single-flight**: two identical calls made at the same time collapse into
  one. In-process coalescing is built into `Wallet`; cross-process coalescing
  uses the claim lease. `Wallet` routes to the lease automatically for any
  claim-capable backend, so `Wallet(SqliteLedger(...))` and
  `Wallet(RemoteLedger(...))` get cross-process dedup with no extra code.
- **`SqliteLedger`**: a single shared file with write-ahead logging, atomic reuse
  counters, and the in-flight lease (`claim` / `submit` / `release`), plus
  `extend` and a `heartbeat` context manager to keep a long job's lease alive.
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
  `GET /result/{key}?wait=`. Every endpoint takes a ready key or a namespace and
  payload.
- `LANDSCAPE.md` comparing related caching, single-flight, and idempotency tools.

### Changed
- Built on [os-helper](https://github.com/warith-harchaoui/os-helper) for
  content-addressed hashing, temporary folders, path helpers, and logging.
- `Ledger.stats()` now reports `{entries, hits}` (results cached and calls saved).

### Removed
- The cost, currency, and budget model (`Cost`, `Budget`, `BudgetExceeded`, and
  all `cost=` / `currency=` arguments).
- The GUI and the MCP tool set.

## [0.1.0] - 2026-07-22

### Added
- Content-addressed `Ledger` for idempotent results, and a `Wallet` front door.
- argparse CLI: `stats`, `path`, `clear`.
