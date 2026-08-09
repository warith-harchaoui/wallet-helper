"""The memoize decorator: bare and configured use, cache_info, cache_clear.

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
"""

from __future__ import annotations

from pathlib import Path

import pytest

from wallet_helper.guard import Wallet, memoize
from wallet_helper.ledger import Ledger
from wallet_helper.sqlite_ledger import SqliteLedger


@pytest.fixture()
def wallet(tmp_path: Path) -> Wallet:
    return Wallet(Ledger(tmp_path))


def test_memoize_over_sqlite_dedups(tmp_path: Path) -> None:
    # A claim-capable backend routes through the lease, but the surface is the same.
    wallet = Wallet(SqliteLedger(tmp_path / "ledger.db"))
    runs = 0

    @memoize(wallet=wallet)
    def cube(n: int) -> int:
        nonlocal runs
        runs += 1
        return n**3

    assert cube(3) == 27
    assert cube(3) == 27  # served from the shared store
    assert runs == 1


def test_bare_decorator_dedups(wallet: Wallet) -> None:
    calls = 0

    @memoize(wallet=wallet)
    def square(n: int) -> int:
        nonlocal calls
        calls += 1
        return n * n

    assert square(9) == 81
    assert square(9) == 81  # cached
    assert square(10) == 100  # different args, real call
    assert calls == 2


def test_ignore_drops_a_volatile_argument(wallet: Wallet) -> None:
    calls = 0

    @memoize(wallet=wallet, ignore=("client",))
    def fetch(n: int, client: object) -> int:
        nonlocal calls
        calls += 1
        return n + 1

    assert fetch(1, client=object()) == 2
    assert fetch(1, client=object()) == 2  # different client, same key, cached
    assert calls == 1


def test_memoize_reuses_across_identical_files_at_different_paths(wallet: Wallet, tmp_path: Path) -> None:
    # The point of content-addressing a file argument: two copies of the same
    # file, at different paths, must run the heavy call only once.
    a = tmp_path / "a" / "input.dat"
    a.parent.mkdir()
    a.write_bytes(b"identical-payload")
    b = tmp_path / "b" / "renamed.dat"
    b.parent.mkdir()
    b.write_bytes(b"identical-payload")
    runs = 0

    @memoize(wallet=wallet)
    def transcribe(path: Path) -> str:
        nonlocal runs
        runs += 1
        return f"result-{runs}"

    first = transcribe(a)
    second = transcribe(b)  # same bytes, different path: served from cache
    assert first == second
    assert runs == 1


def test_memoize_separates_different_files(wallet: Wallet, tmp_path: Path) -> None:
    a = tmp_path / "a.dat"
    a.write_bytes(b"first")
    b = tmp_path / "b.dat"
    b.write_bytes(b"second")
    runs = 0

    @memoize(wallet=wallet)
    def transcribe(path: Path) -> int:
        nonlocal runs
        runs += 1
        return runs

    transcribe(a)
    transcribe(b)  # different bytes: a real second call
    assert runs == 2


def test_cache_info_and_clear(wallet: Wallet) -> None:
    @memoize(namespace="thing", wallet=wallet)
    def thing(n: int) -> int:
        return n

    thing(1)
    thing(1)  # one reuse
    assert thing.cache_info() == {"entries": 1, "hits": 1}
    thing.cache_clear()
    assert thing.cache_info() == {"entries": 0, "hits": 0}
