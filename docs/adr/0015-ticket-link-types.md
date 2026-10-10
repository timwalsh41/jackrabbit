# ADR-0015: Ticket Link Types

## Status
Accepted

## Context
Spec mentions "links to other tickets, mainly parent/child for epics, can link bug tickets or investigations to features." Decision on link type vocabulary.

## Decision
**Three link type pairs** (six directed types):

| Type | Direction | Inverse | Use Case |
|------|-----------|---------|----------|
| `parent` | Epic → Story | `child` | Epic contains story |
| `child` | Story → Epic | `parent` | Story belongs to epic |
| `blocks` | A → B | `blocked_by` | A must complete before B |
| `blocked_by` | B → A | `blocks` | B waiting on A |
| `relates_to` | A ↔ B | `relates_to` | General association (bidirectional) |

### Properties
- **`parent`/`child`**: One parent per child (enforced by app), but Epic can have many children
- **`blocks`/`blocked_by`**: Multiple allowed; used for sprint planning (blocked tickets can't start)
- **`relates_to`**: Symmetric; stored as two directed rows or single undirected (implementation choice)

### Schema
```sql
CREATE TABLE ticket_link (
    id INTEGER PRIMARY KEY,
    source_ticket_id INTEGER NOT NULL REFERENCES ticket(id),
    target_ticket_id INTEGER NOT NULL REFERENCES ticket(id),
    link_type TEXT NOT NULL CHECK (link_type IN ('parent','child','blocks','blocked_by','relates_to')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_ticket_id, target_ticket_id, link_type)
);
```

## Consequences

### Positive
- **Covers all spec cases** — epic→story, bug→feature, dependency tracking
- **Minimal but complete** — no proliferation of types
- **Queryable** — "what blocks this?", "what stories in this epic?"
- **Extensible** — new types added to CHECK constraint if needed

### Negative
- **`relates_to` symmetric but stored directed** — queries need `OR` or view
- **No `duplicates`/`duplicated_by`** — user didn't request; can add later

## Alternatives Considered
- **Free-form types**: Rejected — no schema validation, hard to query.
- **Only hierarchy + blocks**: Rejected — `relates_to` needed for loose associations.
- **Jira-like (10+ types)**: Rejected — YAGNI; three pairs cover 90% of cases.