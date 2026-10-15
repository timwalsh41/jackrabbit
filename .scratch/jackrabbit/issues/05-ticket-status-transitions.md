# 05: Ticket Status Transitions (Guarded)

**What to build:** State machine for ticket status with guarded forward transitions, free backward transitions, and restore from Rejected. Audit log of all transitions.

**Blocked by:** 04

**Status:** resolved

- [ ] Status enum: `Open`, `Groomed`, `In Progress`, `Ready for Review`, `Complete`, `Rejected`
- [ ] Transition rules (ADR-0009):
  - Open → Groomed: requires `approach`, `files_to_change`, `test_plan`, `validation_steps` all non-empty
  - Groomed → In Progress: requires `branch_name` non-empty (validated format)
  - In Progress → Ready for Review: requires `pr_url` non-empty (valid URL)
  - Ready for Review → Complete: requires PR merged (manual confirmation) or Spike report accepted
  - Backward (any → previous): always allowed, no guards
  - Rejected → any prior state: allowed if that state's guard criteria currently met
  - Any → Rejected: always allowed
- [ ] API: `POST /api/v1/tickets/{id}/transition` with `{to_status, reason}` → validates guard, updates ticket, writes `ticket_transition` audit row
- [ ] Service: `can_transition(ticket, to_status)` returns `(bool, error_message)`
- [ ] Service: `transition(ticket, to_status, reason)` — atomic update + audit
- [ ] Web: Ticket detail shows current status badge + action buttons for valid next states
  - Buttons use `hx-post="/api/v1/tickets/{id}/transition"` → returns updated status badge + history partial
  - Guard failures return 400 with error message (displayed via HTMX)
- [ ] Web: Transition history section on ticket detail (timestamp, from→to, reason)
- [ ] Unit tests: all 30+ transition combinations (forward guarded, backward free, rejected restore)