# 06: Sprint CRUD (API + Web)

**What to build:** Full CRUD for Sprints via `/api/v1/sprints` REST API and Sprint list page. Serial numbering `2601`, `2602`... continuing past 52. Optional date fields.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] API: `GET /api/v1/sprints` (list, ordered by number desc), `POST /api/v1/sprints` (create), `GET /api/v1/sprints/{id}` (get with tickets), `PATCH /api/v1/sprints/{id}` (update), `DELETE /api/v1/sprints/{id}` (delete) <!-- VERIFIER: all 5 endpoints exist and are tested, but list is NOT ordered by number desc (services.py list_sprints has no order_by) -->
- [ ] Sprint number: auto-assign `MAX(number)+1` (starts at 2601); user can override <!-- VERIFIER: get_next_sprint_number exists and starts at 2601 (tested), and user override is inherent, but POST /sprints requires `number` (no auto-assign fallback in create_sprint); auto-fill only happens in the web form; number is str, not int -->
- [ ] Fields: `number` (int), `planned_start` (date, optional), `planned_duration_days` (int, optional), `actual_start` (date, optional), `actual_finish` (date, optional) <!-- VERIFIER: model has all (plus planned_end; actual_finish named actual_end; number is str) but API schemas (SprintCreate/Update/Read) omit planned_duration_days and actual_* -->
- [x] Web: `GET /sprints` — table of sprints with number, date range (planned/actual), ticket count, status (Planned/Active/Complete), actions <!-- VERIFIER: implemented (web.py:449, sprint_list.html, sprint_row.html); only planned dates shown — actual dates not settable via API anyway -->
- [x] Web: `GET /sprints/new` — create form (number auto-filled, date pickers); `hx-post="/api/v1/sprints"` → returns row <!-- VERIFIER: number pre-filled via /sprints/next-number; POST returns JSON (not an HTML row) and the table refreshes via HTMX JS; e2e test_create_sprint verifies the row appears -->
- [ ] Web: `GET /sprints/{id}/edit` — edit form; `hx-patch="/api/v1/sprints/{id}"` → returns updated row <!-- VERIFIER: route + form exist, but sprint_form.html hardcodes hx-post (not hx-patch) against the PATCH-only API route → 405 on submit -->
- [x] Web: Delete button with `hx-delete` + `hx-confirm` <!-- VERIFIER: sprint_row.html:50-53 -->
- [ ] Sprint status derived: no actual_start → Planned; actual_start set, no actual_finish → Active; actual_finish set → Complete <!-- VERIFIER: a Planned/Active/Complete status IS derived and tested, but from planned dates + all-tickets-Complete, NOT from actual_start/actual_finish as specified -->
## Answer

**Verified by:** verifier subagent on branch `jackrabbit-integration` @ `97f36c3`, 2026-10-15 (inspection of `jackrabbit/` code + targeted test runs).

**Evidence gathered:**
- `uv run pytest tests/unit tests/integration -q -k sprint` → **61 passed** (incl. `tests/unit/test_sprint_service.py` — 26 tests covering 2601 numbering, status derivation, CRUD, assign/unassign; `tests/integration/test_sprint_api.py` — 24 tests covering POST/GET/PATCH/DELETE, next-number, status derivation, 404/409 paths, delete cascade).
- Code inspection: `jackrabbit/api.py` (sprint routes), `jackrabbit/services.py` (`SprintService`), `jackrabbit/models.py` (`Sprint`), `jackrabbit/schemas.py`, `jackrabbit/web.py` (sprint web routes), `jackrabbit/templates/sprint_list.html`, `sprint_row.html`, `sprint_form.html`, `sprint_form_partial.html`.

**Per-criterion verdicts:**

1. **API endpoints — not-satisfied (partial).** All five endpoints exist and are tested (`api.py:124` POST, `:138` GET list, `:148` GET {id} with tickets, `:287` PATCH, `:305` DELETE; `SprintService.create/get/get_sprint_with_tickets/update/delete`). **However `SprintService.list_sprints` (services.py:637) has no `order_by`** — list is not "ordered by number desc" as specified.
2. **Auto-assign number — not-satisfied (partial).** `get_next_sprint_number` (services.py:810) returns `MAX(number)+1` starting at 2601 (unit tests `test_first_sprint_starts_at_2601`, `test_increments_after_existing_sprint`, `test_increments_from_max_not_latest`, `test_non_numeric_max_falls_back_to_2601`; integration `test_get_next_sprint_number`). But **`POST /api/v1/sprints` requires `number`** (`SprintCreate.number: str` required; `create_sprint` has no auto-assign fallback) — auto-fill only happens in the web form via `/sprints/next-number`. Also `number` is `str`, not int.
3. **Fields — not-satisfied (partial).** `Sprint` model (models.py:61) has `number` (str, not int), `planned_start`, `planned_end` (extra), `planned_duration_days`, `actual_start`, `actual_end` (ticket says `actual_finish`). **API schemas omit `planned_duration_days` and `actual_*`** (`SprintBase`/`SprintCreate`/`SprintUpdate` don't include them; `SprintRead` only reads actual_* but nothing sets them).
4. **Web list — satisfied.** `web.py:449 GET /sprints` renders `sprint_list.html` + `sprint_row.html` with number, planned date range, ticket count, derived status badge, and Edit/Delete actions. Gap: actual dates are not displayed (they aren't settable via the API either).
5. **Create form — satisfied.** `web.py:473 GET /sprints/new` renders `sprint_form.html`/`sprint_form_partial.html` with number pre-filled from `get_next_sprint_number()`, `<input type="date">` pickers, and `hx-post="/api/v1/sprints"`. Note: the API returns JSON (not a literal row); the form's `htmx:afterRequest` handler refreshes the table so the row appears — verified by e2e `tests/e2e/test_sprint_workflow.py::test_create_sprint`.
6. **Edit form — not-satisfied.** `web.py:496 GET /sprints/{id}/edit` and `sprint_form.html` exist, but the shared form hardcodes **`hx-post="{{ action }}"`**; for edit, action is `/api/v1/sprints/{id}`, a PATCH-only route → a POST submission would get 405. No `hx-patch` anywhere in templates.
7. **Delete button — satisfied.** `sprint_row.html:50-53`: `hx-delete="/api/v1/sprints/{{ sprint.id }}"` with `hx-confirm`.
8. **Status derivation — not-satisfied.** A Planned/Active/Complete status IS derived (`_derive_status`, services.py:663) and well-tested (unit `test_no_dates_is_planned`…`test_one_incomplete_ticket_keeps_derived_status`; integration `test_sprint_status_derivation_*`), **but the logic uses planned dates + "all tickets Complete", not `actual_start`/`actual_finish` as the ticket specifies.**

**Gaps / residual risks:**
- `list_sprints` unordered; number is str not int; `planned_duration_days`/`actual_*` not exposed or settable via API; edit form submits POST to a PATCH-only route (likely 405 in real use); status derivation semantics differ from spec.
- E2E tests (`tests/e2e/test_sprint_workflow.py`) require a live server + Playwright and were not executed here; the sprint-API evidence comes from unit + integration suites (61 passed).
