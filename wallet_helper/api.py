"""FastAPI surface: a centralized dedup server (optional ``[api]`` extra).

Many clients (processes, hosts, containers) point at one wallet-helper server so
the same heavy call is never run twice, even when two identical calls start at
almost the same time. The server holds one shared ledger and hands out a lease:
the first caller of a key runs the work, everyone else waits and gets that same
result when it lands.

Protocol (claim, run, submit)
-----------------------------
1. ``POST /claim`` with a namespace and payload. The reply is one of:
   ``hit`` (already computed, use ``result``), ``leased`` (you are the leader,
   run the work then ``POST /submit``), or ``pending`` (someone else is running
   it, wait and claim again, or long-poll ``GET /result``).
2. Leader runs the heavy work, then ``POST /submit`` with the result. On failure
   it calls ``POST /release`` so a waiter can take over.
3. Followers either re-claim, or call ``GET /result/{key}?wait=SECONDS`` which
   blocks until the result is ready.

There is no endpoint that runs your code: the work stays in your process, so the
server never executes caller-supplied code.

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

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel, Field
except ModuleNotFoundError as exc:  # pragma: no cover - only hit without fastapi
    raise SystemExit(
        "The HTTP surface needs the optional 'api' extra. Install it with\n"
        "  pip install 'wallet-helper[api]'"
    ) from exc

from wallet_helper import __version__
from wallet_helper.ledger import make_key
from wallet_helper.sqlite_ledger import SqliteLedger


class Call(BaseModel):
    """A namespace plus the payload that identifies one call."""

    namespace: str = Field(..., description="Scope for the call, e.g. 'transcribe'.")
    payload: Any = Field(..., description="What determines the result (any JSON value).")


class ClaimRequest(Call):
    """A claim, with how long the lease is honoured before it can be stolen."""

    lease_seconds: float = 300.0


class SubmitRequest(Call):
    """A leader submitting the result it computed."""

    result: Any


def create_app(ledger: SqliteLedger | None = None) -> FastAPI:
    """Build the app around a SQLite ledger (its atomic lease backs the dedup).

    Parameters
    ----------
    ledger : wallet_helper.sqlite_ledger.SqliteLedger, optional
        The shared store. Defaults to a :class:`SqliteLedger` at the standard
        location. A SQLite backend is required because the claim/submit lease
        relies on its atomic transactions.

    Returns
    -------
    fastapi.FastAPI
        The configured application.
    """
    store = ledger if ledger is not None else SqliteLedger()
    app = FastAPI(title="wallet-helper", version=__version__)

    @app.get("/health")
    def health() -> dict:
        """Report that the server is up and where it stores results."""
        return {"status": "ok", "version": __version__, "ledger": store.location}

    @app.get("/stats")
    def stats() -> dict:
        """Return how many results are cached and how often they were reused."""
        return store.stats()

    @app.post("/key")
    def key(call: Call) -> dict:
        """Return the content-addressed key for a namespace and payload."""
        return {"key": make_key(call.namespace, call.payload)}

    @app.post("/claim")
    def claim(req: ClaimRequest) -> dict:
        """Get the cached result, or lease the right to compute it (see module doc)."""
        k = make_key(req.namespace, req.payload)
        outcome = store.claim(k, lease_seconds=req.lease_seconds)
        return {"key": k, **outcome}

    @app.post("/submit")
    def submit(req: SubmitRequest) -> dict:
        """Store a leader's result and release its lease."""
        k = make_key(req.namespace, req.payload)
        store.submit(k, req.result)
        return {"key": k, "stored": True}

    @app.post("/release")
    def release(call: Call) -> dict:
        """Drop a lease without a result, so a waiter can take over."""
        k = make_key(call.namespace, call.payload)
        store.release(k)
        return {"key": k, "released": True}

    @app.get("/result/{key}")
    async def result(key: str, wait: float = 0.0, poll: float = 0.1) -> dict:
        """Return a stored result, optionally waiting up to ``wait`` seconds.

        With ``wait > 0`` this long-polls: it checks the ledger every ``poll``
        seconds until the result is ready or the wait runs out, so a follower can
        block on one call and receive the leader's result when it lands.
        """
        waited = 0.0
        while True:
            record = store.get_record(key)
            if record is not None:
                store.register_hit(key)
                return {"key": key, "result": record["result"]}
            if waited >= wait:
                raise HTTPException(status_code=404, detail=f"no result for key {key!r} yet")
            await asyncio.sleep(poll)
            waited += poll

    return app


# Module-level app for `uvicorn wallet_helper.api:app`.
app = create_app()
