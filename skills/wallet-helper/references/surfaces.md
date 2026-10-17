# wallet-helper non-CLI surfaces

## 1. Library — the primary surface

```python
from wallet_helper import memoize, Wallet, default_wallet, make_key
from wallet_helper import Ledger, SqliteLedger, RemoteLedger, LedgerLike
```

### `@memoize`

```python
@memoize(namespace="transcribe", ttl=7 * 24 * 3600)
def transcribe(path: str) -> str: ...


@memoize(namespace="embed")
async def embed(text: str) -> list[float]: ...
```

Works on `def` and `async def`. In-process single-flight is built in.

### `Wallet` and the ledgers

```python
w = Wallet(ledger=SqliteLedger("~/.cache/my-app/wallet.db"), max_entries=10_000)
```

| Ledger | Store | Single-flight scope |
|---|---|---|
| `Ledger` (default) | a folder of JSON files, readable and deletable by hand | in-process |
| `SqliteLedger` | one shared SQLite file | cross-process, same machine |
| `RemoteLedger` | an HTTP dedup server | cross-machine |

`LedgerLike` is the protocol, so a custom backend is a class, not a fork.
`make_key` exposes the content-addressing directly when you want the key
without the decorator. `default_wallet()` is the process-wide instance the
bare decorator uses.

Logging and file management route through `os_helper` — the suite convention.

## 2. CLIs — argparse (core) and click (`[cli]`)

`wallet-helper` and `wallet-helper-click`. See `cli-reference.md`.

## 3. HTTP dedup server — FastAPI (`[api]`)

```bash
pip install 'wallet-helper[api]'
python -m wallet_helper.api         # 127.0.0.1:8000, OpenAPI docs at /docs
```

| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | liveness |
| GET | `/stats` | entry count and size |
| POST | `/key` | compute a content-addressed key |
| POST | `/claim` | take a lease on a key (become the leader) |
| POST | `/submit` | write the result, with the fencing token |
| POST | `/release` | give up a lease |
| POST | `/extend` | heartbeat a long-running lease |
| GET | `/result/{key}` | read a stored result |
| POST | `/clear`, `/evict` | prune the store |

The claim / submit / release / extend quartet **is** the single-flight
protocol — `RemoteLedger` is just a client for it. Many clients on any host
can share one dedup point this way.

## 4. MCP — `fastapi-mcp` over the *same* app (`[mcp]`)

```bash
pip install 'wallet-helper[mcp]'
wallet-helper-mcp                   # same app, MCP mounted at /mcp
```

`wallet_helper.mcp` takes the FastAPI app from `wallet_helper.api` and mounts
`FastApiMCP` on it. Every MCP tool *is* an HTTP route, so the two surfaces
cannot drift and one process serves both doors.

Register it with Claude Code:

```bash
claude mcp add wallet-helper --transport http http://127.0.0.1:8000/mcp
```

`clear` and `evict` are reachable as MCP tools: confirm before calling either
on a store the user did not just create.

## Where this sits in the suite

wallet-helper is infrastructure, not media: any suite pipeline whose steps are
slow or paid — a transcription, a model download, an LLM call routed through
`best-engine-ai-helper` — can wrap that step in `@memoize` and stop paying for
repeats. It depends on `os-helper` and on nothing else in the suite.
