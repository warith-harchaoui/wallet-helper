"""SQLite ledger: storage parity with the JSON backend, plus the claim lease.

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
"""
from __future__ import annotations

from pathlib import Path

import pytest

from wallet_helper.sqlite_ledger import SqliteLedger


@pytest.fixture()
def ledger(tmp_path: Path) -> SqliteLedger:
    return SqliteLedger(tmp_path / "ledger.db")


def test_put_get_and_stats(ledger: SqliteLedger) -> None:
    ledger.put("asr_a", {"text": "hi"})
    ledger.register_hit("asr_a")
    ledger.register_hit("asr_a")
    assert ledger.get("asr_a") == {"text": "hi"}
    assert ledger.stats() == {"entries": 1, "hits": 2}
    assert ledger.stats("asr") == {"entries": 1, "hits": 2}


def test_missing_key_returns_none(ledger: SqliteLedger) -> None:
    assert ledger.get("absent") is None and ledger.get_record("absent") is None


def test_claim_leases_then_submits(ledger: SqliteLedger) -> None:
    first = ledger.claim("asr_x")
    assert first["status"] == "leased"          # first caller computes
    second = ledger.claim("asr_x")
    assert second["status"] == "pending"        # a concurrent caller waits
    ledger.submit("asr_x", {"done": True})      # leader stores and releases
    third = ledger.claim("asr_x")
    assert third == {"status": "hit", "result": {"done": True}}


def test_release_lets_another_caller_take_over(ledger: SqliteLedger) -> None:
    assert ledger.claim("asr_y")["status"] == "leased"
    ledger.release("asr_y")                      # leader failed and released
    assert ledger.claim("asr_y")["status"] == "leased"  # someone else can lead


def test_stale_lease_is_stolen(ledger: SqliteLedger) -> None:
    assert ledger.claim("asr_z", lease_seconds=100)["status"] == "leased"
    # A zero-second lease is already expired, so the next caller becomes leader.
    assert ledger.claim("asr_z", lease_seconds=0)["status"] == "leased"


def test_clear_scopes_to_a_namespace(ledger: SqliteLedger) -> None:
    ledger.put("a_1", 1)
    ledger.put("b_1", 2)
    ledger.clear("a")
    assert ledger.stats("a")["entries"] == 0 and ledger.stats("b")["entries"] == 1
