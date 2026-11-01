"""One guard: requirements.txt must declare exactly what the package declares.

Two files state this package's runtime dependencies, and until 2026-10-31
nothing compared them. They had drifted in ten of the suite's sixteen
dependents at once: `click` became a core dependency when the argparse door was
dropped, `pyproject.toml` recorded it, and `requirements.txt` did not — so
`pip install -r requirements.txt` built an environment whose command line could
not start, while `pip install -e .` built a working one. Neither reader could
notice, because a *missing* requirement fails only when something imports it
and a *surplus* one installs cleanly.

Floors drifted the same way: `os-helper>=1.5.0` sat in requirements.txt while
the package itself demanded `>=2.6.0`.

Deliberately regex, not `tomllib`: this file must run on the floor Python
(3.10), where `tomllib` is not in the standard library, and `[project]
dependencies` is a flat array of strings that needs no TOML parser.

Author
------
Warith HARCHAOUI, https://linkedin.com/in/warith-harchaoui
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _declared() -> set[str]:
    """The `[project] dependencies` array of pyproject.toml, as written."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r"^dependencies\s*=\s*\[(.*?)^\]", text, re.S | re.M)
    assert match, "pyproject.toml has no [project] dependencies array"
    # Comments inside the array quote specifiers too ("it was \">=1.0\""), so
    # they have to go before anything is read as a dependency.
    body = re.sub(r"#[^\n]*", "", match.group(1))
    return {m.group(1) for m in re.finditer(r'"([^"]+)"', body)}


def _pinned() -> set[str]:
    """The dependency lines of requirements.txt, comments stripped."""
    lines = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    return {s for s in (line.split("#")[0].strip() for line in lines) if s}


def test_requirements_txt_mirrors_the_package_metadata() -> None:
    declared, pinned = _declared(), _pinned()
    assert pinned == declared, (
        f"requirements.txt only: {sorted(pinned - declared)}; pyproject.toml only: {sorted(declared - pinned)}"
    )


# --------------------------------------------------------------- the extras
#
# The guard above compares runtime dependencies. This one compares *extras*,
# and it exists because the two files were wrong about them in a way nothing
# could notice: `pip install ".[dev,cli,api]"` answers an unknown extra with a
# **warning and exit 0**. Measured, not assumed. So an install line naming a
# dead extra installs a working-but-smaller environment and reports success.
#
# `[cli]` was dropped when the argparse door was, because click became a base
# dependency. `requirements-dev.txt` went on asking for it, and its own comment
# claimed CI installed `".[dev,cli,api]"` while the workflow installs
# `".[dev,api]"` — two statements about one fact, both wrong, for a fortnight.

#: Files that *instruct* a reader to install something. CHANGELOG.md is not one
#: of them: it names `[cli]` on purpose, in the entry that removed it, and a
#: history that cannot mention a dead name is a history that cannot explain a
#: migration.
INSTRUCTING = (
    "requirements.txt",
    "requirements-dev.txt",
    "README.md",
    "LISEZMOI.md",
    "EXAMPLES.md",
    "SKILL.md",
)

_EXTRA_SPEC = re.compile(r"(?:wallet-helper|\.)\[([a-z0-9,\-\s]+)\]")


def _declared_extras() -> set[str]:
    """The names of `[project.optional-dependencies]`, by regex for 3.10."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = re.search(r"^\[project\.optional-dependencies\](.*?)(?=^\[|\Z)", text, re.S | re.M)
    assert block, "pyproject.toml declares no optional-dependencies"
    return set(re.findall(r"^([a-z][a-z0-9-]*)\s*=", block.group(1), re.M))


def test_the_extras_were_actually_found() -> None:
    """Non-vacuity: an empty set would make the check below pass on anything."""
    assert "api" in _declared_extras()
    assert "dev" in _declared_extras()


def test_no_install_line_names_an_extra_that_does_not_exist() -> None:
    """The class, not the one occurrence.

    Aimed at every file that tells someone what to type, plus the workflows,
    because an unknown extra there is a CI that quietly installs less than it
    says it does.
    """
    declared = _declared_extras()
    offenders: list[str] = []
    paths = [ROOT / name for name in INSTRUCTING]
    paths += sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    checked = 0
    for path in paths:
        if not path.is_file():
            continue
        checked += 1
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for match in _EXTRA_SPEC.finditer(line):
                for extra in (e.strip() for e in match.group(1).split(",")):
                    if extra and extra not in declared:
                        offenders.append(
                            f"{path.name}:{number} names [{extra}] — declared extras are {', '.join(sorted(declared))}"
                        )
    assert checked >= 4, f"only {checked} instructing files found; the walk is wrong"
    assert not offenders, "\n  ".join(["", *offenders])
