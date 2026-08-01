"""wallet-helper: never run the same heavy call twice.

Persistent, content-addressed memoization for expensive calls (a paid API
request, a slow model, any heavy function). An identical call is served from a
local ledger instead of running again, across process restarts, and two
identical calls made at the same time collapse into one (single-flight), so the
second waits for the first and reuses its result.

The front door is :class:`~wallet_helper.guard.Wallet` and the
:func:`~wallet_helper.guard.memoize` decorator. Storage is a
:class:`~wallet_helper.ledger.Ledger` (a folder of JSON files) or a
:class:`~wallet_helper.sqlite_ledger.SqliteLedger` (one shared, concurrency-safe
file, with a cross-process lease).

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
"""
from __future__ import annotations

from wallet_helper.guard import Wallet, default_wallet, memoize
from wallet_helper.ledger import Ledger, LedgerLike, make_key
from wallet_helper.remote import RemoteLedger
from wallet_helper.sqlite_ledger import SqliteLedger

__version__ = "0.3.1"

__all__ = [
    "Ledger",
    "LedgerLike",
    "RemoteLedger",
    "SqliteLedger",
    "Wallet",
    "default_wallet",
    "make_key",
    "memoize",
    "__version__",
]
