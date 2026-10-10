# ADR-0007: Epic as Flat Ticket Type (Not Schema-Enforced Container)

## Status
Accepted

## Context
Spec says "epics represent large multi-feature plan." Two models:
- **Container**: Epic is parent; Stories are children via FK; Epic status derived from children
- **Flat type**: Epic is just `type: "Epic"`; links to stories are optional `parent`/`child` links

## Decision
**Flat type with optional links**. Epic is a ticket with `type = "Epic"`. Hierarchy expressed via `parent`/`child` link records (same as bug↔feature links).

## Consequences

### Positive
- **Flexibility** — Epic can exist without children; can link to any ticket type; multiple parents possible
- **Uniform link model** — all relationships (epic→story, blocks, relates_to) use same `TicketLink` table
- **Simpler schema** — no `parent_epic_id` FK, no derived status logic
- **Matches user mental model** — "epic is a big ticket that relates to smaller tickets"

### Negative
- **No automatic rollup** — Epic status doesn't auto-update from children
- **No FK enforcement** — orphaned child links possible (mitigated by app-level validation)
- **Query "stories in epic" requires join** — but indexed FK makes this fast

### Mitigations
- UI can show "child tickets" section on Epic detail (query `TicketLink` where `type='parent'` and `source_id=epic_id`)
- Status rollup can be a computed property in API/UI if desired later
- App validates: `parent` link only allowed from non-Epic → Epic

## Alternatives Considered
- **Container model**: Rejected — user preferred flexibility; "epic is just a type" matches their workflow better. Derived status adds complexity for marginal benefit.