# ADR-0003: SSR + HTMX for Frontend

## Status
Accepted

## Context
Need a web UI for the project management tool. Options:
- SSR + HTMX (server-rendered HTML + reactive attributes)
- React/Vue/Svelte SPA + REST API
- React/Vue/Svelte + Vite (separate frontend)
- Alpine.js + server-rendered

## Decision
Use **Server-Side Rendering with HTMX** (Jinja2 templates via FastAPI).

## Consequences

### Positive
- **Single process** — one Python binary (`uv run server.py`), no Node, no build step
- **Trivial deployment** — copy repo, `uv sync`, run
- **Server owns state** — simpler mental model, easier debugging, no client-state sync bugs
- **HTMX gives 80% SPA feel** — partial updates, transitions, forms, websockets via SSE
- **Progressive enhancement** — works without JS (mostly), accessible by default
- **API-first compatible** — templates can call internal Python functions or hit `/api/v1/`
- **Low learning curve** — HTML + `hx-*` attributes, no component lifecycle, no state management

### Negative
- **Less client-side interactivity** — no optimistic updates, complex drag-drop requires more work
- **Server round-trip for interactions** — latency on local network is negligible
- **HTMX learning curve** — team must learn `hx-get`, `hx-post`, `hx-swap`, `hx-target`, `hx-trigger`
- **Migration to SPA later** — requires rewriting templates as components, adding build pipeline

### Migration Path to SPA (if needed)
1. Backend already exposes `/api/v1/` JSON API
2. Add Vite + React/Vue/Svelte in `frontend/`
3. Proxy `/api/*` to backend in dev
4. Rewrite templates as components consuming same API
5. Deploy as static files + API (or keep SSR for SEO/initial load)

## Alternatives Considered
- **SPA + REST**: Rejected — adds Node, build step, client-state complexity, dual deployment for a local tool.
- **Alpine.js**: Rejected — less powerful than HTMX for server-driven updates; HTMX's `hx-swap`/`hx-target` model fits CRUD better.