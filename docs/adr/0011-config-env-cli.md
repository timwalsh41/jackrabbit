# ADR-0011: Configuration via .env + CLI Args

## Status
Accepted

## Context
Spec: "Deployable via script or simple tool that manages dependencies, takes in user configuration (such as the port to run the web server on, where to store state data, etc.)". Options:
- `.env` + CLI args override
- `config.toml` + `pyproject.toml`
- YAML config + env vars
- SQLite-backed config table

## Decision
**`.env` file with CLI argument overrides** (12-factor style).

### Config Keys
| Key | Description | Default |
|-----|-------------|---------|
| `PORT` | Web server port | `8080` |
| `DATA_DIR` | Directory for SQLite DB and uploads | `./data` |
| `DATABASE_URL` | SQLite connection string | `sqlite:///{DATA_DIR}/jackrabbit.db` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `ENVIRONMENT` | `development` / `production` | `development` |

### CLI Overrides
```bash
uv run server.py --port 3000 --data-dir /custom/path
```

## Consequences

### Positive
- **Simple** — one file, `KEY=VALUE` format, no parsing library needed
- **12-factor compliant** — env vars in production, `.env` in dev
- **Scriptable** — CI/CD, systemd, Docker all use env vars
- **CLI overrides** — easy to run multiple instances on different ports
- **No build step** — read at startup

### Negative
- **No nested config** — flat keys only (sufficient for this tool)
- **Type coercion** — all strings, app must parse (port → int)

### Implementation
- `python-dotenv` loads `.env` at startup
- `argparse` / `typer` for CLI args
- CLI args override env vars override defaults
- Validate required keys on startup

## Alternatives Considered
- **TOML**: Rejected — adds `tomllib`/`tomli` dependency; overkill for 5 keys.
- **YAML**: Rejected — same; PyYAML dependency.
- **SQLite config table**: Rejected — chicken-egg (need config to find DB); adds complexity.