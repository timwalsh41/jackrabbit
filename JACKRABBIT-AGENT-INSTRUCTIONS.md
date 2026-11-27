# Jackrabbit Issue Tracker

Jackrabbit offers a lightweight, web-based issue tracking and project/sprint management system. This document describes its capabilities and where to find documentation.

## Capabilities

- **Ticket CRUD**: Create, read, update tickets via API
- **Status transitions**: Open → Groomed → In Progress → Ready for Review → Complete (Rejected)
- **Ticket types**: Epic (specs), Story, Bug, Spike
- **Blocking links**: Native `blocks`/`blocked_by` relationships for task graph dependencies
- **Epic→Story hierarchy**: Native `parent`/`child` links
- **Transition metadata**: Branch name, PR URL, and groomed fields recorded during status transitions

## Usage instructions

- Accessing the service:
    - **API base**: `http://localhost:8080/api/v1` (configurable)
    - **Full API docs**: `http://localhost:8080/docs` (OpenAPI 3.1)
- Address tickets by designator (`JRB-028`), never a bare integer — see [Identifiers](#identifiers)
- Update ticket status appropriately as you proceed through workflow (after grooming, status should be `Groomed`, move ticket to `In Progress` when implementing, to `Ready for Review` when PR is available, and to `Complete` when merged)
- Always reference the ticket number (epic, story, or bug) in the commit title and PR title
- Create blocking and parent-child links between tickets as relevant when creating tickets or grooming
- Triage labels are attached by name via `POST /api/v1/tickets/{designator}/labels` (e.g. `triage:ready-for-agent`). The five canonical names live in `docs/agents/triage-labels.md`.
- Do not modify sprints (CRUD, move tickets, etc.) without explicit user consent or instruction

## Identifiers

- **`full_id` is the one public identifier.** Every ticket has a project-scoped designator, `full_id` (e.g. `JRB-028`), built from the project prefix plus a never-reused per-project ticket number; every ticket response carries `project_prefix` and `full_id`, so clients never need the internal primary key (`id`)
- **Path params take the designator.** Address tickets as `/api/v1/tickets/JRB-028` (also `.../transition`, `.../labels`, `.../criteria`, `.../links`, `.../children`); sprints are addressed by sprint number (`/api/v1/sprints/2601`); resolution is case-insensitive and zero-padding-agnostic (`web-28`, `WEB-0028` and `Web-000028` all match)
- **Designators are mutable across projects.** `POST /api/v1/tickets/{designator}/move-project` re-allocates the number from the target project and changes the designator (the response names `old_full_id`/`new_full_id`); historical mentions stay resolvable via the ticket's `original_id`, the durable cross-reference recorded on the move. Link payloads always speak `full_id`s.

## Groomed fields

Five fields carry the contract for a groomed ticket: `approach`, `files_to_change`, `test_plan`, `validation_steps`, and `criteria` — the acceptance criteria, a list of strings saying what *done* means. All five are **required** for `Story` and `Bug` (`criteria` needs at least one entry); `Epic` and `Spike` are exempt.

- **When a skill says "groom a ticket"**: fill the fields and move `Open → Groomed` in one call — `POST /api/v1/tickets/{designator}/transition` with `{"to_status": "Groomed", "approach": "...", "files_to_change": "...", "test_plan": "...", "validation_steps": "...", "criteria": ["...", "..."]}`. The guard checks them **in that call** (or set them with `PATCH /api/v1/tickets/{designator}` while still `Open`); pre-check with `GET /api/v1/tickets/{designator}/transition/can?to_status=Groomed`.
- **Criteria stay editable only in `Open`/`Groomed`** (`/api/v1/tickets/{designator}/criteria` CRUD): a later change needs a round-trip back through `Groomed`.
- **Criteria are signed off per row** — `PATCH /api/v1/tickets/{designator}/criteria/{criterion_id}` with `{"verified": true}`, allowed in `In Progress`/`Ready for Review` — and they **gate `Complete`**: `Ready for Review → Complete` fails while any criterion is unverified (`Spike` and zero-criterion tickets exempt).
- **Scope**: grooming changes status and these fields **only** — it does not apply triage labels (`triage:needs-triage` and the rest), and branch name and PR URL belong to the `In Progress` and `Ready for Review` transitions, not grooming.

