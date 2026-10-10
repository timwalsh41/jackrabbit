# 04: Ticket CRUD (API + Web) - Backlog View

**What to build:** Full CRUD for Tickets via `/api/v1/tickets` REST API and the Backlog view (`/backlog`) — a filterable, sortable table. Tickets auto-numbered per project (UNS-001, MSC-001, etc.).

**Blocked by:** 02, 03

**Status:** ready-for-agent

- [ ] API: `GET /api/v1/tickets` with query filters: `project_id`, `type`, `status`, `sprint_id`, `q` (title search), `sort`, `order`; returns paginated list
- [ ] API: `POST /api/v1/tickets` — create with `project_id`, `type`, `title`; auto-assigns `number = MAX(number)+1` for that project; defaults `status=Open`
- [ ] API: `GET /api/v1/tickets/{id}` — full ticket with links & transitions
- [ ] API: `PATCH /api/v1/tickets/{id}` — update fields (title, description, priority, story_points, type)
- [ ] API: `DELETE /api/v1/tickets/{id}` — delete ticket
- [ ] Web: `GET /backlog` — main view, filterable table (project, type, status, priority, sprint)
  - HTMX filter controls: `hx-get="/backlog"` with query params, `hx-target="#ticket-table-body"`
  - Columns: ID (link), Title, Type, Status, Priority, Points, Sprint, Actions
  - "New Ticket" button → `hx-get="/tickets/new"` → modal/form partial
- [ ] Web: `GET /tickets/new` — create ticket form (project dropdown, type select, title, description, priority, points); `hx-post="/api/v1/tickets"` → returns row + closes modal
- [ ] Web: `GET /tickets/{id}/edit` — edit form; `hx-patch="/api/v1/tickets/{id}"` → returns updated row
- [ ] Ticket ID display format: `{prefix}-{number:03d}` (e.g., `MSC-005`, `UNS-001`)
- [ ] UNS project pre-selected in dropdown for new tickets