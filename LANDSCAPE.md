# Landscape

[🇫🇷 PAYSAGE.md](https://github.com/warith-harchaoui/wallet-helper/blob/main/PAYSAGE.md) · 🇬🇧 English

Where wallet-helper sits among caching, memoization, single-flight, and
idempotency tools. The pieces exist separately. What is uncommon is the
combination: persistent, content-addressed memoization that also coalesces
concurrent identical calls, in one process and across processes, while staying
local (no separate service required).

A note on dependencies: wallet-helper has one direct dependency, os-helper (the
shared utility layer of the AI Helpers suite), which in turn pulls a few common
libraries (requests, pyyaml, tqdm, validators, python-dotenv, psutil). So it is
local-first and self-contained at the service level, but not dependency-free.

Two problems make a heavy call run twice:

- **Repetition over time.** You call it again next run or next week. A persistent
  cache solves this.
- **Concurrency.** Two callers start the same call before either finishes.
  Single-flight (a.k.a. request coalescing, dogpile, stampede protection) solves
  this.

Most tools address one problem. wallet-helper addresses both, with the same key.

## At a glance

Rated ⭐ (absent or poor) to ⭐⭐⭐⭐⭐ (best in class) per column. The ratings are
one maintainer's reading of each project's own documentation rather than a
benchmark; [Sources and as-of date](#sources-and-as-of-date) says where they
came from and when.

- **Persistent**: results survive a process restart.
- **Content-addresses input**: keys on a file's content or raw bytes, not just arguments.
- **In-process single-flight**: concurrent identical calls in one process coalesce into one.
- **Cross-process single-flight**: the same, across processes or hosts.
- **TTL / expiry**: per-entry freshness with expiry and eviction.
- **Server for many clients**: a shared endpoint that centralizes dedup.
- **Decorator**: transparent `@decorator` ergonomics.
- **Async support**: works with `async def` coroutines, not only synchronous functions.
- **Local (no service)**: runs without a separate database or cache server. This
  is about deployment footprint, not dependency count.
- **Hit-rate visible**: the store can tell you whether it is earning its keep —
  not just how many entries it holds, but how many calls it has served and
  missed over its lifetime.

<!-- TABLE:START -->
| Caching | Persistent | Content-addresses input | In-process single-flight | Cross-process single-flight | TTL / expiry | Server for many clients | Decorator | Async support | Local (no service) | Hit-rate visible |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **wallet-helper** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| functools.lru_cache | ⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| joblib.Memory | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐ |
| diskcache | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| cachier | ⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐ |
| requests-cache | ⭐⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| dogpile.cache | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐ |
| Redis | ⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ |
| Go singleflight | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ |
| AWS Powertools Idempotency | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐⭐ |
| Stripe idempotency keys | ⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐ | ⭐ | ⭐⭐ |
| litellm cache | ⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐ |
| cashews | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| cacheme | ⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| GPTCache (semantic) | ⭐⭐⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |<!-- TABLE:END -->

## Positioning map

<!-- FIGURE:START -->
2D representation of the table above.

![Positioning map](https://raw.githubusercontent.com/warith-harchaoui/wallet-helper/main/assets/landscape.png)

The map is a 2-D summary of the ten criteria, so read it as a shape, not a scoreboard. `wallet-helper` is at the top-right corner. The axes read **Horizontal: Autonomy ↔ Scalable** and **Vertical: Responsive ↔ Elegant**.
<!-- FIGURE:END -->

## Positioning

The two columns that place wallet-helper are **Content-addresses input** and the
pair of single-flight columns, read together with **Local (no service)**.

Take them one at a time and the field splits cleanly. Persistence is everywhere:
`joblib.Memory`, `diskcache`, `cachier` and `requests-cache` all survive a
restart. Coalescing is not rare either: Go's `singleflight` is the reference
primitive, `dogpile.cache` has had `get_or_create` for years, `cashews` and
`cacheme` ship stampede protection. Content-addressing exists too — it is
`joblib.Memory`'s distinguishing feature.

What is uncommon is holding all three *with one key and no service*. The tools
that coalesce across processes mostly do it by delegating to something you have
to run: redis for `dogpile.cache`, `cashews` and `cacheme`, DynamoDB or redis for
AWS Powertools Idempotency. For those, "local" and "cross-process" are not true
at the same time. wallet-helper's cross-process path is a fenced lease in a
SQLite file, or in its own small HTTP server, so a laptop and a fleet run the
same code and only the backend changes.

That buys a specific shape, visible in the map as the top-right corner, and it
costs the opposite one. Redis sits at the far end of the Autonomy ↔ Scalable
axis on purpose: it is the shared, operated store many of these tools build on,
and nothing here competes with it at fleet scale. wallet-helper is deliberately
the smaller claim — one file or one folder, no daemon, nothing to operate — and
it is the wrong tool the moment you want a cache that several teams administer
as infrastructure.

## Pros and cons

| Caching | Pros | Cons |
|---|---|---|
| **wallet-helper** | Persistent and content-addressed (hashes file content and bytes, not just args); single-flight in-process (threads) and cross-process (a fenced SQLite or HTTP lease, so a crashed or stalled leader cannot disrupt a new leader); sync and async (`async def`); time-to-live, stale-while-revalidate, and automatic eviction; optional HTTP server and `RemoteLedger` centralize dedup for a fleet; simple `@memoize`; runs with no separate service. | Younger and smaller than the veterans; one direct dependency (os-helper) that pulls a few transitive libraries; cross-process lease needs the SQLite backend or the server; no rolling budget windows or semantic (embedding) matching. |
| `functools.lru_cache` | Stdlib, zero setup, great `cache_info()`. | In-memory only (lost on restart); keys on args only; does not coalesce concurrent calls; bounded by `maxsize`. |
| `joblib.Memory` | Mature; persists to disk; hashes argument content (numpy aware); invalidates when the function's source changes. | No concurrent-call coalescing; heavier; oriented to scientific pipelines. |
| `diskcache` | Fast SQLite store; tags and bulk evict; `memoize_stampede`; locks. | Keys on args, not input file content; single-host; stampede tools are opt-in and separate. |
| `cachier` | Simple decorator; time-to-live (`stale_after`); several backends. | No true single-flight; distributed use needs mongo or redis. |
| `requests-cache` | Transparent for `requests`; rich per-response cache metadata. | HTTP only; no coalescing; not for arbitrary functions. |
| `dogpile.cache` | Real dogpile lock (`get_or_create`); stale-while-revalidate; pluggable. | Needs a cache backend (memcached, redis) for the shared case; more moving parts. |
| Redis | The scalable pole opposite wallet-helper: the in-memory store many of these tools build on; TTL and eviction; a shared server that centralizes state across clients and hosts; async clients. | A separate service to run and operate, so not local or self-contained; you manage keys explicitly, with no input content-addressing; no built-in call coalescing or `@decorator`; single-flight only if you layer a lock on top. |
| Go `singleflight` | The reference in-flight coalescing primitive; tiny. | In-flight only (no cache); single process; Go, not Python. |
| AWS Powertools Idempotency | Robust INPROGRESS lease; delete-on-failure; expiry; battle-tested. | Needs DynamoDB or redis; followers reject-and-retry rather than wait; AWS-centric. |
| Stripe idempotency keys | Industry standard; replays completed results; rejects concurrent duplicates. | Remote and account-bound; HTTP only; caller must manage keys. |
| `litellm` cache | Caching plus provider features for LLMs. | LLM only; large dependency; no content-addressing of arbitrary inputs. |
| `cashews` | Modern async-first decorator cache; TTL/key templates; built-in stampede protection (`lock=True`, early recompute); memory / disk / redis backends. | Async-only; keys on args/templates, not input file content; the distributed lock (cross-process) needs redis, so "local" and "cross-process" are not both true at once. |
| `cacheme` | Asyncio cache framework with strong thundering-herd (single-flight) protection; typed nodes; pluggable storage (in-memory TLRU, redis, mongo). | Async-only; keys on node args, not input content; cross-process needs redis/mongo; no self-contained local cross-process path. |
| GPTCache (semantic) | Different axis: matches *similar* prompts via embeddings + vector search, so paraphrases hit: the semantic caching wallet-helper deliberately does not do. | LLM-oriented; needs an embedder and a vector store; probabilistic hits (a similarity threshold) rather than exact, content-addressed reuse. |

## Two things wallet-helper is not

- **Not a semantic cache.** GPTCache and similar tools match *similar* prompts
  via embeddings and a similarity threshold, trading exactness for a higher hit
  rate on paraphrases. wallet-helper is the opposite by design: an exact,
  content-addressed hit or a miss, with no model in the loop. The two are
  complementary, not competing.
- **Not an HTTP-protocol cache.** `requests-cache` and the newer
  [hishel](https://github.com/karpetrosyan/hishel) (RFC 9111 caching for HTTPX)
  cache HTTP responses by their cache-control semantics. wallet-helper caches
  *any* function's result by the content of its inputs, so it also covers a slow
  local model or a non-HTTP call, but it does not read HTTP cache headers.

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

## When to pick what

Most of the time the honest answer is not this package.

- **One process, cheap function, no restarts to survive.** `functools.lru_cache`
  or `functools.cache`. Stdlib, no files, nothing to clean up. Reach for a
  persistent store only once a result is worth keeping between runs.
- **A scientific pipeline whose inputs are arrays and dataframes.**
  `joblib.Memory`. It hashes argument content with numpy awareness and
  invalidates when the function's source changes, which wallet-helper does not
  do — change a memoized body here and the old result is still served until you
  clear its namespace.
- **A big local key/value cache on one host.** `diskcache`. It is fast, mature,
  has tags and bulk eviction, and `memoize_stampede` if you need coalescing.
- **Caching HTTP responses by their cache-control semantics.** `requests-cache`
  for `requests`, [hishel](https://github.com/karpetrosyan/hishel) for HTTPX.
  They read the headers; wallet-helper never looks at them.
- **An async-first codebase where redis is already running.** `cashews` or
  `cacheme`. Both are built for `async def` and both do stampede protection
  well; the distributed lock is redis's job.
- **A cache several teams operate as infrastructure.** Redis, and a lock of your
  own on top. This is the pole opposite wallet-helper and it is the right answer
  at that scale.
- **Idempotency for a request handler, on AWS.** AWS Powertools Idempotency,
  with DynamoDB. It is designed for exactly that lifecycle.
- **Paraphrases of a prompt should hit the same cached answer.** GPTCache. That
  is semantic matching, which wallet-helper deliberately refuses — here it is an
  exact content-addressed hit or a miss.

Pick wallet-helper when several of these are true at once:

- The call is expensive enough that running it twice is a real cost — a billed
  API, a slow model, a long job.
- A result is worth keeping across restarts, not just within one run.
- The input is, or contains, a **file or a blob**, and you want a copy under
  another name to hit the same entry.
- Two callers can plausibly start the same call at the same time, and you want
  the second to wait rather than pay.
- You want that to hold **across processes** without standing up redis or
  DynamoDB first — one SQLite file, or one small HTTP server you own.

## Sources and as-of date

**As of 2026-10-27.** The stars and the pros/cons are a qualitative reading of
each project's own documentation and README, done by this package's maintainer.
No benchmark was run, no timing or throughput figure is claimed anywhere in this
document, and no version numbers are quoted — a star here says "the docs
describe this capability", not "we measured it".

Treat the ratings for other people's software as a starting point and check the
column that matters to you against its own documentation, because these projects
move and this file does not move with them.

- `functools.lru_cache` — <https://docs.python.org/3/library/functools.html>
- joblib — <https://joblib.readthedocs.io/>
- diskcache — <https://grantjenks.com/docs/diskcache/>
- cachier — <https://github.com/python-cachier/cachier>
- requests-cache — <https://requests-cache.readthedocs.io/en/stable/>
- dogpile.cache — <https://dogpilecache.sqlalchemy.org/>
- Redis — <https://redis.io/docs/latest/>
- Go `singleflight` — <https://pkg.go.dev/golang.org/x/sync/singleflight>
- AWS Powertools Idempotency —
  <https://docs.powertools.aws.dev/lambda/python/latest/utilities/idempotency/>
- Stripe idempotent requests — <https://docs.stripe.com/api/idempotent_requests>
- litellm caching — <https://docs.litellm.ai/docs/proxy/caching>
- cashews — <https://github.com/Krukov/cashews>
- cacheme — <https://github.com/Yiling-J/cacheme>
- GPTCache — <https://github.com/zilliztech/GPTCache>
- hishel — <https://github.com/karpetrosyan/hishel>

The wallet-helper row is the exception: it is read off this repository's own
code and test suite at the version in `pyproject.toml`, so it is the only row
that is checked mechanically rather than by reading.
