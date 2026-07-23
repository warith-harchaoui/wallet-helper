"""Wallet and the memoize decorator: run a heavy call once, never twice.

:class:`Wallet` is the front door of wallet-helper. It wraps a callable whose
run is expensive (a paid API request, a slow model, any heavy function) so that:

1. an identical call already in the ledger returns the stored result without
   running, across process restarts (persistent memoization);
2. two identical calls made at the same time collapse into one: the second waits
   for the first and reuses its result instead of running again (single-flight).

The :func:`memoize` decorator wires that onto a function in one line, using a
shared default wallet, so the common case needs no setup.

Usage example
-------------
>>> import os_helper as osh
>>> from wallet_helper.ledger import Ledger
>>> with osh.temporary_folder() as tmp:
...     w = Wallet(Ledger(tmp))
...     def transcribe():
...         print("running the heavy call")   # a visible side effect
...         return {"text": "hello"}
...     w.call("demo", {"file": "a.wav"}, transcribe)   # miss: runs
...     w.call("demo", {"file": "a.wav"}, transcribe)   # hit: silent
running the heavy call
({'text': 'hello'}, False)
({'text': 'hello'}, True)

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
"""
from __future__ import annotations

import inspect
import threading
from functools import wraps
from typing import Any, Callable

from wallet_helper.ledger import Ledger, LedgerLike, make_key


def _payload_from_args(fn: Callable, args: tuple, kwargs: dict, ignore: tuple[str, ...]) -> Any:
    """Build the cache payload from a call's arguments, dropping ``ignore`` names.

    With no ``ignore`` the payload is simply ``{"args", "kwargs"}``. When names
    are ignored, arguments are bound to their parameter names first, so an
    ignored argument is dropped whether it was passed positionally or by keyword.
    This is the tidy way to exclude a volatile handle (``self``, a client object)
    without writing a bespoke ``key=`` function.
    """
    if not ignore:
        return {"args": args, "kwargs": kwargs}
    try:
        bound = inspect.signature(fn).bind_partial(*args, **kwargs)
        bound.apply_defaults()
        return {name: value for name, value in bound.arguments.items() if name not in ignore}
    except TypeError:
        # Signature binding can fail (for example on some builtins); fall back.
        return {"args": args, "kwargs": kwargs}


class Wallet:
    """A ledger plus in-process single-flight around heavy calls.

    Parameters
    ----------
    ledger : wallet_helper.ledger.LedgerLike, optional
        The result store, any backend satisfying
        :class:`~wallet_helper.ledger.LedgerLike` (the default JSON
        :class:`~wallet_helper.ledger.Ledger`, or a
        :class:`~wallet_helper.sqlite_ledger.SqliteLedger`). A default
        :class:`Ledger` is created when omitted.
    """

    def __init__(self, ledger: LedgerLike | None = None) -> None:
        self.ledger: LedgerLike = ledger if ledger is not None else Ledger()
        # Single-flight registry: key -> Event that the in-flight leader sets when
        # done, so concurrent identical callers wait instead of running again.
        self._inflight: dict[str, threading.Event] = {}
        self._inflight_lock = threading.Lock()

    def call(self, namespace: str, key_payload: Any, fn: Callable[[], Any]) -> tuple[Any, bool]:
        """Return a cached result, or run ``fn`` once and store it.

        Parameters
        ----------
        namespace : str
            Scope for the call, for example the provider or endpoint name.
        key_payload : Any
            What determines the result: arguments, a file path, or bytes. Hashed
            to the ledger key (see :func:`wallet_helper.ledger.make_key`).
        fn : callable
            Zero-argument callable doing the heavy work, run at most once per key
            even under concurrency.

        Returns
        -------
        tuple of (Any, bool)
            The result and ``from_cache``: ``True`` when served from the ledger,
            ``False`` when this call did the real work. A raising ``fn`` stores
            nothing, so a failed call is never cached.
        """
        key = make_key(namespace, key_payload)
        record = self.ledger.get_record(key)
        if record is not None:
            self.ledger.register_hit(key)
            return record["result"], True

        # Miss. Coalesce concurrent identical misses: exactly one caller (the
        # leader) runs fn; the rest wait for it and then read the stored result.
        while True:
            with self._inflight_lock:
                event = self._inflight.get(key)
                is_leader = event is None
                if is_leader:
                    event = threading.Event()
                    self._inflight[key] = event

            if not is_leader:
                # A follower: wait for the leader, then reuse its stored result.
                event.wait()
                record = self.ledger.get_record(key)
                if record is not None:
                    self.ledger.register_hit(key)
                    return record["result"], True
                # Leader failed or stored nothing; retry as a fresh contender.
                continue

            # We are the leader: do the real work exactly once.
            try:
                result = fn()  # if this raises, we store nothing and re-raise
                self.ledger.put(key, result)
                return result, False
            finally:
                with self._inflight_lock:
                    self._inflight.pop(key, None)
                event.set()  # wake any followers waiting on this key

    def paid(
        self,
        namespace: str,
        *,
        key: Callable[..., Any] | None = None,
        ignore: tuple[str, ...] = (),
    ) -> Callable:
        """Decorator memoizing a function through this wallet.

        Parameters
        ----------
        namespace : str
            Scope for the call.
        key : callable, optional
            ``key(*args, **kwargs)`` returning the payload that identifies the
            result. Overrides the default (all args and kwargs).
        ignore : tuple of str, optional
            Parameter names to exclude from the cache key, the tidy alternative
            to a ``key=`` lambda when you just need to drop a volatile handle
            (for example ``ignore=("client",)``).

        Returns
        -------
        callable
            The wrapped function (repeat identical calls are free). It carries
            ``.cache_info()`` (this namespace's ``{entries, hits}``) and
            ``.cache_clear()`` (drop this namespace's entries), like
            ``functools.lru_cache``.

        Examples
        --------
        >>> import os_helper as osh
        >>> from wallet_helper.ledger import Ledger
        >>> with osh.temporary_folder() as tmp:
        ...     w = Wallet(Ledger(tmp))
        ...     @w.paid("square")
        ...     def square(n):
        ...         return n * n
        ...     square(9), square(9)                  # second is free
        ...     square.cache_info()["entries"]        # one entry stored
        (81, 81)
        1
        """

        def decorator(fn: Callable) -> Callable:
            @wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                payload = key(*args, **kwargs) if key is not None else _payload_from_args(fn, args, kwargs, ignore)
                result, _ = self.call(namespace, payload, lambda: fn(*args, **kwargs))
                return result

            # lru_cache-style introspection and eviction, scoped to this namespace.
            wrapper.cache_info = lambda: self.ledger.stats(namespace)
            wrapper.cache_clear = lambda: self.ledger.clear(namespace)
            wrapper.wallet = self
            wrapper.namespace = namespace
            return wrapper

        return decorator


# --- A shared default wallet, so memoize works with zero setup ---------------

_default_wallet: Wallet | None = None


def default_wallet() -> Wallet:
    """Return the process-wide default :class:`Wallet`, created on first use.

    It uses the default :class:`~wallet_helper.ledger.Ledger` location
    (``$WALLET_HELPER_DIR`` then ``~/.cache/wallet-helper``). Assign
    ``wallet_helper.guard._default_wallet`` yourself to point it elsewhere.
    """
    global _default_wallet
    if _default_wallet is None:
        _default_wallet = Wallet()
    return _default_wallet


def memoize(
    fn: Callable | None = None,
    *,
    namespace: str | None = None,
    key: Callable[..., Any] | None = None,
    ignore: tuple[str, ...] = (),
    wallet: Wallet | None = None,
) -> Callable:
    """Persistent memoization: a cache that survives restarts, plus single-flight.

    Drop it on any function and its results are content-addressed to disk,
    reused across process restarts, and shared between concurrent callers so the
    same heavy call never runs twice. Works bare (``@memoize``) or configured
    (``@memoize(namespace="asr", ignore=("client",))``).

    Parameters
    ----------
    fn : callable, optional
        The function, when used bare as ``@memoize`` (filled in by Python).
    namespace : str, optional
        Cache scope; defaults to the function's ``module.qualname`` so distinct
        functions never collide.
    key : callable, optional
        Custom key builder ``key(*args, **kwargs)``.
    ignore : tuple of str, optional
        Parameter names to exclude from the key.
    wallet : Wallet, optional
        The wallet to use; defaults to the shared :func:`default_wallet`.

    Returns
    -------
    callable
        The memoized function, carrying ``.cache_info()`` and ``.cache_clear()``.

    Examples
    --------
    >>> import os_helper as osh
    >>> from wallet_helper.ledger import Ledger
    >>> with osh.temporary_folder() as tmp:
    ...     w = Wallet(Ledger(tmp))
    ...     @memoize(wallet=w)
    ...     def double(n):
    ...         return n * 2
    ...     double(21), double(21)
    (42, 42)
    """

    def make(func: Callable) -> Callable:
        ns = namespace or f"{func.__module__}.{func.__qualname__}"
        w = wallet or default_wallet()
        return w.paid(ns, key=key, ignore=ignore)(func)

    # Support both @memoize and @memoize(...): a bare call passes the function.
    return make(fn) if callable(fn) else make
