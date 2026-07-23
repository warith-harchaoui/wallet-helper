# wallet-helper Examples

A cookbook of common uses. Every Python block is self-contained and uses a
temporary store, so you can paste it into a REPL and watch it work.

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
- [12. Command line](#12-command-line)

## 1. Memoize a heavy call

Wrap any function whose run is expensive. The first call runs it; an identical
second call is served from the store. `from_cache` tells you which happened.

```python
import os_helper as osh
from wallet_helper import Wallet, Ledger

with osh.temporary_folder() as tmp:
    wallet = Wallet(Ledger(tmp))

    def transcribe(path):
        return {"text": "hello"}   # stand-in for a slow, paid API call

    r1, from_cache1 = wallet.call("transcribe", {"file": "a.wav"}, lambda: transcribe("a.wav"))
    r2, from_cache2 = wallet.call("transcribe", {"file": "a.wav"}, lambda: transcribe("a.wav"))

    print(r1, from_cache1)   # {'text': 'hello'} False   -> ran
    print(r2, from_cache2)   # {'text': 'hello'} True    -> served from the store
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

    print(square(9), square(9), square(10))   # 81 81 100
    print(square.cache_info())                 # {'entries': 2, 'hits': 1}
    square.cache_clear()
    print(square.cache_info())                 # {'entries': 0, 'hits': 0}
```

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

    print(fetch(7, client=Client()))   # runs
    print(fetch(7, client=Client()))   # different client, same key, served from the store
```

## 4. Content-address a file

Pass a file path (or raw `bytes`) as the payload. The key is the file's content,
so renaming the file still hits, and two different files never collide.

```python
import os_helper as osh
from pathlib import Path
from wallet_helper import make_key

with osh.temporary_folder() as tmp:
    d = Path(tmp)
    (d / "clip.wav").write_bytes(b"AUDIO-BYTES")
    (d / "renamed.wav").write_bytes(b"AUDIO-BYTES")   # same content, different name

    print(make_key("asr", d / "clip.wav") == make_key("asr", d / "renamed.wav"))   # True
    print(make_key("asr", d / "clip.wav") == make_key("asr", b"AUDIO-BYTES"))       # True
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
        time.sleep(0.3)   # long enough for the second thread to arrive mid-flight
        return "value"

    out = []
    def worker():
        out.append(wallet.call("job", {"x": 1}, slow))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads: t.start()
    for t in threads: t.join()

    print(len(runs))                       # 1   -> ran exactly once
    print(sorted(c for _, c in out))       # [False, True]  -> one leader, one follower
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
    print(r, from_cache)   # 42 False
    r, from_cache = wallet.call("job", {"x": 1}, lambda: 42)
    print(r, from_cache)   # 42 True
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
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))

def get_or_run(namespace, payload, work):
    call = {"namespace": namespace, "payload": payload}
    while True:
        outcome = post("/claim", call)
        if outcome["status"] == "hit":
            return outcome["result"]                       # already computed
        if outcome["status"] == "leased":
            result = work()                                # we are the leader
            post("/submit", {**call, "result": result})
            return result
        time.sleep(0.2)                                    # pending: someone else runs it

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
It uses only the standard library.

```python
from wallet_helper import Wallet, RemoteLedger, memoize

wallet = Wallet(RemoteLedger("http://cache.internal:8000"))

@memoize(wallet=wallet)
def transcribe(path):
    return call_some_paid_api(path)   # runs once across the whole fleet

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

    wallet.call("price", {"sym": "ACME"}, lambda: 100, ttl=3600)   # fresh for an hour

    ledger.put("old", 1, ttl=0.0)                 # already expired
    print(ledger.evict())                          # 1   -> removed the expired entry
    print(ledger.evict(max_entries=10))            # keep only the newest 10
    print(ledger.evict(older_than=86400))          # drop entries older than a day
```

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

    print(wallet.call("cfg", {}, build, ttl=0.05))   # (1, False)  -> computed
    time.sleep(0.06)                                   # let it expire
    print(wallet.call("cfg", {}, build, ttl=0.05, stale_while_revalidate=True))  # (1, True) stale now
    time.sleep(0.2)                                    # background refresh runs
    print(wallet.call("cfg", {}, build, ttl=100))     # (2, True)   -> refreshed value
```

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
        c = await fetch(6)          # served from the store
        return a, b, c, len(runs)

    print(asyncio.run(main()))       # (36, 36, 36, 1)
```

## 12. Command line

Inspect and manage the store. Two interchangeable tools ship: the argparse one
(always available) and a click variant (the `[cli]` extra). Point either at a
JSON directory with `--dir` or a SQLite file with `--sqlite`.

```bash
python -m wallet_helper.cli_argparse stats            # entries and calls saved
python -m wallet_helper.cli_argparse path              # where the store lives
python -m wallet_helper.cli_argparse clear             # empty the store
python -m wallet_helper.cli_argparse evict --older-than 604800   # drop entries older than a week

wallet-helper-click --sqlite ./ledger.db stats         # inspect a SQLite store
wallet-helper-click evict --max-entries 1000           # keep only the newest 1000
wallet-helper-click clear --yes                        # skip the confirmation prompt
```
