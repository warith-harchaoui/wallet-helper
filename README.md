# wallet-helper

[🇫🇷](https://github.com/warith-harchaoui/wallet-helper/blob/main/LISEZMOI.md) · [🇬🇧](https://github.com/warith-harchaoui/wallet-helper/blob/main/README.md)

[![CI](https://github.com/warith-harchaoui/wallet-helper/actions/workflows/ci.yml/badge.svg)](https://github.com/warith-harchaoui/wallet-helper/actions/workflows/ci.yml) [![License: BSD-3-Clause](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](https://github.com/warith-harchaoui/wallet-helper/blob/main/LICENSE) [![Python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue.svg)](#)

![wallet-helper Logo](assets/logo.png)

Never run the same heavy call twice. wallet-helper is persistent memoization for expensive calls (a paid API request, a slow model, any heavy function): an identical call is served from a local store instead of running again, across process restarts. When two identical calls start at the same time, they collapse into one, so the second waits for the first and reuses its result instead of running in parallel (single-flight).

By [Warith HARCHAOUI](https://linkedin.com/in/warith-harchaoui)

## Documentation

[📋 Examples](https://github.com/warith-harchaoui/wallet-helper/blob/main/EXAMPLES.md)

[🔭 Landscape](https://github.com/warith-harchaoui/wallet-helper/blob/main/LANDSCAPE.md)

## What it does

A heavy call is a problem you do not want to pay for twice. Two things cause a double run:

1. You call it again next week. wallet-helper stores each result on disk, content-addressed by a namespace plus the inputs (arguments, a file's content, or bytes), so the repeat is served from the store rather than recomputed.
2. You call it twice at once. Two threads, or two processes, launch the same slow call before either finishes. wallet-helper lets one of them run it and makes the others wait for that result, so the work happens once.

It is content-addressed, so a renamed input file still hits and two different inputs never collide. The default store is a folder of JSON files, easy to read and to delete. A SQLite backend adds a shared, concurrency-safe store and cross-process single-flight. A small HTTP server centralizes that dedup for many clients.

## Status

What ships today:

- **library** with `Wallet` and the `@memoize` decorator, over a `Ledger` (JSON files) or a `SqliteLedger` (one shared file). In-process single-flight is built in.
- **cross-process single-flight** through the SQLite backend's claim, submit, release lease.
- **`wallet-helper` / `cli_argparse`** and **`wallet-helper-click`**: inspect and clear the store.
- **HTTP dedup server** (the `[api]` extra): claim, submit, and long-poll a result across many clients.

## Installation

The only requirement is **Python 3.10 to 3.13**. If you need Python itself:

- 🍎 **macOS** ([Homebrew](https://brew.sh)): `brew install python`
- 🐧 **Ubuntu/Debian**: `sudo apt update && sudo apt install -y python3 python3-pip`
- 🪟 **Windows** (PowerShell): `winget install Python.Python.3.12`

Install from GitHub, pinned to the release tag:

```bash
pip install "git+https://github.com/warith-harchaoui/wallet-helper.git@v0.2.0"
```

The command-line and HTTP surfaces are opt-in extras:

```bash
pip install "wallet-helper[cli] @ git+https://github.com/warith-harchaoui/wallet-helper.git@v0.2.0"   # click CLI variant    -> click
pip install "wallet-helper[api] @ git+https://github.com/warith-harchaoui/wallet-helper.git@v0.2.0"   # HTTP dedup server     -> fastapi, uvicorn
```

## Quick start

Memoize any function with one line. The result is stored on disk and reused on the next identical call, this run or next week:

```python
from wallet_helper import memoize

@memoize
def transcribe(path):
    return call_some_paid_api(path)   # slow and billed; runs at most once per file

transcribe("meeting.wav")   # runs, stores the result
transcribe("meeting.wav")   # served from the store, no second call
```

Ignore an argument that should not change the result, such as a client handle:

```python
@memoize(ignore=("client",))
def fetch(doc_id, client):
    return client.get(doc_id)
```

Inspect or drop a function's cache, like `functools.lru_cache`:

```python
transcribe.cache_info()    # {'entries': 1, 'hits': 1}
transcribe.cache_clear()   # forget this function's stored results
```

Two command-line tools inspect and manage the store (it defaults to `$WALLET_HELPER_DIR`, then `~/.cache/wallet-helper`):

```bash
python -m wallet_helper.cli_argparse stats   # how many results are cached and how many calls they saved
python -m wallet_helper.cli_argparse path    # where the store lives
python -m wallet_helper.cli_argparse clear    # empty the store

wallet-helper-click stats                     # same, via the click variant
```

For a shared store and cross-process single-flight, use the SQLite backend or the HTTP server. See [EXAMPLES.md](https://github.com/warith-harchaoui/wallet-helper/blob/main/EXAMPLES.md).

## Built on os-helper

wallet-helper is part of the AI Helpers suite and builds on [os-helper](https://github.com/warith-harchaoui/os-helper) for content-addressed hashing, temporary folders, path helpers, and logging.

## Architecture

| Piece | Role |
|---|---|
| `make_key` | Content hash of a namespace plus a payload (arguments, file content, or bytes). |
| `Ledger` | Default store: one JSON file per entry. |
| `SqliteLedger` | One shared SQLite file, atomic reuse counters, and the claim/submit/release lease. |
| `Wallet` / `memoize` | Front door: lookup, in-process single-flight, then store. |
| `wallet_helper.api` | HTTP server that centralizes dedup for many clients. |

## Tests

```bash
make install   # editable install with dev and all extras
make lint      # ruff (PEP 8 and import order)
make test      # pytest and doctests
make           # lint then test
```

CI runs the same gate on a Python 3.10 to 3.13 matrix (Linux, plus macOS and Windows on the newest version).

## Author

- [Warith HARCHAOUI](https://linkedin.com/in/warith-harchaoui).

## License

`wallet-helper` is licensed under **BSD-3-Clause**. See [LICENSE](LICENSE).
