"""Money, budgets and the over-budget error for wallet-helper.

Module summary
--------------
A billable call has a *cost* (an amount in a currency). A *budget* is a spend
ceiling in one currency that refuses charges once exhausted. These two tiny value
types are the accounting half of wallet-helper (the caching half lives in
:mod:`wallet_helper.ledger`); :mod:`wallet_helper.guard` ties them together.

Author
------
Warith HARCHAOUI — https://linkedin.com/in/warith-harchaoui
"""
from __future__ import annotations

from dataclasses import dataclass


class BudgetExceeded(RuntimeError):
    """A paid call was refused because it would push spend over the budget."""


@dataclass(frozen=True)
class Cost:
    """A monetary amount in a currency.

    Parameters
    ----------
    amount : float
        The cost, which must be non-negative (a call cannot earn you money).
    currency : str, optional
        ISO-ish currency code — free text, so ``"USD"``, ``"EUR"``, or even
        ``"credits"`` / ``"tokens"`` all work. Defaults to ``"USD"``.

    Examples
    --------
    >>> Cost(0.75, "EUR") + Cost(0.25, "EUR")
    Cost(amount=1.0, currency='EUR')
    """

    amount: float
    currency: str = "USD"

    def __post_init__(self) -> None:
        # A negative price is almost always a bug in the caller's cost model.
        if self.amount < 0:
            raise ValueError(f"cost amount must be >= 0, got {self.amount}")

    def __add__(self, other: Cost) -> Cost:
        """Add two costs of the *same* currency (mixing currencies is an error)."""
        if self.currency != other.currency:
            raise ValueError(f"cannot add {self.currency} and {other.currency}")
        return Cost(self.amount + other.amount, self.currency)


@dataclass
class Budget:
    """A spend ceiling in one currency, tracking what has been charged.

    Parameters
    ----------
    limit : float
        Maximum total spend allowed.
    currency : str, optional
        Currency of the limit; charges in another currency are refused.
    spent : float, optional
        Amount already spent (usually starts at ``0.0``; settable so a budget can
        be resumed across processes).

    Examples
    --------
    >>> b = Budget(1.0, "EUR")
    >>> b.charge(Cost(0.6, "EUR"))
    >>> round(b.remaining(), 2)
    0.4
    """

    limit: float
    currency: str = "USD"
    spent: float = 0.0

    def remaining(self) -> float:
        """Return the amount still available (never negative)."""
        return max(0.0, self.limit - self.spent)

    def would_exceed(self, cost: Cost) -> bool:
        """Return ``True`` if charging ``cost`` now would break the limit.

        A cost in a different currency always "exceeds" — it cannot be reconciled
        against this budget and must be refused rather than silently ignored.
        """
        if cost.currency != self.currency:
            return True
        return self.spent + cost.amount > self.limit

    def charge(self, cost: Cost) -> None:
        """Charge ``cost`` against the budget, or raise :class:`BudgetExceeded`.

        Parameters
        ----------
        cost : Cost
            The amount to spend.

        Raises
        ------
        BudgetExceeded
            When the charge would break the limit (or is in another currency).
            The budget is left unchanged in that case.
        """
        if self.would_exceed(cost):
            raise BudgetExceeded(
                f"charge of {cost.amount} {cost.currency} would exceed budget "
                f"({self.spent}/{self.limit} {self.currency} spent)"
            )
        self.spent += cost.amount
