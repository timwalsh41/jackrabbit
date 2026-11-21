# ADR-0005: Ticket Renumbering on Project Move

## Status
Accepted (amended by JRB-037: numbers are never reused)

## Context
When a ticket moves from one project to another (e.g., `MSC-005` → `WEB`), what happens to its number? Options:
- Next available in target (recommended)
- Preserve serial (gaps allowed in source)
- Keep number, update prefix (collisions possible)
- User chooses interactively

## Decision
**Next available in target project**. `MSC-005` moving to `WEB` becomes WEB's next
never-before-used serial (e.g. `WEB-003` if `WEB-001`, `WEB-002` exist) — see the
JRB-037 amendment below for what "next available" means under the never-reuse
counter.

## Consequences

### Positive
- **Automatic allocation** — the target serial comes straight from the project's `next_number` counter (JRB-037). Density is not guaranteed anywhere: numbers are never reissued, so freed serials leave permanent gaps in both projects
- **Clean UX** — user doesn't pick numbers; system manages
- **Source project history preserved** — `MSC-005` stays in MSC history (can show "moved to WEB-001")
- **Simple implementation** — increment the target project's `next_number` counter in the move transaction (JRB-037); `MAX(number) + 1` is no longer the allocation rule anywhere

### Negative
- **Number changes** — references in commits, PRs, docs become stale
- **No global uniqueness** — `MSC-005` and `WEB-005` are different tickets

### Mitigations
- Store `original_id` on ticket (e.g., `MSC-005`) for traceability
- Display "formerly MSC-005" in UI when moved
- Git commits reference the ticket at time of commit — that's acceptable

## Amendment (JRB-037, stable ticket numbers)

JRB-037 replaced the per-project ``MAX(number) + 1`` allocation with a
monotone per-project ``next_number`` counter. Consequences for this ADR:

- "Next available in target" now means the next **never-before-used** serial
  in the target project; numbers are never reissued, not after deletes and
  not after a move frees a serial in the source project.
- Source project numbering is unchanged by a move: the vacated serial stays
  allocated, so "no gaps in source" no longer holds (gaps are permanent).
- ``MAX(number) + 1`` is no longer the allocation rule anywhere; the counter
  on the project row is the single source of truth (seeded by migration
  ``f1a2b3c4d5e6`` for pre-existing data).

## Alternatives Considered
- **Preserve serial**: Rejected — references the old prefix anyway (`WEB-001` arriving with `MSC-005`'s serial is still a new designator, and it would reissue serials the counter has already spent).
- **Keep number**: Rejected — collision if target already has that number.
- **User chooses**: Rejected — decision fatigue; user shouldn't manage serial numbers.