"""Shared test fixtures for Jackrabbit unit and integration tests."""

import os
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from jackrabbit.config import Settings, get_settings
from jackrabbit.main import create_app
from jackrabbit.models import (
    Priority,
    Project,
    Sprint,
    Ticket,
    TicketStatus,
    TicketType,
)
from jackrabbit.services import ProjectService, SprintService, TicketService
from sqlmodel import Session, SQLModel, create_engine

REPO_ROOT = Path(__file__).resolve().parents[1]


# Override settings for testing
@pytest.fixture(scope="session")
def test_settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    """Test settings: DATA_DIR in a temp dir, PORT=0 (pick a free port)."""
    return Settings(
        environment="test",
        database_url="sqlite://",
        data_dir=tmp_path_factory.mktemp("jackrabbit-data"),
        port=0,
        log_level="DEBUG",
    )


@pytest.fixture(scope="module")
def test_engine(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory):
    """Fresh SQLite *file* database per test module, in a pytest temp directory.

    The schema is applied via Alembic migrations (the schema source of truth),
    not ``create_all``. Individual tests get isolation from the ``test_db``
    fixture, which drops/recreates the tables inside this module-scoped file.
    """
    module_name = request.module.__name__.rsplit(".", 1)[-1]
    db_dir = tmp_path_factory.mktemp(f"{module_name}-db")
    db_path = db_dir / "test.db"
    database_url = f"sqlite:///{db_path}"

    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    # Apply migrations. Alembic's env.py resolves the URL from settings, so the
    # DATABASE_URL env var must point at this module's temp database.
    old_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        alembic_cfg = Config(str(REPO_ROOT / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
        command.upgrade(alembic_cfg, "head")
    finally:
        if old_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_url

    yield engine
    engine.dispose()


@pytest.fixture
def test_db(test_engine) -> Generator[Session, None, None]:
    """Create a fresh database session for each test."""
    # Create tables fresh for each test
    SQLModel.metadata.drop_all(test_engine)
    SQLModel.metadata.create_all(test_engine)

    with Session(test_engine) as session:
        yield session


@pytest.fixture
async def client(test_db: Session) -> AsyncGenerator[httpx.AsyncClient, None]:
    """httpx.AsyncClient wired to the app with the test database session.

    httpx no longer accepts ``app=`` directly; ASGITransport is the supported
    equivalent for ``httpx.AsyncClient(app=app, base_url="http://test")``.
    """

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

    # Override the database session dependency
    from jackrabbit.database import get_session

    app.dependency_overrides[get_session] = get_test_session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(base_url="http://test", transport=transport) as async_client:
        yield async_client

    app.dependency_overrides.clear()


@pytest.fixture
def sync_client(test_db: Session) -> Generator[TestClient, None, None]:
    """Legacy sync TestClient (kept for unit-level endpoint spot checks)."""

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

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def seeded_projects(test_db: Session) -> list[Project]:
    """Create seeded projects for testing."""
    project_service = ProjectService(test_db)

    # System project (UNS)
    uns = project_service.create_project(
        prefix="UNS",
        name="Unsorted",
        description="Default unsorted project",
        color="#9ca3af",
        is_system=True,
    )

    # Two regular test projects
    web = project_service.create_project(
        prefix="WEB",
        name="Web Application",
        description="Frontend web application",
        color="#6366f1",
    )

    api = project_service.create_project(
        prefix="API",
        name="Backend API",
        description="REST API service",
        color="#10b981",
    )

    return [uns, web, api]


@pytest.fixture
def seeded_tickets(test_db: Session, seeded_projects: list[Project]) -> list[Ticket]:
    """Create tickets in various states (Open, Groomed, In Progress, Ready for Review)."""
    ticket_service = TicketService(test_db)

    uns, web, api = seeded_projects

    tickets = []

    # Two plain Open tickets in UNS
    tickets.append(
        ticket_service.create_ticket(
            project_id=uns.id,
            title="Fix login bug",
            type=TicketType.BUG,
            priority=Priority.HIGH,
            description="Users cannot login with OAuth",
        )
    )

    tickets.append(
        ticket_service.create_ticket(
            project_id=uns.id,
            title="Add dark mode toggle",
            type=TicketType.STORY,
            priority=Priority.MEDIUM,
            description="Add a dark/light mode toggle to settings",
        )
    )

    # Groomed ticket in WEB (carries the 4 grooming fields)
    tickets.append(
        ticket_service.create_ticket(
            project_id=web.id,
            title="Redesign dashboard",
            type=TicketType.EPIC,
            priority=Priority.HIGH,
            description="Complete dashboard redesign",
            approach="Redesign with new design system",
            files_to_change="dashboard.py, templates/dashboard.html",
            test_plan="Unit + E2E tests",
            validation_steps="Visual check on staging",
        )
    )
    ticket_service.transition(tickets[-1], TicketStatus.GROOMED, "Ready for development")

    # In Progress ticket in WEB (branch auto-generated on transition)
    tickets.append(
        ticket_service.create_ticket(
            project_id=web.id,
            title="Implement new header component",
            type=TicketType.STORY,
            priority=Priority.MEDIUM,
            description="New responsive header",
            approach="Extract header into component",
            files_to_change="header.py",
            test_plan="Unit tests",
            validation_steps="Manual check",
        )
    )
    ticket_service.transition(tickets[-1], TicketStatus.GROOMED, "Ready")
    ticket_service.transition(tickets[-1], TicketStatus.IN_PROGRESS, "Started work")

    # Ready for Review ticket in API (PR URL provided at transition time)
    tickets.append(
        ticket_service.create_ticket(
            project_id=api.id,
            title="Add rate limiting",
            type=TicketType.STORY,
            priority=Priority.CRITICAL,
            description="Implement rate limiting on all endpoints",
            approach="Token bucket middleware",
            files_to_change="api.py",
            test_plan="Integration tests",
            validation_steps="Load test on staging",
        )
    )
    ticket_service.transition(tickets[-1], TicketStatus.GROOMED, "Ready")
    ticket_service.transition(tickets[-1], TicketStatus.IN_PROGRESS, "Started work")
    tickets[-1].pr_url = "https://github.com/test/repo/pull/1"
    ticket_service.transition(tickets[-1], TicketStatus.READY_FOR_REVIEW, "PR opened")

    return tickets


@pytest.fixture
def seeded_sprints(test_db: Session) -> list[Sprint]:
    """Create seeded sprints for testing."""
    sprint_service = SprintService(test_db)

    sprints = []

    sprints.append(
        sprint_service.create_sprint(
            number=2601,
            name="Sprint 2601",
            description="First sprint of 2026",
        )
    )

    sprints.append(
        sprint_service.create_sprint(
            number=2602,
            name="Sprint 2602",
            description="Second sprint of 2026",
        )
    )

    return sprints


@pytest.fixture
def ticket_service(test_db: Session) -> TicketService:
    """Create a TicketService instance."""
    return TicketService(test_db)


@pytest.fixture
def project_service(test_db: Session) -> ProjectService:
    """Create a ProjectService instance."""
    return ProjectService(test_db)


@pytest.fixture
def sprint_service(test_db: Session) -> SprintService:
    """Create a SprintService instance."""
    return SprintService(test_db)


# Helper fixtures for specific test scenarios
@pytest.fixture
def groomed_ticket(test_db: Session, seeded_projects: list[Project]) -> Ticket:
    """Create a ticket in GROOMED status with all required fields."""
    uns = seeded_projects[0]
    ticket_service = TicketService(test_db)

    ticket = ticket_service.create_ticket(
        project_id=uns.id,
        title="Well groomed ticket",
        type=TicketType.STORY,
        priority=Priority.MEDIUM,
        approach="Implement feature X",
        files_to_change="file1.py, file2.py",
        test_plan="Unit tests + integration tests",
        validation_steps="1. Run tests 2. Manual verification",
    )
    # Transition to GROOMED
    ticket_service.transition(ticket, TicketStatus.GROOMED, "Ready for development")
    return ticket


@pytest.fixture
def in_progress_ticket(test_db: Session, seeded_projects: list[Project]) -> Ticket:
    """Create a ticket in IN_PROGRESS status with branch."""
    uns = seeded_projects[0]
    ticket_service = TicketService(test_db)

    ticket = ticket_service.create_ticket(
        project_id=uns.id,
        title="In progress ticket",
        type=TicketType.STORY,
        priority=Priority.MEDIUM,
        approach="Implement feature Y",
        files_to_change="file3.py",
        test_plan="Unit tests",
        validation_steps="Run tests",
    )
    ticket_service.transition(ticket, TicketStatus.GROOMED, "Ready")
    ticket_service.transition(ticket, TicketStatus.IN_PROGRESS, "Started work")
    return ticket


@pytest.fixture
def ready_for_review_ticket(test_db: Session, seeded_projects: list[Project]) -> Ticket:
    """Create a ticket in READY_FOR_REVIEW status with PR URL."""
    uns = seeded_projects[0]
    ticket_service = TicketService(test_db)

    ticket = ticket_service.create_ticket(
        project_id=uns.id,
        title="Ready for review ticket",
        type=TicketType.STORY,
        priority=Priority.MEDIUM,
        approach="Implement feature Z",
        files_to_change="file4.py",
        test_plan="Unit tests",
        validation_steps="Run tests",
    )
    ticket_service.transition(ticket, TicketStatus.GROOMED, "Ready")
    ticket_service.transition(ticket, TicketStatus.IN_PROGRESS, "Started work")
    ticket.pr_url = "https://github.com/test/repo/pull/1"
    ticket_service.transition(ticket, TicketStatus.READY_FOR_REVIEW, "PR opened")
    return ticket
