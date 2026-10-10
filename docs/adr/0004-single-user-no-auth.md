# ADR-0004: Single-User, No Authentication

## Status
Accepted

## Context
The tool is for "AI coding tasks" — a local developer tool. Options:
- Single-user, no auth
- Multi-user with auth (OAuth, sessions, RBAC)
- Multi-user, no auth (trusted LAN, username header)

## Decision
**Single-user, no authentication**.

## Consequences

### Positive
- **Zero auth complexity** — no sessions, cookies, password hashing, reset flows, RBAC, audit logs
- **Simpler data model** — no `User` table, no ownership on tickets/sprints/projects
- **Faster development** — all effort on domain features
- **Local-first philosophy** — runs on developer's machine, no network exposure needed
- **No security surface** — no login page to attack, no session hijacking

### Negative
- **No multi-user support** — cannot share instance with team
- **No audit trail of who did what** — but single-user makes this moot
- **Cannot deploy to shared server** — would need auth added first

### Future: Adding Auth
If multi-user needed later:
1. Add `User` table + `Session` table
2. Add `owner_id` FK to `Ticket`, `Sprint`, `Project` (or `created_by`/`updated_by`)
3. Implement session cookie or JWT via middleware
4. Add login page (HTMX form → sets cookie)
5. Protect all routes with auth dependency
6. ~1-2 weeks of work

## Alternatives Considered
- **Multi-user with auth**: Rejected — YAGNI. Spec doesn't mention collaboration, teams, or shared instances.
- **Multi-user no auth**: Rejected — security risk if exposed; adds complexity without real benefit.