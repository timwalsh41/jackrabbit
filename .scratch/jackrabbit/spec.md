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