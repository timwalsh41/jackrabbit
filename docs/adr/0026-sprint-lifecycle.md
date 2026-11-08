# ADR-0026: Sprint Lifecycle — Persisted Status and Manual Transitions

## Status
Accepted

## Context
Sprint status has been derived on read from the actual dates (`_derive_status`):
an `actual_finish` meant Complete, an `actual_start` meant Active, otherwise
Planned. Three problems follow:

- **Status is write-ambiguous.** Any PATCH of the actual dates silently moves
  the sprint through its lifecycle, so there is no deliberate "Start Sprint"
  moment and no audit trail of who moved the sprint.
- **The vocabulary leaks.** "Planned/Active" is UI jargon distinct from the
  ticket vocabulary ("Not Started/In Progress/Complete"), so every consumer
  maps strings again.
- **Completion is unguarded.** A sprint can read as Complete while it still
  holds open tickets; nothing forces the loose ends to be resolved first.

## Decision
**Sprint status becomes a persisted state machine with explicit manual
transitions.**

- **States** — `SprintStatus`: `Not Started`, `In Progress`, `Complete`. The
  `sprint.status` column (VARCHAR, storing the human value like
  `TicketCriterionHistory.event`) is the single source of truth; the
  `_derive_status` reader is deleted and every consumer reads the column.

- **Legal transitions** — exactly three:
  - `Not Started → In Progress` ("Start Sprint") — sets `actual_start` to
    today, overwriting any existing value.
  - `In Progress → Complete` ("Complete Sprint") — sets `actual_finish` to
    today, overwriting any existing value. **Guarded**: refused while the
    sprint holds tickets in Open, Groomed, In Progress or Ready for Review;
    the refusal names the blocking tickets and the sprint stays In Progress.
    Complete and Rejected tickets do not block.
  - `Complete → In Progress` ("Reopen Sprint") — clears `actual_finish` and
    keeps the original `actual_start`.

  Any other move raises `SprintTransitionError` (HTTP 400) and leaves the
  sprint unchanged; a guarded completion raises
  `SprintCompletionBlockedError` (HTTP 409).

- **Dates are transition-owned.** `actual_start`/`actual_finish` are removed
  from `SprintUpdate` and rendered read-only in the sprint form. Create is
  the single exception: `SprintCreate` still accepts the dates and seeds the
  status with the backfill rule below, because sprint creation happens once
  and never through the transition endpoint.

- **Audit trail** — a `sprinttransition` table mirrors the ticket `Transition`
  shape (from status, to status, timestamp, optional note). Every accepted
  transition appends exactly one row in the same commit as the status and
  date change; the history is rendered on the sprint board in the style of
  the ticket detail page's criteria history. Start, Complete and Reopen are
  offered on the sprint board and on each Sprints list row.

- **Backfill** — the migration adds the column and history table and backfills
  pre-existing sprints from their dates (`actual_finish` → Complete,
  `actual_start` → In Progress, else Not Started). Their history starts empty:
  no synthetic rows are written for transitions that never happened.

## Consequences
- **Positive** — status changes are deliberate, guarded and auditable; the UI
  vocabulary matches the ticket lifecycle; completion is blocked while work
  remains, with the blockers named.
- **Costs** — a persisted column must be migrated and kept coherent with the
  dates; the dates are no longer directly editable (accepted: transitions are
  the only writer, which is the point).
- **Round-trip** — reopening a completed sprint clears the finish date but
  keeps the start, so the sprint's original duration is lost on the board but
  preserved in the history rows.

## Alternatives Considered
- **Keep date-derived status** — no schema change, but no deliberate start
  moment, no guard, no audit trail. Rejected (this is the status quo the
  ticket exists to fix).
- **Timestamped status events only (no column)** — status queries become
  "latest event", and completion guards get murkier. Rejected: a plain column
  is queryable and the history table covers the audit need.
