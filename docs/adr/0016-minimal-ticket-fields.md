# ADR-0016: Minimal Ticket Fields

## Status
Accepted — the `labels`/`tags` exclusion below is superseded by ADR-0024

## Context
Beyond spec-mandated fields (type, status, links, sprint, project), what else? Options:
- Practical middle ground (title, description, assignee, labels, priority, story points)
- Minimal (title, description, priority, story points)
- Full Jira-like (components, versions, environment, security...)

User chose **Minimal**: Title, description, priority, story points (+ system: created_at, updated_at).

## Decision
**Ticket fields**:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | INTEGER PK | Auto | SQLite autoincrement |
| `project_id` | INTEGER FK | Yes | References `project(id)` |
| `number` | INTEGER | Yes | Per-project serial (1, 2, 3...) |
| `type` | TEXT | Yes | `Epic`, `Story`, `Bug`, `Spike` |
| `status` | TEXT | Yes | `Open`, `Groomed`, `In Progress`, `Ready for Review`, `Complete`, `Rejected` |
| `title` | TEXT | Yes | Short summary |
| `description` | TEXT | No | Markdown supported |
| `priority` | TEXT | No | `Low`, `Medium`, `High`, `Critical` |
| `story_points` | INTEGER | No | Fibonacci-ish: 1,2,3,5,8,13,21 |
| `sprint_id` | INTEGER FK | No | Nullable, references `sprint(id)` |
| `branch_name` | TEXT | No | Set on In Progress transition |
| `pr_url` | TEXT | No | Set on Ready for Review transition |
| `approach` | TEXT | No* | Required for Groomed |
| `files_to_change` | TEXT | No* | Required for Groomed (JSON array) |
| `test_plan` | TEXT | No* | Required for Groomed |
| `validation_steps` | TEXT | No* | Required for Groomed |
| `created_at` | TIMESTAMP | Auto | |
| `updated_at` | TIMESTAMP | Auto | |

*Not DB-required; app-enforced for `Groomed` transition.

### Not Included (YAGNI)
- `assignee` — single-user tool; no user table
- `labels`/`tags` — priority + type + project + sprint cover filtering (superseded by ADR-0024)
- `components` — not needed for personal/small-team use
- `fix_version`/`affects_version` — sprint serves this role
- `reporter` — single user
- `time_tracking` — not in spec

## Consequences

### Positive
- **Simple schema** — easy to understand, migrate, query
- **Fast UI** — fewer fields to render, less form complexity
- **Focus** — only fields that drive decisions (priority, points, sprint, status)

### Negative
- **Less metadata** — can't filter by component, assignee, version
- **No audit of who changed what** — single-user mitigates

## Alternatives Considered
- **Middle ground**: Rejected — assignee/labels add tables/columns without clear need.
- **Full Jira**: Rejected — massive overkill.