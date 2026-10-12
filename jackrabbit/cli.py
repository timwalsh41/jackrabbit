"""CLI commands for Jackrabbit."""

from pathlib import Path

import typer

from jackrabbit.config import get_settings

app = typer.Typer(help="Jackrabbit - Ticket tracking and sprint management")


@app.command()
def server(
    port: int | None = typer.Option(None, "--port", "-p", help="Server port"),
    data_dir: Path | None = typer.Option(None, "--data-dir", "-d", help="Data directory"),
    database_url: str | None = typer.Option(None, "--database-url", help="Database URL"),
    log_level: str | None = typer.Option(None, "--log-level", help="Log level"),
    environment: str | None = typer.Option(None, "--environment", "-e", help="Environment"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload"),
) -> None:
    """Start the FastAPI server with Uvicorn."""
    settings = get_settings(
        port=port,
        data_dir=data_dir,
        database_url=database_url,
        log_level=log_level,
        environment=environment,
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


if __name__ == "__main__":
    app()
