# Jackrabbit

Ticket tracking and sprint management system.

## Quick Start

```bash
# Install dependencies
uv sync

# Copy example env file
cp .env.example .env

# Initialize database
uv run server.py init-db

# Load demo data (idempotent; safe to re-run)
uv run server.py seed

# Create a project
uv run server.py create-project WEB "Web Project"

# Start the server
uv run server.py
```

The server will start on port 8080 (or the PORT from .env).

- Web UI: http://localhost:8080
- API: http://localhost:8080/api/v1/
- API Docs: http://localhost:8080/docs

## CLI Commands

```bash
uv run server.py --help              # Show all commands
uv run server.py server --help       # Show server options
uv run server.py server --port 3000  # Override port
uv run server.py init-db             # Initialize database
uv run server.py seed                # Load idempotent demo data
uv run server.py create-project PREFIX "Name"  # Create project
```

## Configuration

Configuration is loaded from `.env` file with CLI overrides:

- `PORT` - Server port (default: 8080)
- `DATA_DIR` - Data directory (default: ./data)
- `DATABASE_URL` - Database URL (default: sqlite:///./data/jackrabbit.db)
- `LOG_LEVEL` - Log level (default: INFO)
- `ENVIRONMENT` - Environment (default: development)
- `DEBUG_SQL` - Echo every SQL statement (default: false)

## Project Structure

```
jackrabbit/
├── config.py       # Configuration management
├── database.py     # Database session management
├── models.py       # SQLModel models & API schemas
├── services.py     # Business logic services
├── api.py          # FastAPI REST API routes
├── web.py          # HTMX + Jinja2 web routes
├── cli.py          # Typer CLI commands
├── main.py         # FastAPI app factory
├── templates/      # Jinja2 templates
└── static/         # css/, js/, and vendored third-party assets

frontend/           # Tailwind build tooling (not needed to run the app)
```

## Development

```bash
# Run with auto-reload
uv run server.py server --reload

# Run tests
uv run pytest

# Lint
uv run ruff check .
uv run ruff format .

# Type check
uv run mypy jackrabbit
```

## End-to-end tests

The Playwright suite owns its server: `pytest tests/e2e` boots
`jackrabbit.main` on a free port with a throwaway `DATA_DIR` under pytest's temp
root (ADR-0023), so `./data` is never written and two runs in a row must both
pass (`make test-e2e-idempotent`). Set `E2E_BASE_URL` to point the suite at a
server you started yourself instead.

## Frontend assets

Every asset is served from `/static` — the app loads nothing from a CDN, so page
loads work offline (ADR-0022). htmx and its `json-enc` extension are vendored in
`jackrabbit/static/vendor/`; `jackrabbit/static/css/tailwind.css` is a
**committed build artifact** purged from the templates:

```bash
make build-css   # needs Node only at build time (frontend/package.json)
make css-check   # fails if the committed stylesheet is stale
```

Change Tailwind classes in a template → run `make build-css` and commit the
regenerated file, or `tests/unit/test_static_assets.py` fails.