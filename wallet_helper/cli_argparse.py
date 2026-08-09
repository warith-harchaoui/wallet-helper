"""wallet-helper argparse command line (no extra dependency).

Inspect and manage the local ledger: where it lives, how many results are
cached and how many repeat calls they saved, and clearing it. The calls
themselves are memoized from your own code through
:class:`wallet_helper.guard.Wallet`; this tool just reads and prunes the store.

Usage
-----
``python -m wallet_helper.cli_argparse stats``
``python -m wallet_helper.cli_argparse path``
``python -m wallet_helper.cli_argparse clear``
``python -m wallet_helper.cli_argparse --sqlite ~/.cache/wallet-helper/ledger.db stats``

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
"""

from __future__ import annotations

import argparse

from wallet_helper import __version__
from wallet_helper.ledger import Ledger, LedgerLike
from wallet_helper.sqlite_ledger import SqliteLedger


def _open_ledger(directory: str | None, sqlite: str | None) -> LedgerLike:
    """Return the SQLite ledger if ``--sqlite`` was given, else the JSON one."""
    return SqliteLedger(sqlite) if sqlite else Ledger(directory)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the argparse CLI.

    Parameters
    ----------
    argv : list of str, optional
        Argument vector (defaults to ``sys.argv`` when ``None``).

    Returns
    -------
    int
        Process exit code (``0`` on success).
    """
    parser = argparse.ArgumentParser(prog="wallet-helper", description="Inspect the wallet-helper ledger.")
    parser.add_argument("--version", action="version", version=f"wallet-helper {__version__}")
    parser.add_argument(
        "--dir", default=None, help="JSON ledger directory (default: $WALLET_HELPER_DIR or ~/.cache/wallet-helper)."
    )
    parser.add_argument("--sqlite", default=None, help="Inspect a SQLite ledger file instead of the JSON directory.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("stats", help="Show how many results are cached and how many calls they saved.")
    sub.add_parser("path", help="Print where the ledger is stored.")
    sub.add_parser("clear", help="Delete every cached result (irreversible).")
    evict = sub.add_parser("evict", help="Prune expired results, and optionally by age or size.")
    evict.add_argument("--max-entries", type=int, default=None, help="Keep only the newest N entries.")
    evict.add_argument("--older-than", type=float, default=None, help="Remove entries older than this many seconds.")

    args = parser.parse_args(argv)
    ledger = _open_ledger(args.dir, args.sqlite)

    if args.command == "path":
        print(ledger.location)
        return 0
    if args.command == "clear":
        ledger.clear()
        print(f"cleared {ledger.location}")
        return 0
    if args.command == "evict":
        removed = ledger.evict(max_entries=args.max_entries, older_than=args.older_than)
        print(f"evicted {removed} entries from {ledger.location}")
        return 0
    # stats
    s = ledger.stats()
    print(f"ledger: {ledger.location}")
    print(f"entries: {s['entries']}")
    print(f"calls saved (cache hits): {s['hits']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
