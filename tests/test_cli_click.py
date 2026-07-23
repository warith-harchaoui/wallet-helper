"""click CLI variant — feature-equivalent to the argparse one. Skipped sans click.

Author
------
Warith HARCHAOUI — https://linkedin.com/in/warith-harchaoui
"""
from __future__ import annotations

from pathlib import Path

import pytest

# The click CLI is an optional extra; skip the whole module when it is absent so
# a core-only install still has a green suite.
pytest.importorskip("click")

from wallet_helper.cli_click import main  # noqa: E402  (after importorskip on purpose)
from wallet_helper.ledger import Ledger, make_key  # noqa: E402


def test_path_prints_the_ledger_dir(tmp_path: Path, capsys) -> None:
    assert main(["--dir", str(tmp_path), "path"]) == 0
    assert capsys.readouterr().out.strip() == str(tmp_path)


def test_stats_reports_entries_and_savings(tmp_path: Path, capsys) -> None:
    lg = Ledger(tmp_path)
    key = make_key("demo", {"x": 1})
    lg.put(key, {"ok": True}, cost=0.5, currency="EUR")
    lg.register_hit(key)
    assert main(["--dir", str(tmp_path), "stats"]) == 0
    out = capsys.readouterr().out
    assert "entries: 1" in out and "EUR" in out and "0.5000" in out


def test_clear_with_yes_removes_the_directory(tmp_path: Path) -> None:
    lg = Ledger(tmp_path)
    lg.put(make_key("demo", {"x": 1}), {"ok": True})
    assert main(["--dir", str(tmp_path), "clear", "--yes"]) == 0
    assert not tmp_path.exists()
