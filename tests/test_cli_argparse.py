"""argparse CLI: stats, path, clear against a temporary ledger.

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
"""

from __future__ import annotations

from pathlib import Path

from wallet_helper.cli_argparse import main
from wallet_helper.ledger import Ledger, make_key


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


def test_clear_empties_the_ledger(tmp_path: Path, capsys) -> None:
    lg = Ledger(tmp_path)
    lg.put(make_key("demo", {"x": 1}), {"ok": True})
    assert main(["--dir", str(tmp_path), "clear"]) == 0
    assert lg.stats()["entries"] == 0
