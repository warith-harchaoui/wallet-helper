"""FastAPI surface: a centralized dedup server (optional ``[api]`` extra).

Many clients (processes, hosts, containers) point at one wallet-helper server so
the same heavy call is never run twice, even when two identical calls start at
almost the same time. The server holds one shared ledger and hands out a lease:
the first caller of a key runs the work, everyone else waits and gets that same
result when it lands.

Every endpoint accepts either a ready-made ``key`` or a ``namespace`` plus a
``payload`` (the server hashes it), so both :class:`wallet_helper.remote.RemoteLedger`
(which sends keys) and a hand-written client (which sends inputs) work.

Protocol (claim, run, submit)
-----------------------------
1. ``POST /claim``. The reply is ``hit`` (already computed, use ``result``),
   ``leased`` (you are the leader, run the work then ``POST /submit``), or
   ``pending`` (someone else is running it, wait and claim again).
2. The leader runs the work, then ``POST /submit`` with the result. On failure it
   calls ``POST /release`` so a waiter can take over. For a long job it calls
   ``POST /extend`` to keep the lease alive.
3. Followers either re-claim, or call ``GET /result/{key}?wait=SECONDS`` which
   blocks until the result is ready.

There is no endpoint that runs your code: the work stays in your process.

Run it
------
``uvicorn wallet_helper.api:app`` then talk to it over HTTP (docs at ``/docs``).

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
"""
from __future__ import annotations

import asyncio
from typing import Any

import os_helper as osh

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
except ModuleNotFoundError as exc:  # pragma: no cover - only hit without fastapi
    raise SystemExit(
        "The HTTP surface needs the optional 'api' extra. Install it with\n"
        "  pip install 'wallet-helper[api]'"
    ) from exc

from wallet_helper import __version__
from wallet_helper.ledger import make_key
from wallet_helper.sqlite_ledger import SqliteLedger


class Ref(BaseModel):
    """A reference to a call: a ready ``key``, or a ``namespace`` plus ``payload``.

    ``token`` is the fencing token from a ``claim``; pass it to ``submit``,
    ``release``, and ``extend`` so only the current leader can finish a lease.
    """

    key: str | None = None
    namespace: str | None = None
    payload: Any | None = None
    token: str | None = None


class ClaimRequest(Ref):
    """A claim, with how long the lease is honoured before it can be stolen."""

    lease_seconds: float = 300.0


class SubmitRequest(Ref):
    """A leader submitting the result it computed, with an optional freshness ttl."""

    result: Any = None
    ttl: float | None = None


class ClearRequest(BaseModel):
    """A request to clear the store, all of it or one namespace."""

    namespace: str | None = None


class EvictRequest(BaseModel):
    """A request to prune the store by age and/or a size cap."""

    max_entries: int | None = None
    older_than: float | None = None


def _resolve_key(ref: Ref) -> str:
    """Return the ledger key for a reference, hashing the payload when needed.

    Parameters
    ----------
    ref : Ref
        A request carrying either ``key`` or ``namespace`` (with optional
        ``payload``).

    Returns
    -------
    str
        The ledger key.

    Raises
    ------
    fastapi.HTTPException
        With status 422 when neither a key nor a namespace was given.
    """
    if ref.key:
        return ref.key
    if ref.namespace is not None:
        return make_key(ref.namespace, ref.payload)
    raise HTTPException(status_code=422, detail="provide 'key', or 'namespace' with an optional 'payload'")


def create_app(ledger: SqliteLedger | None = None) -> FastAPI:
    """Build the app around a SQLite ledger (its atomic lease backs the dedup).

    Parameters
    ----------
    ledger : wallet_helper.sqlite_ledger.SqliteLedger, optional
        The shared store. Defaults to a :class:`SqliteLedger` at the standard
        location. A SQLite backend is required because the claim lease relies on
        its atomic transactions.

    Returns
    -------
    fastapi.FastAPI
        The configured application.
    """
    store = ledger if ledger is not None else SqliteLedger()
    osh.info(f"wallet-helper server backed by {store.location}")
    app = FastAPI(title="wallet-helper", version=__version__)

    @app.get("/health")
    def health() -> dict:
        """Report that the server is up and where it stores results."""
        return {"status": "ok", "version": __version__, "ledger": store.location}

    @app.get("/stats")
    def stats(namespace: str | None = None) -> dict:
        """Return how many results are cached and how often they were reused."""
        return store.stats(namespace)

    @app.post("/key")
    def key(ref: Ref) -> dict:
        """Return the content-addressed key for a reference."""
        return {"key": _resolve_key(ref)}

    @app.post("/claim")
    def claim(req: ClaimRequest) -> dict:
        """Get the cached result, or lease the right to compute it (see module doc)."""
        k = _resolve_key(req)
        return {"key": k, **store.claim(k, lease_seconds=req.lease_seconds)}

    @app.post("/submit")
    def submit(req: SubmitRequest) -> dict:
        """Store a leader's result and release its lease."""
        k = _resolve_key(req)
        store.submit(k, req.result, token=req.token, ttl=req.ttl)
        return {"key": k, "stored": True}

    @app.post("/release")
    def release(ref: Ref) -> dict:
        """Drop a lease without a result, so a waiter can take over."""
        k = _resolve_key(ref)
        store.release(k, token=ref.token)
        return {"key": k, "released": True}

    @app.post("/extend")
    def extend(ref: Ref) -> dict:
        """Renew a lease so a long-running job is not treated as abandoned."""
        k = _resolve_key(ref)
        return {"key": k, "extended": store.extend(k, token=ref.token)}

    @app.get("/result/{key:path}")
    async def result(key: str, wait: float = 0.0, poll: float = 0.1) -> dict:
        """Return a stored result, optionally waiting up to ``wait`` seconds.

        With ``wait > 0`` this long-polls: it checks the ledger every ``poll``
        seconds until the result is ready or the wait runs out, so a follower can
        block on one call and receive the leader's result when it lands. The
        SQLite reads run in a worker thread, so a long poll never blocks the
        event loop and the server stays responsive under load.

        The ``:path`` converter matches a key that contains a ``/`` (a namespace
        with a slash in it), not only the common ``namespace_hash`` shape.
        """
        waited = 0.0
        while True:
            record = await asyncio.to_thread(store.get_record, key)
            if record is not None:
                await asyncio.to_thread(store.register_hit, key)
                return {"key": key, "result": record["result"]}
            if waited >= wait:
                raise HTTPException(status_code=404, detail=f"no result for key {key!r} yet")
            await asyncio.sleep(poll)
            waited += poll

    @app.post("/clear")
    def clear(req: ClearRequest) -> dict:
        """Delete cached results, all of them or one namespace."""
        store.clear(req.namespace)
        osh.info(f"cleared {'all' if req.namespace is None else req.namespace} on {store.location}")
        return {"cleared": True}

    @app.post("/evict")
    def evict(req: EvictRequest) -> dict:
        """Prune the store by age and/or a size cap; report how many were removed."""
        removed = store.evict(max_entries=req.max_entries, older_than=req.older_than)
        osh.info(f"evicted {removed} entries from {store.location}")
        return {"removed": removed}

    return app


# Module-level app for `uvicorn wallet_helper.api:app`.
app = create_app()
