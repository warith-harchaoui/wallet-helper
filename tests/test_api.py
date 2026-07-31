"""HTTP dedup server: the claim, submit, result protocol. Skipped without fastapi.

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
"""
from __future__ import annotations

from pathlib import Path

import pytest

# Optional surface: needs fastapi and httpx (the TestClient transport). Skip
# cleanly when either is missing so a core install stays green.
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from wallet_helper.api import create_app  # noqa: E402
from wallet_helper.sqlite_ledger import SqliteLedger  # noqa: E402


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(SqliteLedger(tmp_path / "ledger.db")))


def test_health_reports_ok(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok" and "version" in body


def test_claim_submit_result_dedups(client: TestClient) -> None:
    call = {"namespace": "asr", "payload": {"file": "a.wav"}}

    first = client.post("/claim", json=call).json()
    assert first["status"] == "leased"           # first caller computes

    second = client.post("/claim", json=call).json()
    assert second["status"] == "pending"          # a concurrent caller waits

    client.post("/submit", json={**call, "result": {"text": "hi"}})

    third = client.post("/claim", json=call).json()
    assert third["status"] == "hit" and third["result"] == {"text": "hi"}


def test_result_long_poll_returns_after_submit(client: TestClient) -> None:
    call = {"namespace": "asr", "payload": {"file": "b.wav"}}
    key = client.post("/key", json=call).json()["key"]
    client.post("/claim", json=call)                       # lease it
    client.post("/submit", json={**call, "result": 42})    # store it
    got = client.get(f"/result/{key}", params={"wait": 1.0}).json()
    assert got["result"] == 42


def test_result_times_out_when_absent(client: TestClient) -> None:
    assert client.get("/result/nope", params={"wait": 0.0}).status_code == 404


def test_stats_counts_entries(client: TestClient) -> None:
    call = {"namespace": "asr", "payload": {"file": "c.wav"}}
    client.post("/claim", json=call)
    client.post("/submit", json={**call, "result": 1})
    assert client.get("/stats").json()["entries"] == 1


def test_extend_renews_a_lease(client: TestClient) -> None:
    call = {"namespace": "asr", "payload": {"file": "d.wav"}}
    client.post("/claim", json=call)
    assert client.post("/extend", json=call).json()["extended"] is True


def test_clear_empties_the_store(client: TestClient) -> None:
    call = {"namespace": "asr", "payload": {"file": "e.wav"}}
    client.post("/claim", json=call)
    client.post("/submit", json={**call, "result": 1})
    client.post("/clear", json={})
    assert client.get("/stats").json()["entries"] == 0


def test_evict_reports_removed_count(client: TestClient) -> None:
    for name in ("f.wav", "g.wav"):
        call = {"namespace": "asr", "payload": {"file": name}}
        client.post("/claim", json=call)
        client.post("/submit", json={**call, "result": 1})
    assert client.post("/evict", json={"max_entries": 1}).json()["removed"] == 1


def test_missing_ref_is_422(client: TestClient) -> None:
    assert client.post("/claim", json={}).status_code == 422


def test_result_route_accepts_a_key_with_a_slash(client: TestClient) -> None:
    # A namespace with a "/" makes the key itself contain one; the route must
    # still match the whole thing, not just the segment before the first slash.
    call = {"namespace": "asr/v2", "payload": {"file": "h.wav"}}
    key = client.post("/key", json=call).json()["key"]
    assert "/" in key
    client.post("/claim", json=call)
    client.post("/submit", json={**call, "result": "ok"})
    assert client.get(f"/result/{key}").json()["result"] == "ok"
