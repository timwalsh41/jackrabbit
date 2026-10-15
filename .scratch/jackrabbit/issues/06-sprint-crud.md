# 06: Sprint CRUD (API + Web)

**What to build:** Full CRUD for Sprints via `/api/v1/sprints` REST API and Sprint list page. Serial numbering `2601`, `2602`... continuing past 52. Optional date fields.

**Blocked by:** 02

**Status:** resolved

- [x] API: `GET /api/v1/sprints` (list, ordered by number desc), `POST /api/v1/sprints` (create), `GET /api/v1/sprints/{id}` (get with tickets), `PATCH /api/v1/sprints/{id}` (update), `DELETE /api/v1/sprints/{id}` (delete)
- [x] Sprint number: auto-assign `MAX(number)+1` (starts at 2601); user can override
- [x] Fields: `number` (int), `planned_start` (date, optional), `planned_duration_days` (int, optional), `actual_start` (date, optional), `actual_finish` (date, optional)
- [x] Web: `GET /sprints` — table of sprints with number, date range (planned/actual), ticket count, status (Planned/Active/Complete), actions
- [x] Web: `GET /sprints/new` — create form (number auto-filled, date pickers); `hx-post="/api/v1/sprints"` → returns row
- [x] Web: `GET /sprints/{id}/edit` — edit form; `hx-patch="/api/v1/sprints/{id}"` → returns updated row
- [x] Web: Delete button with `hx-delete` + `hx-confirm`
- [x] Sprint status derived: no actual_start → Planned; actual_start set, no actual_finish → Active; actual_finish set → Complete

## Answer

**Implemented by:** implementer subagent (ticket 06), TDD red-green-refactor.

**Changes:**

- `jackrabbit/models.py` — `Sprint.number` changed str → `int` (per ticket); `actual_end` renamed to `actual_finish` (ticket naming).
- `alembic/versions/0001_initial.py` — sprint `number` column → `sa.Integer`; `actual_end` → `actual_finish`.
- `jackrabbit/services.py`:
  - `create_sprint(number=None, ...)` — number now optional; auto-assigns `get_next_sprint_number()` when omitted; also accepts `planned_duration_days`, `actual_start`, `actual_finish`.
  - `get_next_sprint_number()` returns `int` (MAX+1, starts at 2601).
  - `list_sprints()` now `order_by(Sprint.number.desc())`.
  - `_derive_status()` rewritten per ticket: `actual_finish` → Complete; `actual_start` → Active; otherwise Planned. Ticket-completeness and planned-date heuristics removed (tickets no longer drive sprint status).
  - `update_sprint()` accepts/sets `planned_duration_days`, `actual_start`, `actual_finish`.
- `jackrabbit/schemas.py` — `SprintBase`/`SprintCreate`/`SprintRead`/`SprintUpdate`/`PlanSprintResponse` expose `planned_duration_days`, `actual_start`, `actual_finish`; `number: int`, optional (auto-assign) on `SprintCreate` with `""` → None (forms submit empty strings for untouched optional fields; validator mixin tolerates `""` for optional dates/duration).
- `jackrabbit/api.py` — POST/PATCH pass through the new fields; duplicate number → 409 (was a 500 IntegrityError); Read schemas include the new fields.
- `jackrabbit/web.py` — `/sprints/new` and `/sprints/{id}/edit` pass `method` ("post"/"patch") and serve the modal partial (`sprint_form_partial.html`) for HX-Request on edit too.
- Templates — forms use `hx-{{ method }}="{{ action }}"` (fixes the edit-form POST→405 bug); create/edit forms include `planned_duration_days`, `actual_start`, `actual_finish` pickers; sprint list shows planned AND actual date ranges (header "Dates (Planned / Actual)"); Edit opens the modal.
- Test infra — `tests/integration/conftest.py` and `tests/e2e/conftest.py` no longer hardcode `/workspace/projects/jackrabbit`; they resolve the repo root relative to the test files so integration tests and the e2e server run the checkout they belong to.

**Tests (red-green):**
- `tests/unit/test_sprint_service.py` — numbering (2601 start, MAX+1 from max, past-52 continuation, override), status derivation from actual dates (incl. by-status view, tickets don't drive status), list ordering desc, auto-assign create, CRUD with new fields.
- `tests/unit/test_models.py` — SprintCreate int/optional-number schema.
- `tests/integration/test_sprint_api.py` — list ordered desc; POST without number auto-assigns; empty-string form fields accepted; duplicate number 409; PATCH sets planned_duration_days/actual_start/actual_finish; status derivation via actual dates incl. Active→Complete via PATCH; next-number int.
- `tests/integration/test_sprint_web.py` (new) — list page shows planned+actual dates and derived status; new form `hx-post` + auto-filled 2601; edit form `hx-patch` (and no `hx-post` fallback), prefilled values, new fields present; edit 404.
- `tests/integration/test_plan_api.py`, `test_api.py`, `tests/conftest.py` — int numbers, actual dates to preserve status expectations.
- `tests/e2e/conftest.py` + `test_sprint_workflow.py` — factory omits number (auto-assign), create test uses auto-filled number, int-safe number matching.

**Results:** `uv run pytest -x tests/unit tests/integration` → 270 passed. `tests/e2e` → 34 passed, 5 failed — all 5 failures (epic-story links ×2, project-move, sprint assign-row, ticket-lifecycle) reproduce on the clean tree, i.e. pre-existing, not from this ticket (two previously-failing sprint e2e tests now pass). `ruff check` clean; `mypy` unchanged vs. base (pre-existing errors only). e2e Sprint workflow suite itself: 3/4 pass (4th pre-existing).

**Decisions:** kept `planned_end` (spec Plan view depends on it) alongside the ticket-mandated fields; kept `number` unique with 409 on collision; edit form keeps number readonly (identity field).
