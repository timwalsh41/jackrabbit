# ADR-0019: HTMX Project Forms Submit to Web Routes and Receive Row Partials

## Status
Accepted

## Context
Ticket 03 (spec). Project create/edit had to work both as JSON API calls and as in-page HTMX interactions (create from the Projects list, inline row edit without a full page load). The JSON API (`/api/v1/projects`) returns data, not markup, so HTMX posts could not target it directly.

## Decision
HTMX Project forms submit to **web routes**, not the versioned API:
- `POST /projects` (create), `PATCH /projects/{id}` (edit), **form-encoded**, validated via `ProjectCreate` / `ProjectUpdate`
- The response is the **`project_row.html` row partial** for the affected project
- Create success and full-page edit success set **`HX-Redirect: /projects`**; inline row edits swap the row in place via **`HX-Target: project-row-*`**

## Consequences

### Positive
- **One source of validation truth** — web routes reuse the same Pydantic schemas as the API
- **No full page reload** for inline edits; explicit redirect only when the whole page must refresh
- **API stays pure** — `/api/v1/` continues to serve JSON only

### Negative
- **A second set of routes to maintain alongside the API** — accepted; they are thin wrappers around the same services/schemas

## Alternatives Considered
- **HTMX posting JSON to `/api/v1/`**: Rejected — API returns JSON, so HTMX would need client-side JS to re-render rows, defeating the no-build-step SSR approach.