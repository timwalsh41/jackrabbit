"""Database configuration and session management."""

from collections.abc import Generator

from alembic import command
from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from jackrabbit.config import get_settings


def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()  # type: ignore[attr-defined]


def get_engine() -> Engine:
    """Create database engine from settings."""
    settings = get_settings()
    engine = create_engine(settings.database_url, echo=settings.environment == "development")

    # Enable WAL mode for SQLite
    if settings.database_url.startswith("sqlite"):
        event.listen(engine, "connect", _set_sqlite_pragma)

    return engine


def run_migrations() -> None:
    """Run Alembic migrations to head."""
    settings = get_settings()
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(alembic_cfg, "head")


def init_db() -> None:
    """Initialize database by running migrations."""
    # Migrations are the source of truth for schema, not create_all
    run_migrations()


def get_session() -> Generator[Session, None, None]:
    """Get database session."""
    engine = get_engine()
    with Session(engine) as session:
        yield session


if __name__ == "__main__":
    # For direct execution
    init_db()
