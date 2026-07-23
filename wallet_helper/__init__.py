"""wallet-helper — never pay twice for the same billable call.

A tiny, local-first, provider-agnostic guard around any call that costs money
(an HTTP API, a paid binary, a metered function — in any currency). It combines
three things that usually live in separate tools:

- **idempotency** — a content-addressed :class:`~wallet_helper.ledger.Ledger`
  returns the stored result of an identical call instead of running it again;
- **spend accounting** — every real call records its :class:`~wallet_helper.cost.Cost`;
- **budget control** — an optional :class:`~wallet_helper.cost.Budget` refuses a
  call that would exceed a ceiling, *before* it runs.

The front door is :class:`~wallet_helper.guard.Wallet` (a ``call`` method and a
``@paid`` decorator).

Author
------
Warith HARCHAOUI — https://linkedin.com/in/warith-harchaoui
"""
from __future__ import annotations

from wallet_helper.cost import Budget, BudgetExceeded, Cost
from wallet_helper.guard import Wallet
from wallet_helper.ledger import Ledger, make_key

__version__ = "0.1.0"

__all__ = [
    "Budget",
    "BudgetExceeded",
    "Cost",
    "Ledger",
    "Wallet",
    "make_key",
    "__version__",
]
