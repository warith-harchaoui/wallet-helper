# wallet-helper

[🇫🇷](https://github.com/warith-harchaoui/wallet-helper/blob/main/LISEZMOI.md) · [🇬🇧](https://github.com/warith-harchaoui/wallet-helper/blob/main/README.md)

[![CI](https://github.com/warith-harchaoui/wallet-helper/actions/workflows/ci.yml/badge.svg)](https://github.com/warith-harchaoui/wallet-helper/actions/workflows/ci.yml) [![License: BSD-3-Clause](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](https://github.com/warith-harchaoui/wallet-helper/blob/main/LICENSE) [![Python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue.svg)](#) [![Local-first](https://img.shields.io/badge/privacy-local--first-2f6f5e.svg)](#the-promise)

![wallet-helper Logo](https://raw.githubusercontent.com/warith-harchaoui/wallet-helper/main/assets/logo.png)

Never run the same heavy call twice. wallet-helper is persistent memoization for expensive calls (a paid API request, a slow model, any heavy function): an identical call is served from a local store instead of running again, across process restarts. When two identical calls start at the same time, they collapse into one, so the second waits for the first and reuses its result instead of running in parallel (single-flight).

## Documentation

[💻 Documentation](https://deraison.ai/ai-helpers/docs/wallet-helper-doc/)

[🗺️ Landscape](https://github.com/warith-harchaoui/wallet-helper/blob/main/LANDSCAPE.md)

[📋 Examples](https://github.com/warith-harchaoui/wallet-helper/blob/main/EXAMPLES.md)

## What it does

A heavy call is a problem you do not want to pay for twice. Two things cause a double run:

1. You call it again next week. wallet-helper stores each result on disk, content-addressed by a namespace plus the inputs (arguments, a file's content, or bytes), so the repeat is served from the store rather than recomputed.
2. You call it twice at once. Two threads, or two processes, launch the same slow call before either finishes. wallet-helper lets one of them run it and makes the others wait for that result, so the work happens once.

It is content-addressed, so a renamed input file still hits and two different inputs never collide. The default store is a folder of JSON files, easy to read and to delete. A SQLite backend adds a shared, concurrency-safe store and cross-process single-flight. A small HTTP server centralizes that dedup for many clients.

## Status

Battle-tested: 122 tests, a green CI gate across four jobs, and semantic-versioned releases on PyPI (see the badges above). What ships today:

- **library** with `Wallet` and the `@memoize` decorator (sync and `async def`), over a `Ledger` (JSON files), a `SqliteLedger` (one shared file), or a `RemoteLedger` (an HTTP server). In-process single-flight is built in.
- **cross-process single-flight** through the SQLite backend or the server. Three mechanisms keep one execution honest across machines:
  - a **fencing token** — a random, unique value handed out with each lease. A new leader taking over a stale lease gets a fresh one, so a late write carrying the old value no longer matches and is rejected, and a crashed or stalled leader cannot disrupt the new leader's lease;
  - a **lease timeout**, so a dead leader never blocks waiters;
  - a **heartbeat**, so a long job keeps its lease.

  Duplicates coalesce as long as the leader finishes within its lease or keeps a heartbeat.
- **time-to-live and eviction**: per-entry `ttl`, optional stale-while-revalidate, an `evict` policy by age or size, and an automatic size cap (`max_entries`).
- **`wallet-helper`**: one command, with `stats`, `path`, `clear`, and `evict`, to inspect and prune the store.
- **HTTP dedup server** (the `[api]` extra) plus `RemoteLedger`, so many clients on any host share one dedup point.
- **MCP tools** (the `[mcp]` extra): the same HTTP dedup server exposed as MCP tools for any MCP-aware agent host, served by a second command, `wallet-helper-mcp`.

## How it works

![How wallet-helper works: the same expensive call, charged once](https://raw.githubusercontent.com/warith-harchaoui/wallet-helper/main/assets/diagrams/how-it-works.png)

## Installation

The only requirement is **Python 3.10 to 3.13**. If you need Python itself:

- 🍎 **macOS** ([Homebrew](https://brew.sh)): `brew install python`
- 🐧 **Ubuntu/Debian**: `sudo apt update && sudo apt install -y python3 python3-pip`
- 🪟 **Windows** (PowerShell): `winget install Python.Python.3.12`

Install from PyPI:

```bash
pip install wallet-helper
```

Or from source:

```bash
git clone https://github.com/warith-harchaoui/wallet-helper.git
cd wallet-helper
pip install -e .
```

The `wallet-helper` command ships with the core install. The HTTP surfaces are opt-in extras:

```bash
pip install "wallet-helper[api]"   # HTTP dedup server     -> fastapi, uvicorn
pip install "wallet-helper[mcp]"   # MCP tools + the above -> fastapi-mcp
```

The `[mcp]` extra adds a second command, `wallet-helper-mcp`, serving the HTTP API and an `/mcp` endpoint from the same app.

## Quick start

Memoize any function with one line. The result is stored on disk and reused on the next identical call, this run or next week:

```python
from wallet_helper import memoize


@memoize
def transcribe(path):
    return call_some_paid_api(path)  # slow and billed; runs at most once per file


transcribe("meeting.wav")  # runs, stores the result
transcribe("meeting.wav")  # served from the store, no second call
```

A file argument is keyed by its content, not its path. So the same file reached under a different name, or a byte-for-byte copy in another folder, still hits, and two different files never collide even if their names look alike:

```python
transcribe("meeting.wav")  # runs
transcribe("archive/meeting.wav")  # a copy with the same bytes, served from the store
```

Ignore an argument that should not change the result, such as a client handle:

```python
@memoize(ignore=("client",))
def fetch(doc_id, client):
    return client.get(doc_id)
```

Inspect or drop a function's cache, like `functools.lru_cache`:

```python
transcribe.cache_info()
# {'entries': 1, 'hits': 1, 'lifetime_hits': 1, 'lifetime_misses': 1}
transcribe.cache_clear()  # forget this function's stored results
```

Two calls, one of them served from the store: one entry, one hit, and one miss — the first call, which had to run.

`entries` and `hits` describe what exists **now**. The lifetime tallies describe everything the store has **ever** done.

The difference is not pedantry. `hits` is stored inside each record, so evicting or expiring an entry destroys the record of every call it ever saved. On a store with five entries and a hundred reuses each, `evict(max_entries=2)` took the reported total from 500 to 200 — sixty per cent of the saved calls gone, with nothing raised.

Since eviction and TTL are this package's own features, a long-running cache under-reported its own value, and did so *more* the better it was housekeeping. `lifetime_hits` survives both.

`lifetime_misses` is what makes the number mean something. A hit count alone
cannot say whether a cache is earning its keep — 500 hits is excellent against
520 calls and dismal against 50 000:

```python
info = transcribe.cache_info()
rate = info["lifetime_hits"] / (info["lifetime_hits"] + info["lifetime_misses"])
```

Set a freshness window with `ttl` (seconds), and share one store across a fleet by pointing at a running server:

```python
from wallet_helper import Wallet, RemoteLedger, memoize


@memoize(ttl=3600)  # results expire after an hour
def price(symbol):
    return call_pricing_api(symbol)


wallet = Wallet(RemoteLedger("http://cache.internal:8000"))


@memoize(wallet=wallet)  # every host dedups through one server
def transcribe(path):
    return call_some_paid_api(path)
```

Async functions work the same. The result is cached, never the coroutine, and concurrent awaits coalesce:

```python
@memoize
async def fetch(url):
    return await http_get(url)
```

The `wallet-helper` command inspects and manages the store (it defaults to `$WALLET_HELPER_DIR`, then `~/.cache/wallet-helper`):

```bash
wallet-helper stats   # how many results are cached and how many calls they saved
wallet-helper path    # where the store lives
wallet-helper clear   # empty the store
```

For a shared store and cross-process single-flight, use the SQLite backend or the HTTP server. See [EXAMPLES.md](https://github.com/warith-harchaoui/wallet-helper/blob/main/EXAMPLES.md).

## Built on os-helper

wallet-helper is part of the AI Helpers suite and builds on [os-helper](https://github.com/warith-harchaoui/os-helper) for content-addressed hashing, path helpers, temporary folders, and logging. That is one direct dependency, which pulls a few common transitive libraries (requests, pyyaml, tqdm, and so on). wallet-helper is local-first and needs no separate service, but it is not dependency-free.

## Architecture

| Piece | Role |
|---|---|
| `make_key` | Content hash of a namespace plus a payload (arguments, file content, or bytes). |
| `Ledger` | Default store: one JSON file per entry. |
| `SqliteLedger` | One shared SQLite file, atomic reuse counters, TTL, and the claim/submit/release/extend lease. |
| `RemoteLedger` | A `LedgerLike` that talks to the server, so `Wallet(RemoteLedger(url))` dedups across a fleet. |
| `Wallet` / `memoize` | Front door: lookup, single-flight (in-process or via the lease), then store. |
| `wallet_helper.api` | HTTP server that centralizes dedup for many clients. |

## Tests

```bash
make install   # editable install with the dev and api extras
make lint      # ruff (PEP 8 and import order)
make test      # pytest and doctests
make           # lint then test
```

CI is deliberately a light gate: the exhaustive multi-version sweep belongs on a
contributor's machine before the push. Four jobs run.

- **lint** — `ruff check .` and `ruff format --check .`, with ruff pinned to a
  known version so a new default rule cannot turn the gate red by surprise.
- **test** — the whole suite with the `[dev,api]` extras, on one Python (3.12)
  on Linux. The cross-process test leans on `spawn`-based multiprocessing, which
  is minutes-slow on a Windows runner, so it is not paid for on every push.
- **smoke** — the install procedure itself, on all three platforms you might
  install on (🐧 Linux, 🍎 macOS, 🪟 Windows). It installs the package plus the
  `[api]` extra, then proves it works: the package imports, `wallet-helper`
  answers `--version` and `--help`, and a memoize round-trip runs the work
  exactly once. This is what "verified on Windows too" means here.
- **floor** — `pip install .` then `import wallet_helper` on Python 3.10, so the
  `requires-python = ">=3.10"` promise has evidence behind it instead of being
  a claim nobody ever ran.

## The Promise

wallet-helper is part of a local-first, sovereignty-minded suite, and like
os-helper it is a small toolbox rather than a service. Rather than market that,
here is the honest, case-by-case reality:

1. **Guaranteed local.** The default `Ledger` (a folder of JSON files) and the
   `SqliteLedger` (one file) live under `$WALLET_HELPER_DIR`, or
   `~/.cache/wallet-helper`, on your machine. Nothing is uploaded, there is no
   telemetry, and there is no account. Your cached results, and the inputs that
   key them, never leave the disk.

2. **Where local is not possible: the caveat.** wallet-helper exists to *avoid*
   running your heavy call; it makes no network requests of its own. The one
   exception is by design: the optional `[api]` dedup server and `RemoteLedger`
   speak HTTP so a fleet can share one dedup point, and they talk only to the
   endpoint you point them at.

3. **Your decision.** wallet-helper stores whatever your function returns; if
   that function calls a paid cloud API, that is your code's choice, never
   wallet-helper's. Point `RemoteLedger` at your own host and the shared store
   stays sovereign; point it at a third party and that too is your call, never
   a default.

## Use it as an agent skill

`skills/wallet-helper/` packages wallet-helper as a **Claude Skill** *and* an **OpenCode
skill**, so an agent can reach for it on your behalf. See
[`skills/README.md`](https://github.com/warith-harchaoui/wallet-helper/blob/main/skills/README.md) to install it (symlink into
`~/.claude/skills/` and `~/.opencode/skills/`), and
[`TRIGGERS.md`](https://github.com/warith-harchaoui/wallet-helper/blob/main/TRIGGERS.md) for the exhaustive trigger catalogue —
`scripts/check_triggers.py` keeps the skill's description in sync with it, and
the test suite fails if a capability stops being named.

## Author

- [Warith HARCHAOUI](https://linkedin.com/in/warith-harchaoui).

## License

`wallet-helper` is licensed under **BSD-3-Clause**. See [LICENSE](https://github.com/warith-harchaoui/wallet-helper/blob/main/LICENSE).
