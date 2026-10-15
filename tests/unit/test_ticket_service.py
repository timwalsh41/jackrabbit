"""Unit tests for TicketService: CRUD, numbering, listing, details, transitions."""

import pytest
from jackrabbit.models import (
    LinkType,
    Priority,
    Project,
    TicketStatus,
    TicketType,
    Transition,
)
from jackrabbit.services import LinkService, ProjectService, TicketService
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select


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
def link_service(session):
    return LinkService(session)


@pytest.fixture
def setup_projects(project_service):
    """UNS (seeded) plus WEB and API projects."""
    uns = project_service.get_project_by_prefix("UNS")
    web = project_service.create_project(prefix="WEB", name="Web Project")
    api = project_service.create_project(prefix="API", name="API Project")
    return {"uns": uns, "web": web, "api": api}


@pytest.fixture
def sample_ticket(ticket_service, setup_projects):
    return ticket_service.create_ticket(
        project_id=setup_projects["web"].id, title="Sample Ticket", type=TicketType.STORY
    )


class TestCreateTicket:
    """Tests for create_ticket numbering and defaults."""

    def test_defaults(self, ticket_service, setup_projects):
        ticket = ticket_service.create_ticket(project_id=setup_projects["web"].id, title="First")
        assert ticket.number == 1
        assert ticket.status == TicketStatus.OPEN
        assert ticket.type == TicketType.STORY
        assert ticket.priority == Priority.MEDIUM
        assert ticket.id is not None

    def test_numbering_is_sequential_within_project(self, ticket_service, setup_projects):
        web_id = setup_projects["web"].id
        t1 = ticket_service.create_ticket(project_id=web_id, title="One")
        t2 = ticket_service.create_ticket(project_id=web_id, title="Two")
        t3 = ticket_service.create_ticket(project_id=web_id, title="Three")
        assert [t1.number, t2.number, t3.number] == [1, 2, 3]

    def test_numbering_is_independent_per_project(self, ticket_service, setup_projects):
        web_ticket = ticket_service.create_ticket(project_id=setup_projects["web"].id, title="Web")
        api_ticket = ticket_service.create_ticket(project_id=setup_projects["api"].id, title="Api")
        assert web_ticket.number == 1
        assert api_ticket.number == 1

    def test_number_reuses_highest_after_delete(self, ticket_service, setup_projects):
        web_id = setup_projects["web"].id
        t1 = ticket_service.create_ticket(project_id=web_id, title="One")
        ticket_service.create_ticket(project_id=web_id, title="Two")
        ticket_service.create_ticket(project_id=web_id, title="Three")
        ticket_service.delete_ticket(t1.id + 2)
        t4 = ticket_service.create_ticket(project_id=web_id, title="Four")
        # max remaining number is 2, so the next number is 3
        assert t4.number == 3

    def test_full_creation_options(self, ticket_service, setup_projects):
        ticket = ticket_service.create_ticket(
            project_id=setup_projects["api"].id,
            title="Full ticket",
            type=TicketType.BUG,
            description="A bug",
            priority=Priority.HIGH,
            story_points=5,
            approach="Do the thing",
            files_to_change="a.py",
            test_plan="unit tests",
            validation_steps="run tests",
            status=TicketStatus.GROOMED,
        )
        assert ticket.type == TicketType.BUG
        assert ticket.priority == Priority.HIGH
        assert ticket.story_points == 5
        assert ticket.status == TicketStatus.GROOMED


class TestTicketLookup:
    """Tests for get_ticket and get_ticket_by_full_id."""

    def test_get_ticket(self, ticket_service, sample_ticket):
        assert ticket_service.get_ticket(sample_ticket.id) is not None
        assert ticket_service.get_ticket(9999) is None

    def test_get_ticket_by_full_id(self, ticket_service, sample_ticket):
        found = ticket_service.get_ticket_by_full_id("WEB", 1)
        assert found is not None
        assert found.id == sample_ticket.id

    def test_get_ticket_by_full_id_prefix_is_case_insensitive(self, ticket_service, sample_ticket):
        found = ticket_service.get_ticket_by_full_id("web", 1)
        assert found is not None
        assert found.id == sample_ticket.id

    def test_get_ticket_by_full_id_unknown_prefix(self, ticket_service):
        assert ticket_service.get_ticket_by_full_id("NOPE", 1) is None

    def test_get_ticket_by_full_id_wrong_number(self, ticket_service, sample_ticket):
        assert ticket_service.get_ticket_by_full_id("WEB", 99) is None


class TestTicketUpdates:
    """Tests for update_ticket and legacy update_status."""

    def test_update_ticket_sets_fields(self, ticket_service, sample_ticket):
        updated = ticket_service.update_ticket(
            sample_ticket, title="Renamed", priority=Priority.CRITICAL, story_points=8
        )
        assert updated.title == "Renamed"
        assert updated.priority == Priority.CRITICAL
        assert updated.story_points == 8

    def test_update_status_sets_completed_at(self, ticket_service, sample_ticket):
        ticket = ticket_service.update_status(sample_ticket, TicketStatus.COMPLETE)
        assert ticket.status == TicketStatus.COMPLETE
        assert ticket.completed_at is not None

    def test_update_status_without_complete_leaves_completed_at(
        self, ticket_service, sample_ticket
    ):
        ticket = ticket_service.update_status(sample_ticket, TicketStatus.IN_PROGRESS)
        assert ticket.status == TicketStatus.IN_PROGRESS
        assert ticket.completed_at is None


class TestDeleteTicket:
    def test_delete_existing_ticket(self, ticket_service, sample_ticket):
        assert ticket_service.delete_ticket(sample_ticket.id) is True
        assert ticket_service.get_ticket(sample_ticket.id) is None

    def test_delete_missing_ticket(self, ticket_service):
        assert ticket_service.delete_ticket(9999) is False


class TestListTickets:
    @pytest.fixture
    def many_tickets(self, ticket_service, setup_projects):
        """WEB: 3 tickets; API: 2 tickets with varied status/type."""
        web_id = setup_projects["web"].id
        api_id = setup_projects["api"].id
        t1 = ticket_service.create_ticket(project_id=web_id, title="Login bug", type=TicketType.BUG)
        t2 = ticket_service.create_ticket(
            project_id=web_id, title="Dark mode", type=TicketType.STORY
        )
        t3 = ticket_service.create_ticket(
            project_id=web_id, title="Query research", type=TicketType.SPIKE
        )
        t4 = ticket_service.create_ticket(
            project_id=api_id, title="Rate limiting", type=TicketType.STORY
        )
        t5 = ticket_service.create_ticket(
            project_id=api_id, title="Login page cache", type=TicketType.BUG
        )
        return [t1, t2, t3, t4, t5]

    def test_filter_by_project(self, ticket_service, setup_projects, many_tickets):
        tickets, total = ticket_service.list_tickets(project_id=setup_projects["web"].id)
        assert total == 3
        assert all(t.project_id == setup_projects["web"].id for t in tickets)

    def test_filter_by_status(self, ticket_service, many_tickets):
        ticket_service.update_status(many_tickets[0], TicketStatus.IN_PROGRESS)
        tickets, total = ticket_service.list_tickets(status=TicketStatus.IN_PROGRESS)
        assert total == 1
        assert tickets[0].id == many_tickets[0].id

    def test_filter_by_type(self, ticket_service, many_tickets):
        tickets, total = ticket_service.list_tickets(type=TicketType.BUG)
        assert total == 2
        assert all(t.type == TicketType.BUG for t in tickets)

    def test_filter_by_sprint(self, ticket_service, setup_projects, many_tickets):
        from jackrabbit.services import SprintService

        sprint = SprintService(ticket_service.session).create_sprint(number="2601")
        ticket_service.update_ticket(many_tickets[0], sprint_id=sprint.id)
        tickets, total = ticket_service.list_tickets(sprint_id=sprint.id)
        assert total == 1
        assert tickets[0].id == many_tickets[0].id

    def test_search_by_title(self, ticket_service, many_tickets):
        tickets, total = ticket_service.list_tickets(q="login")
        assert total == 2
        titles = {t.title for t in tickets}
        assert titles == {"Login bug", "Login page cache"}

    def test_search_is_case_insensitive(self, ticket_service, many_tickets):
        tickets, total = ticket_service.list_tickets(q="LOGIN")
        assert total == 2

    def test_sortAscending_by_title(self, ticket_service, many_tickets):
        tickets, _total = ticket_service.list_tickets(sort="title", order="asc")
        titles = [t.title for t in tickets]
        assert titles == sorted(titles)

    def test_sort_descending_by_number(self, ticket_service, many_tickets):
        tickets, _total = ticket_service.list_tickets(sort="number", order="desc")
        numbers = [t.number for t in tickets]
        # Numbers are per-project, so just assert non-increasing order overall
        assert numbers == sorted(numbers, reverse=True)

    def test_pagination(self, ticket_service, many_tickets):
        page1, total = ticket_service.list_tickets(page=1, page_size=2, sort="title", order="asc")
        page2, _ = ticket_service.list_tickets(page=2, page_size=2, sort="title", order="asc")
        page3, _ = ticket_service.list_tickets(page=3, page_size=2, sort="title", order="asc")
        assert total == 5
        assert len(page1) == 2
        assert len(page2) == 2
        assert len(page3) == 1

    def test_pagination_beyond_end_returns_empty(self, ticket_service, many_tickets):
        tickets, total = ticket_service.list_tickets(page=10, page_size=2)
        assert total == 5
        assert tickets == []


class TestTransitionSideEffects:
    """Tests for transition() side effects (full matrix lives in test_transitions.py)."""

    def test_transition_to_in_progress_autogenerates_branch(
        self, ticket_service, sample_ticket, setup_projects
    ):
        ticket_service.update_ticket(
            sample_ticket,
            approach="Approach",
            files_to_change="files",
            test_plan="Plan",
            validation_steps="Steps",
        )
        ticket = ticket_service.transition(sample_ticket, TicketStatus.GROOMED)
        ticket = ticket_service.transition(ticket, TicketStatus.IN_PROGRESS)
        assert ticket.branch_name == "feature/WEB-001-sample-ticket"

    def test_transition_records_audit_trail(self, ticket_service, sample_ticket):
        ticket = ticket_service.transition(sample_ticket, TicketStatus.REJECTED, "Not doing it")
        transitions = ticket_service.session.exec(
            select(Transition).where(Transition.ticket_id == ticket.id)
        ).all()
        assert len(transitions) == 1
        assert transitions[0].to_status == TicketStatus.REJECTED
        assert transitions[0].reason == "Not doing it"

    def test_get_ticket_with_details(self, ticket_service, link_service, sample_ticket):
        ticket_service.transition(sample_ticket, TicketStatus.REJECTED, "Nope")
        details = ticket_service.get_ticket_with_details(sample_ticket.id, link_service)
        assert details is not None
        assert details["project_prefix"] == "WEB"
        assert details["links"] == []
        assert len(details["transitions"]) == 1
        assert details["transitions"][0]["to_status"] == "Rejected"
        assert details["transitions"][0]["reason"] == "Nope"

    def test_get_ticket_with_details_missing_ticket(self, ticket_service, link_service):
        assert ticket_service.get_ticket_with_details(9999, link_service) is None

    def test_links_appear_in_details(
        self, ticket_service, link_service, setup_projects, sample_ticket
    ):
        bug = ticket_service.create_ticket(
            project_id=setup_projects["web"].id, title="Blocker", type=TicketType.BUG
        )
        link_service.create_link(bug.id, sample_ticket.id, LinkType.BLOCKS)
        details = ticket_service.get_ticket_with_details(sample_ticket.id, link_service)
        assert len(details["links"]) == 2  # blocks + blocked_by inverse
