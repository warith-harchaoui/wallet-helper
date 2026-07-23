# Landscape

Where wallet-helper sits among caching, memoization, single-flight, and
idempotency tools. The pieces exist separately. What is uncommon is the
combination: persistent, content-addressed memoization that also coalesces
concurrent identical calls, in one process and across processes, staying local
and light.

Two problems make a heavy call run twice:

- **Repetition over time.** You call it again next run or next week. A persistent
  cache solves this.
- **Concurrency.** Two callers start the same call before either finishes.
  Single-flight (a.k.a. request coalescing, dogpile, stampede protection) solves
  this.

Most tools address one problem. wallet-helper addresses both, with the same key.

## Feature comparison

Legend: yes, no, partial.

| Project | Persistent (survives restart) | Content-addresses file / bytes input | In-process single-flight | Cross-process single-flight | Server for many clients | Decorator | Namespace evict | Light / local |
|---|---|---|---|---|---|---|---|---|
| **wallet-helper** | yes | yes | yes (wait and share) | yes (SQLite lease) | yes (own HTTP) | yes | yes | yes (one dep) |
| `functools.lru_cache` | no | no | no | no | no | yes | no | yes (stdlib) |
| `joblib.Memory` | yes | partial (arg content) | no | no | no | yes | partial (per function) | partial (dep) |
| `diskcache` | yes | no (args) | partial (`memoize_stampede`, `Lock`) | partial (SQLite, same host) | no | yes | yes (tags) | yes |
| `cachier` | yes | no | no | partial (mongo / redis) | no | yes | partial | partial |
| `requests-cache` | yes | no (HTTP request) | no | no | no | no (session) | partial | HTTP only |
| `dogpile.cache` | yes (backends) | no | yes (mutex `get_or_create`) | yes (with shared backend) | no (needs cache server) | yes | partial (regions) | no (needs backend) |
| Go `singleflight` | no (in-flight only) | no | yes | no | no | no | no | yes |
| AWS Powertools Idempotency | yes (DynamoDB / redis) | partial (JMESPath key) | partial (local cache) | yes (reject and retry) | no (lib plus store) | yes | no | no (needs store) |
| Stripe idempotency keys | yes (24 h) | no (client key) | yes (409 on concurrent) | yes | yes (Stripe's) | no | no | no (remote) |
| `litellm` cache | yes (backends) | no (prompt) | no | partial (redis) | no | no | partial | no (LLM only, large) |

## Pros and cons

| Project | Pros | Cons |
|---|---|---|
| **wallet-helper** | Persistent and content-addressed (hashes file content and bytes, not just args); single-flight both in-process and cross-process; optional HTTP server centralizes dedup; simple `@memoize`; local, one dependency. | Younger and smaller than the veterans; no time-to-live or eviction policy yet; cross-process lease needs the SQLite backend or the server. |
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
