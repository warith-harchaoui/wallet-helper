"""wallet-helper — FastAPI HTTP surface + minimal GUI (optional ``[api]`` extra).

Turns the local ledger into a small HTTP service so several processes (or hosts)
can share one content-addressed store: derive a key, look a record up, store a
result with its cost, register a cache hit, read spend/savings stats, and check a
prospective charge against a budget. A minimal browser dashboard lives at
``/gui``.

Design note — why there is no "run my paid call" endpoint
---------------------------------------------------------
:class:`wallet_helper.guard.Wallet` runs an arbitrary callable on a cache miss.
Executing caller-supplied code over HTTP would be a remote-code-execution hole,
so this surface deliberately exposes only the *accounting* half: key derivation,
record storage/lookup, hit counting, stats and budget checks. Your paid callable
stays in your own process; the service is the shared ledger behind it.

Run it
------
``uvicorn wallet_helper.api:app``  then open ``http://127.0.0.1:8000/gui``.

Author
------
Warith HARCHAOUI — https://linkedin.com/in/warith-harchaoui
"""
from __future__ import annotations

from typing import Any

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse
    from pydantic import BaseModel, Field
except ModuleNotFoundError as exc:  # pragma: no cover - exercised only sans fastapi
    # Optional surface: keep the failure actionable rather than a bare traceback.
    raise SystemExit(
        "The HTTP surface needs the optional 'api' extra. Install it with\n"
        "  pip install 'wallet-helper[api]'"
    ) from exc

from wallet_helper import __version__
from wallet_helper.cost import Budget, Cost
from wallet_helper.ledger import Ledger, make_key

# --- Request/response schemas -------------------------------------------------
# Small, explicit models so the OpenAPI docs at /docs are self-describing.


class KeyRequest(BaseModel):
    """A namespace + payload to hash into a ledger key."""

    namespace: str = Field(..., description="Scope for the call, e.g. 'openai.chat'.")
    payload: Any = Field(..., description="What determines the result (JSON value).")


class RecordRequest(BaseModel):
    """Everything needed to store the result of one real paid call."""

    namespace: str
    payload: Any
    result: Any = Field(..., description="The JSON-serialisable result to cache.")
    cost: float = Field(0.0, ge=0.0, description="What this call cost.")
    currency: str = "USD"


class BudgetCheckRequest(BaseModel):
    """A budget snapshot and a prospective charge to test against it."""

    limit: float
    currency: str = "USD"
    spent: float = 0.0
    cost: float = Field(..., ge=0.0)
    cost_currency: str = "USD"


def create_app(ledger: Ledger | None = None) -> FastAPI:
    """Build the FastAPI application around a given (or default) ledger.

    Parameters
    ----------
    ledger : wallet_helper.ledger.Ledger, optional
        The store to serve. Defaults to a :class:`Ledger` at the standard
        location — override in tests to point at a temporary directory.

    Returns
    -------
    fastapi.FastAPI
        The configured application (mount it, or run with uvicorn).
    """
    store = ledger if ledger is not None else Ledger()
    app = FastAPI(
        title="wallet-helper",
        version=__version__,
        summary="Never pay twice for the same billable call — shared ledger over HTTP.",
    )

    @app.get("/health")
    def health() -> dict:
        """Liveness probe: confirm the service is up and where it stores."""
        return {"status": "ok", "version": __version__, "ledger": str(store.dir)}

    @app.get("/stats")
    def stats() -> dict:
        """Spend and cache savings, aggregated per currency."""
        return store.stats()

    @app.post("/key")
    def key(req: KeyRequest) -> dict:
        """Derive the content-addressed ledger key for a namespace + payload."""
        return {"key": make_key(req.namespace, req.payload)}

    @app.get("/records/{key}")
    def get_record(key: str) -> dict:
        """Return the full stored record for ``key`` (404 if unknown)."""
        record = store.get_record(key)
        if record is None:
            # A missing record is a normal "cache miss" from the caller's view;
            # 404 lets clients branch on it without parsing a body.
            raise HTTPException(status_code=404, detail=f"no record for key {key!r}")
        return record

    @app.put("/records")
    def put_record(req: RecordRequest) -> dict:
        """Store the result of a real paid call; returns the key it was stored under."""
        k = make_key(req.namespace, req.payload)
        store.put(k, req.result, cost=req.cost, currency=req.currency)
        return {"key": k, "stored": True}

    @app.post("/records/{key}/hit")
    def register_hit(key: str) -> dict:
        """Count one reuse of a cached result (no-op if the key is unknown)."""
        existed = store.has(key)
        store.register_hit(key)
        return {"key": key, "registered": existed}

    @app.post("/budget/check")
    def budget_check(req: BudgetCheckRequest) -> dict:
        """Would charging ``cost`` break this budget? (does not mutate anything)."""
        budget = Budget(req.limit, req.currency, spent=req.spent)
        cost = Cost(req.cost, req.cost_currency)
        return {"would_exceed": budget.would_exceed(cost), "remaining": budget.remaining()}

    @app.get("/gui", response_class=HTMLResponse)
    def gui() -> str:
        """A minimal zero-build dashboard that reads /stats and shows the totals."""
        return _GUI_HTML

    return app


# A single self-contained page: no framework, no build step — vanilla fetch()
# against /stats. Kept intentionally tiny so the extra ships one HTML string.
_GUI_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>wallet-helper</title>
  <style>
    :root { color-scheme: light dark; }
    body { font: 15px/1.5 system-ui, sans-serif; max-width: 40rem; margin: 3rem auto; padding: 0 1rem; }
    h1 { font-size: 1.4rem; }
    table { border-collapse: collapse; width: 100%; margin-top: 1rem; }
    th, td { text-align: left; padding: .4rem .6rem; border-bottom: 1px solid #8884; }
    td.num { text-align: right; font-variant-numeric: tabular-nums; }
    .muted { opacity: .7; }
  </style>
</head>
<body>
  <h1>wallet-helper</h1>
  <p class="muted">Never pay twice for the same billable call.</p>
  <p id="summary" class="muted">loading…</p>
  <table id="by-currency" hidden>
    <thead><tr><th>currency</th><th class="num">spent</th><th class="num">saved</th></tr></thead>
    <tbody></tbody>
  </table>
  <script type="module">
    // Refresh the totals from the JSON API — the page is just a viewer.
    async function refresh() {
      const s = await (await fetch("stats")).json();
      document.getElementById("summary").textContent =
        `${s.entries} entries · ${s.hits} cache hits (calls saved)`;
      const tbody = document.querySelector("#by-currency tbody");
      const rows = Object.entries(s.by_currency).sort(([a], [b]) => a.localeCompare(b));
      tbody.innerHTML = rows.map(([cur, v]) =>
        `<tr><td>${cur}</td><td class="num">${v.spent.toFixed(4)}</td>` +
        `<td class="num">${v.saved.toFixed(4)}</td></tr>`).join("");
      document.getElementById("by-currency").hidden = rows.length === 0;
    }
    refresh();
  </script>
</body>
</html>
"""

# Module-level app for `uvicorn wallet_helper.api:app`.
app = create_app()
