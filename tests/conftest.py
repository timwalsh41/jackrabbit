"""Shared test fixtures for Jackrabbit unit and integration tests."""

from collections.abc import Generator
from pathlib import Path

import pytest
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
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


# Override settings for testing
@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Create test settings with in-memory database."""
    return Settings(
        environment="test",
        database_url="sqlite://",
        data_dir=Path("./data"),
        log_level="DEBUG",
    )


@pytest.fixture(scope="session")
def test_engine(test_settings: Settings):
    """Create a test database engine."""
    engine = create_engine(
        test_settings.database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Create all tables
    SQLModel.metadata.create_all(engine)
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
def client(test_db: Session) -> Generator[TestClient, None, None]:
    """Create a test client with the test database session."""

    def get_test_session():
        yield test_db

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        environment="test",
        database_url="sqlite://",
        data_dir=Path("./data"),
        log_level="DEBUG",
    )

    # Override the database session dependency
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

    # Regular projects
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

    mobile = project_service.create_project(
        prefix="MOB",
        name="Mobile App",
        description="Mobile application",
        color="#f59e0b",
    )

    return [uns, web, api, mobile]


@pytest.fixture
def seeded_tickets(test_db: Session, seeded_projects: list[Project]) -> list[Ticket]:
    """Create seeded tickets for testing."""
    ticket_service = TicketService(test_db)

    uns, web, api, mobile = seeded_projects

    tickets = []

    # Tickets in UNS project
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

    # Tickets in WEB project
    tickets.append(
        ticket_service.create_ticket(
            project_id=web.id,
            title="Redesign dashboard",
            type=TicketType.EPIC,
            priority=Priority.HIGH,
            description="Complete dashboard redesign",
        )
    )

    tickets.append(
        ticket_service.create_ticket(
            project_id=web.id,
            title="Implement new header component",
            type=TicketType.STORY,
            priority=Priority.MEDIUM,
            description="New responsive header",
        )
    )

    # Tickets in API project
    tickets.append(
        ticket_service.create_ticket(
            project_id=api.id,
            title="Add rate limiting",
            type=TicketType.STORY,
            priority=Priority.CRITICAL,
            description="Implement rate limiting on all endpoints",
        )
    )

    tickets.append(
        ticket_service.create_ticket(
            project_id=api.id,
            title="Optimize database queries",
            type=TicketType.SPIKE,
            priority=Priority.MEDIUM,
            description="Investigate slow query performance",
        )
    )

    # Tickets in MOB project
    tickets.append(
        ticket_service.create_ticket(
            project_id=mobile.id,
            title="Fix crash on startup",
            type=TicketType.BUG,
            priority=Priority.CRITICAL,
            description="App crashes on cold start",
        )
    )

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
    ticket_service.transition(
        ticket,
        TicketStatus.READY_FOR_REVIEW,
        "PR opened",
    )
    return ticket
