# 13: Testing Infrastructure

**What to build:** pytest configuration, test fixtures (seeded DB, test client), Playwright + chrome-devtools-axi setup, CI workflow.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] `pytest.ini` / `pyproject.toml` `[tool.pytest]` config: async mode, test paths, coverage
- [ ] `tests/conftest.py` fixtures:
  - `test_settings` — overrides DATA_DIR to temp dir, PORT=0
  - `test_db` — fresh SQLite file per test (or `:memory:`), runs migrations
  - `client` — `httpx.AsyncClient(app=app, base_url="http://test")` for integration tests
  - `seeded_projects` — creates UNS + 2 test projects
  - `seeded_tickets` — creates tickets in various states
- [ ] `tests/e2e/conftest.py` — Playwright fixtures: `page`, `browser`, `base_url`
- [ ] `chrome-devtools-axi` integration: helper to launch Chrome with devtools protocol for agent-driven E2E
- [ ] GitHub Actions workflow (`.github/workflows/ci.yml`):
  - Lint: `ruff check .`
  - Type: `mypy jackrabbit`
  - Unit: `pytest tests/unit -x`
  - Integration: `pytest tests/integration -x`
  - E2E: `pytest tests/e2e -x` (headed Chrome in CI)
- [ ] `Makefile` or `justfile` with targets: `test`, `test-unit`, `test-int`, `test-e2e`, `lint`, `typecheck`, `migrate`