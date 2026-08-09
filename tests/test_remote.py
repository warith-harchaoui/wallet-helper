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
