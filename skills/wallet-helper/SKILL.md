---
name: wallet-helper
description: >-
  Never run the same heavy call twice. Persistent, content-addressed
  memoization for expensive work — a paid API request, a slow model, any
  costly function — plus single-flight so two identical calls launched at the
  same time collapse into one run the others wait on. Backends: JSON files, a
  shared SQLite ledger (cross-process single-flight with leases, fencing
  tokens and heartbeats), or a remote HTTP dedup server. TTL,
  stale-while-revalidate, eviction by age or size. Use when the user says
  "cache this expensive call", "memoize this function", "stop paying for the
  same API call twice", "don't recompute this across restarts", "two workers
  are doing the same job", "deduplicate concurrent calls", "add a TTL to this
  cache", "clear / evict the cache", "how big is the cache", or names
  `wallet-helper`, `wallet-helper-click`, `wallet-helper-mcp`, `@memoize`,
  `Wallet`, `SqliteLedger`, `RemoteLedger`. Do NOT use for an in-process
  one-shot cache (`functools.lru_cache`), a database, or a message queue.
license: BSD-3-Clause
metadata:
  author: Warith Harchaoui
  package: wallet-helper
  suite: ai-helpers
  homepage: https://deraison.ai/ai-helpers
---

# wallet-helper — persistent memoization with single-flight

A heavy call is a problem you do not want to pay for twice. Two things cause a
double run, and `wallet-helper` covers both:

1. **You call it again next week.** Results are stored on disk,
   content-addressed by a namespace plus the inputs (arguments, a file's
   content, or bytes), so the repeat is served from the store instead of
   recomputed — across process restarts.
2. **You call it twice at once.** Two threads or two processes start the same
   slow call before either finishes. One runs it; the others wait for that
   result. This is *single-flight*.

Content addressing means a renamed input file still hits, and two different
inputs never collide.

## Before anything: verify it is installed

```bash
wallet-helper stats               # argparse CLI; also proves the store is reachable
python -c "import wallet_helper"  # library import check
```

Install:

```bash
pip install wallet-helper                  # core: library + argparse CLI
pip install 'wallet-helper[cli]'           # + the click twin
pip install 'wallet-helper[api]'           # + the HTTP dedup server
pip install 'wallet-helper[mcp]'           # + MCP tools over the same app
```

## The library is the main surface

```python
from wallet_helper import memoize, Wallet, SqliteLedger


@memoize(namespace="transcribe", ttl=7 * 24 * 3600)
def transcribe(path: str) -> str: ...  # runs once per distinct file content


w = Wallet(ledger=SqliteLedger("~/.cache/my-app/wallet.db"))
```

`@memoize` works on `def` and on `async def`. In-process single-flight is
built in; **cross-process** single-flight needs the SQLite backend or the
HTTP server.

Pick the backend from the sharing you need:

| Situation | Backend |
|---|---|
| One process, readable store | `Ledger` — a folder of JSON files (default) |
| Several processes on one machine | `SqliteLedger` — one shared file |
| Several machines | `RemoteLedger` — the HTTP dedup server |

## The CLI inspects and prunes the store

| Intent | Command |
|---|---|
| Where does the store live | `wallet-helper path` |
| How many entries, how big | `wallet-helper stats` |
| Drop everything | `wallet-helper clear` |
| Prune by age or size | `wallet-helper evict` |

For the full flag matrix, the key model and the lease mechanics, read
`references/cli-reference.md`. For the HTTP dedup protocol and the MCP tools,
read `references/surfaces.md`. For the exhaustive trigger list, read
`references/triggers.md`.

## Rules of thumb

- **Namespace every memoized function.** The namespace is what keeps two
  functions with identical argument shapes from sharing a key.
- **Content, not paths.** Hash a file's *content* when the input is a file; a
  path-keyed cache goes stale the moment someone edits in place.
- **TTL is a correctness decision, not a tuning knob.** Model outputs that
  depend on a remote service deserve one; a pure function does not.
- **Reach for SQLite the moment a second process appears.** The default JSON
  ledger gives in-process single-flight only — two processes will both run the
  call.
- **`clear` is destructive and `evict` is partial.** Run `stats` first, report
  what will go, and confirm before clearing a store the user did not just
  create.
- **This is not `lru_cache`.** If the result does not need to survive the
  process, the stdlib is simpler and this package is the wrong tool.
- **After running, report the cache hit or miss and the store size** — the
  point of the package is knowing you did not pay twice.
