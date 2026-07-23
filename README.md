# wallet-helper

[🇫🇷](https://github.com/warith-harchaoui/wallet-helper/blob/main/LISEZMOI.md) · [🇬🇧](https://github.com/warith-harchaoui/wallet-helper/blob/main/README.md)

[![CI](https://github.com/warith-harchaoui/wallet-helper/actions/workflows/ci.yml/badge.svg)](https://github.com/warith-harchaoui/wallet-helper/actions/workflows/ci.yml) [![License: BSD-3-Clause](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](https://github.com/warith-harchaoui/wallet-helper/blob/main/LICENSE) [![Python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue.svg)](#) [![Zero-dependency](https://img.shields.io/badge/deps-zero%20(stdlib)-2f6f5e.svg)](#the-promise)

![wallet-helper Logo](assets/logo.png)


**Never pay twice for the same billable call.** A tiny, local-first, provider-agnostic guard around any call that costs something — an HTTP API, a paid binary, a metered function — in any currency: money, time, energy, water, CO₂. It combines idempotency (a content-addressed ledger returns the stored result instead of running the call again), spend accounting (every real call records its cost) and budget control (an optional ceiling refuses a call that would overspend, *before* it runs) — three things that usually live in separate tools, with **zero runtime dependencies** so it drops into any project.

By [Warith HARCHAOUI](https://linkedin.com/in/warith-harchaoui)

## Documentation

[💻 Documentation](https://harchaoui.org/warith/ai-helpers/docs/wallet-helper-doc/)

[📋 Examples](https://github.com/warith-harchaoui/wallet-helper/blob/main/EXAMPLES.md)

## The promise

> **The same billable call runs, and bills, at most once.** No cloud account, no
> framework, no dependency — the guard lives in your process and the ledger is a
> folder of JSON files on your disk.

This is not a cost *dashboard* you send your traffic to. It is a local
*property*: an identical call (same namespace, same content, same parameters) is
served from a content-addressed ledger instead of being re-run, so you never pay
for it twice — and an optional budget refuses the call that would overspend
before any money leaves. Provider-agnostic and currency-agnostic: `"USD"`,
`"EUR"`, or even `"tokens"` / `"CO2"` all work.

## Status — v0.1.0

What ships today:

- **library** — content-addressed `Ledger` (idempotency cache), `Cost` / `Budget` value types, and `Wallet` (the `call` method + `@paid` decorator) tying them together. Stdlib only.
- **`wallet-helper` / `cli_argparse`** — dependency-free CLI: `stats`, `path`, `clear`.
- **`wallet-helper-click`** — feature-equivalent CLI on `click` (the `[cli]` extra).
- **FastAPI surface + `/gui`** — a shared ledger over HTTP with a minimal dashboard (the `[api]` extra).
- **`wallet-helper-mcp`** — the same accounting operations as Model Context Protocol tools (the `[mcp]` extra).

## Installation

**Prerequisites** — the only requirement is **Python 3.10–3.13**; the core is
pure standard library, so there are no OS-level packages to install. If you need
Python itself, cross-platform:

- 🍎 **macOS** ([Homebrew](https://brew.sh)): `brew install python`
  (install `brew` thanks to [brew.sh](https://brew.sh/))
- 🐧 **Ubuntu/Debian**: `sudo apt update && sudo apt install -y python3 python3-pip`
- 🪟 **Windows** (PowerShell): `winget install Python.Python.3.12`

### From source

Install from GitHub, pinned to the release tag:

```bash
pip install "git+https://github.com/warith-harchaoui/wallet-helper.git@v0.1.0"
```

Optional extras — every surface beyond the core is opt-in, so the base stays
dependency-free (pick what you need):

```bash
pip install "wallet-helper[cli] @ git+https://github.com/warith-harchaoui/wallet-helper.git@v0.1.0"   # click CLI variant           -> click
pip install "wallet-helper[api] @ git+https://github.com/warith-harchaoui/wallet-helper.git@v0.1.0"   # FastAPI HTTP surface + /gui  -> fastapi, uvicorn
pip install "wallet-helper[mcp] @ git+https://github.com/warith-harchaoui/wallet-helper.git@v0.1.0"   # MCP tool set                 -> mcp
```

## Quick start

As a library:

```python
from wallet_helper import Wallet, Ledger, Budget

wallet = Wallet(Ledger("~/.cache/my-app"), budget=Budget(10.0, "EUR"))

# Wrap any paid call. The second identical call is free (served from the ledger)
# and never touches the budget.
result, from_cache = wallet.call(
    "gladia",                                    # namespace (provider / endpoint)
    {"file": "call.wav", "diarization": True},   # what determines the result
    lambda: call_gladia("call.wav"),             # the paid work (runs at most once)
    cost=0.75, currency="EUR",
)

# Or as a decorator — repeat identical calls return the cached result:
@wallet.paid("openai.chat", cost=0.02, currency="USD")
def summarize(text: str) -> str:
    return openai_chat(text)
```

The payload is **content-addressed**: pass a file path or `bytes` and a renamed
file still hits; different files never collide. Parameters are hashed too, so
`diarization=True` and `diarization=False` are distinct entries.

Two interchangeable CLIs inspect and manage the ledger (defaults to
`$WALLET_HELPER_DIR` then `~/.cache/wallet-helper`, one JSON file per entry):

```bash
python -m wallet_helper.cli_argparse stats   # spend + cache savings per currency
python -m wallet_helper.cli_argparse path    # where the ledger lives
python -m wallet_helper.cli_argparse clear    # wipe the ledger

wallet-helper-click stats                     # same, via the click variant
```

As an HTTP API or MCP server (aligns with the rest of the `*-helper` suite):

```bash
pip install -e ".[api,mcp]"

# FastAPI: shared ledger over HTTP + dashboard at /gui — OpenAPI docs at /docs
uvicorn wallet_helper.api:app                 # http://127.0.0.1:8000/gui

# MCP: expose the same accounting tools to an MCP client
wallet-helper-mcp                             # or: python -m wallet_helper.mcp_server
```

Both surfaces expose only the *accounting* half (key derivation, records, hits,
stats, budget checks). They never run your paid callable — that stays in your own
process, so there is no remote-code-execution surface. For the full catalog of
recipes, see [📋 EXAMPLES.md](https://github.com/warith-harchaoui/wallet-helper/blob/main/EXAMPLES.md).

## Prior art — what already exists on these subjects

wallet-helper deliberately sits in a gap. The pieces exist separately; the
combination — **idempotency + cost ledger + budget, provider-agnostic and
local-first** — is what is uncommon.

- **General memoization / disk cache** — `functools.lru_cache` (in-memory only),
  `joblib.Memory`, `diskcache`. They deduplicate expensive calls but have **no
  notion of money** (cost, currency, budget) and are not framed around billing.
- **HTTP response caching** — `requests-cache`, `CacheControl`, `VCR.py` (tests).
  Cache by HTTP request; again **no spend accounting or budget**, and HTTP-only.
- **LLM-specific cost/limits** — `litellm` (caching + spend tracking + budgets,
  the closest cousin, but **LLM-only and a large dependency**), `tokencost`
  (price tables, no cache/guard), LangChain's LLM cache (cache only), and SaaS
  observability like Helicone / OpenMeter / provider dashboards (**remote,
  account-bound, not a local guard**).
- **Idempotency keys** — Stripe-style keys, AWS Lambda Powertools idempotency.
  These prevent **double side-effects on retries** (a different goal) and are
  server/cloud-oriented, not a client-side "don't re-pay" cache.

If your world is only LLMs and you already run `litellm`, its budget + cache may
be enough. wallet-helper is for the rest: **any** paid callable, no framework, no
service, no dependency.

## Architecture

Three concerns behind one front door (`Wallet`), over a folder of JSON entries:

| Concern | Component |
|---|---|
| **Idempotency** | `Ledger` — content-addressed store (`make_key` → sha256 of namespace + payload) |
| **Accounting** | `Cost` / `Budget` — money value types with over-budget refusal |
| **Guard** | `Wallet` — the `call` method + `@paid` decorator tying them together |

## Tests

```bash
make install   # editable install with dev + all optional extras
make lint      # ruff (PEP 8 + import order) — the CI gate
make test      # pytest + doctests across every surface
make           # lint + test (run before pushing)
```

CI runs the same `lint` + `test` gate on a Python 3.10–3.13 matrix
(Linux, plus macOS and Windows on the newest version).

## Author

- [Warith HARCHAOUI](https://linkedin.com/in/warith-harchaoui).

## License

`wallet-helper` is licensed under **BSD-3-Clause**. See [LICENSE](LICENSE).
