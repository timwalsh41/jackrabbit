# 11: Plan View (Calendar/Roadmap)

**What to build:** `/plan` page showing all sprints with date ranges, ticket counts, color-coded by status — a roadmap/calendar view.

**Blocked by:** 06, 04

**Status:** resolved

- [ ] API: `GET /api/v1/plan` — returns all sprints with nested ticket counts by status
  - Response: `[{sprint: {...}, counts: {Open: 3, Groomed: 2, "In Progress": 1, ...}, date_range: {planned_start, planned_end, actual_start, actual_finish}}]`
- [ ] Web: `GET /plan` — vertical timeline/calendar:
  - Each sprint as a horizontal bar spanning planned_start → planned_end (or "unscheduled")
  - Color coding: Planned=gray, Active=blue, Complete=green
  - Badge: sprint number, ticket count, status summary
  - Click sprint → navigate to `/sprints/{id}`
  - Future sprints (no actual_start) shown below current
  - Unsprinted tickets noted at top/bottom
- [ ] HTMX: filter by project (dropdown) → `hx-get="/plan?project_id=..."`
- [ ] Empty state: "No sprints created" with link to `/sprints/new`
- [ ] Responsive: horizontal scroll on narrow viewports