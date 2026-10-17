"""CLI commands for Jackrabbit."""

import os
import sys
from collections.abc import Mapping
from pathlib import Path

import typer

from jackrabbit.config import get_settings

app = typer.Typer(help="Jackrabbit - Ticket tracking and sprint management")


# Environment variable names for each CLI override. The server command starts
# uvicorn, which re-imports ``jackrabbit.main:app`` in a fresh process; setting
# these env vars is how CLI flags (--port/--data-dir/--database-url/...) take
# effect there (pydantic-settings reads them at import/config time).
_ENV_OVERRIDES: dict[str, str] = {
    "port": "PORT",
    "data_dir": "DATA_DIR",
    "database_url": "DATABASE_URL",
    "log_level": "LOG_LEVEL",
    "environment": "ENVIRONMENT",
    "debug_sql": "DEBUG_SQL",
}


def apply_env_overrides(overrides: Mapping[str, str]) -> None:
    """Export CLI overrides as environment variables (in-process).

    Uvicorn imports the app in a fresh interpreter (possibly with --reload),
    which cannot see typer option values; environment variables are inherited
    by that process and picked up by pydantic-settings.
    """
    for key, value in overrides.items():
        os.environ[key] = value


_COMMANDS = {"server", "init_db", "create_project", "seed"}


def main(args: list[str] | None = None) -> None:
    """CLI entry point (``uv run server.py``).

    Defaults to the ``server`` command when no arguments are given (bare
    ``uv run server.py`` starts the server — spec: Deployment) and also when
    the first argument is not a command name (e.g. ``server.py --port 8177``).
    """
    argv = sys.argv[1:] if args is None else args
    if not argv:
        argv = ["server"]
    elif argv[0] not in _COMMANDS:
        argv = ["server", *argv]
    app(args=argv)


def _cli_overrides_to_env(
    port: int | None,
    data_dir: Path | None,
    database_url: str | None,
    log_level: str | None,
    environment: str | None,
    debug_sql: bool | None = None,
) -> dict[str, str]:
    """Map explicitly-provided CLI options to their environment variables."""
    provided: dict[str, str] = {}
    values = {
        "port": port,
        "data_dir": data_dir,
        "database_url": database_url,
        "log_level": log_level,
        "environment": environment,
        "debug_sql": debug_sql,
    }
    for field, value in values.items():
        if value is None:
            continue
        if isinstance(value, Path):
            value = str(value)
        provided[_ENV_OVERRIDES[field]] = str(value)
    return provided


@app.command()
def server(
    port: int | None = typer.Option(None, "--port", "-p", help="Server port"),
    data_dir: Path | None = typer.Option(None, "--data-dir", "-d", help="Data directory"),
    database_url: str | None = typer.Option(None, "--database-url", help="Database URL"),
    log_level: str | None = typer.Option(None, "--log-level", help="Log level"),
    environment: str | None = typer.Option(None, "--environment", "-e", help="Environment"),
    debug_sql: bool | None = typer.Option(
        None,
        "--debug-sql/--no-debug-sql",
        help="Echo every SQL statement (verbose; off by default)",
    ),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload"),
) -> None:
    """Start the FastAPI server with Uvicorn."""
    settings = get_settings(
        port=port,
        data_dir=data_dir,
        database_url=database_url,
        log_level=log_level,
        environment=environment,
        debug_sql=debug_sql,
    )

    # Propagate CLI overrides into the (fresh) uvicorn process via env vars;
    # otherwise --data-dir/--database-url/--port would be silently discarded.
    apply_env_overrides(
        _cli_overrides_to_env(
            port=port,
            data_dir=data_dir,
            database_url=database_url,
            log_level=log_level,
            environment=environment,
            debug_sql=debug_sql,
        )
    )

    import uvicorn

    uvicorn.run(
        "jackrabbit.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=reload,
        log_level=settings.log_level.lower(),
    )


@app.command()
def init_db() -> None:
    """Initialize the database tables."""
    from jackrabbit.database import init_db as init_db_func

    init_db_func()
    typer.echo("Database initialized.")


@app.command()
def create_project(
    prefix: str = typer.Argument(..., help="Project prefix (e.g., WEB)"),
    name: str = typer.Argument(..., help="Project name"),
    description: str = typer.Option("", "--description", "-d", help="Project description"),
    color: str = typer.Option("#6366f1", "--color", "-c", help="Project color (hex)"),
) -> None:
    """Create a new project."""
    from jackrabbit.database import get_session
    from jackrabbit.services import ProjectService

    session = next(get_session())
    service = ProjectService(session)
    project = service.create_project(prefix=prefix, name=name, description=description, color=color)
    typer.echo(f"Created project: {project.prefix} - {project.name}")


# Environments the seeder writes into on its own initiative. `development` is
# the default and `test` is what the suite runs under; anything else has to be
# forced, because ENVIRONMENT labels the process, not the data.
_SEED_SAFE_ENVIRONMENTS = frozenset({"development", "test"})


@app.command()
def seed(
    force: bool = typer.Option(
        False,
        "--force",
        help="Seed despite a non-development environment or existing non-demo tickets",
    ),
) -> None:
    """Populate the database with demo data.

    Idempotent: entities are matched on their natural key, so a second run
    reports "already present" and changes nothing. See jackrabbit/seed.py.

    Two safety checks, both overridable with --force: the environment must be
    development/test, and the database must not already hold tickets the seeder
    did not write, because demo rows would consume real ticket serial numbers.
    """
    from jackrabbit.database import get_session, init_db
    from jackrabbit.seed import count_foreign_tickets, seed_demo_data

    settings = get_settings()
    if settings.environment not in _SEED_SAFE_ENVIRONMENTS and not force:
        typer.echo(
            f"Refusing to write demo data while ENVIRONMENT={settings.environment}; "
            "pass --force to override.",
            err=True,
        )
        raise typer.Exit(code=1)

    init_db()
    session = next(get_session())

    foreign = count_foreign_tickets(session)
    if foreign and not force:
        typer.echo(
            f"Refusing to seed: this database holds {foreign} ticket(s) the seeder did not "
            "create, and demo rows would consume real ticket serial numbers.\n"
            "  pass --force to seed anyway, or use `make db-reset` for a throwaway database.",
            err=True,
        )
        raise typer.Exit(code=1)

    result = seed_demo_data(session)
    typer.echo(result.summary())


if __name__ == "__main__":
    app()
