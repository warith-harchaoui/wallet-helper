"""A real multi-process test of the cross-process single-flight guarantee.

Four separate OS processes race to run the same slow call through one shared
SQLite ledger. The claim lease must let exactly one of them run the work; the
others wait and receive its result. We prove "ran once" by having the real run
append to a shared file and counting the bytes afterwards.

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
"""
from __future__ import annotations

import multiprocessing
import os
import time
from pathlib import Path


def _worker(args: tuple[str, str]) -> bool:
    """Run the shared slow call in a child process; return whether it was cached.

    Parameters
    ----------
    args : tuple of (str, str)
        The SQLite database path and the marker-file path.

    Returns
    -------
    bool
        ``from_cache``: ``False`` for the one leader, ``True`` for the followers.
    """
    from wallet_helper import SqliteLedger, Wallet

    db_path, marker_path = args
    wallet = Wallet(SqliteLedger(db_path))

    def slow() -> str:
        # Record that a real run happened, then take long enough that the other
        # processes are all waiting on the lease by the time we finish.
        with open(marker_path, "a") as handle:
            handle.write("x")
        time.sleep(0.5)
        return "value"

    _, from_cache = wallet.call("job", {"x": 1}, slow)
    return from_cache


def test_cross_process_single_flight(tmp_path: Path) -> None:
    db_path = str(tmp_path / "ledger.db")
    marker_path = str(tmp_path / "runs.txt")

    from wallet_helper import SqliteLedger

    SqliteLedger(db_path)  # create the schema once before the processes race

    ctx = multiprocessing.get_context("spawn")  # spawn works the same on every OS
    with ctx.Pool(4) as pool:
        results = pool.map(_worker, [(db_path, marker_path)] * 4)

    runs = len(open(marker_path).read()) if os.path.exists(marker_path) else 0
    assert runs == 1                                  # the work ran once across processes
    assert results.count(False) == 1                   # exactly one leader
    assert results.count(True) == 3                    # three followers reused the result
