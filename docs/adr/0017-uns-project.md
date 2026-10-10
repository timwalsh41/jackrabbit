# ADR-0017: UNS as Real Project Record

## Status
Accepted

## Context
Spec: "Use UNS for unsorted." Options:
- Real Project record (`prefix='UNS'`, `name='Unsorted'`, cannot delete)
- Special sentinel (`project_id=NULL`, display as UNS)
- Auto-created on first use

## Decision
**Real Project record** in `project` table:
```sql
INSERT INTO project (prefix, name, description, color, is_system)
VALUES ('UNS', 'Unsorted', 'Default project for tickets without a project', '#6b7280', true);
```
- `is_system` flag prevents deletion via UI/API
- Exists on first migration (seeded)

## Consequences

### Positive
- **Consistent FK model** — every ticket has `project_id` (NOT NULL), no special NULL handling
- **Queryable** — `SELECT * FROM ticket WHERE project_id = (SELECT id FROM project WHERE prefix='UNS')`
- **Metadata** — can have description, color for UI theming
- **Extensible** — if UNS needs special behavior later, it's a real row

### Negative
- **One extra row** — negligible
- **Must seed on init** — handled by migration

## Alternatives Considered
- **NULL sentinel**: Rejected — requires `LEFT JOIN` everywhere, `COALESCE` in queries, special case in FK logic.
- **Auto-create**: Rejected — race condition on first insert; seeding is simpler.