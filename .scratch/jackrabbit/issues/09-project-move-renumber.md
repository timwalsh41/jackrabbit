# 09: Project Move with Renumbering

**What to build:** Move a ticket to another project → renumbered to next available serial in target; `original_id` preserved for traceability.

**Blocked by:** 04, 03

**Status:** resolved

- [ ] Ticket model: add `original_id` TEXT field (stores `MSC-005` format)
- [ ] API: `POST /api/v1/tickets/{id}/move-project` with `{target_project_id}`
  - Computes `new_number = MAX(number)+1` for target project (in transaction)
  - Updates `project_id`, `number`, sets `original_id = f"{old_prefix}-{old_number:03d}"` (if not already set)
  - Returns updated ticket with new ID format
- [ ] Service: `move_ticket_to_project(ticket_id, target_project_id)` — atomic, handles race conditions
- [ ] Web: Ticket detail — "Move Project" button → modal with project dropdown (excludes current)
  - `hx-post="/api/v1/tickets/{id}/move-project"` → returns updated ticket detail partial
  - Display "Formerly {original_id}" below ticket ID if `original_id` set
- [ ] Web: Backlog — ticket row shows current ID; hover/tooltip shows original ID
- [ ] Edge case: moving already-moved ticket preserves first `original_id`
- [ ] Unit tests: move to empty project (→ 001), move to project with gaps (→ next), chained moves preserve first original_id, concurrent moves handled