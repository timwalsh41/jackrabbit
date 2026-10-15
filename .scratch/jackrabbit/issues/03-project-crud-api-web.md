# 03: Project CRUD (API + Web)

**What to build:** Full CRUD for Projects via `/api/v1/projects` REST API and SSR web pages. UNS project protected from deletion. Project list page, create form, edit form.

**Blocked by:** 02

**Status:** ready-for-agent

- [x] API: `GET /api/v1/projects` (list), `POST /api/v1/projects` (create), `GET /api/v1/projects/{id}` (get), `PATCH /api/v1/projects/{id}` (update), `DELETE /api/v1/projects/{id}` (delete)
- [x] Validation: prefix unique, 2-10 chars uppercase; name required; color hex format
- [x] `DELETE /api/v1/projects/{id}` returns 403 if `is_system=true` (protects UNS)
- [x] Web: `GET /projects` — table of projects with prefix, name, color badge, ticket count, actions
- [x] Web: `GET /projects/new` — create form (HTMX `hx-post` → returns row partial)
- [x] Web: `GET /projects/{id}/edit` — edit form (HTMX `hx-patch` → returns row partial)
- [x] Web: Delete button with `hx-delete` + `hx-confirm` (disabled for UNS)
- [x] Base template `base.html` with HTMX loaded, navigation bar (Backlog, Sprints, Plan, Projects)
- [x] All templates use glossary vocabulary: "Project", "Ticket", "Sprint"

**Status:** resolved

## Answer

**Verification of ticket 03 on branch `jackrabbit-integration` (commit 97f36c3).**

### Verified as satisfied

1. **API CRUD endpoints — SATISFIED.** All five routes exist in `jackrabbit/api.py`: `POST /projects` (line 68, 201), `GET /projects` (line 81), `GET /projects/{id}` (line 86, 404 if missing), `PATCH /projects/{id}` (line 94, 404 if missing), `DELETE /projects/{id}` (line 111, 204/404/403). Covered by `tests/integration/test_api.py` (test_list_projects, test_get_project 200/404, test_delete_project, plus create/update flows). Full `tests/integration/test_api.py` run: **17 passed**.
2. **DELETE returns 403 for is_system — SATISFIED.** `services.py:615-616` raises `ValueError` for system projects; `api.py:111-120` maps it to HTTP 403. Test `test_delete_system_project_forbidden` (asserts 403 on UNS project id 1) passes.
3. **Web project list — SATISFIED.** `web.py:338-353` renders `project_list.html` with ticket counts (`ProjectService.get_project_ticket_count`). Template shows prefix, name/description, color badge, ticket count, system flag, Edit/View/Delete actions. Live check: `GET /projects` → 200 (ad-hoc TestClient run).
4. **Delete button — SATISFIED.** `project_list.html:86-91`: `hx-delete="/api/v1/projects/{{ project.id }}"` with `hx-confirm`; for `is_system` projects the button is replaced by a disabled-looking gray span (no hx-delete).
5. **Glossary vocabulary — SATISFIED.** Templates consistently use "Project(s)", "Ticket(s)", "Sprint" per `GLOSSARY.md`; no off-vocabulary domain terms found (grep for "tasks/stories/work item" only hits type wording "Stories/Bugs/Spikes" in `ticket_links_section.html`, which matches ticket types).

### Not verified as satisfied (left unchecked)

- **Validation criterion — PARTIAL.** Prefix format (2-10 uppercase alpha, `schemas.py:39-49`), name required (`schemas.py:51-56`), and hex color (`schemas.py:59-69`, `95-106`) are validated with 422 responses — all covered by passing tests (`test_create_project_validation_prefix/name/color`, `test_update_project_validation`). **BUT** prefix uniqueness is only a DB constraint (`models.py:50` `Field(unique=True)`): a duplicate `POST /api/v1/projects` with an existing prefix surfaces as an unhandled `IntegrityError` → **HTTP 500**, not a 4xx validation error (confirmed in an ad-hoc TestClient run). No API-level uniqueness check exists in `ProjectService.create_project` or `ProjectCreate`.
- **Create form row partial — NOT SATISFIED.** `GET /projects/new` (web.py:356) and the form exist (`project_form.html` with `hx-post`), but `hx-target="#project-form"` swaps the form itself, and the POST target `/api/v1/projects` returns a JSON `ProjectRead` body (201), not a row partial. No `project_row.html` partial exists. The "returns row partial" behavior is absent.
- **Edit form hx-patch — NOT SATISFIED.** `GET /projects/{id}/edit` exists (web.py:432) and renders the form with `action="/api/v1/projects/{id}"`, but the form uses `hx-post` (not `hx-patch`); `POST /api/v1/projects/{id}` returns **405 Method Not Allowed** (confirmed live). No `hx-patch` attribute exists anywhere in templates. So submitting the edit form fails.
- **base.html nav — PARTIAL.** `base.html` loads HTMX 1.9.10 (+json-enc ext) and has a nav bar with **Backlog, Plan, Projects** — but the **Sprints** link required by this criterion is missing (there is a `GET /sprints` page at `web.py:449`).

### Test runs

- `uv run pytest tests/unit tests/integration -q -k "not move_project"` → **244 passed, 12 deselected**. (3 failures/errors in `tests/unit/test_move_project.py::TestMoveProjectAPI` are in the move-project ticket-API feature, out of scope for ticket 03.)
- `uv run pytest tests/integration/test_api.py -q` → **17 passed**.

### Residual risks / gaps

1. Duplicate project prefix → HTTP 500 (IntegrityError) instead of 4xx with a helpful message.
2. Edit project form is broken end-to-end (hx-post → 405); users cannot save project edits from the web UI.
3. Neither create nor edit HTMX form returns a row partial; after successful create the raw JSON replaces the form DOM.
4. Nav lacks Sprints link.
5. Unrelated: 3 failing tests in `test_move_project.py` (belongs to a different ticket).

---

### Implementation (this run) — gaps closed

1. **Prefix uniqueness** — `ProjectService.create_project` now checks for an existing
   (case-insensitive, uppercase-normalized) prefix and raises `ValueError`; the API
   endpoint maps it to **409 Conflict** (previously an unhandled IntegrityError → 500).
   Tests: `tests/unit/test_project_service.py` (dup, case-insensitive dup, system-prefix dup),
   `tests/integration/test_api.py::test_create_project_duplicate_prefix_conflict` (+case-insensitive).
2. **Create form (`GET /projects/new`)** — full page form (and bare form partial for
   `HX-Request`) posts via `hx-post="/projects"` to a new web route `POST /projects`
   (form-encoded, validated through `ProjectCreate`). Success returns the new
   `project_row.html` row partial (with `HX-Redirect: /projects`); validation/duplicate
   errors re-render the form partial with an inline error message.
3. **Edit form (`GET /projects/{id}/edit`)** — full page form uses
   `hx-patch="/projects/{id}"` (previously `hx-post` to the API → 405). `HX-Request`
   returns `project_edit_row.html` (inline row-level form, cancel via `GET /projects/{id}/row`).
   New web route `PATCH /projects/{id}` validates via `ProjectUpdate` and returns the
   updated row partial (inline swaps in place; full page sets `HX-Redirect: /projects`).
4. **base.html** — nav now includes **Sprints** (`/sprints`) alongside Backlog, Plan, Projects; HTMX 1.9.10 already loaded.
5. **Templates** — new `project_row.html` (row partial, used by list, create, edit,
   cancel endpoints), `project_form_partial.html`, `project_edit_row.html`; list table
   de-duplicated to 5 columns (Prefix, Name, Color, Tickets, Actions). Glossary
   vocabulary maintained.
6. Added `python-multipart` dependency (required by FastAPI `Form` handling).

### Tests (this run)
- `tests/unit/test_project_service.py` — 8 unit tests (uniqueness, update, delete guard).
- `tests/integration/test_project_web.py` — 14 integration tests covering all web criteria.
- `tests/integration/test_api.py` — +2 duplicate-prefix 409 tests.
- Full gate: `uv run pytest -x tests/unit tests/integration` → **279 passed**; ruff clean on touched files.

### Remaining notes
- E2E (Playwright) coverage for project CRUD was not added: project flows are not in the spec's E2E flow list (spec lists ticket lifecycle, sprint workflow, project move, epic links, filters). Integration TestClient tests cover the web routes end-to-end at HTTP level.
- The pre-existing `sys.path.insert(0, "/workspace/projects/jackrabbit")` in `tests/integration/conftest.py` is dead weight under the editable install (verified the worktree package is imported) but was left untouched as shared test infrastructure.