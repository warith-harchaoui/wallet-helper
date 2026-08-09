"""pytest configuration: skip optional-surface modules when their deps are absent.

``--doctest-modules`` (see pyproject.toml) imports every module under
``wallet_helper/`` to collect docstring examples. Three surfaces,
:mod:`wallet_helper.cli_click`, :mod:`wallet_helper.api`, and
:mod:`wallet_helper.mcp`, raise ``SystemExit`` on import when their optional
dependency is missing. On a core install we drop them from collection so the
suite stays green; when the extras are installed (CI, or a full local env)
they are collected and their doctests run.

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
"""

from __future__ import annotations

import importlib.util

# (module path, dependency it needs): mirror the try/except guards in each file.
_OPTIONAL = [
    ("wallet_helper/cli_click.py", "click"),
    ("wallet_helper/api.py", "fastapi"),
    ("wallet_helper/mcp.py", "fastapi_mcp"),
]

collect_ignore = [path for path, dep in _OPTIONAL if importlib.util.find_spec(dep) is None]
