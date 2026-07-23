# wallet-helper developer commands.
#
# The same checks CI runs, in one word on a contributor's machine. Run `make`
# (or `make all`) before pushing: lint then test, the exact gate CI enforces, so
# failures show up locally rather than in a pull request.
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
	python -m pip install -e ".[dev,cli,api]"

fmt:
	ruff check --fix .

lint:
	ruff check .

test:
	python -m pytest -q

all: lint test
