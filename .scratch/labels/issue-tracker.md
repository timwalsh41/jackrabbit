# Issue tracker: Jackrabbit (running app)

This repo's engineering issues are tracked as tickets in a running Jackrabbit instance
—the project's own local-first tracker — not in GitHub Issues or local markdown.

## Connecting

- **Prod instance:** `http://localhost:8080` (JSON API at `/api/v1`, Swagger UI at `/docs`,
  OpenAPI spec at `/openapi.json`).
- **Auth:** none (Jackrabbit is single-user).
- **Project:** `JRB` (id `3`, prefix `JRB`) is the project for this repo's engineering work.
  A spec is an **Epic**; each implementation stage is a **Story** linked as `child` under
  the spec epic (`POST /api/v1/tickets/{epic_id}/links`, `link_type: "child"`).
  Ticket types: `Epic`/`Story`/`Bug`/`Spike`. Priorities: `Low`/`Medium`/`High`/`Critical`.
  Link types: `parent`/`child`/`blocks`/`blocked_by`/`relates_to`.

## Creating a ticket

`POST /api/v1/tickets` with a `TicketCreate` body: `project_id: 3`, `type`, `title`,
`description`, `priority`, ... (optional: `approach`, `files_to_change`, `test_plan`,
`validation_steps`, `story_points`, `sprint_id`).

## Reading a ticket

`GET /api/v1/tickets/{ticket_id}` returns full details (`TicketReadWithDetails`: full id,
status, priority, links, transitions, project prefix). A ticket's human-readable id is
`{prefix}-{number}`, zero-padded (e.g. `JRB-001`), reachable directly at
`GET /api/v1/tickets/by-id/{project_prefix}/{number}`.

## Updating a ticket

`PATCH /api/v1/tickets/{ticket_id}` with a `TicketUpdate` body — every field is optional:
`title`, `description`, `type`, `status`, `priority`, `story_points`, `approach`,
`files_to_change`, `test_plan`, `validation_steps`, `sprint_id`, `transition_reason`.
Use it to edit a ticket's `description` in place (the acceptance criteria live there).

## Resolving a ticket (agent workflow)

The agent workflow (`/implement-spec`) closes a ticket by editing its **description**:

1. Check off each acceptance criterion: replace its `- [ ]` with `- [x]`.
2. Append the implementation summary under a `## Answer` heading at the end.
3. Set the `**Status:**` line (first line of the description) to `resolved` — edit it in
   place, never append a second one.

A ticket counts as **resolved** when its description carries `**Status:** resolved` (or
its status field is `Complete`). The workflow's status *transitions* (below) are for the
human review flow; agents resolve tickets this way and do not walk the ticket through
`Groomed` → `In Progress` → `Ready for Review` → `Complete`.

## Progressing a ticket

`POST /api/v1/tickets/{ticket_id}/transition` with `to_status`:
`Open`/`Groomed`/`In Progress`/`Ready for Review`/`Complete`/`Rejected` (forward
transitions are guarded — `Groomed` needs the four structured fields, `In Progress`
needs `branch_name`, `Ready for Review` needs `pr_url`; see ADR-0009).

## Triage

Jackrabbit has no labels/comments/tags fields, so the five triage roles are recorded as a
keyword line at the top of the ticket **description** — `**TRIAGE_STATUS**: <role>`
(e.g. `**TRIAGE_STATUS**: ready-for-agent`). See `triage-labels.md`. (Stopgap until a
labels feature is added to Jackrabbit; when deployed to prod, update these instructions.)

## Testing against a local instance

`.env` is the source of truth for the dev instance's configuration (see ADR-0011). Run the
dev instance with `uv run server.py`; it reads configuration from `.env`. Point test scripts
at this dev instance's `/api/v1`. Do not write to production instance during dev testing.
