# ADR-0001: SQLite for Local Data Storage

## Status
Accepted

## Context
The spec requires data stored "on the local filesystem in a consolidated way to support backups." Options considered:
- SQLite (single file, ACID, SQL queries, migrations)
- JSON files per ticket (git-friendly, no query engine)
- JSON Lines / NDJSON (append-only, streaming)
- Markdown with frontmatter (human-editable, git-diffable)

## Decision
Use **SQLite** as the primary data store.

## Consequences

### Positive
- **Single file** — trivial backup/copy (`cp data.db backup.db`)
- **ACID guarantees** — no partial writes, referential integrity via FKs
- **SQL queries** — filtering, sorting, joins for backlog/sprint/plan views
- **Mature migration tooling** — Alembic integrates with SQLAlchemy/SQLModel
- **Concurrent access** — WAL mode allows readers + single writer
- **No external dependency** — embedded in Python stdlib

### Negative
- **Not git-diffable** — binary file, though schema migrations are reviewable
- **Less human-readable** — requires tooling to inspect. `make db-info` prints
  table counts through the app's own driver, so inspection never depends on the
  `sqlite3` CLI (not a dependency, and absent on many machines) or DB Browser
  being installed
- **Schema changes require migrations** — more ceremony than adding JSON fields

### Mitigations
- Export/import to JSON for debugging/portability — **not implemented**; listed
  here as the intended escape hatch, not a current capability
- Alembic migrations are plain SQL, reviewable in PRs
- Single file makes "consolidated backup" trivial

## Alternatives Considered
- **JSON files**: Rejected — referential integrity (links, sprint assignment, project FK) would need application-level enforcement; concurrent writes risk corruption; querying requires loading all files.
- **Markdown**: Rejected — same integrity issues; parsing frontmatter at scale is slow; no query capability.