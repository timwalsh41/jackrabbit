# 12: Ticket Detail Page (Full)

**What to build:** Complete ticket detail view with all fields, links, transition history, and action buttons (status transitions, link management, sprint assignment, project move, edit).

**Blocked by:** 04, 05, 08, 10

**Status:** resolved

- [x] Web: `GET /tickets/{id}` — single page with sections:
  - **Header**: Ticket ID (`MSC-005`), Title, Type badge, Status badge (with transition buttons), Priority, Story Points
  - **Metadata**: Project link, Sprint link (or "Unassigned" + "Assign to Sprint" dropdown), Branch name (copy), PR URL (link), "Formerly MSC-003" if moved
  - **Description**: Markdown-rendered (HTMX safe)
  - **Groomed Fields** (collapsible): Approach, Files to Change, Test Plan, Validation Steps — editable inline if not Complete/Rejected
  - **Links**: Table of links (type, target ticket link, remove button) + "Add Link" button
  - **Transition History**: Chronological list (timestamp, from→to, reason)
  - **Actions**: Edit (→ `/tickets/{id}/edit`), Move Project, Delete (confirm)
- [x] All mutations via HTMX partials: status buttons, link add/remove, sprint assign, project move, field edits
- [x] URL-based: deep-linkable, browser back/forward works
- [x] 404 page for non-existent tickets

## Answer

Implemented by the ticket-12 agent on worktree branch `pi-subagents/impl-1-t12-0f34637-cc08-s0-t0`.

- **Route**: `GET /tickets/{id}` added in `jackrabbit/web.py` (canonical; `/ticket/{id}` kept as an alias). The route verifies the ticket exists and server-renders the shell: header (full ID `MSC-005`, title, type/status/priority/story-points meta), actions row (Edit → `/tickets/{id}/edit`, Move Project modal, Delete with `hx-confirm` → redirect to `/backlog`), and a metadata grid (project link → `/projects/{id}/tickets`, sprint partial loader, branch name with Copy button, PR URL link, "Formerly MSC-003" badge).
- **Dynamic sections via HTMX**: status badge + transition buttons + transition history render from `GET /api/v1/tickets/{id}` JSON (unchanged ticket-05 behavior); links section via `GET /tickets/{id}/links` (ticket-10); new fields partial `GET /tickets/{id}/fields` (markdown description + collapsible `<details>` Groomed Fields); new sprint partial `GET /tickets/{id}/sprint-section`.
- **Markdown (HTMX-safe)**: new dependency-free `jackrabbit/markdown.py` (`render_markdown`) — escapes all raw HTML first, then renders headings, bold/italic, inline code, fenced code blocks, links (javascript:/vbscript:/data: URLs neutralized), lists, paragraphs. Registered as a Jinja filter `markdown`; description renders through it with `| safe`.
- **Sprint assignment partial**: `GET /tickets/{id}/sprint-section` shows the sprint link (`/sprint/{id}`) + Remove, or "Unassigned" + an "Assign to Sprint…" dropdown. `POST /tickets/{id}/assign-sprint` (form `sprint_id`) and `POST /tickets/{id}/unassign-sprint` wrap `SprintService` and return the refreshed partial (outerHTML swap, no reload).
- **Inline groomed-field edits**: `GET /tickets/{id}/fields/{field}/edit` returns a textarea form partial; `PATCH /tickets/{id}/fields/{field}` (urlencoded form) validates the field against the whitelist (approach, files_to_change, test_plan, validation_steps — status changes impossible through it), enforces the Complete/Rejected freeze server-side (400), updates via `TicketService.update_ticket`, and returns the refreshed fields section. Edit affordances are hidden for Complete/Rejected tickets.
- **404 page**: new `templates/404.html`; global `HTTPException` handler in `main.py` renders it for browser (text/html Accept) requests to non-`/api/` paths — non-existent tickets get a real HTML 404 on `/tickets/{id}` and `/ticket/{id}`, while API 404s stay JSON.
- **Fixed a race in the Move Project modal** (`ticket_move_project_modal.html`): the submit-enable logic moved from an end-of-body `addEventListener` (htmx evaluates swapped scripts asynchronously → change events could fire before attachment, leaving the button permanently disabled) to an inline `onchange` on the select.
- **Tests**: `tests/unit/test_markdown.py` (17 unit tests) and `tests/integration/test_ticket_detail_web.py` (29 integration tests: page render/deep-link, HTML 404, markdown + XSS escaping, sprint assign/unassign partials, inline field edit incl. Complete/Rejected freeze and status-edit block, delete/edit/move actions, project link). Full gate: `uv run pytest tests/unit tests/integration` → 394 passed. E2E (fresh DB): 37/40 pass; the 3 failures (`test_epic_story` ×2, `test_sprint_workflow::test_assign_ticket_to_sprint`) reproduce identically on the pre-change baseline (DB-pollution/ordering flakiness in existing tests, unrelated to this ticket).

## Prior verification notes (pre-implementation, superseded above)

Verification performed on branch `jackrabbit-integration` (HEAD 97f36c3). Only criterion 3 could be checked with concrete evidence; the others have material gaps.

**Criterion 1 — `GET /tickets/{id}` detail page: NOT satisfied.**
A ticket detail page exists, but at `GET /ticket/{ticket_id}` (singular), not `/tickets/{id}` (`jackrabbit/web.py:244-248`). It is a server-rendered shell (`jackrabbit/templates/ticket_detail.html`) whose content is fetched client-side via `hx-get="/api/v1/tickets/{{ ticket_id }}"` and rendered by inline JavaScript. Section status:
- Present: header with full ID (`MSC-005` format), title, type, status badge, transition buttons (`renderTransitionButtons`, incl. modals for Groomed/In Progress/Ready for Review), priority, story points, branch name with Copy button, PR URL link with git-host detection, "Formerly {original_id}" badge, transition history (from→to, reason, timestamp), links section (delegated to `GET /tickets/{id}/links`), Edit (`/tickets/{id}/edit`) and Move Project actions.
- Missing/deviating: **Project is plain text** (`${ticket.project_prefix} (ID: ...)`), not a link; **no Sprint link and no "Assign to Sprint" dropdown** (just `#${sprint_id}` or `—`); **description/groomed fields are NOT markdown-rendered** (plain `whitespace-pre-wrap` text; no markdown library anywhere in `jackrabbit/`) and are injected via `innerHTML` (XSS-unsafe, contrary to "HTMX safe"); groomed fields are **not collapsible** and **not editable inline** on the detail page (they are editable only through the `→ Groomed` transition modal, `ticket_transition_groomed_modal.html`); **no Delete action** (delete exists only as API `DELETE /tickets/{ticket_id}`, `api.py:444`; no Delete button in the detail template).

**Criterion 2 — all mutations via HTMX partials: NOT fully satisfied.**
HTMX-driven: status transitions (`hx-post /api/v1/tickets/{id}/transition` + transition modals), link add (modal → `hx-post .../links`) and remove (`ticket_link_row.html:74`, `hx-delete` with `hx-confirm`), project move (`ticket_move_project_modal.html:26`, `hx-post .../move-project`). Missing: **sprint assign is not available anywhere on the detail page**, and **field edits are not inline HTMX edits** (only via the Groomed transition modal or the separate edit page).

**Criterion 3 — URL-based deep-linkable: SATISFIED (with path caveat).**
`GET /ticket/{id}` (`web.py:244-248`) renders the full page shell; content loads on page load (`hx-trigger="load"`, `ticket_detail.html:15-18`), so a direct URL/deep link, browser back and forward all render the complete ticket. E2E tests navigate directly to this URL (`tests/e2e/test_epic_story.py:74`, `test_project_move.py:23`, `test_ticket_lifecycle.py:47`, `test_reject_restore.py:23`). Caveat: the URL is `/ticket/{id}`, not `/tickets/{id}` as specified.

**Criterion 4 — 404 page for non-existent tickets: NOT satisfied.**
`GET /ticket/{ticket_id}` does not check ticket existence — it always renders the shell, which then receives a JSON 404 from `GET /api/v1/tickets/{id}` and stays on "Loading ticket details...". There is no 404 template and no exception handler (`grep exception_handler|404.html` over `main.py`/`web.py`/templates: no hits); web sub-routes (links, move-project, transitions) raise plain `HTTPException(404)` which FastAPI renders as default JSON, not an HTML 404 page.

**Tests run** (`uv run pytest tests/unit tests/integration -q`):
- `tests/unit/test_transitions.py` — 53 passed
- `tests/unit/test_move_project.py` — 12 passed
- `tests/unit/test_links.py` — 36 passed
- Full-suite combined runs are flaky in this environment: `sqlite3.OperationalError: disk I/O error` intermittently on the session-scoped in-memory `StaticPool` engine (`tests/conftest.py:41-48`) when multiple files run together (e.g. 3-6 failures in `-k "links or move_project or transition"` batches); each affected file passes in isolation. Test-infra flakiness, not a product failure, but it means combined-suite green runs cannot be attested here.

**Bottom line:** the detail page skeleton, links, transitions, and project-move flows are implemented and partially test-covered, but the ticket as specified is not complete: wrong route path, no sprint assignment on the page, no markdown rendering, no collapsible/inline groomed-field editing, no Delete action, no project link, and no HTML 404 handling.

## Review fix (integration branch)

Security fix in `jackrabbit/markdown.py::_stash_url`: link URLs are now entity-escaped (`html.escape(url, quote=True)`) before interpolation into `href`, closing an XSS where a `"` in a link URL broke out of the attribute (e.g. `[click](x"onmouseover=...)`). Regression tests in `tests/unit/test_markdown.py`.
