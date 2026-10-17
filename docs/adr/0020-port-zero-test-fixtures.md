# ADR-0020: PORT=0 Means "Pick a Free Port" (Test Fixture Strategy)

## Status
Accepted

## Context
Ticket 13 (spec). Integration/E2E tests need the app served on a real port. Hardcoding a port causes flaky failures when suites run in parallel or a port is already taken. Test fixtures also need a database that never touches the developer's real data, and `httpx` 0.27+ deprecated the direct `app=` kwarg on `TestClient`/`AsyncClient`.

## Decision
- **`PORT=0` is a valid Settings value** meaning "bind to an ephemeral free port" — the OS chooses; used by test fixtures
- **`test_settings` overrides `DATA_DIR`** to a pytest temp dir so tests never read/write the developer's SQLite file
- **`client` fixture** is `httpx.AsyncClient` via **`ASGITransport`** (not the deprecated `app=` kwarg), with `base_url="http://test"`
- **Seed fixtures**: `seeded_projects` = UNS + 2 test projects (WEB, API); `seeded_tickets` spans Open / Groomed / In-Progress / Ready-for-Review
- **CI runs E2E headed Chrome under Xvfb** (`xvfb-run`) so headed-mode Playwright runs are reproducible in CI

## Consequences

### Positive
- **No port collisions** — suites can run in parallel locally and in CI
- **Isolation** — temp `DATA_DIR` means tests can't corrupt real data
- **Future-proof** — `ASGITransport` matches current httpx API

### Negative
- **`PORT=0` must be handled everywhere the port is logged/printed** — resolved by reporting the actually-bound port where needed

## Alternatives Considered
- **Fixed test port**: Rejected — flakes under parallel runs.
- **In-memory ASGI-only testing**: Rejected — E2E flows need a real served port for Playwright.