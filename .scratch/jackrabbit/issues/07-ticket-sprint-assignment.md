# 07: Ticket ↔ Sprint Assignment

**What to build:** Assign/unassign tickets to sprints (one sprint per ticket). Sprint detail view shows tickets grouped by status.

**Blocked by:** 04, 06

**Status:** ready-for-agent

- [ ] API: `POST /api/v1/sprints/{id}/tickets/{ticket_id}` — assign ticket to sprint (fails if ticket already in another sprint)
- [ ] API: `DELETE /api/v1/sprints/{id}/tickets/{ticket_id}` — unassign ticket from sprint
- [ ] API: `GET /api/v1/sprints/{id}` returns sprint with nested tickets grouped by status
- [ ] Ticket model: `sprint_id` FK (nullable), enforced unique per ticket via DB constraint
- [ ] Web: Sprint detail page `GET /sprints/{id}` — columns for each status (Open, Groomed, In Progress, Ready for Review, Complete, Rejected) showing tickets as cards
  - HTMX: drag-drop not required; "Move to Sprint" dropdown on ticket card in backlog → `hx-post` to assign
  - Ticket card in sprint view shows "Remove from Sprint" button → `hx-delete`
- [ ] Web: Backlog view adds "Sprint" column + filter; unassigned tickets show "—"
- [ ] Validation: cannot assign ticket to sprint if already assigned (return 409 with current sprint info)
- [ ] Unit tests: assign, unassign, double-assign prevention, sprint deletion cascades (unassigns tickets)