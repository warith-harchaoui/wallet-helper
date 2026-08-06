"""wallet-helper: Model Context Protocol (MCP) surface (optional ``[mcp]`` extra).

A thin adapter that exposes the FastAPI app from :mod:`wallet_helper.api` as MCP
tools, so any MCP-aware host (an agent runtime, an IDE integration, a custom
shell) can call the centralized dedup server — claim/run/submit a lease,
check /stats, fetch a stored /result, /clear or /evict the store — as
first-class tools. Uses `fastapi-mcp`
(https://github.com/tadata-org/fastapi_mcp): one wrapper publishes the whole
existing HTTP surface, so the routes are never duplicated.

Install the extra to pull in ``fastapi-mcp``::

    pip install "wallet-helper[mcp]"

Then run the server (HTTP API + MCP endpoint at ``/mcp``)::

    wallet-helper-mcp             # console entry point
    python -m wallet_helper.mcp   # equivalent

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
"""
from __future__ import annotations

try:
    from fastapi_mcp import FastApiMCP
except ModuleNotFoundError as exc:  # pragma: no cover - only hit without the extra
    raise SystemExit(
        "The MCP surface needs the optional 'mcp' extra. Install it with\n"
        "  pip install 'wallet-helper[mcp]'"
    ) from exc

# Reuse the exact same FastAPI app: MCP is a thin wrapper on top, no new routes.
from wallet_helper.api import app

# Publish the HTTP endpoints (claim / submit / release / extend / result /
# stats / clear / evict) as MCP tools.
mcp = FastApiMCP(
    app,
    name="wallet-helper",
    description=(
        "wallet-helper MCP tools: persistent, content-addressed memoization "
        "for expensive calls, with single-flight so concurrent identical "
        "calls collapse into one. Claim a lease, submit or fetch a result, "
        "inspect stats, clear or evict the store — entirely on the local "
        "machine (or a shared server you point every client at)."
    ),
)
# Newer fastapi-mcp splits mount() into transport-specific mount_http(); fall back to
# the legacy mount() so a range of fastapi-mcp versions keeps working.
if hasattr(mcp, "mount_http"):
    mcp.mount_http()
else:  # pragma: no cover - legacy fastapi-mcp
    mcp.mount()


def main() -> None:
    """Console entry point (``wallet-helper-mcp``): serve the API + MCP endpoint.

    Boots the FastAPI app (now serving both the plain HTTP routes and the
    ``/mcp`` MCP endpoint) with uvicorn in a single worker. Local-first: binds
    to loopback by default (override with ``WALLET_HELPER_HOST`` /
    ``WALLET_HELPER_PORT``).
    """
    import os

    import uvicorn

    host = os.environ.get("WALLET_HELPER_HOST", "127.0.0.1")
    port = int(os.environ.get("WALLET_HELPER_PORT", "8012"))
    print(f"wallet-helper API + MCP -> http://{host}:{port}  (MCP at /mcp)")
    uvicorn.run(app, host=host, port=port, workers=1)


if __name__ == "__main__":  # pragma: no cover
    main()
