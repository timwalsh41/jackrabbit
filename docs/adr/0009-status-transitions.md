# ADR-0009: Guarded Forward Transitions, Free Backward, Restore from Rejected

## Status
Accepted

## Context
Ticket status: `Open` → `Groomed` → `In Progress` → `Ready for Review` → `Complete`, with `Rejected` from anywhere. User wants:
- Forward transitions guarded (require criteria)
- Backward transitions free
- `Rejected` → restore to any prior valid state

## Decision
**State machine with asymmetric transitions**:

| From \ To | Open | Groomed | In Progress | Ready for Review | Complete | Rejected |
|-----------|------|---------|-------------|------------------|----------|----------|
| **Open**      | —    | ✅*     | ❌          | ❌               | ❌       | ✅       |
| **Groomed**   | ✅    | —       | ✅*         | ❌               | ❌       | ✅       |
| **In Progress**| ✅  | ✅      | —           | ✅*              | ❌       | ✅       |
| **Ready for Review**| ✅ | ✅  | ✅          | —                | ✅*      | ✅       |
| **Complete**  | ✅    | ✅      | ✅          | ✅               | —        | ✅       |
| **Rejected**  | ✅†   | ✅†     | ✅†         | ✅†              | ✅†      | —        |

✅* = Guarded forward (requires criteria)
✅ = Free backward
✅† = Restore to any prior valid state (must meet that state's guard criteria)

### Guard Criteria
- `Open → Groomed`: All four structured fields present (`approach`, `files_to_change`, `test_plan`, `validation_steps`)
- `Groomed → In Progress`: Git branch exists (naming convention `{project}-{number}-{slug}`)
- `In Progress → Ready for Review`: PR URL present (or report for Spike)
- `Ready for Review → Complete`: PR merged (or report accepted)

### Consequences

#### Positive
- **Prevents invalid states** — can't reach In Progress without branch, Review without PR
- **Allows correction** — move back freely when review finds issues
- **Rejected isn't terminal** — can restore to any state if work resumes
- **Audit trail** — every transition logged with timestamp, user, reason

#### Negative
- **More complex than free state machine** — requires validation logic
- **Restore from Rejected requires re-meeting guards** — can't jump to Complete without passing through gates

### Implementation
- `TicketStatus` enum in code
- `can_transition(from, to, ticket)` function with guard checks
- `transition_history` table: `ticket_id`, `from_status`, `to_status`, `at`, `reason`
- API: `POST /api/v1/tickets/{id}/transition` with `to_status` and optional `reason`

### Epic Exemption
An `Epic` (a planning container, not a unit of code) is exempt from two of the
forward guards: the `Open -> Groomed` structured-field requirement and the
`Groomed -> In Progress` branch-name format check. An Epic may therefore be
groomed with the four fields blank, and its branch name is optional and
auto-generated on transition to `In Progress`. The branch-name format check is
skipped entirely for Epics; `Story`/`Bug`/`Spike` keep the check. The exemption
is applied in `TicketService._validate_guard`, gated on `ticket.type`.

## Alternatives Considered
- **Strict linear**: Rejected — no backward, no restore from Rejected.
- **Free any→any**: Rejected — allows invalid states (In Progress without branch).