# ADR-0005: Ticket Renumbering on Project Move

## Status
Accepted

## Context
When a ticket moves from one project to another (e.g., `MSC-005` → `WEB`), what happens to its number? Options:
- Next available in target (recommended)
- Preserve serial (gaps allowed in source)
- Keep number, update prefix (collisions possible)
- User chooses interactively

## Decision
**Next available in target project**. `MSC-005` moving to `WEB` becomes `WEB-001` (or `WEB-003` if `WEB-001`, `WEB-002` exist).

## Consequences

### Positive
- **No gaps in target** — serial numbers stay dense
- **Clean UX** — user doesn't pick numbers; system manages
- **Source project history preserved** — `MSC-005` stays in MSC history (can show "moved to WEB-001")
- **Simple implementation** — `MAX(number) + 1` in target project transaction

### Negative
- **Number changes** — references in commits, PRs, docs become stale
- **No global uniqueness** — `MSC-005` and `WEB-005` are different tickets

### Mitigations
- Store `original_id` on ticket (e.g., `MSC-005`) for traceability
- Display "formerly MSC-005" in UI when moved
- Git commits reference the ticket at time of commit — that's acceptable

## Alternatives Considered
- **Preserve serial**: Rejected — creates gaps in target (`WEB-001`, `WEB-002`, `WEB-006` looks odd).
- **Keep number**: Rejected — collision if target already has that number.
- **User chooses**: Rejected — decision fatigue; user shouldn't manage serial numbers.