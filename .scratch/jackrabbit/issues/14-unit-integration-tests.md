# 14: Unit & Integration Tests

**What to build:** Comprehensive unit tests for services and integration tests for all API endpoints.

**Blocked by:** 04, 05, 06, 07, 08, 09, 10, 13

**Status:** ready-for-agent

- [x] **Unit tests** (`tests/unit/`):
  - `test_ticket_service.py`: `generate_branch_name`, `slugify`, `can_transition` (all 30+ combos), `move_ticket_to_project` (renumbering, original_id), `assign_to_sprint`
  - `test_sprint_service.py`: `next_sprint_number`, `sprint_status_derived`
  - `test_project_service.py`: `next_ticket_number`, `validate_prefix`
  - `test_link_service.py`: `add_link` (all 5 types, inverses, validation), `get_blockers`, `get_children`
- [ ] **Integration tests** (`tests/integration/`):
  - `test_tickets_api.py`: CRUD, filtering, pagination, transitions (guarded/unguarded), links, project move, branch/PR
  - `test_projects_api.py`: CRUD, UNS protection, ticket counts
  - `test_sprints_api.py`: CRUD, ticket assignment, status derivation
  - `test_links_api.py`: add/remove all types, symmetric relates_to, blocker queries
  - `test_migrations.py`: `alembic upgrade head` → `downgrade -1` → `upgrade head` round-trip
- [ ] Test DB: fresh SQLite file per test module (tmp_path), migrations applied
- [ ] Coverage target: >90% on `services/`, >80% on `api/`
- [ ] Run: `pytest tests/unit tests/integration -v --cov=jackrabbit`

## Answer

**Verification result: 3 of 5 criteria checked; 256 tests pass, but the ticket spec is only partially met.**

Note: the implementation deviates from the ticket's file layout (single `jackrabbit/services.py` / `jackrabbit/api.py` instead of `services/` and `api/` packages, and different test file names). Verdicts below judge substance against the code as built.

### Criterion: Unit tests — **checked**
All named behaviors are unit-tested, distributed across files:
- `slugify` / `generate_branch_name` / `validate_pr_url`: `tests/unit/test_branch_pr.py` (slugify edge cases, branch naming per ticket type, URL host detection).
- `can_transition` all 30+ combos: `tests/unit/test_transitions.py::TestAllTransitionCombinations::test_all_combinations` — parametrized over 6×6 = 36 status combinations, plus guarded/unguarded transition tests and `TestTransitionAPI` endpoint tests.
- `move_ticket_to_project` (renumbering, original_id): `tests/unit/test_move_project.py` (incl. preserving first original_id across multiple moves) plus API-level tests in the same file.
- `assign_to_sprint`, `next_sprint_number`, sprint status derivation: `tests/unit/test_sprint_service.py` (24 tests incl. derived-status edge cases and ticket-completion override).
- `add_link` (all 5 types, inverses, validation), `get_blockers`, `get_children`: `tests/unit/test_links.py` (all 5 link types, inverse handling, self/duplicate rejection, blocker queries).
- Ticket numbering per project (`next_ticket_number` equivalent): `tests/unit/test_ticket_service.py` (sequential/independent/reuse-after-delete). Prefix validation is implemented as Pydantic validators in `jackrabbit/schemas.py` (no `validate_prefix` service method exists); rules are exercised in `tests/integration/test_api.py::test_create_project_validation_prefix`. No dedicated `test_project_service.py` file — gap noted but substance covered.

### Criterion: Integration tests — **NOT checked**
Partially satisfied. Present: `tests/integration/test_api.py` (projects CRUD, UNS delete protection, validation), `tests/integration/test_sprint_api.py` (comprehensive CRUD, assign/unassign, status derivation, cascade unassign), `tests/integration/test_plan_api.py`. Ticket transitions and project-move endpoints are API-tested in `tests/unit/test_transitions.py::TestTransitionAPI` and `tests/unit/test_move_project.py::TestMoveProjectAPI` (in the unit dir, not `tests/integration/`).
Gaps: no `test_links_api.py` — link API integration coverage is a single create-link test (`test_api.py::test_create_link`); no delete-link/symmetric relates_to/blocker-query integration tests. No `test_migrations.py` — no `alembic upgrade head → downgrade -1 → upgrade head` round-trip test exists anywhere in `tests/` (migrations are exercised incidentally via `init_db()` in the move/transition API test fixtures, but never downgraded). No tickets-API filtering/pagination integration tests (covered only at service level).

### Criterion: Test DB (fresh SQLite file per test module via tmp_path, migrations applied) — **NOT checked**
`tests/conftest.py` uses a shared **in-memory** SQLite engine (`StaticPool`) with `drop_all`/`create_all` per test — no tmp_path file per module, and tables are created via `SQLModel.metadata.create_all`, not Alembic migrations. `tests/unit/test_move_project.py` / `test_transitions.py` do use real file DBs (`./data/test_move.db`, `./data/test_transition.db`) with `init_db()` → Alembic migrations, but those are hardcoded paths, not tmp_path, and require manual cleanup (see residual risks).

### Criterion: Coverage (>90% services/, >80% api/) — **NOT checked**
Measured with `--cov=jackrabbit.services --cov=jackrabbit.api`: `services.py` **96%** (target met), `api.py` **78%** (target >80% missed by 2 points). Full-package run shows `schemas.py` 94%, `models.py` 100%, `web.py` 33% (web UI not in scope of the targets).

### Criterion: Run command — **checked**
`uv run pytest tests/unit tests/integration -q --cov=jackrabbit` → **256 passed** (ran with `-q` instead of `-v`). Caution: the suite passes only when stale `./data/*.db` artifacts from prior runs are removed; see residual risks.

### Residual risks
- `TestMoveProjectAPI` / `TestTransitionAPI` fixtures write to hardcoded `./data/test_move.db` / `./data/test_transition.db` and run Alembic against them. Stale DB files from interrupted runs cause `sqlite3.OperationalError` ("attempt to write a readonly database" / "no such table: project") — reproduced twice in this checkout; deleting `./data/test_move.db*` restored a green run. Flaky under parallel/dirty working-tree conditions.
- api.py coverage (78%) is below the 80% target; the missed lines are concentrated in error branches.
- `web.py` (server-rendered UI) is at 33% coverage and has no coverage target.
- No Alembic downgrade path is ever tested; a broken downgrade migration would go undetected.
- `tests/e2e/` contains additional Playwright-style scenario tests outside this ticket's scope; they were not evaluated in depth.