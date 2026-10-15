# 04: Ticket CRUD (API + Web) - Backlog View

**What to build:** Full CRUD for Tickets via `/api/v1/tickets` REST API and the Backlog view (`/backlog`) — a filterable, sortable table. Tickets auto-numbered per project (UNS-001, MSC-001, etc.).

**Blocked by:** 02, 03

**Status:** ready-for-agent

- [x] API: `GET /api/v1/tickets` with query filters: `project_id`, `type`, `status`, `sprint_id`, `q` (title search), `sort`, `order`; returns paginated list
- [x] API: `POST /api/v1/tickets` — create with `project_id`, `type`, `title`; auto-assigns `number = MAX(number)+1` for that project; defaults `status=Open`
- [x] API: `GET /api/v1/tickets/{id}` — full ticket with links & transitions
- [x] API: `PATCH /api/v1/tickets/{id}` — update fields (title, description, priority, story_points, type)
- [x] API: `DELETE /api/v1/tickets/{id}` — delete ticket
- [ ] Web: `GET /backlog` — main view, filterable table (project, type, status, priority, sprint)
  - [x] HTMX filter controls: `hx-get="/backlog"` with query params, `hx-target="#tickets-table-body"` (id differs from the ticket text but is consistent across the template)
  - Columns: ID (link), Title, Type, Status, Priority, Points, Sprint, Actions
  - "New Ticket" button → `hx-get="/tickets/new"` → modal/form partial
- [x] Web: `GET /tickets/new` — create ticket form (project dropdown, type select, title, description, priority, points); `hx-post="/api/v1/tickets"` → closes modal + refreshes table
- [ ] Web: `GET /tickets/{id}/edit` — edit form; `hx-patch="/api/v1/tickets/{id}"` → returns updated row
- [x] Ticket ID display format: `{prefix}-{number:03d}` (e.g., `MSC-005`, `UNS-001`)
- [x] UNS project pre-selected in dropdown for new tickets

## Answer

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