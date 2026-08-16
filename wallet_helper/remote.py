"""RemoteLedger: use a wallet-helper HTTP server as a shared, remote store.

A :class:`~wallet_helper.ledger.LedgerLike` backend that talks to the dedup
server in :mod:`wallet_helper.api`. Point a wallet at one and every process, on
any host, shares the same store and the same in-flight lease, so the same heavy
call is not run twice across a whole fleet:

>>> from wallet_helper import Wallet, memoize        # doctest: +SKIP
>>> from wallet_helper.remote import RemoteLedger    # doctest: +SKIP
>>> wallet = Wallet(RemoteLedger("http://cache.internal:8000"))   # doctest: +SKIP
>>> @memoize(wallet=wallet)                          # doctest: +SKIP
... def transcribe(path):
...     return call_some_paid_api(path)

Because it offers ``claim`` / ``submit`` / ``release``,
:class:`~wallet_helper.guard.Wallet` routes through the server's lease, giving
cross-process single-flight with no extra code.

It uses only the Python standard library (``urllib``), so a client host needs
nothing installed beyond wallet-helper itself. The HTTP call is isolated in
:meth:`RemoteLedger._request`, which can be replaced with a custom transport
(handy in tests).

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

import os_helper as osh

# Signature of a transport: (method, path, body_or_None) -> parsed_json_or_None.
Transport = Callable[[str, str, "dict | None"], "dict | None"]


class RemoteLedger:
    """A ledger backed by a wallet-helper HTTP server.

    Parameters
    ----------
    base_url : str
        Root URL of the server, for example ``"http://127.0.0.1:8000"``. A
        trailing slash is fine; it is trimmed.
    timeout : float, optional
        Per-request timeout in seconds. Defaults to 30.
    request : callable, optional
        A custom transport ``request(method, path, body) -> dict | None`` used
        instead of the built-in ``urllib`` one. Mainly for tests, where it can
        route to a FastAPI ``TestClient``.
    """

    def __init__(self, base_url: str, *, timeout: float = 30.0, request: Transport | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._transport = request

    @property
    def location(self) -> str:
        """The server URL that backs this ledger (for display)."""
        return self.base_url

    def _request(self, method: str, path: str, body: dict | None = None) -> dict | None:
        """Send one HTTP request and return the parsed JSON, or ``None`` on 404.

        Parameters
        ----------
        method : str
            HTTP method, for example ``"GET"`` or ``"POST"``.
        path : str
            Path on the server, for example ``"/claim"``.
        body : dict, optional
            JSON body for the request; omitted for GET.

        Returns
        -------
        dict or None
            The decoded JSON response, or ``None`` when the server answers 404
            (a normal "not stored yet" signal).
        """
        if self._transport is not None:
            return self._transport(method, path, body)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if data is not None else {}
        req = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            osh.error(f"wallet-helper server error on {method} {path}: {exc}")
            raise

    # --- Claim protocol (this is what Wallet uses for cross-process dedup) -----

    def claim(self, key: str, lease_seconds: float = 300.0) -> dict:
        """Get the cached result, or lease the right to compute it (see the server)."""
        return self._request("POST", "/claim", {"key": key, "lease_seconds": lease_seconds})

    def submit(self, key: str, result: Any, *, token: str | None = None, ttl: float | None = None) -> dict:
        """Store a leader's result on the server and release its own lease."""
        return self._request("POST", "/submit", {"key": key, "result": result, "token": token, "ttl": ttl})

    def release(self, key: str, token: str | None = None) -> None:
        """Drop a lease on the server so a waiter can take over (your own, if fenced)."""
        self._request("POST", "/release", {"key": key, "token": token})

    def extend(self, key: str, token: str | None = None) -> bool:
        """Renew a lease on the server for a long-running job."""
        resp = self._request("POST", "/extend", {"key": key, "token": token})
        return bool(resp and resp.get("extended"))

    # --- LedgerLike read/write surface ----------------------------------------

    def get_record(self, key: str) -> dict | None:
        """Return a partial record ``{"key", "result"}`` for ``key``, or ``None``."""
        # A namespace (and so a key) can legitimately contain URL-reserved
        # characters -- "/" (a namespace with a slash, see the server's
        # {key:path} route), "?", "&", "#" (a plain string is a valid
        # namespace). Un-encoded, any of these truncates or corrupts the
        # request line before it reaches the server: "?" turns the rest of
        # the key into a bogus query string, silently mis-routing to a
        # *different, shorter* key -- the same "namespace as untrusted
        # string" bug class already fixed once for the JSON/SQLite stores.
        resp = self._request("GET", f"/result/{urllib.parse.quote(key, safe='')}")
        return None if resp is None else {"key": key, "result": resp["result"]}

    def get(self, key: str) -> Any | None:
        """Return just the stored result for ``key``, or ``None`` if absent."""
        record = self.get_record(key)
        return None if record is None else record["result"]

    def has(self, key: str) -> bool:
        """Return ``True`` if the server has a result stored for ``key``."""
        return self.get_record(key) is not None

    def put(self, key: str, result: Any, *, ttl: float | None = None) -> None:
        """Store ``result`` for ``key`` on the server (an alias for submit)."""
        self.submit(key, result, ttl=ttl)

    def register_hit(self, key: str) -> None:
        """No-op: the server counts reuses itself, on claim hits and result reads."""

    def stats(self, namespace: str | None = None) -> dict:
        """Return ``{entries, hits}`` from the server (namespace filter optional)."""
        # Same reasoning as get_record: an un-encoded "&" or "=" in namespace
        # would inject or truncate query parameters instead of being sent as
        # part of the namespace's value.
        path = "/stats" if namespace is None else f"/stats?{urllib.parse.urlencode({'namespace': namespace})}"
        return self._request("GET", path)

    def clear(self, namespace: str | None = None) -> None:
        """Delete results on the server, all of them or just one namespace."""
        self._request("POST", "/clear", {"namespace": namespace})

    def evict(self, *, max_entries: int | None = None, older_than: float | None = None) -> int:
        """Prune results on the server and return how many were removed."""
        resp = self._request("POST", "/evict", {"max_entries": max_entries, "older_than": older_than})
        return int(resp["removed"]) if resp else 0
