"""Wallet and the memoize decorator: run a heavy call once, never twice.

:class:`Wallet` is the front door of wallet-helper. It wraps a callable whose
run is expensive (a paid API request, a slow model, any heavy function) so that:

1. an identical call already in the ledger returns the stored result without
   running, across process restarts (persistent memoization);
2. two identical calls made at the same time collapse into one: the second waits
   for the first and reuses its result instead of running again (single-flight).

Single-flight works in-process for the default :class:`~wallet_helper.ledger.Ledger`
(via threading), and across processes for any backend that offers a claim lease
(:class:`~wallet_helper.sqlite_ledger.SqliteLedger`, or
:class:`~wallet_helper.remote.RemoteLedger` over HTTP). Wallet picks the right
path automatically, so ``Wallet(SqliteLedger(...))`` and
``Wallet(RemoteLedger(url))`` get cross-process dedup with no extra code.

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

import asyncio
import inspect
import threading
import time
from functools import wraps
from typing import Any, Awaitable, Callable

import os_helper as osh

from wallet_helper.ledger import Ledger, LedgerLike, is_fresh, make_key


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
    """A ledger plus single-flight around heavy calls.

    Parameters
    ----------
    ledger : wallet_helper.ledger.LedgerLike, optional
        The result store, any backend satisfying
        :class:`~wallet_helper.ledger.LedgerLike`. With the default JSON
        :class:`~wallet_helper.ledger.Ledger`, single-flight is in-process. With
        a claim-capable backend (:class:`~wallet_helper.sqlite_ledger.SqliteLedger`
        or :class:`~wallet_helper.remote.RemoteLedger`) it is cross-process. A
        default :class:`Ledger` is created when omitted.
    poll_interval : float, optional
        How often a waiter re-checks a claim-based backend while another caller
        computes a key. Defaults to 0.05 s.
    """

    def __init__(self, ledger: LedgerLike | None = None, poll_interval: float = 0.05) -> None:
        self.ledger: LedgerLike = ledger if ledger is not None else Ledger()
        self._poll_interval = poll_interval
        # In-process single-flight registry (used for the default Ledger): key ->
        # Event the leader sets when done, so concurrent callers wait, not run.
        self._inflight: dict[str, threading.Event] = {}
        self._inflight_lock = threading.Lock()
        # The async equivalent: key -> Future the leader coroutine resolves.
        self._async_inflight: dict[str, asyncio.Future] = {}

    def call(
        self,
        namespace: str,
        key_payload: Any,
        fn: Callable[[], Any],
        *,
        ttl: float | None = None,
        stale_while_revalidate: bool = False,
    ) -> tuple[Any, bool]:
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
        ttl : float, optional
            Seconds the stored result stays fresh. After it expires the next call
            recomputes. ``None`` (default) means it never expires.
        stale_while_revalidate : bool, optional
            Only for the in-process :class:`~wallet_helper.ledger.Ledger`. When an
            entry is expired, return the stale result at once and refresh it in a
            background thread, so callers never wait on the recompute.

        Returns
        -------
        tuple of (Any, bool)
            The result and ``from_cache``: ``True`` when served from the ledger,
            ``False`` when this call did the real work. A raising ``fn`` stores
            nothing, so a failed call is never cached.
        """
        key = make_key(namespace, key_payload)
        if hasattr(self.ledger, "claim"):
            # Claim-capable backend: single-flight across processes and threads.
            return self._call_via_claim(key, fn, ttl)
        return self._call_local(key, fn, ttl, stale_while_revalidate)

    def _call_local(self, key: str, fn: Callable[[], Any], ttl: float | None, swr: bool) -> tuple[Any, bool]:
        """In-process path for the default Ledger: freshness, then single-flight."""
        record = self.ledger.get_record(key)
        if record is not None and is_fresh(record):
            self.ledger.register_hit(key)
            return record["result"], True
        if record is not None and swr:
            # Expired but allowed to be served stale: return it now, refresh once
            # in the background so no caller pays the recompute latency.
            self.ledger.register_hit(key)
            self._spawn_refresh(key, fn, ttl)
            return record["result"], True
        return self._compute_local(key, fn, ttl)

    def _compute_local(self, key: str, fn: Callable[[], Any], ttl: float | None) -> tuple[Any, bool]:
        """Run ``fn`` once for ``key`` with in-process single-flight (leader/follower)."""
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
                if record is not None and is_fresh(record):
                    self.ledger.register_hit(key)
                    return record["result"], True
                # Leader failed or stored nothing fresh; retry as a contender.
                continue

            # We are the leader: do the real work exactly once.
            try:
                result = fn()  # if this raises, we store nothing and re-raise
                self.ledger.put(key, result, ttl=ttl)
                return result, False
            finally:
                with self._inflight_lock:
                    self._inflight.pop(key, None)
                event.set()  # wake any followers waiting on this key

    def _spawn_refresh(self, key: str, fn: Callable[[], Any], ttl: float | None) -> None:
        """Recompute ``key`` in a daemon thread, at most one refresh at a time."""
        with self._inflight_lock:
            if key in self._inflight:
                return  # a compute or refresh is already running for this key

        def _run() -> None:
            try:
                self._compute_local(key, fn, ttl)
            except Exception as exc:  # a background failure must not crash anyone
                osh.warning(f"background refresh for {key} failed: {exc}")

        threading.Thread(target=_run, daemon=True).start()

    def _call_via_claim(self, key: str, fn: Callable[[], Any], ttl: float | None) -> tuple[Any, bool]:
        """Cross-process path: claim the key, compute if leader, else wait for it."""
        while True:
            outcome = self.ledger.claim(key)
            status = outcome["status"]
            if status == "hit":
                return outcome["result"], True
            if status == "leased":
                token = outcome.get("token")  # fencing token: guards submit/release
                try:
                    result = fn()
                except BaseException:
                    self.ledger.release(key, token)  # let a waiter take over on failure
                    raise
                self.ledger.submit(key, result, token=token, ttl=ttl)
                return result, False
            # pending: another caller is computing it; wait and try again.
            time.sleep(self._poll_interval)

    async def acall(
        self,
        namespace: str,
        key_payload: Any,
        fn: Callable[[], Awaitable[Any]],
        *,
        ttl: float | None = None,
        stale_while_revalidate: bool = False,
    ) -> tuple[Any, bool]:
        """Async twin of :meth:`call`: await ``fn`` once and cache its result.

        This is what memoizes an ``async def`` correctly: it awaits the coroutine
        and stores the *result*, never the coroutine object. Concurrent identical
        awaits coalesce (async single-flight), and a claim-capable backend still
        gives cross-process dedup (its blocking calls run in a worker thread).

        Parameters mirror :meth:`call`, except ``fn`` is a zero-argument callable
        returning an awaitable.
        """
        key = make_key(namespace, key_payload)
        if hasattr(self.ledger, "claim"):
            return await self._acall_via_claim(key, fn, ttl)
        return await self._acall_local(key, fn, ttl, stale_while_revalidate)

    async def _acall_local(self, key: str, fn: Callable[[], Awaitable[Any]], ttl: float | None, swr: bool) -> tuple[Any, bool]:
        """In-process async path: freshness, then async single-flight."""
        record = self.ledger.get_record(key)
        if record is not None and is_fresh(record):
            self.ledger.register_hit(key)
            return record["result"], True
        if record is not None and swr:
            self.ledger.register_hit(key)
            asyncio.ensure_future(self._arefresh(key, fn, ttl))  # refresh in the background
            return record["result"], True
        return await self._acompute_local(key, fn, ttl)

    async def _acompute_local(self, key: str, fn: Callable[[], Awaitable[Any]], ttl: float | None) -> tuple[Any, bool]:
        """Await ``fn`` once for ``key`` with async single-flight (leader/follower)."""
        while True:
            future = self._async_inflight.get(key)
            if future is None:
                # We are the leader. No await between get and insert, so on the
                # single-threaded event loop this claim of leadership is a race-free.
                future = asyncio.get_running_loop().create_future()
                self._async_inflight[key] = future
                try:
                    result = await fn()
                except BaseException as exc:
                    self._async_inflight.pop(key, None)
                    if not future.done():
                        future.set_exception(exc)
                    raise
                self.ledger.put(key, result, ttl=ttl)
                self._async_inflight.pop(key, None)
                if not future.done():
                    future.set_result(result)
                return result, False
            # A follower: await the leader's result (shield so our cancellation
            # does not cancel the shared work).
            try:
                result = await asyncio.shield(future)
            except BaseException:
                continue  # leader failed; retry as a fresh contender
            self.ledger.register_hit(key)
            return result, True

    async def _arefresh(self, key: str, fn: Callable[[], Awaitable[Any]], ttl: float | None) -> None:
        """Recompute ``key`` in the background for stale-while-revalidate."""
        try:
            await self._acompute_local(key, fn, ttl)
        except Exception as exc:
            osh.warning(f"background refresh for {key} failed: {exc}")

    async def _acall_via_claim(self, key: str, fn: Callable[[], Awaitable[Any]], ttl: float | None) -> tuple[Any, bool]:
        """Cross-process async path: claim, await if leader, else poll for the result."""
        while True:
            outcome = await asyncio.to_thread(self.ledger.claim, key)
            status = outcome["status"]
            if status == "hit":
                return outcome["result"], True
            if status == "leased":
                token = outcome.get("token")
                try:
                    result = await fn()
                except BaseException:
                    await asyncio.to_thread(self.ledger.release, key, token)
                    raise
                await asyncio.to_thread(self.ledger.submit, key, result, token=token, ttl=ttl)
                return result, False
            # pending: another caller is computing it; wait and try again.
            await asyncio.sleep(self._poll_interval)

    def paid(
        self,
        namespace: str,
        *,
        key: Callable[..., Any] | None = None,
        ignore: tuple[str, ...] = (),
        ttl: float | None = None,
        stale_while_revalidate: bool = False,
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
        ttl : float, optional
            Seconds the stored result stays fresh (see :meth:`call`).
        stale_while_revalidate : bool, optional
            Serve a stale result and refresh in the background (in-process Ledger
            only; see :meth:`call`).

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
            def payload_for(args: tuple, kwargs: dict) -> Any:
                return key(*args, **kwargs) if key is not None else _payload_from_args(fn, args, kwargs, ignore)

            if inspect.iscoroutinefunction(fn):
                # An async function: await it and cache the result, never the
                # coroutine object (caching the coroutine is the classic footgun).
                @wraps(fn)
                async def wrapper(*args: Any, **kwargs: Any) -> Any:
                    result, _ = await self.acall(
                        namespace,
                        payload_for(args, kwargs),
                        lambda: fn(*args, **kwargs),
                        ttl=ttl,
                        stale_while_revalidate=stale_while_revalidate,
                    )
                    return result
            else:

                @wraps(fn)
                def wrapper(*args: Any, **kwargs: Any) -> Any:
                    result, _ = self.call(
                        namespace,
                        payload_for(args, kwargs),
                        lambda: fn(*args, **kwargs),
                        ttl=ttl,
                        stale_while_revalidate=stale_while_revalidate,
                    )
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
    ttl: float | None = None,
    stale_while_revalidate: bool = False,
    wallet: Wallet | None = None,
) -> Callable:
    """Persistent memoization: a cache that survives restarts, plus single-flight.

    Drop it on any function and its results are content-addressed to disk,
    reused across process restarts, and shared between concurrent callers so the
    same heavy call never runs twice. Works bare (``@memoize``) or configured
    (``@memoize(ttl=3600, ignore=("client",))``).

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
    ttl : float, optional
        Seconds the stored result stays fresh.
    stale_while_revalidate : bool, optional
        Serve a stale result and refresh in the background (in-process store only).
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
        return w.paid(ns, key=key, ignore=ignore, ttl=ttl, stale_while_revalidate=stale_while_revalidate)(func)

    # Support both @memoize and @memoize(...): a bare call passes the function.
    return make(fn) if callable(fn) else make
