"""Post-install smoke test: prove a fresh install actually works.

Run by CI on every OS a user might install on (Linux, macOS, Windows), and
handy to run by hand after installing. It does not import the test suite; it
exercises the *installed* package the way a user first would:

1. import the package and read its version;
2. memoize a function and confirm the heavy work runs exactly once (the second
   identical call is served from the on-disk store);
3. confirm the wrapper's ``cache_info`` / ``cache_clear`` surface works.

The console-script entry points (``wallet-helper``, ``wallet-helper-click``)
are checked separately in the workflow, since those prove the ``[project.scripts]``
wiring landed on PATH. Exit code is non-zero on any failure, so CI goes red.

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
"""
from __future__ import annotations

import tempfile


def main() -> int:
    """Exercise the installed package end to end; return a process exit code."""
    import wallet_helper as wh
    from wallet_helper import Ledger, Wallet, memoize

    print(f"wallet-helper {wh.__version__} imported")

    # A private store so the smoke test never touches the user's real cache.
    with tempfile.TemporaryDirectory() as tmp:
        wallet = Wallet(Ledger(tmp))
        runs = {"n": 0}

        @memoize(wallet=wallet)
        def double(x: int) -> int:
            runs["n"] += 1
            return x * 2

        assert double(21) == 42, "first call returned the wrong result"
        assert double(21) == 42, "cached call returned the wrong result"
        assert runs["n"] == 1, f"expected exactly one real run, got {runs['n']}"

        info = double.cache_info()
        assert info["entries"] == 1, f"expected one stored entry, got {info}"
        assert info["hits"] == 1, f"expected one reuse, got {info}"
        double.cache_clear()
        assert double.cache_info()["entries"] == 0, "cache_clear did not empty the store"

    print("memoize round-trip OK: ran once, second call served from the store")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
