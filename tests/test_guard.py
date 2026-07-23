"""Wallet: memoization, the failure path, and concurrent single-flight.

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
"""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from wallet_helper.guard import Wallet
from wallet_helper.ledger import Ledger


@pytest.fixture()
def wallet(tmp_path: Path) -> Wallet:
    return Wallet(Ledger(tmp_path))


def test_second_identical_call_reuses_the_result(wallet: Wallet) -> None:
    runs = 0

    def heavy() -> dict:
        nonlocal runs
        runs += 1
        return {"text": "hello"}

    r1, hit1 = wallet.call("demo", {"file": "a.wav"}, heavy)
    r2, hit2 = wallet.call("demo", {"file": "a.wav"}, heavy)
    assert (r1, hit1) == ({"text": "hello"}, False)
    assert (r2, hit2) == ({"text": "hello"}, True)
    assert runs == 1  # the heavy call ran once


def test_failure_is_not_cached(wallet: Wallet) -> None:
    calls = 0

    def flaky() -> str:
        nonlocal calls
        calls += 1
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        wallet.call("demo", {"x": 1}, flaky)
    with pytest.raises(RuntimeError):
        wallet.call("demo", {"x": 1}, flaky)  # not cached, so it runs again
    assert calls == 2


def test_concurrent_identical_calls_run_once(wallet: Wallet) -> None:
    # Two threads start the same slow call at once; single-flight must run it once
    # and hand the second thread the first thread's result.
    runs = 0
    started = threading.Event()
    release = threading.Event()

    def slow() -> str:
        nonlocal runs
        runs += 1
        started.set()
        release.wait(timeout=5)  # hold the leader so the follower arrives mid-flight
        return "value"

    results: list[tuple] = []

    def worker() -> None:
        results.append(wallet.call("demo", {"x": 1}, slow))

    leader = threading.Thread(target=worker)
    leader.start()
    started.wait(timeout=5)          # ensure the leader is inside slow()
    follower = threading.Thread(target=worker)
    follower.start()
    release.set()                    # let the leader finish
    leader.join(timeout=5)
    follower.join(timeout=5)

    assert runs == 1                                    # ran exactly once
    assert {r[0] for r in results} == {"value"}         # both got the value
    assert sorted(r[1] for r in results) == [False, True]  # one leader, one follower
