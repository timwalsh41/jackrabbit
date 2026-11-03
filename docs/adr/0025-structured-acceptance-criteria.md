# ADR-0025: Structured Acceptance Criteria

## Status
Accepted — amends ADR-0008 (Spike exemption) and ADR-0009 (Complete guard)

## Context
Jackrabbit tickets currently carry acceptance criteria as free-text markdown checkboxes
(`- [ ]`) inside the description. This is fragile: the checkbox state is a prose
convention that no schema enforces, criteria cannot be queried ("tickets with unverified
criteria"), per-criterion sign-off is a whole-description rewrite, and the same
description is also home to the Agent Execution Evidence section. The mp-skills
`/implement` and `/implement-spec` workflows treat "acceptance criteria" as a first-class
gate (implementer checks boxes, verifier independently re-derives them and is forbidden
from toggling them), but the storage layer offers no support for that contract.

## Decision
**Acceptance criteria become structured rows in a dedicated `ticket_criteria` table**, with:

- **Storage** — one row per criterion: ticket id, ordinal position, `text`,
  `verified` boolean, `verified_at` timestamp. Per ADR-0016 philosophy, evidence prose
  stays in the description's Agent Execution Evidence section, not on the row.

- **Authorship** — criteria are authored at grooming time via the Groomed transition
  payload, which gains a criteria list alongside the four existing groomed fields.
  Implementers never write criteria; they may *propose* additions, but only the
  orchestrator/user can land them, via the round-trip described below.

- **Gate shape** — grooming (the `Open → Groomed` transition) requires:
  - `Story`, `Bug`: the four groomed fields **plus at least one criterion**
  - `Epic`: exempt (planning container, per ADR-0008)
  - `Spike`: fully exempt — this **relaxes** ADR-0008, which today requires all four
    groomed fields for Spike. Spikes produce reports, not code.

- **UI** — in the transition modal and ticket-detail edit view, a section header
  `Acceptance criteria` with a red asterisk for Story/Bug and plain label for
  Epic/Spike (no "(Optional)" text, since the requirement is type-conditional).
  Below the header, one text-input row per criterion with a remove `×` button and an
  `+ Add criterion` button appending fresh rows. Existing criteria are pre-filled and
  editable before transition. In the non-editing detail view, criteria render as a
  checklist with verified ticks and timestamps, read-only once In Progress.

- **Locking** — rows are freely editable in `Open`/`Groomed`. From `In Progress`
  onward, editing requires a round-trip back to `Groomed`, edit, then forward again
  (the `Groomed → In Progress` guard re-runs trivially).

- **Sign-off** — `PATCH /api/v1/tickets/{id}/criteria/{cid}` flips `verified`
  (allowed in `In Progress`/`Ready for Review`; this is the independent verifier's
  action). Evidence remains in prose.

- **Complete guard** — the `Ready for Review → Complete` transition fails while any
  criterion row is unverified (Spike and zero-criterion tickets exempt).
  `Ready for Review` stays gated on PR URL only, so human and agent flows both work.

- **Migration** — one-time data migration parses each ticket's `## Acceptance criteria`
  description checkboxes into unchecked rows and removes that section;
  `## Agent Execution Evidence` is preserved.

- **Audit** — criterion adds, edits, and verification sign-offs each append a history
  entry with timestamp and the criterion text.

- **API surface** — `POST/GET/PATCH/DELETE /api/v1/tickets/{id}/criteria` for row CRUD
  (rejected outside `Open`/`Groomed`), sign-off `PATCH` as above, criteria list in the
  Groomed transition payload, and `Complete` guard enforcement.

## Consequences

### Positive
- **Enforceable contract** — "Complete" is machine-checked against criterion state,
  not prose convention.
- **Per-criterion sign-off** — the verifier can independently check off individual
  criteria, matching the mp-skills verifier/implementer split.
- **Queryable** — "tickets with unverified criteria" is a cheap query.
- **No blob races** — per-row updates, no read-modify-write of a whole JSON column.
- **Evidence stays in prose** — no duplication or drift between row state and narrative.

### Negative
- **Friction at grooming** — one more required element before a Story/Bug can be groomed.
- **Migration risk** — parsing legacy markdown checkboxes may mis-shape malformed lists;
  mitigated by a dry-run report before the migration commits.
- **Round-trip cost** — mid-run edits require a `Groomed` round-trip rather than a
  single in-place edit; accepted as the cost of keeping the contract auditable.

## Alternatives Considered
- **JSON column on ticket** — simplest schema, but whole-blob updates and no per-criterion
  queries. Rejected.
- **Stay in description markdown** — no schema change, but fragile parsing, no clean
  state, and the verifier/implementer contract lives outside the storage layer. Rejected.
- **Implementer-owned checkboxes, verifier reports only** — matches today's behavior but
  does not give the verifier a first-class sign-off action. Rejected.
- **Two-stage state (claimed → verified)** — preserves both roles' state, but a two-value
  lifecycle is more UI and API surface than the contract needs. Rejected.

## mp-skills alignment
Out of scope here, but the companion change is already agreed: mp-skills'
`/implement` and `/implement-spec` will be updated to consult the issue-tracker guidance
(`docs/agents/issue-tracker.md`, and the emitted `issue-tracker-jackrabbit.md`) for how
criteria are tracked, and the `- [ ]` description-checkbox convention is deprecated in
that guidance.
