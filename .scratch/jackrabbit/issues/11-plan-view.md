# 11: Plan View (Calendar/Roadmap)

**What to build:** `/plan` page showing all sprints with date ranges, ticket counts, color-coded by status — a roadmap/calendar view.

**Blocked by:** 06, 04

**Status:** ready-for-agent

- [x] API: `GET /api/v1/plan` — returns all sprints with nested ticket counts by status
  - Response: `[{sprint: {...}, counts: {Open: 3, Groomed: 2, "In Progress": 1, ...}, date_range: {planned_start, planned_end, actual_start, actual_finish}}]`
- [x] Web: `GET /plan` — vertical timeline/calendar:
  - Each sprint as a horizontal bar spanning planned_start → planned_end (or "unscheduled")
  - Color coding: Planned=gray, Active=blue, Complete=green
  - Badge: sprint number, ticket count, status summary
  - Click sprint → navigate to `/sprints/{id}`
  - Future sprints (no actual_start) shown below current
  - Unsprinted tickets noted at top/bottom
- [x] HTMX: filter by project (dropdown) → `hx-get="/plan?project_id=..."`
- [x] Empty state: "No sprints created" with link to `/sprints/new`
- [ ] Responsive: horizontal scroll on narrow viewports

## Answer

Verified against branch `jackrabbit-integration` on 2026 checkout.

**Criterion 1 (API `GET /api/v1/plan`) — satisfied.**
- Route: `jackrabbit/api.py:205-249` (`get_plan`, `response_model=PlanResponse`); data from `SprintService.get_plan_data` (`jackrabbit/services.py:822-932`), which counts tickets per `TicketStatus` per sprint, derives sprint status, and computes `unsprinted_count`.
- Schema: `PlanResponse` / `PlanSprintResponse` / `PlanSprintTicketCounts` in `jackrabbit/schemas.py:~300-338`, including `planned_start`, `planned_end`, `actual_start`, `actual_end`, per-status counts, `total_tickets`, `status`.
- Shape note: response is `{sprints: [...], unsprinted_count}` rather than the ticket sketch `[{sprint, counts, date_range}]`; all required fields (dates, counts by status) are present per sprint, so substance matches.
- Evidence: `tests/integration/test_plan_api.py::test_get_plan_empty`, `test_get_plan_with_sprints` (asserts ordering, status derivation, per-status counts, unsprinted_count), `test_get_plan_with_project_filter`, `test_get_plan_sprint_without_dates`. All pass.

**Criterion 2 (Web `GET /plan` vertical timeline) — satisfied.**
- Route: `jackrabbit/web.py:224-241` renders `jackrabbit/templates/plan.html`.
- Each sprint renders as a horizontal bar positioned by computed `left_pct`/`width_pct` (timeline spanning planned_start → planned_end; min-width fallback for start-only); unscheduled sprints (no dates) show no bar; today marker included.
- Color coding in `plan.html`: `Complete` → `bg-green-500`, `Active` → `bg-blue-500`, else (Planned) → `bg-gray-400`.
- Badges: sprint `number`, `total_tickets`, per-status summary badges, status badge.
- Click navigates to `/sprints/{{ sprint.id }}/detail` (anchor wrapping each card).
- Future sprints appear below current/past: sprints ordered by `planned_start` asc with nulls last (`services.py` query; asserted in `test_get_plan_with_sprints`).
- Unsprinted tickets noted (bottom of page, amber callout + backlog link).
- Evidence: `test_plan_web_page`, `test_plan_web_page_with_sprints`, `test_plan_web_page_unsprinted_tickets` — all pass.

**Criterion 3 (HTMX project filter) — satisfied.**
- `plan.html` lines ~10-22: `<form hx-get="/plan" hx-target="#plan-content" hx-swap="innerHTML" hx-push-url="true">` wrapping `<select name="project_id" hx-trigger="change">`; server accepts `project_id` query param (`web.py:228`), dropdown selection persisted via `selected_project_id`.
- Evidence: `test_plan_web_page_project_filter` passes.

**Criterion 4 (Empty state) — satisfied.**
- `plan.html`: "No sprints yet" panel with "Create Sprint" link to `/sprints/new` (wording differs slightly from ticket's "No sprints created").
- Evidence: `test_plan_web_page` asserts `"No sprints yet"` and `"Create Sprint"` present — passes.

**Criterion 5 (Responsive: horizontal scroll on narrow viewports) — NOT verified / not satisfied.**
- No `overflow-x-auto` (or any horizontal-scroll container) found in `plan.html`, other templates, or static assets. The timeline is a stacked vertical list with `flex-col sm:flex-row` and percentage-positioned bars, which avoids horizontal overflow rather than providing a horizontal scroll region as specified. No dedicated responsive test exists.

**Test run:** `uv run pytest tests/integration/test_plan_api.py tests/unit/test_sprint_service.py -q` → 40 passed.

**Gaps:** only the horizontal-scroll criterion is unmet; API response shape deviates cosmetically from the ticket sketch (flat list + `unsprinted_count` instead of nested `date_range` entries) but contains all specified data fields.
**Status:** unchanged (`resolved`).