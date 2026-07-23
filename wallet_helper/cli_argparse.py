"""wallet-helper — argparse command-line surface (no extra dependency).

Inspect and manage the local ledger: where it lives, how much it has spent and
saved, and clearing it. The billable calls themselves are made from your own
code through :class:`wallet_helper.guard.Wallet`; this CLI is the accountant, not
the spender.

Usage
-----
``python -m wallet_helper.cli_argparse stats``
``python -m wallet_helper.cli_argparse path``
``python -m wallet_helper.cli_argparse clear``

Author
------
Warith HARCHAOUI — https://linkedin.com/in/warith-harchaoui
"""
from __future__ import annotations

import argparse
import shutil

from wallet_helper import __version__
from wallet_helper.ledger import Ledger


def _fmt_money(by_currency: dict) -> str:
    """Render the per-currency spend/saved breakdown as one readable line."""
    if not by_currency:
        return "  (empty ledger)"
    lines = []
    for cur, slot in sorted(by_currency.items()):
        lines.append(f"  {cur}: spent {slot['spent']:.4f} · saved {slot['saved']:.4f}")
    return "\n".join(lines)


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
    parser.add_argument("--dir", default=None, help="Ledger directory (default: $WALLET_HELPER_DIR or ~/.cache/wallet-helper).")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("stats", help="Show spend and cache savings.")
    sub.add_parser("path", help="Print the ledger directory.")
    sub.add_parser("clear", help="Delete every ledger entry (irreversible).")

    args = parser.parse_args(argv)
    ledger = Ledger(args.dir)

    if args.command == "path":
        print(ledger.dir)
        return 0
    if args.command == "clear":
        # Remove the whole directory; a fresh one is recreated on next write.
        if ledger.dir.exists():
            shutil.rmtree(ledger.dir)
        print(f"cleared {ledger.dir}")
        return 0
    # stats
    s = ledger.stats()
    print(f"ledger: {ledger.dir}")
    print(f"entries: {s['entries']} · cache hits (calls saved): {s['hits']}")
    print("by currency:")
    print(_fmt_money(s["by_currency"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
