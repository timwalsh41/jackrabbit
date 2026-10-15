"""Unit tests for ticket project move functionality."""

import pytest
from jackrabbit.database import init_db
from jackrabbit.models import (
    Priority,
    Project,
    TicketStatus,
    TicketType,
)
from jackrabbit.services import ProjectService, TicketService
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine


def get_test_engine():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return engine


def get_test_session(engine):
    """Create a test session with initialized schema."""
    from jackrabbit.models import SQLModel

    SQLModel.metadata.create_all(engine)
    # Seed UNS project
    with Session(engine) as session:
        uns = Project(
            id=1,
            prefix="UNS",
            name="Unsorted",
            description="Default",
            color="#9ca3af",
            is_system=True,
        )
        session.add(uns)
        session.commit()
    return Session(engine)


@pytest.fixture
def session():
    engine = get_test_engine()
    session = get_test_session(engine)
    yield session
    session.close()


@pytest.fixture
def ticket_service(session):
    return TicketService(session)


@pytest.fixture
def project_service(session):
    return ProjectService(session)


@pytest.fixture
def setup_projects(session, project_service):
    """Create test projects."""
    uns = project_service.get_project_by_prefix("UNS")
    web = project_service.create_project(prefix="WEB", name="Web Project", color="#3b82f6")
    api = project_service.create_project(prefix="API", name="API Project", color="#10b981")
    return {"uns": uns, "web": web, "api": api}


@pytest.fixture
def test_ticket(session, ticket_service, setup_projects):
    """Create a test ticket in UNS project."""
    ticket = ticket_service.create_ticket(
        project_id=setup_projects["uns"].id,
        title="Test Ticket",
        type=TicketType.STORY,
    )
    return ticket


class TestMoveTicketToProject:
    """Tests for move_ticket_to_project method."""

    def test_move_ticket_to_different_project(self, ticket_service, test_ticket, setup_projects):
        """Move ticket from UNS to WEB project."""
        uns = setup_projects["uns"]
        web = setup_projects["web"]

        # Verify initial state
        assert test_ticket.project_id == uns.id
        assert test_ticket.number == 1
        assert test_ticket.original_id is None
        assert test_ticket.full_id == "UNS-1"

        # Move to WEB
        result = ticket_service.move_ticket_to_project(test_ticket.id, web.id)

        # Check result
        assert result["ticket_id"] == test_ticket.id
        assert result["old_project_id"] == uns.id
        assert result["new_project_id"] == web.id
        assert result["old_full_id"] == "UNS-1"
        assert result["new_full_id"] == "WEB-1"
        assert result["original_id"] == "UNS-1"

        # Refresh ticket
        ticket_service.session.refresh(test_ticket)
        assert test_ticket.project_id == web.id
        assert test_ticket.number == 1
        assert test_ticket.original_id == "UNS-1"
        assert test_ticket.full_id == "WEB-1"

    def test_move_ticket_preserves_original_id_on_second_move(
        self, ticket_service, test_ticket, setup_projects
    ):
        """Moving already-moved ticket preserves first original_id."""
        web = setup_projects["web"]
        api = setup_projects["api"]

        # First move: UNS -> WEB
        ticket_service.move_ticket_to_project(test_ticket.id, web.id)
        ticket_service.session.refresh(test_ticket)
        assert test_ticket.original_id == "UNS-1"
        assert test_ticket.full_id == "WEB-1"

        # Second move: WEB -> API
        result = ticket_service.move_ticket_to_project(test_ticket.id, api.id)

        # Check result preserves original original_id
        assert result["original_id"] == "UNS-1"
        assert result["old_full_id"] == "WEB-1"
        assert result["new_full_id"] == "API-1"

        ticket_service.session.refresh(test_ticket)
        assert test_ticket.project_id == api.id
        assert test_ticket.original_id == "UNS-1"
        assert test_ticket.full_id == "API-1"

    def test_move_ticket_assigns_next_number_in_target_project(
        self, ticket_service, setup_projects
    ):
        """Moving ticket assigns next available number in target project."""
        web = setup_projects["web"]

        # Create two tickets in WEB project
        ticket1 = ticket_service.create_ticket(project_id=web.id, title="Ticket 1")
        ticket2 = ticket_service.create_ticket(project_id=web.id, title="Ticket 2")
        assert ticket1.number == 1
        assert ticket2.number == 2

        # Create ticket in UNS and move to WEB
        uns = setup_projects["uns"]
        ticket3 = ticket_service.create_ticket(project_id=uns.id, title="Ticket 3")
        assert ticket3.number == 1

        # Move to WEB - should get number 3
        result = ticket_service.move_ticket_to_project(ticket3.id, web.id)
        assert result["new_full_id"] == "WEB-3"

        ticket_service.session.refresh(ticket3)
        assert ticket3.number == 3

    def test_move_ticket_same_project_raises_error(
        self, ticket_service, test_ticket, setup_projects
    ):
        """Moving ticket to same project raises ValueError."""
        uns = setup_projects["uns"]

        with pytest.raises(ValueError) as exc_info:
            ticket_service.move_ticket_to_project(test_ticket.id, uns.id)
        assert "already in this project" in str(exc_info.value)

    def test_move_ticket_nonexistent_ticket_raises_error(self, ticket_service, setup_projects):
        """Moving nonexistent ticket raises ValueError."""
        web = setup_projects["web"]

        with pytest.raises(ValueError) as exc_info:
            ticket_service.move_ticket_to_project(99999, web.id)
        assert "not found" in str(exc_info.value)

    def test_move_ticket_nonexistent_project_raises_error(
        self, ticket_service, test_ticket, setup_projects
    ):
        """Moving ticket to nonexistent project raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            ticket_service.move_ticket_to_project(test_ticket.id, 99999)
        assert "not found" in str(exc_info.value)

    def test_move_ticket_with_various_fields(self, ticket_service, test_ticket, setup_projects):
        """Moving ticket preserves all other fields."""
        web = setup_projects["web"]

        # Set various fields on ticket
        test_ticket.description = "Test description"
        test_ticket.type = TicketType.BUG
        test_ticket.priority = Priority.HIGH
        test_ticket.story_points = 5
        test_ticket.approach = "Test approach"
        test_ticket.files_to_change = "test.py"
        test_ticket.test_plan = "Test plan"
        test_ticket.validation_steps = "Validate"
        test_ticket.branch_name = "feature/test"
        test_ticket.pr_url = "https://github.com/test/pull/1"
        test_ticket.status = TicketStatus.GROOMED
        ticket_service.session.add(test_ticket)
        ticket_service.session.commit()

        # Move ticket
        ticket_service.move_ticket_to_project(test_ticket.id, web.id)
        ticket_service.session.refresh(test_ticket)

        # Verify all fields preserved
        assert test_ticket.description == "Test description"
        assert test_ticket.type == TicketType.BUG
        assert test_ticket.priority == Priority.HIGH
        assert test_ticket.story_points == 5
        assert test_ticket.approach == "Test approach"
        assert test_ticket.files_to_change == "test.py"
        assert test_ticket.test_plan == "Test plan"
        assert test_ticket.validation_steps == "Validate"
        assert test_ticket.branch_name == "feature/test"
        assert test_ticket.pr_url == "https://github.com/test/pull/1"
        assert test_ticket.status == TicketStatus.GROOMED
        assert test_ticket.sprint_id is None  # sprint_id preserved (None)


class TestMoveProjectAPI:
    """Integration tests for the move project API endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        import os

        os.environ["DATABASE_URL"] = "sqlite:///./data/test_move.db"
        from jackrabbit.main import create_app

        app = create_app()
        init_db()

        from fastapi.testclient import TestClient

        client = TestClient(app)
        yield client
        # Cleanup
        import os

        if os.path.exists("./data/test_move.db"):
            os.remove("./data/test_move.db")

    def test_move_project_endpoint(self, client):
        """Test POST /tickets/{id}/move-project endpoint."""
        # Create projects
        client.post("/api/v1/projects", json={"prefix": "WEB", "name": "Web Project"})
        client.post("/api/v1/projects", json={"prefix": "API", "name": "API Project"})

        # Create ticket in UNS (project_id=1)
        response = client.post("/api/v1/tickets", json={"project_id": 1, "title": "Test Ticket"})
        ticket_id = response.json()["id"]

        # Move to WEB (project_id=2)
        response = client.post(f"/api/v1/tickets/{ticket_id}/move-project", json={"project_id": 2})
        assert response.status_code == 200
        data = response.json()
        assert data["old_full_id"] == "UNS-1"
        assert data["new_full_id"] == "WEB-1"
        assert data["original_id"] == "UNS-1"

        # Verify ticket updated
        response = client.get(f"/api/v1/tickets/{ticket_id}")
        assert response.json()["project_id"] == 2
        assert response.json()["number"] == 1
        assert response.json()["original_id"] == "UNS-1"

    def test_move_project_already_moved_preserves_first_original_id(self, client):
        """Test moving already-moved ticket preserves first original_id via API."""
        # Create projects
        client.post("/api/v1/projects", json={"prefix": "WEB", "name": "Web Project"})
        client.post("/api/v1/projects", json={"prefix": "API", "name": "API Project"})
        client.post("/api/v1/projects", json={"prefix": "MOB", "name": "Mobile Project"})

        # Create ticket in UNS
        response = client.post("/api/v1/tickets", json={"project_id": 1, "title": "Test Ticket"})
        ticket_id = response.json()["id"]

        # First move: UNS -> WEB
        response = client.post(f"/api/v1/tickets/{ticket_id}/move-project", json={"project_id": 2})
        assert response.status_code == 200
        assert response.json()["original_id"] == "UNS-1"

        # Second move: WEB -> API
        response = client.post(f"/api/v1/tickets/{ticket_id}/move-project", json={"project_id": 3})
        assert response.status_code == 200
        assert response.json()["original_id"] == "UNS-1"
        assert response.json()["old_full_id"] == "WEB-1"
        assert response.json()["new_full_id"] == "API-1"

        # Third move: API -> MOB
        response = client.post(f"/api/v1/tickets/{ticket_id}/move-project", json={"project_id": 4})
        assert response.status_code == 200
        assert response.json()["original_id"] == "UNS-1"
        assert response.json()["old_full_id"] == "API-1"
        assert response.json()["new_full_id"] == "MOB-1"

    def test_move_project_same_project_returns_400(self, client):
        """Moving to same project returns 400."""
        response = client.post("/api/v1/tickets", json={"project_id": 1, "title": "Test Ticket"})
        ticket_id = response.json()["id"]

        response = client.post(f"/api/v1/tickets/{ticket_id}/move-project", json={"project_id": 1})
        assert response.status_code == 400
        assert "already in this project" in response.json()["detail"]

    def test_move_project_nonexistent_ticket_returns_404(self, client):
        """Moving nonexistent ticket returns 404."""
        client.post("/api/v1/projects", json={"prefix": "WEB", "name": "Web Project"})
        response = client.post("/api/v1/tickets/99999/move-project", json={"project_id": 2})
        assert response.status_code == 404

    def test_move_project_nonexistent_project_returns_400(self, client):
        """Moving to nonexistent project returns 400."""
        response = client.post("/api/v1/tickets", json={"project_id": 1, "title": "Test Ticket"})
        ticket_id = response.json()["id"]

        response = client.post(
            f"/api/v1/tickets/{ticket_id}/move-project", json={"project_id": 99999}
        )
        assert response.status_code == 400
        assert "not found" in response.json()["detail"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
