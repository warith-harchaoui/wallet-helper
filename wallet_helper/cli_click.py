"""wallet-helper — click command-line surface (optional ``[cli]`` extra).

A second CLI variant, feature-equivalent to :mod:`wallet_helper.cli_argparse`
but built on `click <https://click.palletsprojects.com/>`_ for those who prefer
its ergonomics (grouped subcommands, coloured ``--help``). It inspects and
manages the local ledger; the billable calls themselves are made from your own
code through :class:`wallet_helper.guard.Wallet` — this CLI is the accountant,
not the spender.

Because ``click`` is an optional dependency, importing this module without it
installed raises a clear, actionable error rather than a bare ``ModuleNotFound``.

Usage
-----
``wallet-helper-click stats``
``python -m wallet_helper.cli_click path``
``python -m wallet_helper.cli_click clear --yes``

Author
------
Warith HARCHAOUI — https://linkedin.com/in/warith-harchaoui
"""
from __future__ import annotations

import shutil

try:
    import click
except ModuleNotFoundError as exc:  # pragma: no cover - exercised only sans click
    # Fail loud and helpful: the argparse CLI needs no dependency, so nudge the
    # user toward the extra (or that zero-dependency fallback) instead of a
    # cryptic import traceback.
    raise SystemExit(
        "The click CLI needs the optional 'cli' extra. Install it with\n"
        "  pip install 'wallet-helper[cli]'\n"
        "or use the dependency-free CLI: python -m wallet_helper.cli_argparse"
    ) from exc

from wallet_helper import __version__
from wallet_helper.ledger import Ledger


def _fmt_money(by_currency: dict) -> str:
    """Render the per-currency spend/saved breakdown as one readable block.

    Parameters
    ----------
    by_currency : dict
        The ``by_currency`` mapping from :meth:`wallet_helper.ledger.Ledger.stats`.

    Returns
    -------
    str
        One indented line per currency, or a placeholder for an empty ledger.
    """
    if not by_currency:
        return "  (empty ledger)"
    # Sort so the output is stable across runs (dict order is insertion order).
    lines = [f"  {cur}: spent {slot['spent']:.4f} · saved {slot['saved']:.4f}" for cur, slot in sorted(by_currency.items())]
    return "\n".join(lines)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="wallet-helper")
@click.option(
    "--dir",
    "cache_dir",
    default=None,
    help="Ledger directory (default: $WALLET_HELPER_DIR or ~/.cache/wallet-helper).",
)
@click.pass_context
def cli(ctx: click.Context, cache_dir: str | None) -> None:
    """Inspect and manage the wallet-helper ledger."""
    # Stash one Ledger on the context so every subcommand shares the same store.
    ctx.obj = Ledger(cache_dir)


@cli.command()
@click.pass_obj
def stats(ledger: Ledger) -> None:
    """Show spend and cache savings, per currency."""
    s = ledger.stats()
    click.echo(f"ledger: {ledger.dir}")
    click.echo(f"entries: {s['entries']} · cache hits (calls saved): {s['hits']}")
    click.echo("by currency:")
    click.echo(_fmt_money(s["by_currency"]))


@cli.command()
@click.pass_obj
def path(ledger: Ledger) -> None:
    """Print the ledger directory."""
    click.echo(str(ledger.dir))


@cli.command()
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
@click.pass_obj
def clear(ledger: Ledger, yes: bool) -> None:
    """Delete every ledger entry (irreversible)."""
    # Guard a destructive wipe behind a confirmation unless --yes is passed.
    if not yes:
        click.confirm(f"Delete every entry under {ledger.dir}?", abort=True)
    if ledger.dir.exists():
        shutil.rmtree(ledger.dir)  # a fresh directory is recreated on next write
    click.echo(f"cleared {ledger.dir}")


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
