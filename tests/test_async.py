"""Async memoization: cache the result, not the coroutine, and coalesce awaits.

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from wallet_helper.guard import Wallet, memoize
from wallet_helper.ledger import Ledger
from wallet_helper.sqlite_ledger import SqliteLedger


def test_async_memoize_caches_the_result(tmp_path: Path) -> None:
    wallet = Wallet(Ledger(tmp_path))
    runs = 0

    @memoize(wallet=wallet)
    async def fetch(n: int) -> int:
        nonlocal runs
        runs += 1
        await asyncio.sleep(0)
        return n * n

    async def main() -> tuple[int, int]:
        return await fetch(6), await fetch(6)

    a, b = asyncio.run(main())
    assert (a, b) == (36, 36) and runs == 1  # result cached, coroutine not re-run


def test_async_single_flight_coalesces(tmp_path: Path) -> None:
    wallet = Wallet(Ledger(tmp_path))
    runs = 0

    @memoize(wallet=wallet)
    async def slow(n: int) -> int:
        nonlocal runs
        runs += 1
        await asyncio.sleep(0.1)  # long enough for both awaits to overlap
        return n

    async def main() -> list[int]:
        return list(await asyncio.gather(slow(5), slow(5)))

    assert asyncio.run(main()) == [5, 5]
    assert runs == 1  # two concurrent awaits ran the work once


def test_async_memoize_over_sqlite(tmp_path: Path) -> None:
    wallet = Wallet(SqliteLedger(tmp_path / "ledger.db"))
    runs = 0

    @memoize(wallet=wallet)
    async def fetch(n: int) -> int:
        nonlocal runs
        runs += 1
        return n + 1

    async def main() -> tuple[int, int]:
        return await fetch(1), await fetch(1)

    assert asyncio.run(main()) == (2, 2) and runs == 1
