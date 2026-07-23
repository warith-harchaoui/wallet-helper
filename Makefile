# wallet-helper — shift-left developer commands (gist rule 18).
#
# The same deterministic checks CI runs, runnable on a contributor's machine in
# one word. Run `make` (or `make all`) before pushing: format, lint, test — the
# exact gate CI enforces, so failures surface locally, not in a PR.
#
# Targets:
#   make install   editable install with dev + all optional extras
#   make fmt        autofix lints (ruff --fix), leaving hand-formatting intact
#   make lint       lint only, no changes (what CI checks)
#   make test       run the test suite (pytest + doctests)
#   make all        lint + test (the pre-push gate)  [default]

.DEFAULT_GOAL := all
.PHONY: install fmt lint test all

install:
	python -m pip install -e ".[dev,cli,api,mcp]"

fmt:
	ruff check --fix .

lint:
	ruff check .

test:
	python -m pytest -q

all: lint test
