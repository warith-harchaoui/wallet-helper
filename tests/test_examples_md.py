"""EXAMPLES.md's cookbook, executed for real so the docs cannot silently rot.

Every fenced ```python block in EXAMPLES.md that uses ``osh.temporary_folder``
is, by the file's own header, self-contained and safe to run as-is. This
extracts and runs each one, so a future API change that breaks the cookbook
fails CI instead of only being noticed by a reader. The remaining blocks
(illustrative snippets against a paid API, or a live HTTP server) are out of
scope here; the server protocol they show is exercised for real by
test_api.py and test_remote.py instead.

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_EXAMPLES_MD = Path(__file__).resolve().parent.parent / "EXAMPLES.md"


def _self_contained_blocks() -> list[str]:
    """Return every fenced python block that carries its own temporary store."""
    text = _EXAMPLES_MD.read_text(encoding="utf-8")
    blocks = re.findall(r"```python\n(.*?)```", text, re.DOTALL)
    return [block for block in blocks if "osh.temporary_folder" in block]


_BLOCKS = _self_contained_blocks()


def test_examples_md_has_self_contained_blocks() -> None:
    # A canary for the extraction itself: if EXAMPLES.md's fencing or its
    # "osh.temporary_folder" self-containment convention ever changes shape,
    # this fails loudly instead of the parametrized test below silently
    # collecting zero cases.
    assert len(_BLOCKS) >= 8


@pytest.mark.parametrize("code", _BLOCKS, ids=[f"block-{i}" for i in range(len(_BLOCKS))])
def test_example_block_runs(code: str) -> None:
    exec(compile(code, str(_EXAMPLES_MD), "exec"), {"__name__": "__main__"})
