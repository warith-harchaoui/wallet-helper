"""Wallet — tie a ledger and a budget around any billable call.

Module summary
--------------
:class:`Wallet` is the front door of wallet-helper. It wraps a callable whose
invocation costs money so that:

1. an identical call already in the :class:`wallet_helper.ledger.Ledger` returns
   the stored result **without calling** (no charge, no network) — idempotency;
2. a genuine miss is charged against an optional
   :class:`wallet_helper.cost.Budget` **before** the call runs, refusing it if it
   would break the ceiling — spend control;
3. the cost is recorded, so :meth:`wallet_helper.ledger.Ledger.stats` can report
   total spend and money saved by the cache.

It is provider-agnostic: the callable can hit an HTTP API, shell out to a paid
binary, or run any metered function.

Usage example
-------------
>>> import tempfile
>>> from wallet_helper.ledger import Ledger
>>> w = Wallet(Ledger(tempfile.mkdtemp()))
>>> runs = {"n": 0}
>>> def transcribe():
...     runs["n"] += 1
...     return {"text": "hello"}
>>> w.call("demo", {"file": "a.wav"}, transcribe, cost=0.75, currency="USD")
({'text': 'hello'}, False)
>>> w.call("demo", {"file": "a.wav"}, transcribe, cost=0.75, currency="USD")
({'text': 'hello'}, True)
>>> runs["n"]
1

Author
------
Warith HARCHAOUI — https://linkedin.com/in/warith-harchaoui
"""
from __future__ import annotations

import time
from functools import wraps
from typing import Any, Callable, Union

from wallet_helper.cost import Budget, Cost
from wallet_helper.ledger import Ledger, LedgerLike, make_key

# A call's cost is either a fixed number known up front, or a callable evaluated
# AFTER the real run as ``cost(result, elapsed_seconds)`` — so the price can be
# the wall-clock time it took, the tokens in the response, bytes processed, etc.
CostLike = Union[float, Callable[[Any, float], float]]


def elapsed(result: Any, seconds: float) -> float:
    """A dynamic cost equal to the call's wall-clock time, in seconds.

    Pass as ``cost=elapsed`` (with ``currency="seconds"``) to memoize an
    expensive call and record *how long* each real run took — the natural "price"
    when the scarce resource is time, not money.

    Parameters
    ----------
    result : Any
        The value the paid call returned (ignored here; available to custom cost
        functions that price by output size, token count, …).
    seconds : float
        Measured wall-clock duration of the real call.

    Returns
    -------
    float
        ``seconds``.
    """
    return seconds


class Wallet:
    """A ledger + optional budget guarding billable calls.

    Parameters
    ----------
    ledger : wallet_helper.ledger.LedgerLike, optional
        The result store — any backend satisfying
        :class:`~wallet_helper.ledger.LedgerLike` (the default JSON
        :class:`~wallet_helper.ledger.Ledger`, or a
        :class:`~wallet_helper.sqlite_ledger.SqliteLedger`). A default
        :class:`Ledger` is created when omitted.
    budget : wallet_helper.cost.Budget, optional
        A spend ceiling. When set, a miss that would exceed it raises
        :class:`wallet_helper.cost.BudgetExceeded` and the call does not run.
    """

    def __init__(self, ledger: LedgerLike | None = None, budget: Budget | None = None) -> None:
        self.ledger: LedgerLike = ledger if ledger is not None else Ledger()
        self.budget = budget

    def call(
        self,
        namespace: str,
        key_payload: Any,
        fn: Callable[[], Any],
        *,
        cost: float = 0.0,
        currency: str = "USD",
    ) -> tuple[Any, bool]:
        """Return a cached result, or run ``fn`` once, charge it, and store it.

        Parameters
        ----------
        namespace : str
            Scope for the call (e.g. the provider / endpoint name).
        key_payload : Any
            What determines the result — args, a file path, or bytes. Hashed to
            the ledger key (see :func:`wallet_helper.ledger.make_key`).
        fn : callable
            Zero-argument callable performing the paid work; called at most once.
        cost, currency : float, str
            The price of one real call.

        Returns
        -------
        tuple of (Any, bool)
            The result and ``from_cache`` — ``True`` when served from the ledger
            (free), ``False`` when freshly computed (charged).

        Raises
        ------
        wallet_helper.cost.BudgetExceeded
            If a miss would break the wallet's budget — ``fn`` is not called.
        """
        key = make_key(namespace, key_payload)
        record = self.ledger.get_record(key)
        if record is not None:
            self.ledger.register_hit(key)
            return record["result"], True
        # Miss: check the budget BEFORE paying, so we never call then regret it.
        if self.budget is not None:
            self.budget.charge(Cost(cost, currency))  # raises before any call
        result = fn()
        self.ledger.put(key, result, cost=cost, currency=currency)
        return result, False

    def paid(
        self,
        namespace: str,
        *,
        cost: float = 0.0,
        currency: str = "USD",
        key: Callable[..., Any] | None = None,
    ) -> Callable:
        """Decorator making a function idempotent + budgeted through this wallet.

        Parameters
        ----------
        namespace : str
            Scope for the call.
        cost, currency : float, str
            Price of one real invocation.
        key : callable, optional
            ``key(*args, **kwargs)`` returning the payload that identifies the
            result. Defaults to the call's own args/kwargs — override when only
            some arguments affect the result (e.g. ignore a client handle).

        Returns
        -------
        callable
            A decorator; the wrapped function returns the result directly (repeat
            identical calls are free).

        Examples
        --------
        >>> import tempfile
        >>> from wallet_helper.ledger import Ledger
        >>> w = Wallet(Ledger(tempfile.mkdtemp()))
        >>> @w.paid("square", cost=0.01)
        ... def square(n):
        ...     return n * n
        >>> square(9), square(9)
        (81, 81)
        """

        def decorator(fn: Callable) -> Callable:
            @wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                payload = key(*args, **kwargs) if key is not None else {"args": args, "kwargs": kwargs}
                result, _ = self.call(namespace, payload, lambda: fn(*args, **kwargs), cost=cost, currency=currency)
                return result

            return wrapper

        return decorator
