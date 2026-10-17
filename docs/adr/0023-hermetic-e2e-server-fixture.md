# ADR-0023: E2E Server Fixture Owns an Ephemeral Port and Throwaway DATA_DIR

## Status
Accepted (extends ADR-0020)

## Context
ADR-0020 gave in-process test fixtures a temp `DATA_DIR` and `PORT=0`, but the Playwright
`test_server` fixture was never updated: it hardcoded `sqlite:///./data/e2e_test.db` inside the
repo, assumed port 8080, and on teardown deleted only the `.db` file — leaving `-wal`/`-shm`
sidecars behind. The database therefore accumulated across runs, and three e2e tests silently
depended on it being empty (`test_backlog_filters::test_combined_filters` matches a fixed title
substring, `::test_filter_by_date` asserts the global "No tickets found" empty state,
`test_project_move::test_move_back_renumbers_next_available` assumed `MSC` had no tickets — and
counted serials by scanning one unpaginated page of `/api/v1/tickets`). Against a database left
over from a previous run, all three failed.

## Decision
The `test_server` session fixture owns the server: it creates a per-session `DATA_DIR` under
pytest's temp root (so the whole SQLite file plus its WAL sidecars vanish with the run), picks a
free port by binding and releasing an ephemeral socket, starts `python -m jackrabbit.main` with
`ENVIRONMENT=test`, and yields that URL through the `base_url` fixture. `E2E_BASE_URL` remains an
opt-out for pointing the suite at a server you started yourself; a server already answering there
is reused as-is, and its port is honored when the fixture starts its own.

Tests additionally stop encoding assumptions about database state: titles asserted via the `q`
filter are run-unique, the empty-state assertion is scoped by a `q` filter, and project-move
expectations are derived from live, paginated per-project serial queries.

## Consequences

### Positive
- Two consecutive `pytest tests/e2e` runs both pass — enforced by `make test-e2e-idempotent` and
  a second e2e step in CI
- No test artifact ever lands in `./data`; `make test-e2e` needs no manual server orchestration
  and no longer collides with a developer's `make dev` on port 8080
- Startup failure reports the captured server log tail instead of a bare "failed to start"

### Negative
- The suite spends a few seconds booting uvicorn per session rather than reusing a shared server
- A free port is chosen by bind-and-release, so a port can theoretically be stolen between the
  probe and uvicorn binding it; the health wait plus explicit error keeps that visible

### Considered alternatives
- **Delete `./data/e2e_test.db*` on teardown**: rejected — treats the symptom, still serializes
  parallel runs, and keeps numbering assertions order-dependent.
- **Truncate the shared database in an autouse fixture**: rejected — makes "clean state" an
  ambient side effect instead of an owned resource, and still writes inside the repo.
