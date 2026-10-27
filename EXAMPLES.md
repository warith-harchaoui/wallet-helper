# wallet-helper Examples

[🇫🇷 EXEMPLES.md](https://github.com/warith-harchaoui/wallet-helper/blob/main/EXEMPLES.md) · 🇬🇧 English

A cookbook of common uses. Most Python blocks are self-contained and write to a
temporary store, so you can paste one into a REPL and watch it work. The output
written beside each `print` is what the block really printed when this file was
last checked; `tests/test_examples_md.py` re-runs every self-contained block, so
an API change breaks the build rather than the reader.

Three blocks are deliberately **not** runnable as written, and say so where they
appear: the two that call a stand-in `call_some_paid_api`, and the client for
the HTTP server in example 7, which needs that server running.

## Table of Contents

- [Setup](#setup)
- [1. Memoize a heavy call](#1-memoize-a-heavy-call)
- [2. The decorator, with cache_info and cache_clear](#2-the-decorator-with-cache_info-and-cache_clear)
- [3. Ignore a volatile argument](#3-ignore-a-volatile-argument)
- [4. Content-address a file](#4-content-address-a-file)
- [5. Single-flight across threads](#5-single-flight-across-threads)
- [6. A shared store with SQLite](#6-a-shared-store-with-sqlite)
- [7. Cross-process single-flight over HTTP](#7-cross-process-single-flight-over-http)
- [8. A shared store over HTTP with RemoteLedger](#8-a-shared-store-over-http-with-remoteledger)
- [9. Time-to-live and eviction](#9-time-to-live-and-eviction)
- [10. Stale-while-revalidate](#10-stale-while-revalidate)
- [11. Async functions](#11-async-functions)
- [Command line](#command-line)
- [Troubleshooting](#troubleshooting)

## Setup

The library and the `wallet-helper` command come with the base install. Only
examples 7 and 8 need more, because they involve the HTTP dedup server:

```bash
pip install wallet-helper            # library + the wallet-helper command
pip install "wallet-helper[api]"     # adds the HTTP dedup server (examples 7, 8)
```

Every snippet below is written against these names, and each block repeats the
ones it needs so you can start reading from any section. `osh` is
[os-helper](https://github.com/warith-harchaoui/os-helper), the suite's shared
utility layer, and it is where `temporary_folder` comes from:

```python
import os_helper as osh
from wallet_helper import Wallet, Ledger, SqliteLedger, RemoteLedger, make_key, memoize
```

The store the examples do *not* override lives at `$WALLET_HELPER_DIR`, falling
back to `~/.cache/wallet-helper`. Run `wallet-helper path` to print it.

## 1. Memoize a heavy call

Wrap any function whose run is expensive. The first call runs it; an identical
second call is served from the store. `from_cache` tells you which happened.

```python
import os_helper as osh
from wallet_helper import Wallet, Ledger

with osh.temporary_folder() as tmp:
    wallet = Wallet(Ledger(tmp))

    def transcribe(path):
        return {"text": "hello"}  # stand-in for a slow, paid API call

    r1, from_cache1 = wallet.call("transcribe", {"file": "a.wav"}, lambda: transcribe("a.wav"))
    r2, from_cache2 = wallet.call("transcribe", {"file": "a.wav"}, lambda: transcribe("a.wav"))

    print(r1, from_cache1)  # {'text': 'hello'} False   -> ran
    print(r2, from_cache2)  # {'text': 'hello'} True    -> served from the store
```

## 2. The decorator, with cache_info and cache_clear

`@memoize` needs no setup: it uses a shared default store at
`~/.cache/wallet-helper`. Pass a `wallet=` to point it elsewhere (here a
temporary one). The wrapped function carries `cache_info()` and `cache_clear()`,
like `functools.lru_cache`.

```python
import os_helper as osh
from wallet_helper import Wallet, Ledger, memoize

with osh.temporary_folder() as tmp:
    wallet = Wallet(Ledger(tmp))

    @memoize(wallet=wallet)
    def square(n):
        return n * n

    print(square(9), square(9), square(10))  # 81 81 100
    print(square.cache_info())
    # {'entries': 2, 'hits': 1, 'lifetime_hits': 1, 'lifetime_misses': 2}
    square.cache_clear()
    print(square.cache_info())
    # {'entries': 0, 'hits': 0, 'lifetime_hits': 1, 'lifetime_misses': 2}
```

`entries` and `hits` describe what is in the store **now**, so `cache_clear()`
zeroes them. `lifetime_hits` and `lifetime_misses` are store-wide running
totals that survive a clear, an eviction and an expiry, which is what lets you
compute a hit rate that means something.

## 3. Ignore a volatile argument

When an argument does not change the result (a client handle, a session object),
`ignore=` drops it from the key without a custom key function.

```python
import os_helper as osh
from wallet_helper import Wallet, Ledger, memoize

with osh.temporary_folder() as tmp:
    wallet = Wallet(Ledger(tmp))

    @memoize(wallet=wallet, ignore=("client",))
    def fetch(doc_id, client):
        return client.get(doc_id)

    class Client:
        def get(self, doc_id):
            return f"doc:{doc_id}"

    print(fetch(7, client=Client()))  # runs
    print(fetch(7, client=Client()))  # different client, same key, served from the store
```

## 4. Content-address a file

A file argument is keyed by its content, not its path, wherever it sits in the
call. So the same file reached by a different path (a rename, or a byte-for-byte
copy elsewhere) still hits, and two different files never collide, even when the
path is only one argument among several:

```python
import os_helper as osh
from pathlib import Path
from wallet_helper import make_key

with osh.temporary_folder() as tmp:
    d = Path(tmp)
    (d / "clip.wav").write_bytes(b"AUDIO-BYTES")
    (d / "renamed.wav").write_bytes(b"AUDIO-BYTES")  # same content, different name

    # A whole-payload path: renaming still hits.
    print(make_key("asr", d / "clip.wav") == make_key("asr", d / "renamed.wav"))  # True

    # A path nested among other arguments is content-addressed too.
    a = {"args": (str(d / "clip.wav"),), "kwargs": {"lang": "en"}}
    b = {"args": (str(d / "renamed.wav"),), "kwargs": {"lang": "en"}}
    print(make_key("asr", a) == make_key("asr", b))  # True
```

In practice you never build that payload yourself: `@memoize` does it for you, so
two copies of the same file at different paths run the heavy call only once.
Illustrative — `call_some_paid_api` stands in for your own slow, billed call:

```python
from wallet_helper import memoize


@memoize
def transcribe(path, lang="en"):
    return call_some_paid_api(path, lang)  # runs once for a given file + lang


transcribe("clip.wav")  # runs
transcribe("archive/clip.wav")  # same bytes, different path: served from the store
```

## 5. Single-flight across threads

Two threads start the same slow call at once. Only one runs it; the other waits
and receives the same result. No double work, no double bill.

```python
import os_helper as osh
import threading, time
from wallet_helper import Wallet, Ledger

with osh.temporary_folder() as tmp:
    wallet = Wallet(Ledger(tmp))
    runs = []

    def slow():
        runs.append(1)
        time.sleep(0.3)  # long enough for the second thread to arrive mid-flight
        return "value"

    out = []

    def worker():
        out.append(wallet.call("job", {"x": 1}, slow))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print(len(runs))  # 1   -> ran exactly once
    print(sorted(c for _, c in out))  # [False, True]  -> one leader, one follower
```

## 6. A shared store with SQLite

The SQLite backend keeps one file that several processes can share, with atomic
reuse counters. Drop it into a `Wallet` exactly like the JSON store.

```python
import os_helper as osh
from wallet_helper import Wallet, SqliteLedger

with osh.temporary_folder() as tmp:
    wallet = Wallet(SqliteLedger(tmp + "/ledger.db"))
    r, from_cache = wallet.call("job", {"x": 1}, lambda: 42)
    print(r, from_cache)  # 42 False
    r, from_cache = wallet.call("job", {"x": 1}, lambda: 42)
    print(r, from_cache)  # 42 True
```

## 7. Cross-process single-flight over HTTP

`pip install "wallet-helper[api]"` runs a server that centralizes dedup for many
clients, using the claim, submit, release protocol. Start it:

```bash
uvicorn wallet_helper.api:app     # docs at http://127.0.0.1:8000/docs
```

A client claims a key. If it is the leader it runs the work and submits the
result; otherwise it waits and reads the result. This uses only the standard
library, so a client needs nothing installed:

```python
import json, time, urllib.request

BASE = "http://127.0.0.1:8000"


def post(path, body):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    return json.load(urllib.request.urlopen(req))


def get_or_run(namespace, payload, work):
    call = {"namespace": namespace, "payload": payload}
    while True:
        outcome = post("/claim", call)
        if outcome["status"] == "hit":
            return outcome["result"]  # already computed
        if outcome["status"] == "leased":
            result = work()  # we are the leader
            post("/submit", {**call, "result": result})
            return result
        time.sleep(0.2)  # pending: someone else runs it


print(get_or_run("transcribe", {"file": "a.wav"}, lambda: {"text": "hello"}))
```

Followers can also block on one call with `GET /result/{key}?wait=SECONDS`, which
long-polls until the leader's result lands. For a long job, the leader keeps its
lease alive with `POST /extend` (or, in-process, the `SqliteLedger.heartbeat`
context manager).

## 8. A shared store over HTTP with RemoteLedger

`RemoteLedger` is a store backed by that server, so you get cross-process
single-flight with no protocol code: hand it to a `Wallet` and use `@memoize` as
usual. Every host that points at the same server dedups against the same lease.
It uses only the standard library. Illustrative on two counts: the URL has to be
a server you are actually running, and `call_some_paid_api` is yours:

```python
from wallet_helper import Wallet, RemoteLedger, memoize

wallet = Wallet(RemoteLedger("http://cache.internal:8000"))


@memoize(wallet=wallet)
def transcribe(path):
    return call_some_paid_api(path)  # runs once across the whole fleet


transcribe("meeting.wav")
```

## 9. Time-to-live and eviction

Give an entry a freshness window with `ttl` (seconds). After it expires, the next
call recomputes. Prune the store with `evict`, which always drops expired entries
and can also cap by age or count.

```python
import os_helper as osh
from wallet_helper import Wallet, Ledger

with osh.temporary_folder() as tmp:
    ledger = Ledger(tmp)
    wallet = Wallet(ledger)

    wallet.call("price", {"sym": "ACME"}, lambda: 100, ttl=3600)  # fresh for an hour

    ledger.put("old", 1, ttl=0.0)  # already expired
    print(ledger.evict())  # 1   -> removed the expired entry
    print(ledger.evict(max_entries=10))  # 0   -> one entry left, nothing to cap
    print(ledger.evict(older_than=86400))  # 0   -> that entry is seconds old
```

`evict` returns how many entries it removed, so the last two calls printing `0`
is the point: the store was already within both limits.

## 10. Stale-while-revalidate

For the in-process store, serve a stale result immediately and refresh it in the
background, so a caller never waits on the recompute.

```python
import os_helper as osh
import time
from wallet_helper import Wallet, Ledger

with osh.temporary_folder() as tmp:
    wallet = Wallet(Ledger(tmp))
    version = [0]

    def build():
        version[0] += 1
        return version[0]

    print(wallet.call("cfg", {}, build, ttl=0.05))  # (1, False)  -> computed
    time.sleep(0.06)  # let it expire
    print(wallet.call("cfg", {}, build, ttl=60, stale_while_revalidate=True))  # (1, True) -> stale, served now
    time.sleep(0.2)  # the background refresh lands
    print(wallet.call("cfg", {}, build, ttl=60))  # (2, True)   -> refreshed value
```

The `ttl` on the stale-while-revalidate call is the one the **refresh** stores
under, not just the window the current entry is judged against. Asking for
`ttl=0.05` again would refresh into an entry that expires 50 ms later, so the
next caller recomputes anyway and never sees the refreshed value — the reason
the third call here passes `ttl=60`.

## 11. Async functions

`@memoize` handles `async def` too. It caches the awaited result, never the
coroutine object, and concurrent awaits of the same call coalesce into one.

```python
import asyncio
import os_helper as osh
from wallet_helper import Wallet, Ledger, memoize

with osh.temporary_folder() as tmp:
    wallet = Wallet(Ledger(tmp))
    runs = []

    @memoize(wallet=wallet)
    async def fetch(n):
        runs.append(n)
        await asyncio.sleep(0.1)
        return n * n

    async def main():
        # Two concurrent awaits of the same call run the work once.
        a, b = await asyncio.gather(fetch(6), fetch(6))
        c = await fetch(6)  # served from the store
        return a, b, c, len(runs)

    print(asyncio.run(main()))  # (36, 36, 36, 1)
```

## Command line

One command ships with the package: `wallet-helper`, with four subcommands.
Point it at a JSON directory with `--dir` or a SQLite file with `--sqlite`.

```bash
wallet-helper stats                            # entries and calls saved
wallet-helper path                             # where the store lives
wallet-helper clear                            # empty the store (asks first)
wallet-helper evict --older-than 604800        # drop entries older than a week

wallet-helper --sqlite ./ledger.db stats       # inspect a SQLite store
wallet-helper evict --max-entries 1000         # keep only the newest 1000
wallet-helper clear --yes                      # skip the confirmation prompt
```

`stats` prints three lines — the store's location, its entry count, and the
calls those entries have saved:

```text
ledger: /Users/you/.cache/wallet-helper
entries: 0
calls saved (cache hits): 0
```

Installing the `[mcp]` extra adds a second command, `wallet-helper-mcp`, which
serves the HTTP API from example 7 together with an MCP endpoint at `/mcp`.

## Troubleshooting

**The cached result is stale after I edited the function.** The key is the
namespace plus the arguments — never the function's source. Change the body and
every stored result stays valid as far as wallet-helper is concerned. Clear that
one namespace, or bump it:

```python
import os_helper as osh
from wallet_helper import Wallet, Ledger

with osh.temporary_folder() as tmp:
    wallet = Wallet(Ledger(tmp))

    print(wallet.call("rate", {"ccy": "EUR"}, lambda: 1.08))  # (1.08, False)
    print(wallet.call("rate", {"ccy": "EUR"}, lambda: 9.99))  # (1.08, True) -> old value
    wallet.ledger.clear("rate")  # forget just this namespace
    print(wallet.call("rate", {"ccy": "EUR"}, lambda: 9.99))  # (9.99, False)
```

`cache_clear()` on a memoized function does the same for its own namespace.

**`stale_while_revalidate=True` did nothing.** It is implemented for the
in-process `Ledger` only. `SqliteLedger` and `RemoteLedger` go through the
claim/submit lease instead, where the flag is ignored and an expired entry is
recomputed synchronously — so the call returns `(2, False)`, not the stale
`(1, True)` of example 10.

**`cache_info()` shows lifetime numbers I did not expect.** `entries` and `hits`
are scoped to the decorated function's namespace; `lifetime_hits` and
`lifetime_misses` are store-wide by construction, because they are not attached
to entries and so have nothing to be filtered by. Two memoized functions
sharing a store share those two totals.

**A failing call is never cached.** If the work raises, nothing is stored and
the exception propagates, so the next call tries again. The miss is still
counted, which is why `lifetime_misses` can climb while `entries` stays at `0`.

**`wallet-helper stats` reports an empty store.** It is almost always pointing
somewhere else. Run `wallet-helper path`, compare it with the `Ledger` your code
builds, and remember `$WALLET_HELPER_DIR` wins over `~/.cache/wallet-helper`.
