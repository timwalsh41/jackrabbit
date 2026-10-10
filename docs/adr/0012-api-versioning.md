# ADR-0012: API Versioning via URL Prefix `/api/v1/`

## Status
Accepted

## Context
Building API-first for future SPA migration. Versioning options:
- `/api/v1/` prefix from day one
- No versioning until breaking change
- Header-based (`Accept: application/vnd.jackrabbit.v1+json`)

## Decision
**URL prefix `/api/v1/` from day one**.

## Consequences

### Positive
- **Explicit** — version visible in logs, browser, curl
- **Easy routing** — FastAPI `APIRouter(prefix="/api/v1")`
- **Standard practice** — familiar to all API consumers
- **Multiple versions coexist** — `/api/v1/`, `/api/v2/` can run simultaneously
- **No client negotiation** — client just uses the URL

### Negative
- **URL pollution** — `/api/v1/tickets` vs `/tickets` (SSR routes)
- **Prefix everywhere** — but FastAPI router groups handle this

### Mitigations
- SSR routes at root (`/`, `/tickets`, `/sprints`) — separate from API
- API strictly under `/api/v1/`
- OpenAPI spec generated at `/api/v1/openapi.json`

## Alternatives Considered
- **No versioning**: Rejected — breaking changes inevitable; retrofitting versioning is painful.
- **Header-based**: Rejected — invisible in logs, harder to debug, requires client cooperation.