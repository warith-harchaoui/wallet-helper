"""The wallet-helper command line, built with click.

It reads and prunes the local ledger. The calls themselves are memoized from
your own code through :class:`wallet_helper.guard.Wallet` — this module never
runs anything expensive, it only reports and deletes.

It used to be the optional twin of an argparse CLI, reachable under a
``-click`` suffix that named the parsing library rather than the interface.
Both are gone, and ``click`` is a core dependency now, so there is no import
guard left to trip over.

Usage
-----
``wallet-helper stats``
``python -m wallet_helper.cli path``
``wallet-helper clear --yes``

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
"""

from __future__ import annotations

import click

from wallet_helper import __version__
from wallet_helper.ledger import Ledger, LedgerLike
from wallet_helper.sqlite_ledger import SqliteLedger


def _open_ledger(directory: str | None, sqlite: str | None) -> LedgerLike:
    """Return the SQLite ledger if ``--sqlite`` was given, else the JSON one."""
    return SqliteLedger(sqlite) if sqlite else Ledger(directory)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
# ``-V`` beside ``--version``, as the argparse door offered.
@click.version_option(__version__, "-V", "--version", prog_name="wallet-helper")
@click.option(
    "--dir",
    "cache_dir",
    default=None,
    help="JSON ledger directory (default: $WALLET_HELPER_DIR or ~/.cache/wallet-helper).",
)
@click.option("--sqlite", default=None, help="Inspect a SQLite ledger file instead of the JSON directory.")
@click.pass_context
def cli(ctx: click.Context, cache_dir: str | None, sqlite: str | None) -> None:
    """Inspect and manage the wallet-helper ledger."""
    ctx.obj = _open_ledger(cache_dir, sqlite)


@cli.command()
@click.pass_obj
def stats(ledger: LedgerLike) -> None:
    """Show how many results are cached and how many calls they saved."""
    s = ledger.stats()
    click.echo(f"ledger: {ledger.location}")
    click.echo(f"entries: {s['entries']}")
    click.echo(f"calls saved (cache hits): {s['hits']}")


@cli.command()
@click.pass_obj
def path(ledger: LedgerLike) -> None:
    """Print where the ledger is stored."""
    click.echo(ledger.location)


@cli.command()
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
@click.pass_obj
def clear(ledger: LedgerLike, yes: bool) -> None:
    """Delete every cached result (irreversible)."""
    if not yes:
        click.confirm(f"Delete every cached result under {ledger.location}?", abort=True)
    ledger.clear()
    click.echo(f"cleared {ledger.location}")


@cli.command()
@click.option("--max-entries", type=int, default=None, help="Keep only the newest N entries.")
@click.option("--older-than", type=float, default=None, help="Remove entries older than this many seconds.")
@click.pass_obj
def evict(ledger: LedgerLike, max_entries: int | None, older_than: float | None) -> None:
    """Prune expired results, and optionally by age or size."""
    removed = ledger.evict(max_entries=max_entries, older_than=older_than)
    click.echo(f"evicted {removed} entries from {ledger.location}")


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``wallet-helper`` console script.

    Parameters
    ----------
    argv : list of str, optional
        Argument vector for testing; defaults to ``sys.argv`` when ``None``.

    Returns
    -------
    int
        Process exit code (``0`` on success).
    """
    # standalone_mode=False lets click return instead of calling sys.exit, so the
    # function is unit-testable and composes as a normal callable -- but it also
    # disables click's OWN exception handling, so without the try/except below
    # even a plain usage error (an unknown command, a bad option) would leak as
    # a raw ClickException/UsageError traceback instead of click's usual clean
    # "Error: ..." message. A library exception (e.g. a corrupted SQLite ledger)
    # is caught the same way every other CLI surface in this suite handles one.
    try:
        return cli.main(args=argv, prog_name="wallet-helper", standalone_mode=False) or 0
    except click.ClickException as exc:
        exc.show()  # click's own formatting, to stderr
        return exc.exit_code
    except click.exceptions.Abort:
        click.echo("Aborted!", err=True)
        return 1
    except Exception as exc:  # noqa: BLE001 — last resort: see docstring above
        click.echo(f"Error: {exc}", err=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
