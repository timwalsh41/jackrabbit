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
uv run server.py create-project PREFIX "Name"  # Create project
```

## Configuration

Configuration is loaded from `.env` file with CLI overrides:

- `PORT` - Server port (default: 8080)
- `DATA_DIR` - Data directory (default: ./data)
- `DATABASE_URL` - Database URL (default: sqlite:///./data/jackrabbit.db)
- `LOG_LEVEL` - Log level (default: INFO)
- `ENVIRONMENT` - Environment (default: development)

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
└── static/         # Static assets
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