# Jackrabbit Issue Tracker

## Capabilities

- **Ticket CRUD**: Create, read, update tickets via API
- **Status transitions**: Open → Groomed → In Progress → Ready for Review → Complete (Rejected)
- **Ticket types**: Epic (specs), Story (tickets), Bug, Spike
- **Blocking links**: Native `blocks`/`blocked_by` relationships for task graph dependencies
- **Epic→Story hierarchy**: Native `parent`/`child` links
- **Triage roles**: Labels mapped to canonical roles via `/triage/roles` endpoint
- **Transition metadata**: Branch name, PR URL, and groomed fields recorded during status transitions

## Configuration

- **API base**: `http://localhost:8080/api/v1` (configurable)
- **Project**: Selected during setup
- **Full API docs**: `http://localhost:8080/docs` (OpenAPI 3.1)

## When a skill says "groom a ticket"

Used by `/groom`. Groomed tickets carry four implementation fields and move to the `Groomed` status so `/implement` can pick them up (`Groomed → In Progress`).

- **The groomed fields** (Jackrabbit API field names): `approach`, `files_to_change`, `test_plan`, `validation_steps`. They ride on the status transition below, or can be set with `PATCH /api/v1/tickets/{ticket_id}`.
- **The transition**: `Open → Groomed`, via `POST /api/v1/tickets/{ticket_id}/transition` with `{"to_status": "Groomed", "approach": "...", "files_to_change": "...", "test_plan": "...", "validation_steps": "..."}`. Pre-check with `GET /api/v1/tickets/{ticket_id}/transition/can?to_status=Groomed`.
- **Resolve a ticket id**: `/groom <number>` is the tracker number; the full id is `<project_prefix>-<number>` (see `GET /api/v1/tickets/by-id/{project_prefix}/{number}`).
- **Scope**: ticket status and triage labels are independent. Grooming changes status and the four fields **only**; it does **not** apply triage labels (`triage:needs-triage` and the rest), which are `/triage`'s job.
- **Transition metadata**: branch name and PR URL belong to the `In Progress` and `Ready for Review` transitions, not grooming; leave them blank here.

## Agent Execution Evidence

Record concise implementation and independent verification reports in the ticket description under `## Agent Execution Evidence`, using separate `### Implementation` and `### Independent Verification` subsections. On reruns, replace only your own subsection. Include the commit when known, criteria evidence, changed files, tests and gate results, and residual gaps.

Fetch the latest ticket immediately before writing, using `GET /api/v1/tickets/by-id/{project_prefix}/{number}`; use its numeric `id` as `ticket_id`. Preserve all existing description content and update only `description` with `PATCH /api/v1/tickets/{ticket_id}`. Do not change acceptance criteria, status, labels, or grooming fields while recording evidence. Keep the full structured acceptance report in the run artifact.

## Triage Label Mapping

Fetched from `GET /api/v1/triage/roles` at setup time. Canonical roles → Jackrabbit label strings.