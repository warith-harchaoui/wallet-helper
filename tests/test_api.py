"""FastAPI HTTP surface — round-trips against a temporary ledger. Skipped sans fastapi.

Author
------
Warith HARCHAOUI — https://linkedin.com/in/warith-harchaoui
"""
from __future__ import annotations

from pathlib import Path

import pytest

# Optional surface: needs fastapi + httpx (TestClient transport). Skip cleanly
# when either is missing so a core-only install stays green.
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from wallet_helper.api import create_app  # noqa: E402
from wallet_helper.ledger import Ledger  # noqa: E402


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    # Point the app at a temp ledger so tests never touch the real store.
    return TestClient(create_app(Ledger(tmp_path)))


def test_health_reports_ok(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok" and "version" in body


def test_put_then_get_record_round_trips(client: TestClient) -> None:
    key = client.post("/key", json={"namespace": "demo", "payload": {"x": 1}}).json()["key"]
    put = client.put(
        "/records",
        json={"namespace": "demo", "payload": {"x": 1}, "result": {"ok": True}, "cost": 0.75, "currency": "EUR"},
    ).json()
    assert put["key"] == key  # key is derived identically both ways
    record = client.get(f"/records/{key}").json()
    assert record["result"] == {"ok": True} and record["cost"] == 0.75


def test_missing_record_is_404(client: TestClient) -> None:
    assert client.get("/records/nope").status_code == 404


def test_hit_then_stats_shows_savings(client: TestClient) -> None:
    client.put(
        "/records",
        json={"namespace": "demo", "payload": {"x": 1}, "result": 1, "cost": 0.5, "currency": "USD"},
    )
    key = client.post("/key", json={"namespace": "demo", "payload": {"x": 1}}).json()["key"]
    client.post(f"/records/{key}/hit")
    stats = client.get("/stats").json()
    assert stats["entries"] == 1 and round(stats["saved"], 2) == 0.5


def test_budget_check_flags_overspend(client: TestClient) -> None:
    body = client.post(
        "/budget/check",
        json={"limit": 1.0, "currency": "EUR", "spent": 0.8, "cost": 0.5, "cost_currency": "EUR"},
    ).json()
    assert body["would_exceed"] is True and round(body["remaining"], 2) == 0.2


def test_gui_serves_html(client: TestClient) -> None:
    resp = client.get("/gui")
    assert resp.status_code == 200 and "text/html" in resp.headers["content-type"]
    assert "wallet-helper" in resp.text
