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
  uses the SQLite backend's `claim` / `submit` / `release` lease.
- **`SqliteLedger`**: a single shared file with write-ahead logging, atomic reuse
  counters, and the in-flight lease.
- **`@memoize`** decorator with a shared default store, plus `ignore=` to drop a
  volatile argument, and `cache_info()` / `cache_clear()` on the wrapped function.
- **HTTP dedup server** (`wallet_helper.api`, the `[api]` extra): `claim`,
  `submit`, `release`, and a long-polling `GET /result/{key}?wait=` so many
  clients share one dedup point.
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
