# Landscape

Where wallet-helper sits among caching, memoization, single-flight, and
idempotency tools. The pieces exist separately. What is uncommon is the
combination: persistent, content-addressed memoization that also coalesces
concurrent identical calls, in one process and across processes, while staying
local (no separate service required).

A note on dependencies: wallet-helper has one direct dependency, os-helper (the
shared utility layer of the AI Helpers suite), which in turn pulls a few common
libraries (requests, pyyaml, tqdm, validators, python-dotenv). So it is
local-first and self-contained at the service level, but not dependency-free.

Two problems make a heavy call run twice:

- **Repetition over time.** You call it again next run or next week. A persistent
  cache solves this.
- **Concurrency.** Two callers start the same call before either finishes.
  Single-flight (a.k.a. request coalescing, dogpile, stampede protection) solves
  this.

Most tools address one problem. wallet-helper addresses both, with the same key.

## Feature comparison

Rated ⭐ (absent or poor) to ⭐⭐⭐⭐⭐ (best in class) per column.

- **Persistent**: results survive a process restart.
- **Content-addresses input**: keys on a file's content or raw bytes, not just arguments.
- **In-process single-flight**: concurrent identical calls in one process coalesce into one.
- **Cross-process single-flight**: the same, across processes or hosts.
- **TTL / expiry**: per-entry freshness with expiry and eviction.
- **Server for many clients**: a shared endpoint that centralizes dedup.
- **Decorator**: transparent `@decorator` ergonomics.
- **Local (no service)**: runs without a separate database or cache server. This
  is about deployment footprint, not dependency count.

| Project | Persistent | Content-addresses input | In-process single-flight | Cross-process single-flight | TTL / expiry | Server for many clients | Decorator | Local (no service) |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| **wallet-helper** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| `functools.lru_cache` | ⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| `joblib.Memory` | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| `diskcache` | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| `cachier` | ⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| `requests-cache` | ⭐⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐ |
| `dogpile.cache` | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ |
| Go `singleflight` | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ |
| AWS Powertools Idempotency | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐ |
| Stripe idempotency keys | ⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐ |
| `litellm` cache | ⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ⭐ |

## Pros and cons

| Project | Pros | Cons |
|---|---|---|
| **wallet-helper** | Persistent and content-addressed (hashes file content and bytes, not just args); single-flight in-process (threads) and cross-process (a fenced SQLite or HTTP lease, so a crashed or stalled leader cannot disrupt a new leader); sync and async (`async def`); time-to-live, stale-while-revalidate, and automatic eviction; optional HTTP server and `RemoteLedger` centralize dedup for a fleet; simple `@memoize`; runs with no separate service. | Younger and smaller than the veterans; one direct dependency (os-helper) that pulls a few transitive libraries; cross-process lease needs the SQLite backend or the server; no rolling budget windows or semantic (embedding) matching. |
| `functools.lru_cache` | Stdlib, zero setup, great `cache_info()`. | In-memory only (lost on restart); keys on args only; does not coalesce concurrent calls; bounded by `maxsize`. |
| `joblib.Memory` | Mature; persists to disk; hashes argument content (numpy aware); invalidates when the function's source changes. | No concurrent-call coalescing; heavier; oriented to scientific pipelines. |
| `diskcache` | Fast SQLite store; tags and bulk evict; `memoize_stampede`; locks. | Keys on args, not input file content; single-host; stampede tools are opt-in and separate. |
| `cachier` | Simple decorator; time-to-live (`stale_after`); several backends. | No true single-flight; distributed use needs mongo or redis. |
| `requests-cache` | Transparent for `requests`; rich per-response cache metadata. | HTTP only; no coalescing; not for arbitrary functions. |
| `dogpile.cache` | Real dogpile lock (`get_or_create`); stale-while-revalidate; pluggable. | Needs a cache backend (memcached, redis) for the shared case; more moving parts. |
| Go `singleflight` | The reference in-flight coalescing primitive; tiny. | In-flight only (no cache); single process; Go, not Python. |
| AWS Powertools Idempotency | Robust INPROGRESS lease; delete-on-failure; expiry; battle-tested. | Needs DynamoDB or redis; followers reject-and-retry rather than wait; AWS-centric. |
| Stripe idempotency keys | Industry standard; replays completed results; rejects concurrent duplicates. | Remote and account-bound; HTTP only; caller must manage keys. |
| `litellm` cache | Caching plus provider features for LLMs. | LLM only; large dependency; no content-addressing of arbitrary inputs. |

## Ideas borrowed

wallet-helper deliberately borrows proven ideas:

- The wait-and-share leader/follower model, from Go `singleflight` and
  `dogpile.cache` `get_or_create`, so the second caller receives the first's
  result instead of failing.
- A lease with a timeout on the in-progress marker, and deleting it on failure,
  from AWS Powertools Idempotency, so a crashed leader does not block waiters and
  a failed call is not cached.
- Atomic claim with `BEGIN IMMEDIATE` and write-ahead logging on SQLite, so the
  check-then-lease step is race-free across processes.
- `cache_info()` and `cache_clear()` on the decorated function, from
  `functools.lru_cache`, and namespace eviction, from `diskcache` tags.
- Per-entry time-to-live and stale-while-revalidate, from `requests-cache`
  (`expire_after`), `diskcache` (`expire`), and `dogpile.cache`.
