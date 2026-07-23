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
- [8. Command line](#8-command-line)

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
long-polls until the leader's result lands.

## 8. Command line

Inspect and manage the store. Two interchangeable tools ship: the argparse one
(always available) and a click variant (the `[cli]` extra). Point either at a
JSON directory with `--dir` or a SQLite file with `--sqlite`.

```bash
python -m wallet_helper.cli_argparse stats            # entries and calls saved
python -m wallet_helper.cli_argparse path              # where the store lives
python -m wallet_helper.cli_argparse clear             # empty the store

wallet-helper-click --sqlite ./ledger.db stats         # inspect a SQLite store
wallet-helper-click clear --yes                        # skip the confirmation prompt
```
