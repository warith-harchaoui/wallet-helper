"""``SqliteLedger.heartbeat``: what it renews, when it stops, what it never touches.

The contract
------------
``heartbeat(key, token, interval=...)`` is a context manager. While its block
runs, a daemon thread calls :meth:`SqliteLedger.extend` every ``interval``
seconds, which stamps the lease's ``leased_at`` with the current wall clock.
That stamp is the only thing :meth:`SqliteLedger.claim` reads to decide
whether a lease is still live, so the observable effect is this: a waiter
asking with a ``lease_seconds`` shorter than the job keeps seeing
``pending`` instead of stealing the lease.

The rest pins the edges: the renewal stops when the block exits (normally or
by exception, without waiting out a long interval), it is fenced by the
token, it never creates a lease that does not exist, and one failed renewal
does not end the others.

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

import pytest

from wallet_helper.sqlite_ledger import SqliteLedger

TICK = 0.02  # heartbeat interval used throughout, in seconds


@pytest.fixture()
def ledger(tmp_path: Path) -> SqliteLedger:
    return SqliteLedger(tmp_path / "ledger.db")


def _leased_at(ledger: SqliteLedger, key: str) -> float | None:
    """Read the raw lease stamp, bypassing the class under test."""
    with sqlite3.connect(ledger.path) as conn:
        row = conn.execute("SELECT leased_at FROM pending WHERE key = ?", (key,)).fetchone()
    return None if row is None else row[0]


def _owner(ledger: SqliteLedger, key: str) -> str | None:
    with sqlite3.connect(ledger.path) as conn:
        row = conn.execute("SELECT owner FROM pending WHERE key = ?", (key,)).fetchone()
    return None if row is None else row[0]


def _wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(TICK / 4)
    return predicate()


def _heartbeat_threads() -> int:
    """Live threads running the heartbeat's renewal loop."""
    return sum(1 for t in threading.enumerate() if getattr(t, "_target", None) and t._target.__name__ == "_renew")


def test_heartbeat_moves_the_lease_stamp_forward_repeatedly(ledger: SqliteLedger) -> None:
    token = ledger.claim("job_a")["token"]
    stamps = [_leased_at(ledger, "job_a")]
    with ledger.heartbeat("job_a", token, interval=TICK):
        for _ in range(3):
            last = stamps[-1]
            assert _wait_until(lambda last=last: _leased_at(ledger, "job_a") > last)
            stamps.append(_leased_at(ledger, "job_a"))
    assert stamps == sorted(stamps) and len(set(stamps)) == 4
    # It renews the stamp and nothing else: the lease still belongs to its leader.
    assert _owner(ledger, "job_a") == token


def test_the_stamp_is_the_wall_clock_at_renewal(ledger: SqliteLedger) -> None:
    token = ledger.claim("job_c")["token"]
    first = _leased_at(ledger, "job_c")
    time.sleep(5 * TICK)  # let the claim stamp age before any renewal
    before = time.time()
    with ledger.heartbeat("job_c", token, interval=TICK):
        assert _wait_until(lambda: _leased_at(ledger, "job_c") > first)
        stamp = _leased_at(ledger, "job_c")
    after = time.time()
    # Renewed to "now", not pushed forward by an interval or a lease length.
    assert before <= stamp <= after


def test_a_waiter_sees_pending_while_the_heartbeat_runs(ledger: SqliteLedger, tmp_path: Path) -> None:
    lease_seconds = 6 * TICK
    token = ledger.claim("job_w", lease_seconds=lease_seconds)["token"]
    other = SqliteLedger(tmp_path / "ledger.db")  # a second handle, as another process would hold
    with ledger.heartbeat("job_w", token, interval=TICK):
        # Run well past the lease: without renewal the waiter would steal it.
        end = time.monotonic() + 5 * lease_seconds
        while time.monotonic() < end:
            assert other.claim("job_w", lease_seconds=lease_seconds)["status"] == "pending"
            time.sleep(TICK)
    # Once the heartbeat is gone the lease lapses and a waiter takes over.
    time.sleep(2 * lease_seconds)
    stolen = other.claim("job_w", lease_seconds=lease_seconds)
    assert stolen["status"] == "leased" and stolen["token"] != token


def test_renewal_stops_when_the_block_exits(ledger: SqliteLedger) -> None:
    token = ledger.claim("job_s")["token"]
    baseline = _heartbeat_threads()
    with ledger.heartbeat("job_s", token, interval=TICK):
        assert _heartbeat_threads() == baseline + 1
        start = _leased_at(ledger, "job_s")
        assert _wait_until(lambda: _leased_at(ledger, "job_s") > start)
    assert _heartbeat_threads() == baseline
    frozen = _leased_at(ledger, "job_s")
    time.sleep(10 * TICK)
    assert _leased_at(ledger, "job_s") == frozen


def test_renewal_stops_and_the_error_propagates_when_the_block_raises(ledger: SqliteLedger) -> None:
    token = ledger.claim("job_e")["token"]
    baseline = _heartbeat_threads()
    with pytest.raises(RuntimeError, match="job failed"):
        with ledger.heartbeat("job_e", token, interval=TICK):
            raise RuntimeError("job failed")
    assert _heartbeat_threads() == baseline
    frozen = _leased_at(ledger, "job_e")
    time.sleep(10 * TICK)
    assert _leased_at(ledger, "job_e") == frozen


def test_exit_does_not_wait_out_a_long_interval(ledger: SqliteLedger) -> None:
    token = ledger.claim("job_l")["token"]
    start = time.monotonic()
    with ledger.heartbeat("job_l", token, interval=30.0):
        pass
    assert time.monotonic() - start < 2.0


def test_a_stale_leaders_heartbeat_cannot_renew_the_new_lease(ledger: SqliteLedger) -> None:
    old = ledger.claim("job_f")["token"]
    new = ledger.claim("job_f", lease_seconds=0)["token"]  # the lease lapsed and was stolen
    assert new != old
    stamp = _leased_at(ledger, "job_f")
    with ledger.heartbeat("job_f", old, interval=TICK):
        time.sleep(10 * TICK)
    assert _leased_at(ledger, "job_f") == stamp
    assert _owner(ledger, "job_f") == new


def test_without_a_token_the_heartbeat_renews_whoever_holds_the_lease(ledger: SqliteLedger) -> None:
    ledger.claim("job_n")
    new = ledger.claim("job_n", lease_seconds=0)["token"]
    stamp = _leased_at(ledger, "job_n")
    with ledger.heartbeat("job_n", interval=TICK):
        assert _wait_until(lambda: _leased_at(ledger, "job_n") > stamp)
    assert _owner(ledger, "job_n") == new  # renewed, never taken over


def test_a_heartbeat_on_an_absent_lease_creates_nothing(ledger: SqliteLedger) -> None:
    with ledger.heartbeat("never_claimed", "some-token", interval=TICK):
        time.sleep(10 * TICK)
    with ledger.heartbeat("never_claimed", interval=TICK):
        time.sleep(10 * TICK)
    assert _leased_at(ledger, "never_claimed") is None
    assert ledger.claim("never_claimed")["status"] == "leased"


def test_a_heartbeat_outliving_its_submit_does_not_resurrect_the_lease(ledger: SqliteLedger) -> None:
    token = ledger.claim("job_r")["token"]
    with ledger.heartbeat("job_r", token, interval=TICK):
        ledger.submit("job_r", 42, token=token)  # the lease row is gone from here on
        time.sleep(10 * TICK)
    assert _leased_at(ledger, "job_r") is None
    assert ledger.claim("job_r") == {"status": "hit", "result": 42}


def test_one_failed_renewal_does_not_end_the_heartbeat(ledger: SqliteLedger, monkeypatch: pytest.MonkeyPatch) -> None:
    """A transient error (say ``database is locked`` past the busy timeout) is one missed beat.

    Before, the exception escaped the renewal thread and killed it: the block
    went on running, believing its lease was kept alive, while the lease
    quietly lapsed and a waiter started the same work -- the duplicate the
    heartbeat exists to prevent.
    """
    token = ledger.claim("job_t")["token"]
    real_extend = ledger.extend
    calls = {"n": 0}

    def flaky_extend(key: str, token: str | None = None) -> bool:
        calls["n"] += 1
        if calls["n"] == 1:
            raise sqlite3.OperationalError("database is locked")
        return real_extend(key, token)

    monkeypatch.setattr(ledger, "extend", flaky_extend)
    stamp = _leased_at(ledger, "job_t")
    with ledger.heartbeat("job_t", token, interval=TICK):
        assert _wait_until(lambda: _leased_at(ledger, "job_t") > stamp)
    assert calls["n"] >= 2
