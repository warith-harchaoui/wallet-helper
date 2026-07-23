"""Wallet — idempotent calls, budget enforcement, the @paid decorator.

Author
------
Warith HARCHAOUI — https://linkedin.com/in/warith-harchaoui
"""
from __future__ import annotations

from pathlib import Path

import pytest

from wallet_helper.cost import Budget, BudgetExceeded
from wallet_helper.guard import Wallet
from wallet_helper.ledger import Ledger


@pytest.fixture()
def wallet(tmp_path: Path) -> Wallet:
    return Wallet(Ledger(tmp_path))


def test_second_identical_call_is_not_billed(wallet: Wallet) -> None:
    runs = {"n": 0}

    def paid_call() -> dict:
        runs["n"] += 1
        return {"text": "hello"}

    r1, hit1 = wallet.call("demo", {"file": "a.wav"}, paid_call, cost=0.75)
    r2, hit2 = wallet.call("demo", {"file": "a.wav"}, paid_call, cost=0.75)
    assert (r1, hit1) == ({"text": "hello"}, False)
    assert (r2, hit2) == ({"text": "hello"}, True)
    assert runs["n"] == 1  # the paid call ran once


def test_budget_blocks_miss_before_calling(tmp_path: Path) -> None:
    w = Wallet(Ledger(tmp_path), budget=Budget(1.0, "EUR", spent=0.8))
    ran = {"n": 0}

    def paid_call() -> dict:
        ran["n"] += 1
        return {}

    with pytest.raises(BudgetExceeded):
        w.call("demo", {"x": 1}, paid_call, cost=0.5, currency="EUR")
    assert ran["n"] == 0  # refused before spending


def test_cache_hit_does_not_touch_budget(tmp_path: Path) -> None:
    # First call spends; a repeat is served from cache and must NOT charge again.
    w = Wallet(Ledger(tmp_path), budget=Budget(1.0, "EUR"))
    w.call("demo", {"x": 1}, lambda: {"ok": True}, cost=0.6, currency="EUR")
    assert round(w.budget.spent, 2) == 0.6
    _, hit = w.call("demo", {"x": 1}, lambda: {"ok": True}, cost=0.6, currency="EUR")
    assert hit is True and round(w.budget.spent, 2) == 0.6  # unchanged


def test_paid_decorator_dedups(wallet: Wallet) -> None:
    calls = {"n": 0}

    @wallet.paid("square", cost=0.01)
    def square(n: int) -> int:
        calls["n"] += 1
        return n * n

    assert square(9) == 81
    assert square(9) == 81  # cached
    assert square(10) == 100  # different args → real call
    assert calls["n"] == 2


def test_paid_decorator_custom_key_ignores_volatile_arg(wallet: Wallet) -> None:
    # Only `n` should determine the result; a changing `client` handle must not
    # bust the cache.
    calls = {"n": 0}

    @wallet.paid("f", cost=0.01, key=lambda n, client: {"n": n})
    def f(n: int, client: object) -> int:
        calls["n"] += 1
        return n + 1

    assert f(1, client=object()) == 2
    assert f(1, client=object()) == 2  # different client, same key → cached
    assert calls["n"] == 1
