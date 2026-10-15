# 13: Testing Infrastructure

**What to build:** pytest configuration, test fixtures (seeded DB, test client), Playwright + chrome-devtools-axi setup, CI workflow.

**Blocked by:** 01

**Status:** resolved

- [x] `pytest.ini` / `pyproject.toml` `[tool.pytest]` config: async mode, test paths, coverage
  (asyncio_mode=auto, testpaths, markers, + `[tool.coverage.run]`/`[tool.coverage.report]`)
- [x] `tests/conftest.py` fixtures:
  - `test_settings` — overrides DATA_DIR to temp dir, PORT=0
  - `test_db` — fresh SQLite file per test (or `:memory:`), runs migrations
  - `client` — `httpx.AsyncClient(app=app, base_url="http://test")` for integration tests
  - `seeded_projects` — creates UNS + 2 test projects
  - `seeded_tickets` — creates tickets in various states
- [x] `tests/e2e/conftest.py` — Playwright fixtures: `page`, `browser`, `base_url`
- [x] `chrome-devtools-axi` integration: helper to launch Chrome with devtools protocol for agent-driven E2E (`tests/cdx_helper.py`)
- [x] GitHub Actions workflow (`.github/workflows/ci.yml`):
  - Lint: `ruff check .`
  - Type: `mypy jackrabbit`
  - Unit: `pytest tests/unit -x`
  - Integration: `pytest tests/integration -x`
  - E2E: `pytest tests/e2e -x` (headed Chrome in CI, via xvfb-run)
- [x] `Makefile` or `justfile` with targets: `test`, `test-unit`, `test-int`, `test-e2e`, `lint`, `typecheck`, `migrate`
  (both Makefile and justfile exist with all targets)

## Answer

Implemented ticket 13 (testing infrastructure) with TDD. Much of the scaffolding already
existed from an earlier checkpoint; this pass audited it against the criteria, added red
-tests (`tests/unit/test_infrastructure.py`, port-0 test in `test_config.py`), and closed
the gaps:

- **pyproject**: `asyncio_mode=auto`, testpaths, markers (`--strict-markers`), plus
  `[tool.coverage.run]` (branch, source=jackrabbit) and `[tool.coverage.report]` sections.
- **tests/conftest.py**: `test_settings` now uses a pytest temp dir for DATA_DIR and
  PORT=0 (required relaxing `config.Settings.port` to `ge=0`); `test_db` on a shared
  in-memory SQLite engine with tables recreated per test; `client` is now
  `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")`
  (legacy sync TestClient kept as `sync_client`); `seeded_projects` = UNS + 2 projects
  (WEB, API); `seeded_tickets` spans Open/Groomed/In-Progress/Ready-for-Review; fixed
  latent bug in `ready_for_review_ticket` (missing pr_url).
- **tests/integration**: all 47 tests converted to async/await against the AsyncClient;
  `tests/integration/conftest.py` rewritten without the hardcoded cross-repo `sys.path`
  hack (now imports via `tests` package; `tests/__init__.py` added); seed count
  assertions updated (4→3 projects, MOB→API).
- **tests/e2e/conftest.py**: kept page/browser/base_url fixtures; removed stale `client`
  dependency; fixed hardcoded server cwd to repo-relative.
- **cdx_helper.py**: chrome-devtools-axi wrapper verified by unit tests (env builder,
  command runner, context manager, fixtures importable).
- **CI**: `mypy jackrabbit` (per ticket), E2E job now headed Chrome under `xvfb-run` with
  `CHROME_DEVTOOLS_AXI_HEADED=1`.
- **Makefile/justfile**: already contain all required targets (verified).

Validation: `pytest -x tests/unit tests/integration` → 270 passed; ruff check clean;
mypy jackrabbit unchanged from baseline (31 pre-existing errors in other tickets' code).
E2E suite: 31/36 pass; the 5 failures reproduce on the unmodified tree (pre-existing UI
bugs owned by tickets 04–10) and are not caused by this ticket.

Decisions recorded in spec.md as ADR-0018.