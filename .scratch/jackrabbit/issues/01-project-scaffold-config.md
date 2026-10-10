# 01: Project scaffold & config

**What to build:** Initialize the Python project with `pyproject.toml`, `.env.example`, directory structure, and a `config.py` that loads settings from `.env` + CLI overrides. Running `uv run server.py` starts an empty FastAPI app on the configured port.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `pyproject.toml` with dependencies: fastapi, uvicorn, sqlmodel, alembic, httpx, jinja2, python-dotenv, typer, pytest, pytest-asyncio, playwright
- [ ] `.env.example` with keys: PORT, DATA_DIR, DATABASE_URL, LOG_LEVEL, ENVIRONMENT
- [ ] Directory structure: `jackrabbit/{config,database,models,services,api,web,cli}.py` + `tests/{unit,integration,e2e}/`
- [ ] `config.py` using `pydantic-settings` / `python-dotenv` + `typer` for CLI overrides
- [ ] `cli.py` with `server` command that starts FastAPI + Uvicorn
- [ ] `uv run server.py --help` shows config options
- [ ] `uv run server.py` starts server on PORT (default 8080) with empty "/" route