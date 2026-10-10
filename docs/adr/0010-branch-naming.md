# ADR-0010: Branch Naming Convention `{project}-{number}-{slug}`

## Status
Accepted

## Context
"In Progress = branch created." Need a naming convention. Options:
- `{project}-{number}-{slug}` (e.g., `MSC-005-add-auth`)
- `{type}/{project}-{number}-{slug}` (e.g., `story/MSC-005-add-auth`)
- User-defined
- Auto UUID

## Decision
**`{project}-{number}-{slug}`** — e.g., `MSC-005-add-auth`, `WEB-012-fix-login-bug`.

### Slug Generation
- Auto-generated from ticket title: lowercase, hyphenated, non-alphanumeric removed, truncated to 50 chars
- User-editable on ticket create/edit
- Unique per ticket (not globally)

## Consequences

### Positive
- **Traceable** — `git branch -a | grep MSC-005` finds it instantly
- **Readable** — conveys project, number, topic
- **Conventional** — matches common `JIRA-1234-description` pattern
- **No type prefix needed** — ticket type visible in UI, not branch name

### Negative
- **Slug can drift from title** — if title changes, slug doesn't auto-update (by design)
- **Project move changes prefix** — `MSC-005` → `WEB-001` would suggest branch rename (optional)

### Mitigations
- Store `branch_name` on ticket when transitioning to In Progress
- On project move, branch name unaffected (historical); new work uses new prefix
- UI shows branch name on In Progress tickets with "copy" button

## Alternatives Considered
- **Type prefix**: Rejected — adds noise (`story/`, `bug/`); ticket type in UI suffices.
- **User-defined**: Rejected — inconsistency, typos, no grep pattern.
- **UUID**: Rejected — opaque, not grep-friendly, no context.