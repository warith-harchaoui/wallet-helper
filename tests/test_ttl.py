"""Time-to-live, stale-while-revalidate, and eviction.

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from wallet_helper.guard import Wallet
from wallet_helper.ledger import Ledger
from wallet_helper.sqlite_ledger import SqliteLedger


def test_ttl_expires_and_recomputes(tmp_path: Path) -> None:
    wallet = Wallet(Ledger(tmp_path))
    runs = 0

    def heavy() -> str:
        nonlocal runs
        runs += 1
        return "v"

    _, c1 = wallet.call("ns", {"x": 1}, heavy, ttl=0.05)
    _, c2 = wallet.call("ns", {"x": 1}, heavy, ttl=0.05)
    assert (c1, c2) == (False, True)   # fresh hit the second time
    time.sleep(0.06)
    _, c3 = wallet.call("ns", {"x": 1}, heavy, ttl=0.05)
    assert c3 is False and runs == 2   # expired, so it recomputed


def test_stale_while_revalidate_serves_stale_then_refreshes(tmp_path: Path) -> None:
    wallet = Wallet(Ledger(tmp_path))
    runs = 0

    def heavy() -> int:
        nonlocal runs
        runs += 1
        return runs

    first, _ = wallet.call("ns", {"x": 1}, heavy, ttl=0.05)
    assert first == 1
    time.sleep(0.06)  # let it expire
    stale, from_cache = wallet.call("ns", {"x": 1}, heavy, ttl=0.05, stale_while_revalidate=True)
    assert (stale, from_cache) == (1, True)  # served the stale value at once

    # The refresh runs in the background; wait for it to bump the run count.
    deadline = time.time() + 2
    while runs < 2 and time.time() < deadline:
        time.sleep(0.01)
    assert runs == 2


def test_sqlite_ttl_via_claim(tmp_path: Path) -> None:
    ledger = SqliteLedger(tmp_path / "ledger.db")
    # Fresh well within its ttl: a generous window so even a slow or loaded
    # runner reads it back as a hit. (A tight 0.05 s window used to flake here,
    # expiring between the submit and the claim under load.)
    ledger.submit("ns_fresh", "v", ttl=30.0)
    assert ledger.claim("ns_fresh")["status"] == "hit"
    # Already expired: ttl=0 puts expiry at store time, so any later claim sees
    # it as stale and re-leases, with no sleep and no timing race.
    ledger.submit("ns_stale", "v", ttl=0.0)
    assert ledger.claim("ns_stale")["status"] == "leased"


@pytest.mark.parametrize("make", [lambda p: Ledger(p), lambda p: SqliteLedger(p / "l.db")])
def test_evict_expired_and_by_count(tmp_path: Path, make) -> None:
    ledger = make(tmp_path)
    ledger.put("ns_old", 1, ttl=0.01)
    ledger.put("ns_a", 2)
    ledger.put("ns_b", 3)
    time.sleep(0.02)  # ns_old is now expired
    removed = ledger.evict()
    assert removed == 1 and ledger.stats()["entries"] == 2  # only the expired one

    kept = ledger.evict(max_entries=1)
    assert kept == 1 and ledger.stats()["entries"] == 1  # size cap keeps the newest
