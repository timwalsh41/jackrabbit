# ADR-0002: Python + FastAPI for Backend

## Status
Accepted

## Context
Need a web server for the local project management tool. Options:
- Python + FastAPI
- Node.js + Express/Fastify/Hono
- Go + stdlib/Chi/Gin
- Rust + Axum
- Bun + Hono/Elysia

## Decision
Use **Python + FastAPI**.

## Consequences

### Positive
- **Matches existing tooling** — AGENTS.md specifies `uv` for Python package management
- **OpenAPI auto-generation** — `/docs` and `/redoc` endpoints free; clients generated from spec
- **SQLModel/SQLAlchemy** — first-class SQLite support, type-safe models, Alembic migrations
- **Type-safe** — Pydantic models for request/response validation
- **Single dependency** — `uv add fastapi uvicorn sqlmodel alembic httpx`
- **Easy deployment** — `uv run server.py`, no compilation, cross-platform
- **Async support** — handles concurrent requests efficiently

### Negative
- **Python runtime required** — but `uv` manages this
- **GIL** — not an issue for I/O-bound web server with async

### API-First Design
The backend exposes **only** a JSON API at `/api/v1/...`. The SSR + HTMX frontend consumes this same API via internal calls (or direct function calls for simplicity). This enables future SPA migration without backend rewrite.

## Alternatives Considered
- **Node.js**: Rejected — adds Node/npm dependency, separate toolchain, no benefit for Python-centric project.
- **Go/Rust**: Rejected — compilation step, steeper learning curve, overkill for local tool.
- **Bun**: Rejected — newer, less mature ecosystem.