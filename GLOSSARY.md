# Glossary

## Core Domain

**Ticket**
: A unit of work in the backlog. Has a unique identifier (`{project}-{number}`), type, status, optional sprint assignment, optional links to other tickets, and any number of labels.

**Label**
: A free-form tag that categorises a ticket independently of its type, project, status, sprint and priority. A ticket may carry many labels; a label is shared across all projects and may be applied to any ticket regardless of its type. Labels are created on demand and are identified case-insensitively, so `Backend` and `backend` are the same label.

**Ticket Type**
: One of: `Epic`, `Story`, `Bug`, `Spike`. `Epic` represents a large multi-feature plan but is a flat type — hierarchy is expressed via links, not schema.

**Ticket Status**
: One of: `Open`, `Groomed`, `In Progress`, `Ready for Review`, `Complete`, `Rejected`. Transitions are guarded forward (require criteria), backward allowed freely, and `Rejected` can restore to any prior valid state.

**Project**
: A named container for tickets identified by a short prefix (e.g., `MSC`, `WEB`, `UNS`). First-class entity with metadata (name, description, color). `UNS` (Unsorted) is a system project that cannot be deleted.

**Sprint**
: A time-boxed (or open-ended) container of tickets. Identified by a serial number with year prefix (`2601`, `2602`... continuing past 52). Has optional planned/actual dates. A ticket belongs to at most one sprint.

**Link**
: A typed relationship between two tickets. Types: `parent`/`child` (epic→story), `blocks`/`blocked_by` (dependencies), `relates_to` (bidirectional association).

**Groomed**
: A ticket status meaning the approach has been assessed and four structured fields are populated: `approach`, `files_to_change`, `test_plan`, `validation_steps`.

**In Progress**
: A ticket status meaning a git branch has been created (naming convention: `{project}-{number}-{slug}`) and work is underway.

**Ready for Review**
: A ticket status meaning a PR (or report for Spike) is up for human approval.

**Story Points**
: Optional integer estimate of effort for planning.

**Priority**
: One of: `Low`, `Medium`, `High`, `Critical`.

**Triage Role**
: Where a ticket sits in the triage workflow. One of: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. A role is recorded as a label in the `triage:` namespace (`triage:ready-for-agent`), not as a keyword in the ticket description, so it is visible in the interface and queryable. A ticket carries at most one triage role.

## Technical

**API-First**
: The backend is designed as a JSON API (`/api/v1/...`) from day one. Server-rendered HTML (SSR + HTMX) consumes the same API, enabling future SPA migration.

**HTMX**
: A library that allows server-rendered HTML to behave reactively via `hx-*` attributes. No client-side framework, no build step.

**Migration**
: A numbered SQL file that evolves the SQLite schema. Managed by Alembic.

**Configuration**
: `.env` file with CLI argument overrides. Keys: `PORT`, `DATA_DIR`, `DATABASE_URL`.

**Chrome-DevTools-AXI**
: Tooling for agents to run end-to-end browser tests during development.

## UI Views

**Backlog View**
: Filterable, sortable list of all tickets (filter by project, type, status, label, date).

**Sprint View**
: Status board of tickets assigned to the current sprint.

**Plan View**
: Calendar-style list of sprints with their date ranges and ticket counts.

**Ticket Detail**
: Full ticket view with fields, links, history, and actions (status transitions, link management, sprint assignment).