"""Cost + Budget value types.

Author
------
Warith HARCHAOUI — https://linkedin.com/in/warith-harchaoui
"""
from __future__ import annotations

import pytest

from wallet_helper.cost import Budget, BudgetExceeded, Cost


def test_cost_addition_same_currency() -> None:
    assert Cost(0.75, "EUR") + Cost(0.25, "EUR") == Cost(1.0, "EUR")


def test_cost_addition_mixed_currency_raises() -> None:
    with pytest.raises(ValueError, match="cannot add"):
        Cost(1.0, "EUR") + Cost(1.0, "USD")


def test_negative_cost_raises() -> None:
    with pytest.raises(ValueError, match="must be >= 0"):
        Cost(-0.1)


def test_budget_charge_and_remaining() -> None:
    b = Budget(1.0, "EUR")
    b.charge(Cost(0.6, "EUR"))
    assert round(b.remaining(), 2) == 0.4


def test_budget_refuses_overspend_and_stays_unchanged() -> None:
    b = Budget(1.0, "EUR", spent=0.8)
    with pytest.raises(BudgetExceeded):
        b.charge(Cost(0.5, "EUR"))
    assert b.spent == 0.8  # refused charge does not mutate the budget


def test_budget_refuses_wrong_currency() -> None:
    b = Budget(10.0, "EUR")
    assert b.would_exceed(Cost(0.01, "USD")) is True
    with pytest.raises(BudgetExceeded):
        b.charge(Cost(0.01, "USD"))
