# ADR-0021: Plan Epics Section, Zero-Padded IDs, HTMX Content Negotiation, E2E Fixture Scoping

## Status
Accepted

## Context
Ticket 15 (spec/E2E). Building the critical E2E flows surfaced four related gaps: the spec's flows require "view Epic → Stories in Plan" but Plan only rendered sprints; human ticket IDs (`WEB-3`) shifted width as numbers grew; several HTMX interactions returned JSON where the client expected markup; and Playwright e2e fixtures kept alive across a session deadlocked pytest-asyncio against the sync API's main-thread event loop.

## Decision

### 1. Plan renders an **Epics** section
Alongside the sprint calendar, Plan shows every Epic with its child tickets (project-filterable), via `LinkService.get_epics_with_children()`. Plan = sprints (calendar) **and** epics (cards with children).

### 2. Ticket human IDs are **zero-padded**
`WEB-003` (3 digits) everywhere: `Ticket.full_id`, move/transition responses, and client-side re-renders — so IDs sort and align consistently.

### 3. HTMX content negotiation
Routes check the `HX-Request` header and return the partial the caller needs: ticket PATCH (row partial), sprint assign/unassign (row partial), link creation (links-section partial). The Add Link modal posts JSON with a hidden `source_id`.

### 4. E2E fixtures are **function-scoped**
The sync API holds a main-thread asyncio loop; keeping the client alive across a session breaks pytest-asyncio, so e2e fixtures are per-function. Local runs support `pytest tests/e2e --headed` (or `E2E_HEADED=1`) and `--cdx` to attach the chrome-devtools-axi DevTools bridge.

## Consequences

### Positive
- **Spec flow satisfied** — Epic → Story hierarchy is visible in Plan without a new page
- **Stable, sortable IDs** in UI and API
- **No client-side rendering of API JSON** — HTMX keeps its swap model
- **Deterministic e2e runs** — no cross-test loop contamination

### Negative
- **Padding is a display contract now** — changing digit count later is a migration-visible change
- **Function-scoped e2e fixtures** re-seed per test — slower, but reliable

## Alternatives Considered
- **Separate Epics page**: Rejected — the spec flow says "view in Plan."
- **Session-scoped e2e client**: Rejected — main-thread loop conflict with pytest-asyncio.