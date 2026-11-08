# Jackrabbit Issue Tracker

Jackrabbit offers a lightweight, web-based issue tracking and project/sprint management system. This document describes its capabilities and where to find documentation.

## Capabilities

- **Ticket CRUD**: Create, read, update tickets via API
- **Status transitions**: Open → Groomed → In Progress → Ready for Review → Complete (Rejected)
- **Ticket types**: Epic (specs), Story (tickets), Bug, Spike
- **Blocking links**: Native `blocks`/`blocked_by` relationships for task graph dependencies
- **Epic→Story hierarchy**: Native `parent`/`child` links
- **Triage roles**: Labels mapped to canonical roles via `/triage/roles` endpoint
- **Transition metadata**: Branch name, PR URL, and groomed fields recorded during status transitions

## Usage instructions

- Accessing the service:
    - **API base**: `http://localhost:8080/api/v1` (configurable)
    - **Full API docs**: `http://localhost:8080/docs` (OpenAPI 3.1)
- Update ticket status appropriately as you proceed through workflow (after grooming, status should be `Groomed`, move ticket to `In Progress` when implementing, to `Ready for Review` when PR is available, and to `Complete` when merged)
- Always reference the ticket number (epic, story, or bug) in the commit title and PR title
- Create blocking and parent-child links between tickets as relevant when creating tickets or grooming
- Triage label mappings are fetched from `GET /api/v1/triage/roles` at setup time. Canonical roles → Jackrabbit label strings.
- Do not modify sprints (CRUD, move tickets, etc.) without explicit user consent or instruction

## Groomed fields

Five fields carry the contract for a groomed ticket: `approach`, `files_to_change`, `test_plan`, `validation_steps`, and `criteria` — the acceptance criteria, a list of strings saying what *done* means. All five are **required** for `Story` and `Bug` (`criteria` needs at least one entry); `Epic` and `Spike` are exempt.

- **When a skill says "groom a ticket"**: fill the fields and move `Open → Groomed` in one call — `POST /api/v1/tickets/{ticket_id}/transition` with `{"to_status": "Groomed", "approach": "...", "files_to_change": "...", "test_plan": "...", "validation_steps": "...", "criteria": ["...", "..."]}`. The guard checks them **in that call** (or set them with `PATCH /api/v1/tickets/{ticket_id}` while still `Open`); pre-check with `GET /api/v1/tickets/{ticket_id}/transition/can?to_status=Groomed`.
- **Criteria stay editable only in `Open`/`Groomed`** (`/api/v1/tickets/{ticket_id}/criteria` CRUD): a later change needs a round-trip back through `Groomed`.
- **Criteria are signed off per row** — `PATCH /api/v1/tickets/{ticket_id}/criteria/{criterion_id}` with `{"verified": true}`, allowed in `In Progress`/`Ready for Review` — and they **gate `Complete`**: `Ready for Review → Complete` fails while any criterion is unverified (`Spike` and zero-criterion tickets exempt).
- **Scope**: grooming changes status and these fields **only** — it does not apply triage labels (`triage:needs-triage` and the rest), and branch name and PR URL belong to the `In Progress` and `Ready for Review` transitions, not grooming.


