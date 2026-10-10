# 06: Sprint CRUD (API + Web)

**What to build:** Full CRUD for Sprints via `/api/v1/sprints` REST API and Sprint list page. Serial numbering `2601`, `2602`... continuing past 52. Optional date fields.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] API: `GET /api/v1/sprints` (list, ordered by number desc), `POST /api/v1/sprints` (create), `GET /api/v1/sprints/{id}` (get with tickets), `PATCH /api/v1/sprints/{id}` (update), `DELETE /api/v1/sprints/{id}` (delete)
- [ ] Sprint number: auto-assign `MAX(number)+1` (starts at 2601); user can override
- [ ] Fields: `number` (int), `planned_start` (date, optional), `planned_duration_days` (int, optional), `actual_start` (date, optional), `actual_finish` (date, optional)
- [ ] Web: `GET /sprints` — table of sprints with number, date range (planned/actual), ticket count, status (Planned/Active/Complete), actions
- [ ] Web: `GET /sprints/new` — create form (number auto-filled, date pickers); `hx-post="/api/v1/sprints"` → returns row
- [ ] Web: `GET /sprints/{id}/edit` — edit form; `hx-patch="/api/v1/sprints/{id}"` → returns updated row
- [ ] Web: Delete button with `hx-delete` + `hx-confirm`
- [ ] Sprint status derived: no actual_start → Planned; actual_start set, no actual_finish → Active; actual_finish set → Complete