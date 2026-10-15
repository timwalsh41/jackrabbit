# Jackrabbit — AI Coding Task Manager

## Problem Statement

Developers using AI coding agents (like pi, Cursor, Claude Code) need a lightweight, local-first project management tool to track tickets, sprints, and epics for AI-assisted work. Existing tools (Jira, Linear, GitHub Projects) are heavyweight, cloud-dependent, and not designed for the fast iteration cycles of AI coding. We need a tool that:
- Runs locally with zero external dependencies
- Stores data in a single file for trivial backup
- Provides a web UI for visualizing backlog, sprints, and plans
- Integrates with git workflows (branch naming, PR tracking)
- Is scriptable and deployable via a single command

## Solution

A local-first project management web application built with **Python + FastAPI + HTMX**, using **SQLite** for storage. The backend exposes a **versioned JSON API (`/api/v1/`)** from day one; the frontend is **server-rendered HTML with HTMX** for reactivity (no build step, no Node.js). Designed for **single-user** operation with no authentication. Deployable via `uv run server.py` with configuration through `.env` + CLI args.

Core domain: **Projects** (prefixes like `MSC`, `WEB`, `UNS`), **Tickets** (Epic/Story/Bug/Spike with status lifecycle), **Sprints** (serial numbered `2601`, `2602`...), **Links** (parent/child, blocks/blocked_by, relates_to). Ticket status transitions are **guarded forward** (require criteria), **free backward**, with **restore from Rejected**.

## User Stories

1. As a developer, I want to create a ticket with a project prefix and auto-assigned number (e.g., `MSC-001`), so that I can track work without manual numbering.
2. As a developer, I want to set ticket type (Epic, Story, Bug, Spike), so that I can categorize work.
3. As a developer, I want to move a ticket through statuses (Open → Groomed → In Progress → Ready for Review → Complete), so that I can track progress.
4. As a developer, I want to be blocked from advancing to Groomed until I fill in approach, files_to_change, test_plan, and validation_steps, so that "Groomed" means ready to implement.
5. As a developer, I want to be blocked from advancing to In Progress until a git branch exists (named `{project}-{number}-{slug}`), so that status reflects reality.
6. As a developer, I want to be blocked from advancing to Ready for Review until a PR URL is provided, so that review status is meaningful.
7. As a developer, I want to move a ticket backward in status freely (e.g., Review → In Progress when issues found), so that I can correct course.
8. As a developer, I want to reject a ticket and later restore it to any prior valid state, so that rejected work isn't lost.
9. As a developer, I want to create a Project with a prefix (e.g., `WEB`), name, description, and color, so that I can organize tickets.
10. As a developer, I want to move a ticket between projects and have it renumbered to the next available serial in the target project, so that project numbers stay dense.
11. As a developer, I want an `UNS` (Unsorted) project that exists by default and cannot be deleted, so that new tickets always have a home.
12. As a developer, I want to create Sprints with serial numbers (`2601`, `2602`... continuing past 52), so that I can plan work in cohorts.
13. As a developer, I want to assign a ticket to at most one sprint, so that sprint membership is exclusive.
14. As a developer, I want to track planned/actual start and finish dates on sprints (all optional), so that I can see schedule vs reality.
15. As a developer, I want to link tickets as parent/child (Epic→Story), blocks/blocked_by (dependencies), or relates_to (association), so that I can express relationships.
16. As a developer, I want a Backlog view filterable by project, type, status, and date, so that I can find tickets quickly.
17. As a developer, I want a Sprint view showing status of all tickets in the current sprint, so that I can track sprint progress.
18. As a developer, I want a Plan view listing sprints with calendar duration and ticket counts, so that I can see the roadmap.
19. As a developer, I want to see ticket detail with all fields, links, history, and action buttons, so that I can manage a ticket fully.
20. As a developer, I want to configure the server port and data directory via `.env` or CLI args, so that I can run multiple instances.
21. As a developer, I want the database to be a single SQLite file in the data directory, so that backup is `cp data.db backup.db`.
22. As a developer, I want schema migrations managed by Alembic, so that deployed instances can upgrade safely.
23. As a developer, I want the API versioned at `/api/v1/` from day one, so that future SPA migration doesn't require backend rewrite.
24. As a developer, I want unit tests (pytest), integration tests (httpx test client), and E2E tests (Playwright + chrome-devtools-axi), so that agents can verify their own work.

## Implementation Decisions

### Decisions so far (from implemented tickets)
- **Ticket 04 (Ticket CRUD/Backlog)**: Backlog filter routes declare plain-string query params and parse via `_parse_optional_int`/`_parse_optional_enum` (HTMX forms submit empty selects as `""`, which typed Optional params 422 on). `sprint_id=0` is the "No Sprint" sentinel (`sprint_id IS NULL`); `sprint_id=None` = no filter. HTMX (`HX-Request`) filter/sort/pagination requests get a rows-only partial (`backlog_rows.html`) targeting `#tickets-table-body`. The edit flow content-negotiates inside `PATCH /api/v1/tickets/{id}`: `HX-Target: ticket-row-*` returns the rendered `ticket_row.html` partial (modal outerHTML swap), other HTMX requests get `HX-Redirect: /backlog`, plain requests stay JSON — no duplicate web-router PATCH (would silently shadow the API route).
- **Ticket 05 (Ticket Status Transitions)**: Guard-failure errors are surfaced in the UI by a global `htmx:responseError` handler on the ticket detail page (parses FastAPI `detail`, string or 422 validation array) rendering into `#transition-error` (page banner) or `#modal-error` (inside guarded-transition modals). Non-modal transition buttons (e.g. Ready for Review → Complete, Rejected restore) must post JSON like the modals: `hx-ext="json-enc"` + `Content-Type: application/json` header — plain `hx-vals` posts urlencoded and 422s against the Pydantic body. Ready for Review → Complete guard is a documented manual confirmation (no programmatic check, no spike-report flag in the model).
- **Ticket 07 (Sprint assignment)**: `GET /api/v1/sprints/{id}` returns both the flat `tickets` list (backward compat for web sprint-list view) AND `tickets_by_status` — a dict keyed by all six ticket statuses (Open, Groomed, In Progress, Ready for Review, Complete, Rejected) with every key always present (empty list when no tickets in that bucket). The grouping is computed in `SprintService.get_sprint_with_tickets` so both API and web views share one source of truth; the separate `/by-status` endpoint is kept.
- **Ticket 06 (Sprint CRUD)**: `Sprint.number` is an `int` (auto-assigned `MAX(number)+1`, starting at `2601`; clients may override, duplicates → 409). Sprint status is derived **only from actual dates**: `actual_finish` set → Complete, `actual_start` set → Active, otherwise Planned (ticket statuses do not drive sprint status). `actual_end` renamed `actual_finish` per glossary/ticket. `planned_end` kept alongside `planned_duration_days` (Plan view depends on it). Sprint schemas tolerate empty-string form fields (`""` → None) since HTMX `json-enc` submits untouched optional inputs as `""`. Sprint list page shows planned AND actual date ranges.
- **Ticket 14 (Unit & Integration tests)**: The shared test engine (`tests/conftest.py::test_engine`) is module-scoped and creates a fresh SQLite file under pytest `tmp_path_factory` per test module, with the schema applied via Alembic migrations (the schema source of truth — matches production `init_db()`), not `create_all`; per-test isolation comes from `test_db` drop/create. Integration tests live in ticket-named files (`test_projects_api.py`, `test_tickets_api.py`, `test_sprints_api.py`, `test_links_api.py`, `test_migrations.py`) with a migrations round-trip test (`upgrade head → downgrade -1 → upgrade head`). No test writes to `./data/` (temp files only). Coverage: services 95%, api 94%.
- **Ticket 09 (Project move/renumber)**: `POST /api/v1/tickets/{id}/move-project` accepts both JSON and urlencoded/multipart bodies (htmx form compatibility) and both `project_id` / `target_project_id` field names. Renumbering is `MAX(number)+1` in the target project, guarded by `uq_ticket_project_number` (`UNIQUE(project_id, number)` — now declared on the `Ticket` SQLModel too, matching migration 0001); on `IntegrityError` from a concurrent writer, the move retries (≤5 attempts) with a fresh MAX read. The ticket-detail modal posts urlencoded form data and, on success, closes itself and re-fetches the ticket JSON into `#ticket-content` (client-side re-render shows the new ID + "Formerly {original_id}" badge) — no HTML partial variant of the move endpoint was added.
- **Ticket 12 (Ticket Detail Page)**: `GET /tickets/{id}` is the canonical detail route (`/ticket/{id}` kept as alias; both registered AFTER `/tickets/new` and `/tickets/search` so literal paths win). The page is a hybrid: server-rendered shell (header with zero-padded full ID, Edit/Move Project/Delete-with-confirm actions, project link, sprint/branch/PR metadata) + HTMX-loaded sections — ticket JSON card (status badge, transition buttons/history), links partial, a new fields partial (`GET /tickets/{id}/fields`: markdown description + collapsible `<details>` groomed fields), and a new sprint partial (`GET /tickets/{id}/sprint-section`; assign/unassign POST back to web routes returning the refreshed partial — the JSON sprint endpoints are not driven by HTMX directly). Markdown is rendered SERVER-side by dependency-free `jackrabbit/markdown.py` (`render_markdown`: escape-all-HTML-first, then headings/bold/italic/code/links/lists; dangerous URL schemes neutralized), registered as a Jinja filter — no CDN markdown lib, no XSS surface. Inline groomed-field editing uses `GET/PATCH /tickets/{id}/fields/{field}` (whitelist: approach, files_to_change, test_plan, validation_steps; server-side 400 freeze for Complete/Rejected; status edits impossible through the whitelist). Non-existent tickets render a real HTML 404 (`templates/404.html`) via a global `HTTPException` handler in `main.py` that only fires for non-`/api/` paths with an HTML Accept header — API 404s stay JSON. Also fixed a swap-script race in the Move Project modal (submit-enable moved to inline `onchange`).
- **E2E flake fix (post-ticket-15)**: The intermittent `test_link_stories_to_epic` failure was root-caused to a htmx 1.9.10 initialization race, not a server/app bug: htmx swaps the link modal into the DOM before it initializes it (processNode runs in the settle task after the default 20ms settle delay). If the test's `select_option`+`fill` complete within that window, `initNode` seeds `lastValue = elt.value` from the pre-filled search input, so the dispatched `keyup` fails the `changed` check and the search request is never issued. In real usage the input is always empty at init (users cannot type within 20ms), so the fix is test-side determinism: the test now waits until the modal's `htmx-added` class is removed (guaranteeing processNode ran and the keyup listener is attached) before interacting. No template/htmx-trigger change (dropping `changed` would degrade UX with duplicate searches on non-modifying keyups).

### Architecture
- **Backend**: FastAPI application with SQLModel (SQLAlchemy) models
- **Database**: SQLite with WAL mode, single file at `{DATA_DIR}/jackrabbit.db`
- **Migrations**: Alembic, run `upgrade head` on startup
- **API**: Versioned at `/api/v1/` with OpenAPI spec at `/api/v1/openapi.json`
- **Frontend**: Jinja2 templates rendered by FastAPI, HTMX for partial updates
- **Config**: `.env` file + CLI arg overrides (PORT, DATA_DIR, DATABASE_URL, LOG_LEVEL, ENVIRONMENT)
- **Single-user**: No auth, no User table, no sessions

### Modules (Seams)
1. **`config`** — Settings loading from `.env` + CLI, validation, defaults
2. **`database`** — SQLite engine, session management, Alembic runner
3. **`models`** — SQLModel definitions: Project, Ticket, Sprint, TicketLink, TicketTransition
4. **`services`** — Business logic: ticket CRUD, status transitions (with guards), sprint assignment, project move, link management, branch/PR tracking
5. **`api`** — FastAPI routers under `/api/v1/` for tickets, projects, sprints, links, transitions
6. **`web`** — Jinja2 templates + HTMX endpoints for Backlog, Sprint, Plan, Ticket Detail views
7. **`cli`** — Typer app for `server` command with config overrides

### Key Technical Decisions (from ADRs)
- **ADR-0001**: SQLite — single file, ACID, SQL queries, Alembic migrations
- **ADR-0002**: Python + FastAPI — matches `uv`, OpenAPI auto-gen, SQLModel, async
- **ADR-0003**: SSR + HTMX — single process, no build, server-owned state, API-first
- **ADR-0004**: Single-user, no auth — zero auth complexity, local-first
- **ADR-0005**: Project move → next available number in target; store `original_id` for traceability
- **ADR-0006**: Sprint numbering — continuous serial `2601`, `2602`... (not week-bound)
- **ADR-0007**: Epic = flat type; hierarchy via `parent`/`child` links (not FK)
- **ADR-0008**: Groomed requires 4 structured fields: approach, files_to_change, test_plan, validation_steps
- **ADR-0009**: State machine — guarded forward, free backward, restore from Rejected with guard re-check
- **ADR-0010**: Branch naming `{project}-{number}-{slug}`; slug auto from title, editable
- **ADR-0011**: Config via `.env` + CLI overrides
- **ADR-0012**: API versioning `/api/v1/` prefix
- **ADR-0013**: Testing pyramid — Unit + Integration + E2E (Playwright + chrome-devtools-axi)
- **ADR-0014**: Migrations via Alembic (numbered files, reviewable, rollback-capable)
- **ADR-0015**: Link types — parent/child, blocks/blocked_by, relates_to (symmetric)
- **ADR-0016**: Minimal ticket fields — title, description, priority, story_points (+ system: created_at, updated_at, branch_name, pr_url, groomed fields)
- **ADR-0017**: UNS = real seeded Project record (prefix='UNS', is_system=true)
- **ADR-0018** (ticket 03): Project prefix uniqueness enforced at the service layer (`ValueError` → API **409 Conflict**), not just a DB constraint, so duplicate prefixes never surface as 500s.
- **ADR-0019** (ticket 03): HTMX Project forms submit to web routes (`POST /projects`, `PATCH /projects/{id}`, form-encoded, validated via `ProjectCreate`/`ProjectUpdate`) and receive the `project_row.html` row partial back; create success and full-page edit success set `HX-Redirect: /projects`, inline row edits swap the row in place (`HX-Target: project-row-*`).
- **ADR-0020** (ticket 13): PORT=0 is a valid Settings value meaning "pick a free port" (test fixtures use it); `test_settings` overrides DATA_DIR to a pytest temp dir. `client` fixture is `httpx.AsyncClient` via `ASGITransport` (httpx 0.27+ deprecated the direct `app=` kwarg) with `base_url="http://test"`. `seeded_projects` = UNS + 2 test projects (WEB, API). `seeded_tickets` spans Open/Groomed/In-Progress/Ready-for-Review. CI runs E2E headed Chrome under Xvfb (`xvfb-run`).
- **ADR-0021** (ticket 15): The Plan view also renders an "Epics" section (every Epic with its child tickets, project-filterable) — the spec's E2E flow list requires "view in Plan" for Epic→Story hierarchy, so Plan surfaces sprints (calendar) AND epics (cards with children). Data via `LinkService.get_epics_with_children()`. All ticket human IDs are zero-padded (`WEB-003`) across `Ticket.full_id`, move/transition responses, and client-side re-renders. HTMX content negotiation now covers sprint assign/unassign (row partial) and link creation (links-section partial) in addition to ticket PATCH; the Add Link modal posts JSON with a hidden `source_id`, and Playwright e2e fixtures are function-scoped because the sync API's main-thread asyncio loop breaks pytest-asyncio when kept open across a session. Local E2E runs support `pytest tests/e2e --headed` (or `E2E_HEADED=1`) and `--cdx` to attach the chrome-devtools-axi DevTools bridge.

### Schema Overview
```sql
-- Projects
project: id, prefix, name, description, color, is_system, created_at

-- Tickets
ticket: id, project_id, number, type, status, title, description,
        priority, story_points, sprint_id, branch_name, pr_url,
        approach, files_to_change, test_plan, validation_steps,
        created_at, updated_at
UNIQUE(project_id, number)

-- Sprints
sprint: id, number, planned_start, planned_duration_days,
        actual_start, actual_finish, created_at

-- Ticket Links
ticket_link: id, source_ticket_id, target_ticket_id, link_type, created_at
link_type IN ('parent','child','blocks','blocked_by','relates_to')
UNIQUE(source_ticket_id, target_ticket_id, link_type)

-- Status Transitions (audit)
ticket_transition: id, ticket_id, from_status, to_status, reason, at
```

### API Contract (Key Endpoints)
```
GET    /api/v1/projects                    # List projects
POST   /api/v1/projects                    # Create project
GET    /api/v1/projects/{id}               # Get project
PATCH  /api/v1/projects/{id}               # Update project
DELETE /api/v1/projects/{id}               # Delete (not UNS)

GET    /api/v1/tickets                     # List tickets (filters: project, type, status, sprint)
POST   /api/v1/tickets                     # Create ticket
GET    /api/v1/tickets/{id}                # Get ticket with links & transitions
PATCH  /api/v1/tickets/{id}                # Update ticket fields
POST   /api/v1/tickets/{id}/transition     # Status transition (guarded)
POST   /api/v1/tickets/{id}/links          # Add link
DELETE /api/v1/tickets/{id}/links/{link_id}# Remove link
POST   /api/v1/tickets/{id}/move-project   # Move to project (renumbers)

GET    /api/v1/sprints                     # List sprints
POST   /api/v1/sprints                     # Create sprint
GET    /api/v1/sprints/{id}                # Get sprint with tickets
PATCH  /api/v1/sprints/{id}                # Update sprint
POST   /api/v1/sprints/{id}/tickets/{tid}  # Assign ticket to sprint
DELETE /api/v1/sprints/{id}/tickets/{tid}  # Unassign ticket from sprint
```

### Web UI Routes (SSR + HTMX)
```
GET  /                     # Redirect to /backlog
GET  /backlog              # Backlog view (filterable table)
GET  /sprints              # Sprint list
GET  /sprints/{id}         # Sprint detail view (board)
GET  /plan                 # Plan view (calendar)
GET  /tickets/{id}         # Ticket detail (with HTMX partials for actions)
GET  /tickets/new          # Create ticket form
GET  /tickets/{id}/edit    # Edit ticket form
GET  /projects             # Project list
GET  /projects/new         # Create project form
```

## Testing Decisions

### Unit Tests (pytest)
- **Target**: Service functions, model validation, status transition guards, slug generation, sprint numbering, project move renumbering
- **Speed**: <1s per test; run on every change via `pytest -x`
- **Coverage**: >90% of business logic in `services/`

### Integration Tests (pytest + httpx.AsyncClient)
- **Target**: All API endpoints, database operations, migration round-trips
- **Database**: Test SQLite (`:memory:` or temp file per test)
- **Coverage**: All endpoints, all status transitions, all link types, sprint assignment, project move, filtering
- **Fixtures**: Seeded projects (UNS, test projects), test tickets

### E2E Tests (Playwright + chrome-devtools-axi)
- **Target**: Critical user flows in real browser
- **Flows**:
  1. Create ticket → groom (fill 4 fields) → start (branch) → review (PR) → complete
  2. Create sprint → add tickets → start sprint → finish sprint
  3. Move ticket between projects (verify renumbering, original_id preserved)
  4. Create epic → link stories via parent/child → view in Plan
  4. Filter backlog by project/type/status/date
  5. Status transitions: forward guarded, backward free, reject → restore
- **Agent Usage**: Agents drive `chrome-devtools-axi` during development to verify UI updates after API calls, catch HTMX swap issues, form validation, JS errors
- **Run**: Pre-commit (subset), CI (full), agent development loop (continuous)

### Test Data Strategy
- Deterministic seeds via fixtures
- No shared state between tests (transaction rollback or fresh DB)
- Factory functions for Ticket, Sprint, Project, Link

## Out of Scope

- **Multi-user / Authentication** — no login, no sessions, no RBAC, no audit trail of "who"
- **Time tracking** — no logged hours, estimates vs actuals beyond story points
- **Notifications / Webhooks** — no real-time alerts, no external integrations
- **Rich text editor** — description is plain markdown (rendered via HTMX)
- **Drag-and-drop sprint board** — Sprint view is a status table; drag-drop is v2
- **Command palette (cmd+k)** — minimal navigation only
- **Dashboard / Burndown charts** — Plan view shows calendar; charts are v2
- **Project settings / User preferences** — single-user, config via `.env`
- **Attachments / File uploads** — not in spec
- **Custom fields / Workflows** — fixed schema per ADRs
- **Import/Export (JSON, CSV)** — backup is `cp data.db`; export is v2
- **Mobile-responsive UI** — desktop-first; mobile is v2
- **Dark mode** — not in spec

## Further Notes

### Deployment
```bash
# Development
uv sync
uv run server.py

# Production (with overrides)
PORT=8080 DATA_DIR=/var/lib/jackrabbit uv run server.py
```

### Directory Structure (Target)
```
jackrabbit/
├── .env                     # Config (PORT, DATA_DIR, etc.)
├── pyproject.toml           # Dependencies: fastapi, uvicorn, sqlmodel, alembic, httpx, jinja2, htmx, pytest, playwright
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/            # Numbered migrations
├── jackrabbit/
│   ├── __init__.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── tickets.py
│   │   ├── sprints.py
│   │   ├── projects.py
│   │   └── links.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── tickets.py
│   │   │   ├── projects.py
│   │   │   ├── sprints.py
│   │   │   └── links.py
│   │   └── deps.py
│   ├── web/
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   └── templates/
│   │       ├── base.html
│   │       ├── backlog.html
│   │       ├── sprint.html
│   │       ├── plan.html
│   │       ├── ticket_detail.html
│   │       ├── ticket_form.html
│   │       └── project_form.html
│   └── cli.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
└── .scratch/                # Local issue tracker (created by to-tickets)
```

### Migration Strategy
1. `alembic revision --autogenerate -m "initial schema"` → creates `0001_initial.py`
2. Seed UNS project in migration
3. On startup: `alembic upgrade head` (idempotent)
4. Future: `alembic revision --autogenerate -m "description"` → review → commit

### HTMX Patterns
- Forms `hx-post`/`hx-put` → return partial HTML (`hx-swap="outerHTML"`)
- Tables with `hx-get` for filter/sort → return `<tbody>` fragment
- Status buttons `hx-post /api/v1/tickets/{id}/transition` → return updated ticket card
- Delete with `hx-delete` + `hx-confirm` → remove row
- SSE for long-running ops (optional, v2)

### Glossary Compliance
All user-facing strings, API fields, and code identifiers use terms from `GLOSSARY.md`:
- `Ticket`, `Project`, `Sprint`, `Epic`, `Story`, `Bug`, `Spike`
- `Groomed`, `In Progress`, `Ready for Review`, `Complete`, `Rejected`
- `Link` types: `parent`, `child`, `blocks`, `blocked_by`, `relates_to`
- `Story Points`, `Priority`