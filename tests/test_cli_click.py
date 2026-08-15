"""click CLI variant: same behaviour as the argparse one. Skipped without click.

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
"""

from __future__ import annotations

from pathlib import Path

import pytest

# The click CLI is an optional extra; skip the whole module when it is absent so
# a core install still has a green suite.
pytest.importorskip("click")

from wallet_helper.cli_click import main  # noqa: E402  (after importorskip on purpose)
from wallet_helper.ledger import Ledger, make_key  # noqa: E402
from wallet_helper.sqlite_ledger import SqliteLedger  # noqa: E402


def test_path_prints_the_ledger_location(tmp_path: Path, capsys) -> None:
    assert main(["--dir", str(tmp_path), "path"]) == 0
    assert capsys.readouterr().out.strip() == str(tmp_path)


def test_stats_reports_entries_and_saved_calls(tmp_path: Path, capsys) -> None:
    lg = Ledger(tmp_path)
    key = make_key("demo", {"x": 1})
    lg.put(key, {"ok": True})
    lg.register_hit(key)
    assert main(["--dir", str(tmp_path), "stats"]) == 0
    out = capsys.readouterr().out
    assert "entries: 1" in out and "calls saved (cache hits): 1" in out


def test_clear_with_yes_empties_the_ledger(tmp_path: Path) -> None:
    lg = Ledger(tmp_path)
    lg.put(make_key("demo", {"x": 1}), {"ok": True})
    assert main(["--dir", str(tmp_path), "clear", "--yes"]) == 0
    assert lg.stats()["entries"] == 0


def test_unknown_command_prints_clean_usage_error_not_a_traceback(capsys) -> None:
    # standalone_mode=False disables click's OWN exception handling too, not
    # just library exceptions -- without main()'s try/except, even a plain
    # usage error (an unknown subcommand) leaked as a raw ClickException.
    rc = main(["bogus-command"])
    assert rc == 2
    assert "No such command 'bogus-command'" in capsys.readouterr().err


def test_library_exception_prints_clean_error_not_a_traceback(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(self, namespace=None):
        raise RuntimeError("db is locked")

    monkeypatch.setattr(SqliteLedger, "stats", _boom)
    rc = main(["--sqlite", str(tmp_path / "ledger.db"), "stats"])
    assert rc == 1
    assert "Error: db is locked" in capsys.readouterr().err
