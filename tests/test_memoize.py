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


@pytest.fixture()
def wallet(tmp_path: Path) -> Wallet:
    return Wallet(Ledger(tmp_path))


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


def test_cache_info_and_clear(wallet: Wallet) -> None:
    @memoize(namespace="thing", wallet=wallet)
    def thing(n: int) -> int:
        return n

    thing(1)
    thing(1)  # one reuse
    assert thing.cache_info() == {"entries": 1, "hits": 1}
    thing.cache_clear()
    assert thing.cache_info() == {"entries": 0, "hits": 0}
