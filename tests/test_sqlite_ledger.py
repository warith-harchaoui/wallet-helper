"""SQLite ledger: storage parity with the JSON backend, plus the claim lease.

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
"""
from __future__ import annotations

import sqlite3
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


def test_extend_renews_a_lease(ledger: SqliteLedger) -> None:
    assert ledger.claim("asr_k", lease_seconds=100)["status"] == "leased"
    assert ledger.extend("asr_k") is True       # a held lease is renewed
    assert ledger.extend("absent") is False      # nothing to renew


def test_fencing_token_blocks_a_stale_leader(ledger: SqliteLedger) -> None:
    first = ledger.claim("asr_f")
    assert first["status"] == "leased"
    old_token = first["token"]

    # The lease lapses and a new leader steals it, with a different token.
    second = ledger.claim("asr_f", lease_seconds=0)
    assert second["status"] == "leased" and second["token"] != old_token
    new_token = second["token"]

    # The revived old leader cannot extend or release the new leader's lease.
    assert ledger.extend("asr_f", old_token) is False
    ledger.release("asr_f", old_token)                       # no-op, wrong owner
    assert ledger.claim("asr_f")["status"] == "pending"       # new lease still held

    # The rightful holder can renew and release.
    assert ledger.extend("asr_f", new_token) is True
    ledger.release("asr_f", new_token)
    assert ledger.claim("asr_f")["status"] == "leased"


def test_max_entries_auto_evicts(tmp_path: Path) -> None:
    ledger = SqliteLedger(tmp_path / "capped.db", max_entries=2)
    ledger.put("ns_a", 1)
    ledger.put("ns_b", 2)
    ledger.put("ns_c", 3)
    assert ledger.stats()["entries"] == 2  # the store never grows past the cap


def test_clear_scopes_to_a_namespace(ledger: SqliteLedger) -> None:
    ledger.put("a_1", 1)
    ledger.put("b_1", 2)
    ledger.clear("a")
    assert ledger.stats("a")["entries"] == 0 and ledger.stats("b")["entries"] == 1


def test_namespace_like_metacharacters_do_not_leak_across_namespaces(ledger: SqliteLedger) -> None:
    # "a%" is a literal namespace name, not a SQL LIKE pattern. Unescaped, "%"
    # would also match keys under an unrelated namespace like "aXXXb".
    ledger.put("a_1", 1)
    ledger.put("aXXXb_2", 2)
    assert ledger.stats("a%") == {"entries": 0, "hits": 0}
    ledger.clear("a%")
    assert ledger.stats("a")["entries"] == 1 and ledger.stats("aXXXb")["entries"] == 1


def test_operations_do_not_leak_connections(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A connection opened per call and never closed (using sqlite3.Connection as
    # its own context manager only commits/rolls back, it does not close) would
    # exhaust file descriptors over a long-running process. Track every
    # connection this ledger opens and assert each one ends up closed.
    opened: list[sqlite3.Connection] = []
    real_connect = sqlite3.connect

    def tracking_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        opened.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", tracking_connect)

    ledger = SqliteLedger(tmp_path / "ledger.db")
    ledger.put("ns_a", {"v": 1})
    ledger.get("ns_a")
    ledger.has("ns_a")
    ledger.register_hit("ns_a")
    ledger.stats()
    ledger.stats("ns")
    lease = ledger.claim("ns_b")
    ledger.extend("ns_b", lease["token"])
    ledger.submit("ns_b", {"v": 2}, token=lease["token"])
    ledger.release("ns_a")
    ledger.evict()
    ledger.clear("ns")

    assert len(opened) > 5  # sanity: the tracked calls really did open connections
    for conn in opened:
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")  # closed connections refuse to operate
