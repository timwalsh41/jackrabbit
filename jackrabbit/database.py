"""Database configuration and session management."""

from collections.abc import Generator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from jackrabbit.config import get_settings

# Repo root, resolved from this file: alembic.ini and script_location are
# relative to CWD by default, which made `init_db()` (and therefore app
# startup, which calls it in its lifespan) fail whenever the server was started
# from anywhere other than the repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent


def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()  # type: ignore[attr-defined]


# Engine cache keyed by database URL. Settings are re-read on every call so
# env/settings overrides (see tests/conftest.py) are still honored — a changed
# DATABASE_URL simply builds (and caches) a new engine instead of reusing a
# stale one. Engines are otherwise pooled objects and must not be recreated per
# request (get_session used to call get_engine() on every request).
_engines: dict[str, Engine] = {}


def get_engine() -> Engine:
    """Return a cached engine for the current settings' database URL."""
    settings = get_settings()
    url = settings.database_url
    engine = _engines.get(url)
    if engine is None:
        # SQL echo is an explicit operator choice (DEBUG_SQL), not a side effect
        # of running in development.
        engine = create_engine(url, echo=settings.debug_sql)

        # Enable WAL mode for SQLite
        if url.startswith("sqlite"):
            event.listen(engine, "connect", _set_sqlite_pragma)

        _engines[url] = engine
    return engine


def run_migrations() -> None:
    """Run Alembic migrations to head."""
    settings = get_settings()
    alembic_cfg = Config(str(REPO_ROOT / "alembic.ini"))
    # Absolute paths keep migrations working from any CWD.
    alembic_cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
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
