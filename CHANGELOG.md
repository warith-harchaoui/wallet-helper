# Changelog

All notable changes to wallet-helper are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to
semantic versioning.

## [Unreleased]

### Added
- **click CLI** variant (`wallet-helper-click` / `python -m wallet_helper.cli_click`),
  feature-equivalent to the argparse CLI (the `[cli]` extra).
- **FastAPI HTTP surface** (`wallet_helper.api`, the `[api]` extra): key
  derivation, record store/lookup, hit counting, stats and budget checks over
  HTTP — a shared ledger for several processes — plus a minimal dashboard at
  `/gui`. Exposes only the accounting half (never runs your paid callable).
- **MCP tool set** (`wallet_helper.mcp_server` / `wallet-helper-mcp`, the `[mcp]`
  extra): the same accounting operations as Model Context Protocol tools.
- `EXAMPLES.md` runnable cookbook; `requirements.txt` (runtime) split from
  `requirements-dev.txt`; `Makefile` (`install`/`fmt`/`lint`/`test`) and a
  GitHub Actions CI matrix (ruff + pytest, Python 3.10–3.13, Linux/macOS/Windows).
- Cross-platform install notes and a Contributing section in README / LISEZMOI.

### Changed
- Docstring examples now run as doctests in the default `pytest` invocation
  (`--doctest-modules`). Test suite: 39 tests + doctests, ruff-clean.

## [0.1.0] — 2026-07-22

### Added
- Core library: content-addressed `Ledger` (idempotency cache), `Cost` / `Budget`
  value types with over-budget refusal, and `Wallet` (the `call` method +
  `@paid` decorator) tying them together — a provider-agnostic guard so a paid
  call runs, and bills, at most once per (namespace, content, params).
- `Ledger.stats()` reporting spend and cache savings per currency.
- argparse CLI (`wallet-helper` / `python -m wallet_helper.cli_argparse`):
  `stats`, `path`, `clear`.
- Zero runtime dependencies (stdlib only). Bilingual README / LISEZMOI with a
  "prior art" comparison. Test suite: 17 tests + doctests, ruff-clean.
