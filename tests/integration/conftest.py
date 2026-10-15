"""Integration test fixtures - client wired to a seeded database."""

from collections.abc import AsyncGenerator
from pathlib import Path

import httpx
import pytest
from jackrabbit.config import Settings, get_settings
from jackrabbit.main import create_app
from jackrabbit.models import Project
from jackrabbit.services import ProjectService
from sqlmodel import Session


@pytest.fixture
async def client_with_seeds(test_db: Session) -> AsyncGenerator[httpx.AsyncClient, None]:
    """httpx.AsyncClient against the app with a seeded DB (UNS + 2 test projects)."""
    project_service = ProjectService(test_db)

    # System project (UNS) - ID will be 1
    project_service.create_project(
        prefix="UNS",
        name="Unsorted",
        description="Default unsorted project",
        color="#9ca3af",
        is_system=True,
    )

    # Two regular test projects (WEB=2, API=3)
    project_service.create_project(
        prefix="WEB",
        name="Web Application",
        description="Frontend web application",
        color="#6366f1",
    )

    project_service.create_project(
        prefix="API",
        name="Backend API",
        description="REST API service",
        color="#10b981",
    )

    def get_test_session():
        yield test_db

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        environment="test",
        database_url="sqlite://",
        data_dir=Path("./data"),
        port=0,
        log_level="DEBUG",
    )

    from jackrabbit.database import get_session

    app.dependency_overrides[get_session] = get_test_session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(base_url="http://test", transport=transport) as async_client:
        yield async_client

    app.dependency_overrides.clear()


@pytest.fixture
def seeded_projects(test_db: Session) -> list[Project]:
    """Expose the seeded projects as model objects (UNS, WEB, API)."""
    from sqlmodel import select

    return list(test_db.exec(select(Project)).all())
