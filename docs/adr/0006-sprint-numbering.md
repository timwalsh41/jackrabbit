# ADR-0006: Sprint Numbering — Continuous Serial with Year Prefix

## Status
Accepted

## Context
Sprints numbered `2601`, `2602`... What happens after 52? Options:
- Year rolls, week resets (`2601`–`2652` → `2701`, `2702`)
- Continuous serial (`2601`, `2602`... `2653`, `2654`...)
- ISO week format (`2026-01`, `2026-02`...)
- User-defined prefix

User clarified: sprints are **not week-bound** — they're "coherent set of work that may take shorter or longer than a week."

## Decision
**Continuous serial with year prefix**: `2601`, `2602`, `2603`... continuing past 52 (`2653`, `2654`...). The year prefix (`26`) indicates the year the sprint series *started*, not the current year.

## Consequences

### Positive
- **Simple mental model** — just incrementing numbers
- **No week-boundary confusion** — sprints can be any duration
- **Sortable** — lexicographic sort = chronological order
- **Year prefix gives rough era** — `26xx` = started in 2026, `27xx` = started in 2027

### Negative
- **Year prefix becomes misleading** — `2601` created in Dec 2026, `2653` created in June 2027
- **No semantic meaning** — number doesn't encode date

### Mitigations
- Store `planned_start` date on sprint for actual calendar info
- Year prefix is just a namespace, not a contract

## Alternatives Considered
- **Year rolls at 52**: Rejected — implies weekly cadence which spec explicitly doesn't require.
- **ISO week**: Rejected — same weekly assumption; more complex format.