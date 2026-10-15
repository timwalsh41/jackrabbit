# 02: Database layer & migrations

**What to build:** SQLite engine with WAL mode, SQLModel session management, Alembic migration setup. On startup, `alembic upgrade head` runs automatically. Initial migration creates all 5 tables (project, ticket, sprint, ticket_link, ticket_transition) and seeds the UNS project.

**Blocked by:** 01

**Status:** resolved

- [x] `database.py`: SQLite engine with `PRAGMA journal_mode=WAL`, session factory, `init_db()` runs migrations
- [x] `alembic.ini` + `alembic/env.py` configured to read `DATABASE_URL` from settings
- [x] `alembic revision --autogenerate -m "initial schema"` creates `0001_initial.py`
- [x] Migration creates tables per ADR-0016/0015/0017 schema:
  - `project`: id, prefix, name, description, color, is_system, created_at
  - `ticket`: id, project_id, number, type, status, title, description, priority, story_points, sprint_id, branch_name, pr_url, approach, files_to_change, test_plan, validation_steps, created_at, updated_at, UNIQUE(project_id, number)
  - `sprint`: id, number, planned_start, planned_duration_days, actual_start, actual_finish, created_at
  - `ticket_link`: id, source_ticket_id, target_ticket_id, link_type, created_at, UNIQUE(source, target, type)
  - `ticket_transition`: id, ticket_id, from_status, to_status, reason, at
- [x] UNS project seeded in migration: `INSERT INTO project (prefix, name, description, color, is_system) VALUES ('UNS', 'Unsorted', 'Default project for tickets without a project', '#6b7280', true)`
- [x] `alembic upgrade head` runs on app startup (idempotent)
- [x] Test: fresh DB → startup → tables exist + UNS present

## Answer

Verification performed on branch `jackrabbit-integration` (2026-10-15). All criteria checked with first-hand evidence.

**Criterion-by-criterion evidence:**

1. **`database.py` (satisfied)** — `jackrabbit/database.py` defines `_set_sqlite_pragma` executing `PRAGMA journal_mode=WAL` via a `connect` event listener (registered only for sqlite URLs), `get_session()` session factory, and `init_db()` → `run_migrations()` → `alembic.command.upgrade(cfg, "head")`. Verified live: fresh-DB run reports `journal_mode: wal`.
2. **alembic config (satisfied)** — `alembic.ini` exists with `script_location = alembic`; `alembic/env.py` imports `get_settings()` from `jackrabbit.config` and does `config.set_main_option("sqlalchemy.url", settings.database_url)`; `target_metadata = SQLModel.metadata`.
3. **`0001_initial.py` (satisfied)** — `alembic/versions/0001_initial.py` exists with `revision = "0001"`, `down_revision = None`, creating all 5 tables plus UNS seed. `alembic history/current` resolves cleanly to head.
4. **Schema (satisfied, with documented deviations)** — verified via `PRAGMA table_info` on a migrated fresh DB:
   - `project`: id, prefix, name, description, color, is_system, created_at (+ updated_at).
   - `ticket`: all listed columns present incl. type, status, priority, story_points, sprint_id, branch_name, pr_url, approach, files_to_change, test_plan, validation_steps (+ original_id, completed_at); UNIQUE(project_id, number) present as `uq_ticket_project_number`.
   - `sprint`: all listed columns (+ name, description, planned_end, actual_end, updated_at).
   - `ticket_link`: created in 0001 with id, source_id, target_id, link_type, created_at and UNIQUE(source_id, target_id, link_type) — column names are `source_id`/`target_id`, not the spec's `source_ticket_id`/`target_ticket_id` (matches shipped `jackrabbit/models.py::TicketLink`).
   - `ticket_transition`: id, ticket_id, from_status, to_status, reason, at.
   - Deviation: a second migration `alembic/versions/dd5c9a836974_...py` (head) renames `ticket_link` → `ticketlink` and `ticket_transition` → `transition` (data-preserving copy + drop). Final table names differ from spec.md/ADR naming; semantics and constraints are equivalent.
5. **UNS seed (satisfied, with deviations)** — migration seeds `INSERT INTO project ... (1, 'UNS', 'Unsorted', 'Default project for unsorted tickets', '#9ca3af', 1, ...)`. Description text differs from the quoted SQL ('Default project for tickets without a project' per ADR-0017) and color is `#9ca3af` vs `#6b7280`. Functionally: UNS exists as is_system=1 system project (verified live; `is_system=1`).
6. **Startup migrations, idempotent (satisfied)** — `jackrabbit/main.py` lifespan calls `init_db()`; CLI also exposes `init-db` (`jackrabbit/cli.py:42`). Verified live: `init_db()` ran twice on a fresh DB; second run was a no-op with `alembic_version` at head (`dd5c9a836974`), no errors.
7. **Fresh DB test (satisfied)** — No dedicated test asserts "tables exist + UNS present" by name, but `tests/unit/test_move_project.py` and `tests/unit/test_transitions.py` call `init_db()` against a real fresh SQLite file and then successfully use UNS as `project_id=1` (e.g. tickets created in UNS without seeding), which requires all migrated tables + the UNS row. Additionally, a manual fresh-DB script confirmed: tables `project/sprint/ticket/ticketlink/transition` exist, UNS row present, WAL enabled, idempotent re-run.

**Test runs:**
- `uv run pytest tests/unit tests/integration -q` → 253 passed; 1 failed + 2 errors in `tests/unit/test_move_project.py::TestMoveProjectAPI` (see risks).
- `uv run pytest tests/unit/test_move_project.py -q` alone → 12 passed (clean rerun).

**Gaps / residual risks:**
- `TestMoveProjectAPI` is flaky: tests share `./data/test_move.db`, teardown deletes only the `.db` file (not `-wal`/`-shm`), so subsequent tests can hit `disk I/O error` / `attempt to write a readonly database`. Same tests pass on clean reruns — test-hygiene issue, not a migration defect.
- No explicit automated test asserting "fresh DB → startup → tables + UNS"; coverage is implicit via test_move_project/test_transitions plus manual verification.
- Final table names (`ticketlink`, `transition`) and link column names (`source_id`/`target_id`) diverge from spec.md/ADR-0015 literal naming.
- UNS seed description/color differ slightly from the ADR-0017 quoted values.