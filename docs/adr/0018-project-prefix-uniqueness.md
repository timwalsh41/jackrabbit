# ADR-0018: Project Prefix Uniqueness Enforced at the Service Layer

## Status
Accepted

## Context
Ticket 03 (spec). Project prefixes (`MSC`, `WEB`, `UNS`, ...) identify tickets in human-readable IDs (`WEB-003`). A `UNIQUE` DB constraint exists on the prefix column, but a constraint violation at the SQL level surfaces to the API as an unhandled `IntegrityError` → **500**, which is indistinguishable from a crash and gives clients no useful message.

## Decision
Uniqueness is checked **in the service layer**: `ProjectService` raises `ValueError` on a duplicate prefix, and the API layer maps that to **409 Conflict** with a descriptive message. The DB constraint remains as the backstop; the service check is the primary guard so duplicate prefixes never reach it.

## Consequences

### Positive
- **Honest status codes** — duplicate prefix is a client error (409), not a server fault (500)
- **Testable in unit tests** — the guard is reachable without provoking SQL failures
- **Useful message** — the API can name the offending prefix

### Negative
- **Two places encode the rule** — service check + DB constraint must stay in sync (cheap; the constraint only changes if the column definition does)

## Alternatives Considered
- **Catch `IntegrityError` at the API layer**: Rejected — couples route handlers to SQL error strings; the service layer is where the rule belongs.
- **DB constraint only**: Rejected — every violation becomes a 500.