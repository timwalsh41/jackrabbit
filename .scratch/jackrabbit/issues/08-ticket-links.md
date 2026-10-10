# 08: Ticket Links (parent/child, blocks/blocked_by, relates_to)

**What to build:** Typed links between tickets. Three type pairs: parent/child (Epic→Story), blocks/blocked_by (dependencies), relates_to (bidirectional association).

**Blocked by:** 04

**Status:** ready-for-agent

- [ ] Link types: `parent`, `child`, `blocks`, `blocked_by`, `relates_to` (ADR-0015)
- [ ] API: `GET /api/v1/tickets/{id}/links` — list all links for ticket (both directions)
- [ ] API: `POST /api/v1/tickets/{id}/links` — add link `{target_ticket_id, link_type}`
  - Validation: `parent` only to Epic-type ticket; `child` only from Epic-type ticket
  - `blocks`/`blocked_by` create inverse automatically (two rows or symmetric check)
  - `relates_to` creates symmetric pair (or single undirected row)
  - Prevent self-links, duplicate links
- [ ] API: `DELETE /api/v1/tickets/{id}/links/{link_id}` — remove link (removes inverse if paired)
- [ ] Service: `get_blockers(ticket_id)` → tickets with `blocks`→this; `get_blocked(ticket_id)` → this→`blocks`
- [ ] Web: Ticket detail shows "Links" section with type-labeled rows
  - "Add Link" button → modal: select type, search target ticket (by ID/title)
  - Each link row: type badge, target ticket link, "Remove" button (`hx-delete`)
  - `blocks` links show ⚠ warning if blocker not Complete
- [ ] Web: Backlog view — "Blocked" indicator on tickets with open blockers
- [ ] Unit tests: all type pairs, inverse creation, validation rules, blocker queries