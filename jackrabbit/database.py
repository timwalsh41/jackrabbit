"""Database configuration and session management."""

from collections.abc import Generator

from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from jackrabbit.config import get_settings


def get_engine() -> Engine:
    """Create database engine from settings."""
    settings = get_settings()
    return create_engine(settings.database_url, echo=settings.environment == "development")


def init_db() -> None:
    """Initialize database tables."""
    engine = get_engine()
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    """Get database session."""
    engine = get_engine()
    with Session(engine) as session:
        yield session
