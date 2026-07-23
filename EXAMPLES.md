# wallet-helper — Examples

A runnable cookbook of common use cases. Every Python block is self-contained
and uses a throwaway temporary ledger so you can paste it into a REPL and watch
it work. The library is stdlib-only, so the core examples need nothing installed
beyond `wallet-helper` itself.

- [1. Never pay twice (the core idea)](#1-never-pay-twice-the-core-idea)
- [2. The `@paid` decorator](#2-the-paid-decorator)
- [3. Enforce a budget ceiling](#3-enforce-a-budget-ceiling)
- [4. Content-address a file (rename-proof)](#4-content-address-a-file-rename-proof)
- [5. A custom key: ignore volatile arguments](#5-a-custom-key-ignore-volatile-arguments)
- [6. See what you spent and saved](#6-see-what-you-spent-and-saved)
- [7. Command line](#7-command-line)
- [8. HTTP service + GUI (optional)](#8-http-service--gui-optional)
- [9. MCP tool set (optional)](#9-mcp-tool-set-optional)

## 1. Never pay twice (the core idea)

Wrap any callable that costs money. The first call runs and is billed; an
identical second call is served from the ledger for free.

```python
import tempfile
from wallet_helper import Wallet, Ledger

wallet = Wallet(Ledger(tempfile.mkdtemp()))
calls = {"n": 0}

def transcribe():           # stand-in for a paid API call
    calls["n"] += 1
    return {"text": "hello"}

r1, from_cache1 = wallet.call("gladia", {"file": "a.wav"}, transcribe, cost=0.75, currency="EUR")
r2, from_cache2 = wallet.call("gladia", {"file": "a.wav"}, transcribe, cost=0.75, currency="EUR")

print(r1, from_cache1)      # {'text': 'hello'} False   -> ran, charged 0.75
print(r2, from_cache2)      # {'text': 'hello'} True    -> served free from cache
print("real calls:", calls["n"])   # 1
```

## 2. The `@paid` decorator

The same guard as a decorator, when the cache key is simply the function's
arguments. Repeat identical calls return the cached result.

```python
import tempfile
from wallet_helper import Wallet, Ledger

wallet = Wallet(Ledger(tempfile.mkdtemp()))
runs = {"n": 0}

@wallet.paid("square", cost=0.01, currency="USD")
def square(n):
    runs["n"] += 1
    return n * n

print(square(9), square(9), square(10))   # 81 81 100
print("real calls:", runs["n"])           # 2  (9 was cached; 10 was new)
```

## 3. Enforce a budget ceiling

Attach a `Budget`. A cache **miss** that would overspend is refused *before* the
paid call runs — you are never charged for the call that broke the ceiling. Cache
**hits** are free and never touch the budget.

```python
import tempfile
from wallet_helper import Wallet, Ledger, Budget, BudgetExceeded

wallet = Wallet(Ledger(tempfile.mkdtemp()), budget=Budget(1.0, "EUR"))

wallet.call("api", {"q": 1}, lambda: "ok", cost=0.6, currency="EUR")   # spends 0.6
try:
    wallet.call("api", {"q": 2}, lambda: "ok", cost=0.6, currency="EUR")   # 0.6 + 0.6 > 1.0
except BudgetExceeded as e:
    print("refused:", e)

print("remaining:", round(wallet.budget.remaining(), 2))   # 0.4
```

## 4. Content-address a file (rename-proof)

Pass a file path (or raw `bytes`) as the payload. The key is the file's content,
so renaming the file still hits the cache, and two different files never collide.

```python
import tempfile
from pathlib import Path
from wallet_helper import make_key

d = Path(tempfile.mkdtemp())
(d / "clip.wav").write_bytes(b"AUDIO-BYTES")
(d / "renamed.wav").write_bytes(b"AUDIO-BYTES")   # same content, different name

# Same content -> same key -> a cache hit even after the rename.
print(make_key("gladia", d / "clip.wav") == make_key("gladia", d / "renamed.wav"))   # True
# Bytes hash identically to the file that holds them.
print(make_key("gladia", d / "clip.wav") == make_key("gladia", b"AUDIO-BYTES"))      # True
```

## 5. A custom key: ignore volatile arguments

When only some arguments determine the result (e.g. a client handle that changes
every call), pass a `key=` function so the volatile argument does not bust the
cache.

```python
import tempfile
from wallet_helper import Wallet, Ledger

wallet = Wallet(Ledger(tempfile.mkdtemp()))
runs = {"n": 0}

# Only `n` identifies the result; the `client` handle is ignored.
@wallet.paid("f", cost=0.01, key=lambda n, client: {"n": n})
def f(n, client):
    runs["n"] += 1
    return n + 1

print(f(1, client=object()))   # 2   -> real call
print(f(1, client=object()))   # 2   -> different client, same key => cached
print("real calls:", runs["n"])  # 1
```

## 6. See what you spent and saved

`Ledger.stats()` aggregates real spend (each entry, once) and cache savings
(`cost × hits`) per currency.

```python
import tempfile
from wallet_helper import Wallet, Ledger

ledger = Ledger(tempfile.mkdtemp())
wallet = Wallet(ledger)

for _ in range(3):   # one real call + two cache hits
    wallet.call("gladia", {"file": "a.wav"}, lambda: "text", cost=0.75, currency="EUR")

s = ledger.stats()
print(s["entries"], s["hits"])                 # 1 2
print(round(s["by_currency"]["EUR"]["spent"], 2))  # 0.75   paid once
print(round(s["by_currency"]["EUR"]["saved"], 2))  # 1.5    two hits avoided
```

## 7. Command line

Inspect the ledger from a shell. Two interchangeable CLIs ship: the
dependency-free argparse one (always available) and a `click` variant (the
`[cli]` extra). Point either at any ledger directory with `--dir`.

```bash
# argparse CLI — no dependency, always available:
python -m wallet_helper.cli_argparse stats     # spend + cache savings per currency
python -m wallet_helper.cli_argparse path       # where the ledger lives
python -m wallet_helper.cli_argparse clear       # wipe the ledger (irreversible)

# click variant — pip install "wallet-helper[cli]":
wallet-helper-click stats
wallet-helper-click --dir ./my-ledger stats
wallet-helper-click clear --yes                  # skip the confirmation prompt
```

## 8. HTTP service + GUI (optional)

`pip install "wallet-helper[api]"` turns the ledger into a shared store several
processes can use over HTTP, with a dashboard at `/gui`.

```bash
uvicorn wallet_helper.api:app          # then open http://127.0.0.1:8000/gui
# interactive API docs at http://127.0.0.1:8000/docs
```

```python
# Programmatic use with FastAPI's TestClient (no server process needed):
from fastapi.testclient import TestClient
from wallet_helper.api import app

client = TestClient(app)
key = client.post("/key", json={"namespace": "demo", "payload": {"x": 1}}).json()["key"]
client.put("/records", json={"namespace": "demo", "payload": {"x": 1},
                             "result": {"ok": True}, "cost": 0.5, "currency": "USD"})
print(client.get(f"/records/{key}").json()["result"])   # {'ok': True}
print(client.get("/stats").json()["entries"])           # 1
```

> The HTTP and MCP surfaces expose only the *accounting* half (key, records,
> hits, stats, budget checks). They never run your paid callable — that stays in
> your process, so there is no remote-code-execution surface.

## 9. MCP tool set (optional)

`pip install "wallet-helper[mcp]"` exposes the same accounting operations as
Model Context Protocol tools, so an agent can share your ledger.

```bash
python -m wallet_helper.mcp_server      # stdio transport; point your MCP client here
```

Tools: `stats`, `ledger_path`, `ledger_key`, `get_record`, `put_record`,
`register_hit`, `budget_check`.
