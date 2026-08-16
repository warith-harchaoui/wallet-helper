"""RemoteLedger driven through the real API with a TestClient transport.

Skipped without fastapi/httpx. The transport routes RemoteLedger's HTTP calls
into a FastAPI TestClient, so we exercise the whole path (RemoteLedger -> API ->
SqliteLedger) without binding a socket.

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from wallet_helper.api import create_app  # noqa: E402
from wallet_helper.guard import Wallet, memoize  # noqa: E402
from wallet_helper.remote import RemoteLedger  # noqa: E402
from wallet_helper.sqlite_ledger import SqliteLedger  # noqa: E402


@pytest.fixture()
def remote(tmp_path: Path) -> RemoteLedger:
    client = TestClient(create_app(SqliteLedger(tmp_path / "ledger.db")))

    def transport(method: str, path: str, body: dict | None) -> dict | None:
        resp = client.request(method, path, json=body)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    return RemoteLedger("http://testserver", request=transport)


def test_memoize_over_remote_dedups(remote: RemoteLedger) -> None:
    wallet = Wallet(remote)
    runs = 0

    @memoize(wallet=wallet)
    def transcribe(path: str) -> dict:
        nonlocal runs
        runs += 1
        return {"text": "hi"}

    assert transcribe("a.wav") == {"text": "hi"}
    assert transcribe("a.wav") == {"text": "hi"}  # served from the remote store
    assert runs == 1


def test_remote_stats_clear_and_evict(remote: RemoteLedger) -> None:
    remote.submit(remote_key := "ns_a", {"ok": True})
    assert remote.get(remote_key) == {"ok": True}
    assert remote.stats()["entries"] == 1
    assert remote.has(remote_key) is True
    remote.clear()
    assert remote.stats()["entries"] == 0


def test_remote_claim_submit_release(remote: RemoteLedger) -> None:
    assert remote.claim("ns_x")["status"] == "leased"
    assert remote.claim("ns_x")["status"] == "pending"
    remote.release("ns_x")
    assert remote.claim("ns_x")["status"] == "leased"  # released, so re-leasable


@pytest.mark.parametrize(
    "key",
    [
        "outer.<locals>.inner_deadbeef",  # a nested function's real default namespace
        "a/b_deadbeef",  # a namespace with a slash (the server's own {key:path} case)
        "ns?evil=1_deadbeef",  # "?" would otherwise truncate the path into a query string
        "ns&x=1_deadbeef",  # "&" would otherwise inject a second, bogus query param
        "ns#frag_deadbeef",  # "#" would otherwise truncate into a URL fragment
    ],
)
def test_remote_get_record_survives_url_reserved_characters(remote: RemoteLedger, key: str) -> None:
    # Un-encoded, any of these used to silently mis-route to the wrong (or no)
    # key: everything from "?"/"#" onward never reached the server as part of
    # the path, and "&" inside a query value split into two parameters.
    remote.submit(key, {"ok": True})
    assert remote.get(key) == {"ok": True}
    assert remote.has(key) is True
    assert remote.get("wrong_key") is None  # not a false hit on the truncated prefix


def test_remote_stats_survives_url_reserved_characters_in_namespace(remote: RemoteLedger) -> None:
    remote.submit("ns&x=1_a", {"ok": True})
    remote.submit("other_b", {"ok": True})
    assert remote.stats("ns&x=1")["entries"] == 1
