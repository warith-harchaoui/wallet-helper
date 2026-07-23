"""wallet-helper click command line (optional ``[cli]`` extra).

A second command-line variant, same features as
:mod:`wallet_helper.cli_argparse` but built on click, for those who prefer its
grouped subcommands and coloured help. It reads and prunes the local ledger; the
calls themselves are memoized from your own code through
:class:`wallet_helper.guard.Wallet`.

Because click is an optional dependency, importing this module without it
installed raises a clear, actionable error instead of a bare import failure.

Usage
-----
``wallet-helper-click stats``
``python -m wallet_helper.cli_click path``
``wallet-helper-click clear --yes``

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
"""
from __future__ import annotations

try:
    import click
except ModuleNotFoundError as exc:  # pragma: no cover - only hit without click
    raise SystemExit(
        "The click CLI needs the optional 'cli' extra. Install it with\n"
        "  pip install 'wallet-helper[cli]'\n"
        "or use the dependency-free CLI: python -m wallet_helper.cli_argparse"
    ) from exc

from wallet_helper import __version__
from wallet_helper.ledger import Ledger, LedgerLike
from wallet_helper.sqlite_ledger import SqliteLedger


def _open_ledger(directory: str | None, sqlite: str | None) -> LedgerLike:
    """Return the SQLite ledger if ``--sqlite`` was given, else the JSON one."""
    return SqliteLedger(sqlite) if sqlite else Ledger(directory)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="wallet-helper")
@click.option("--dir", "cache_dir", default=None, help="JSON ledger directory (default: $WALLET_HELPER_DIR or ~/.cache/wallet-helper).")
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
    """Entry point for the ``wallet-helper-click`` console script.

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
    # function is unit-testable and composes as a normal callable.
    return cli.main(args=argv, prog_name="wallet-helper", standalone_mode=False) or 0


if __name__ == "__main__":
    raise SystemExit(main())
