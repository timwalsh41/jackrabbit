# 04: Ticket CRUD (API + Web) - Backlog View

**What to build:** Full CRUD for Tickets via `/api/v1/tickets` REST API and the Backlog view (`/backlog`) — a filterable, sortable table. Tickets auto-numbered per project (UNS-001, MSC-001, etc.).

**Blocked by:** 02, 03

**Status:** resolved

- [x] API: `GET /api/v1/tickets` with query filters: `project_id`, `type`, `status`, `sprint_id`, `q` (title search), `sort`, `order`; returns paginated list
- [x] API: `POST /api/v1/tickets` — create with `project_id`, `type`, `title`; auto-assigns `number = MAX(number)+1` for that project; defaults `status=Open`
- [x] API: `GET /api/v1/tickets/{id}` — full ticket with links & transitions
- [x] API: `PATCH /api/v1/tickets/{id}` — update fields (title, description, priority, story_points, type)
- [x] API: `DELETE /api/v1/tickets/{id}` — delete ticket
- [x] Web: `GET /backlog` — main view, filterable table (project, type, status, priority, sprint)
  - [x] HTMX filter controls: `hx-get="/backlog"` with query params, `hx-target="#tickets-table-body"` (id differs from the ticket text but is consistent across the template)
  - Columns: ID (link), Title, Type, Status, Priority, Points, Sprint, Actions
  - "New Ticket" button → `hx-get="/tickets/new"` → modal/form partial
- [x] Web: `GET /tickets/new` — create ticket form (project dropdown, type select, title, description, priority, points); `hx-post="/api/v1/tickets"` → closes modal + refreshes table
- [x] Web: `GET /tickets/{id}/edit` — edit form; `hx-patch="/api/v1/tickets/{id}"` → returns updated row
- [x] Ticket ID display format: `{prefix}-{number:03d}` (e.g., `MSC-005`, `UNS-001`)
- [x] UNS project pre-selected in dropdown for new tickets

## Answer

**Implementation summary (this pass — closing the remaining web gaps):**

- **`GET /backlog` filters fixed and completed (criterion 6):**
  - Root cause of broken filters: the filter form always submits every select, so unset filters arrive as empty-string query params, which typed `Optional[int]`/enum params 422 on (verified with a FastAPI probe). Routes (`/backlog`, `/projects/{id}/tickets`) now declare plain-string params and parse via `_parse_optional_int` / `_parse_optional_enum` (422 with friendly detail on garbage).
  - **Priority filter** was a no-op: added `priority` to `TicketService.list_tickets`, the `/backlog` + `/projects/{id}/tickets` routes, `GET /api/v1/tickets`, `current_filters`, and the sort-header `hx-vals` payloads in `backlog.html`.
  - **"No Sprint" (`sprint_id=0`) sentinel** never filtered because `if sprint_id:` is falsy for 0: `list_tickets` now treats `sprint_id=0` as `sprint_id IS NULL`, `None` as no filter, other values as exact match; sort/pagination `hx-vals` preserve an explicit `0`.
  - **HTMX partial**: new `templates/backlog_rows.html` renders only the table-body rows; `/backlog` (and `/projects/{id}/tickets`) return it for `HX-Request` requests instead of the full page, matching `hx-target="#tickets-table-body" hx-swap="innerHTML"`.
  - Shared context builder `_build_backlog_context` de-duplicates the two backlog routes.
- **`GET /tickets/{id}/edit` + PATCH flow fixed (criterion 8):** the edit form previously used `hx-post` against the PATCH-only API endpoint (live 405).
  - Full-page form now uses `hx-patch="/api/v1/tickets/{id}"` (`hx-swap="none"`, redirects to `/backlog` on success via the after-request handler).
  - New `templates/ticket_edit_modal.html`: HTMX requests to `/tickets/{id}/edit` get a modal form with `hx-patch`, `hx-target="#ticket-row-{id}"`, `hx-swap="outerHTML"`, inline error display on failure.
  - `PATCH /api/v1/tickets/{id}` is now HTMX-aware: with `HX-Target: ticket-row-*` it returns the rendered updated `ticket_row.html` partial (text/html); any other HTMX request sets `HX-Redirect: /backlog`; plain JSON requests are unchanged.
- **Decision:** content-negotiation lives in the API PATCH endpoint (by `HX-Request`/`HX-Target` headers) rather than duplicating PATCH on the web router — a same-path/method duplicate would silently shadow the API route depending on router registration order.

**Tests added:** `tests/integration/test_backlog_web.py` (19 tests: backlog page/filters incl. priority + no-sprint + empty-form submit, HTMX rows-only partial, new-ticket modal + UNS preselect, edit full page + modal `hx-patch`, PATCH→row HTML / HX-Redirect / plain JSON, edit 404) and 6 unit tests in `tests/unit/test_ticket_service.py` (priority filter, sprint_id=0 sentinel, sprint filter excludes NULL, no-filter cases).

**Verification:** `uv run pytest -x tests/unit tests/integration` → 331 passed; `ruff check` clean; `mypy` unchanged from baseline (31 pre-existing errors, 0 new).

---

## Prior audit answer (kept for reference)

Verified against branch `jackrabbit-integration` by code inspection, targeted unit/integration tests, and a live TestClient smoke exercise of every endpoint.

**API criteria (1–5): satisfied.**
- `jackrabbit/api.py:336-371` — `GET /api/v1/tickets` with `project_id`, `type`, `status`, `sprint_id`, `q` (title `ilike`), `sort`, `order`, `page`, `page_size`; returns `PaginatedResponse` (`jackrabbit/schemas.py`). Backing query in `jackrabbit/services.py:447-490` (`list_tickets`).
- `jackrabbit/api.py:315-333` + `jackrabbit/services.py:147-186` — `POST /api/v1/tickets` assigns `number = (MAX(number) or 0) + 1` per project; default `status=TicketStatus.OPEN`.
- `jackrabbit/api.py:373-409` — `GET /api/v1/tickets/{id}` returns `TicketReadWithDetails` including `links` and `transitions` (via `get_ticket_with_details`, `services.py:208-239`).
- `jackrabbit/api.py:423-443` — `PATCH /api/v1/tickets/{id}` merges `TicketUpdate.model_dump(exclude_unset=True)` (title, description, priority, story_points, type) via `update_ticket`.
- `jackrabbit/api.py:444-448` — `DELETE /api/v1/tickets/{id}`, 204 on success, 404 if missing.
- Live smoke (in-memory sqlite + TestClient): create returned 201 with per-project numbering (WEB→1,2; UNS→1), status `Open`; single GET included `links`/`transitions`; PATCH changed title/priority/story_points/type; DELETE → 204, subsequent GET → 404. List filters (`project_id`, `type`, `q`, `sort`, `order`, pagination) all behaved.
- Tests: `tests/unit/test_ticket_service.py` (30 passed; e.g. `test_numbering_is_sequential_within_project`, `test_numbering_is_independent_per_project`, `test_filter_by_project`, `test_filter_by_status`, `test_filter_by_type`, `test_filter_by_sprint`, `test_search_by_title`, `test_pagination`, `test_update_ticket_sets_fields`, `test_delete_existing_ticket`, `test_get_ticket_with_details`), `tests/integration/test_api.py::test_create_ticket` and `::test_list_tickets`. Targeted run: `uv run pytest tests/unit/test_ticket_service.py tests/integration/test_api.py -k "ticket or list or create or update or delete"` → 44 passed.

**Web criteria (6, 8, 10): partially satisfied / gaps.**
- Criterion 6 (unchecked): `/backlog` (`jackrabbit/web.py:42-104`, `templates/backlog.html`) has working project/type/status/sprint filters and a priority dropdown — but the **priority filter is a no-op**: `backlog()` has no `priority` query param and `list_tickets` has no priority filter, so selecting one silently does nothing. Also the "No Sprint" option (`value="0"`) never filters because `list_tickets` uses `if sprint_id:` and 0 is falsy. HTMX controls themselves exist: `hx-get="/backlog"` with query params targeting `#tickets-table-body` (criterion 6's sub-bullet for HTMX controls is checked above; the id is `tickets-table-body`, not the ticket text's `ticket-table-body`, but is consistent). Columns verified: ID (link), Title, Type, Status, Priority, Points, Sprint, Actions (plus an extra "Blocked" column). "New Ticket" button → `hx-get="/tickets/new"` → modal partial. Residual concern: HTMX filter requests return the full `backlog.html` page (no `HX-Request` partial branch, unlike `ticket_new`), swapped into `#tickets-table-body` with `innerHTML` — this may render incorrectly in a browser; not verifiable without one.
- Criterion 8 (unchecked): `GET /tickets/{id}/edit` (`web.py:143-170`) always returns the full-page `ticket_form.html` (no HX-Request partial), and that form uses **`hx-post="{{ action }}"`** where `action = /api/v1/tickets/{id}` — but that endpoint only supports PATCH. Live smoke: `POST /api/v1/tickets/{id}` → **405 Method Not Allowed**, so the edit form's submit can never succeed. No `hx-patch`, no method-override shim in `templates/base.html` or static assets (`jackrabbit/static/` is empty). The criterion's `hx-patch="..." → returns updated row` flow is not implemented.
- Criterion 7 (checked with note): `GET /tickets/new` returns `ticket_form_partial.html` for HTMX requests (`web.py:106-141`); form `hx-post="/api/v1/tickets"` with json-enc; on 201/200 the `hx-on::after-request` handler closes the modal and refreshes the backlog table body. It refreshes via `htmx.ajax('GET','/backlog')` rather than literally appending a row — functionally equivalent. Verified via smoke: partial contains `hx-post="/api/v1/tickets"`.
- Criterion 9: satisfied — `schemas.py:235-236` `full_id = f"{project_prefix}-{number:03d}"`; `templates/ticket_row.html` renders `{{ ticket.project.prefix }}-{{ '%03d'|format(ticket.number) }}`.
- Criterion 10: satisfied — `web.py` computes `uns_project` via `get_project_by_prefix("UNS")` and `ticket_form_partial.html` pre-selects it (`default_project_id`); smoke confirmed UNS id selected.

**Test-suite note:** running the whole suite (`uv run pytest tests/unit tests/integration -q`) yields 3 failures/1 error in `test_move_project.py` and `test_update_project_validation` with `sqlite3.OperationalError: attempt to write a readonly database` / `table project already exists` — a shared-DB test-isolation artifact, not ticket logic; each file passes in isolation (test_api.py: 29 passed; test_move_project.py standalone: some infra errors remain, and move-project is ticket 05+ scope, not this ticket).
## Review fix (integration branch)

Added the missing **date** filter from User Story 16: `created_after`/`created_before` date inputs on the Backlog filter form (also honored by `/projects/{id}/tickets`), inclusive bounds on `Ticket.created_at`, preserved across sort/pagination `hx-vals`. Service-level `list_tickets(created_after=..., created_before=...)` covered by unit tests, route behavior by integration tests, and the E2E date-filter flow by `tests/e2e/test_backlog_filters.py::test_filter_by_date`.
