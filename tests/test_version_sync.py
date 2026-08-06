"""Guard against `__version__` drifting from `pyproject.toml`'s `version`.

The package's version is declared twice on purpose (`pyproject.toml` for
packaging/PyPI, `wallet_helper.__version__` for anyone introspecting the
installed package at runtime), and nothing keeps the two in sync
automatically. They have drifted silently before (0.3.1 vs 1.0.1) with no
build failure — this test fails loudly if it happens again.
"""

from __future__ import annotations

import re
from pathlib import Path

import wallet_helper

_ROOT = Path(__file__).resolve().parent.parent


def test_dunder_version_matches_pyproject() -> None:
    text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^\s*version\s*=\s*"([^"]+)"', text)
    assert match, "could not find [project].version in pyproject.toml"
    assert wallet_helper.__version__ == match.group(1)
