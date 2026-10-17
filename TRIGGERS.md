# TRIGGERS: wallet-helper

This is the user-facing, exhaustive catalogue of what `wallet-helper` can do and
the natural-language phrasings, commands, functions, and situations that should
invoke it.

`wallet-helper` is **persistent, content-addressed memoization with
single-flight**: an identical heavy call is served from a local store instead of
running again, across process restarts, and two identical calls launched at the
same time collapse into one. It is local-first — the store is a folder or a
SQLite file under your own cache directory. It does **not** do in-process-only
caching (that is `functools.lru_cache`), general-purpose storage, or queueing.

## Operations → how to invoke

| Intent | CLI | Library | API |
|--------|-----|---------|-----|
| Memoize a function (sync or async) | n/a | `@memoize(namespace=…, ttl=…)` | n/a |
| Build a wallet over a chosen backend | n/a | `Wallet(ledger=…)` | n/a |
| JSON-file store (default) | n/a | `Ledger` | n/a |
| Shared store, cross-process single-flight | n/a | `SqliteLedger` | n/a |
| Shared store across machines | n/a | `RemoteLedger` | the whole server |
| Compute a content-addressed key | n/a | `make_key` | `POST /key` |
| Take a lease on a key | n/a | (internal) | `POST /claim` |
| Write a result under a lease | n/a | (internal) | `POST /submit` |
| Heartbeat a long lease | n/a | (internal) | `POST /extend` |
| Give up a lease | n/a | (internal) | `POST /release` |
| Read a stored result | n/a | `Wallet.get` | `GET /result/{key}` |
| Where is the store | `wallet-helper path` | `default_wallet` | n/a |
| Entry count and size | `wallet-helper stats` | n/a | `GET /stats` |
| Drop everything | `wallet-helper clear` | n/a | `POST /clear` |
| Prune by age / size / count | `wallet-helper evict` | n/a | `POST /evict` |

Every command is also reachable through the click CLI (`wallet-helper-click …`,
same flags), and the HTTP server doubles as the MCP surface at `/mcp`.

## Natural-language phrasings that should fire

- **Memoize / cache a call**: "cache this expensive call", "memoize this
  function", "don't call this paid API twice", "stop paying for the same
  request", "reuse the previous result", "this model takes 20 minutes, cache
  it", "persist the result across restarts", "warm cache between runs".
- **Content addressing**: "key the cache on the file's content, not its path",
  "a renamed input should still hit", "hash the arguments", "content-addressed
  cache".
- **Single-flight / deduplication**: "two workers are doing the same job",
  "deduplicate concurrent calls", "only run this once even if called twice",
  "thundering herd", "collapse duplicate requests", "the second caller should
  wait for the first".
- **Cross-process / cross-machine**: "several processes share one cache",
  "my workers each recompute it", "a shared dedup point for the whole fleet",
  "SQLite-backed cache", "an HTTP cache server my clients share".
- **Expiry and size**: "add a TTL", "expire after a week", "serve stale while
  revalidating", "cap the cache at N entries", "the cache folder is huge",
  "evict old entries", "reclaim disk from the cache".
- **Inspection and cleanup**: "how big is the cache", "how many cached
  entries", "where does the cache live", "clear the cache", "wipe the store",
  "prune the cache".
- **Lease mechanics**: "fencing token", "the leader crashed and nobody picked
  it up", "a stale writer overwrote a fresh result", "lease timeout",
  "heartbeat a long job".
- **Explicit mentions**: `wallet-helper`, `wallet-helper-click`,
  `wallet-helper-mcp`, `@memoize`, `Wallet`, `Ledger`, `SqliteLedger`,
  `RemoteLedger`, `LedgerLike`, `make_key`, `default_wallet`,
  "install / run wallet-helper".

## Inputs it keys on

- **Call arguments** — anything hashable and anything serialisable.
- **File content** — the bytes, so a rename still hits and an in-place edit
  misses (which is the correct behaviour).
- **Raw bytes** — hand it a buffer directly.
- A **namespace** string always participates in the key: it is what keeps two
  functions with identical argument shapes from colliding, and what you bump
  when a function's semantics change.

## When NOT to use wallet-helper (SKIP)

- The result does not need to survive the process → `functools.lru_cache` is
  simpler and has no store to manage.
- You need a database, a key-value store for application data, or a session
  cache → this is a memoization ledger, not storage.
- You need a task queue, a scheduler, or a worker pool → single-flight
  deduplicates identical calls; it does not distribute work.
- You need an HTTP response cache in front of a web app → use a reverse proxy.
- The call is cheap. A cache that saves nothing still costs a lookup, a disk
  entry, and an invalidation question.

## See also

- the repo's `README.md`: features, install, quick start.
- the repo's `EXAMPLES.md`: runnable recipes.
- the repo's `LANDSCAPE.md`: how wallet-helper compares with `lru_cache`,
  `joblib.Memory`, `diskcache`, Redis, and friends.
- `skills/wallet-helper/SKILL.md`: the same catalogue, compressed for an agent.
