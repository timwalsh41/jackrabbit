"""Unit tests for the label filter on the ticket listing service.

Two behaviours are covered here (JRB-003):

- the label filter itself — a set of label ids plus a match mode (``all`` or
  ``any``, defaulting to ``all``) that selects the right tickets;
- the widened free-text search — a ticket matches when the search text occurs
  in its title, its description or one of its label names, case-insensitively.

Both are observed through the service's public behaviour (the tickets it
returns), never through internal attributes or SQL.
"""

import pytest
from jackrabbit.models import Project, TicketStatus
from jackrabbit.services import LabelService, ProjectService, TicketService
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
def label_service(session):
    return LabelService(session)


@pytest.fixture
def ticket_service(session):
    return TicketService(session)


@pytest.fixture
def project_service(session):
    return ProjectService(session)


@pytest.fixture
def scenario(label_service, ticket_service, project_service):
    """Four tickets with different label sets.

    - ``both`` carries Backend and Frontend
    - ``backend_only`` carries Backend
    - ``frontend_only`` carries Frontend
    - ``unlabelled`` carries nothing
    """
    project = project_service.get_project_by_prefix("UNS")

    both = ticket_service.create_ticket(project_id=project.id, title="Carries both labels")
    backend_only = ticket_service.create_ticket(project_id=project.id, title="Backend only")
    frontend_only = ticket_service.create_ticket(project_id=project.id, title="Frontend only")
    unlabelled = ticket_service.create_ticket(project_id=project.id, title="No labels here")

    label_service.attach(both.id, "Backend")
    label_service.attach(both.id, "Frontend")
    label_service.attach(backend_only.id, "Backend")
    label_service.attach(frontend_only.id, "Frontend")

    backend, _ = label_service.find_or_create("Backend")
    frontend, _ = label_service.find_or_create("Frontend")
    return {
        "tickets": {
            "both": both,
            "backend_only": backend_only,
            "frontend_only": frontend_only,
            "unlabelled": unlabelled,
        },
        "labels": {"backend": backend, "frontend": frontend},
    }


def _titles(tickets) -> set[str]:
    return {ticket.title for ticket in tickets}


class TestLabelFilterMatchModes:
    """The label filter selects tickets by label, in either match mode."""

    def test_match_all_selects_only_the_tickets_carrying_every_label(
        self, ticket_service, scenario
    ):
        labels = scenario["labels"]
        tickets, total = ticket_service.list_tickets(
            label_ids=[labels["backend"].id, labels["frontend"].id],
            label_match="all",
        )
        assert total == 1
        assert _titles(tickets) == {"Carries both labels"}

    def test_match_any_selects_the_tickets_carrying_at_least_one_label(
        self, ticket_service, scenario
    ):
        labels = scenario["labels"]
        tickets, total = ticket_service.list_tickets(
            label_ids=[labels["backend"].id, labels["frontend"].id],
            label_match="any",
        )
        assert total == 3
        assert _titles(tickets) == {
            "Carries both labels",
            "Backend only",
            "Frontend only",
        }

    def test_match_mode_defaults_to_all(self, ticket_service, scenario):
        """Without an explicit match mode every selected label must be present."""
        labels = scenario["labels"]
        tickets, total = ticket_service.list_tickets(
            label_ids=[labels["backend"].id, labels["frontend"].id]
        )
        assert total == 1
        assert _titles(tickets) == {"Carries both labels"}

    def test_a_single_label_selects_the_tickets_carrying_it(self, ticket_service, scenario):
        labels = scenario["labels"]
        tickets, total = ticket_service.list_tickets(label_ids=[labels["backend"].id])
        assert total == 2
        assert _titles(tickets) == {"Carries both labels", "Backend only"}

    def test_no_labels_means_no_filter(self, ticket_service, scenario):
        tickets, total = ticket_service.list_tickets()
        assert total == 4

    def test_an_unknown_label_id_matches_nothing(self, ticket_service, scenario):
        tickets, total = ticket_service.list_tickets(label_ids=[9999])
        assert total == 0
        assert tickets == []

    def test_the_filter_composes_with_the_other_filters(self, ticket_service, scenario):
        """A label filter narrows the result set; it does not replace the others."""
        labels = scenario["labels"]
        ticket_service.update_ticket(
            scenario["tickets"]["backend_only"], status=TicketStatus.GROOMED
        )
        tickets, total = ticket_service.list_tickets(
            label_ids=[labels["backend"].id],
            status=TicketStatus.GROOMED,
        )
        assert total == 1
        assert _titles(tickets) == {"Backend only"}

    def test_the_filter_composes_with_the_project_filter(self, ticket_service, scenario):
        other_project = ticket_service.create_ticket(project_id=1, title="Other project")
        labels = scenario["labels"]
        label_service = LabelService(ticket_service.session)
        label_service.attach(other_project.id, "Backend")
        tickets, total = ticket_service.list_tickets(
            label_ids=[labels["backend"].id],
            project_id=1,
        )
        # Every ticket in the scenario lives in project 1, so all of them match.
        assert total == 3


class TestWidenedSearch:
    """The free-text search covers the title, the description and the labels."""

    def test_search_finds_a_ticket_by_its_title(self, ticket_service, scenario):
        tickets, total = ticket_service.list_tickets(q="Carries both")
        assert total == 1
        assert _titles(tickets) == {"Carries both labels"}

    def test_search_finds_a_ticket_by_its_description(self, ticket_service, scenario):
        ticket = scenario["tickets"]["unlabelled"]
        ticket_service.update_ticket(ticket, description="Rework the billing reconciliation job")
        tickets, total = ticket_service.list_tickets(q="billing reconciliation")
        assert total == 1
        assert _titles(tickets) == {"No labels here"}

    def test_search_finds_a_ticket_by_a_label_name(self, ticket_service, scenario):
        tickets, total = ticket_service.list_tickets(q="Frontend")
        assert total == 2
        assert _titles(tickets) == {"Carries both labels", "Frontend only"}

    def test_search_is_case_insensitive(self, ticket_service, scenario):
        tickets, total = ticket_service.list_tickets(q="frontend")
        assert total == 2
        assert _titles(tickets) == {"Carries both labels", "Frontend only"}

    def test_search_matches_a_substring(self, ticket_service, scenario):
        tickets, total = ticket_service.list_tickets(q="ronten")
        assert total == 2

    def test_search_composes_with_the_label_filter(self, ticket_service, scenario):
        """The widened search and the label filter work together."""
        labels = scenario["labels"]
        tickets, total = ticket_service.list_tickets(
            q="Frontend",
            label_ids=[labels["backend"].id],
        )
        assert total == 1
        assert _titles(tickets) == {"Carries both labels"}

    def test_search_composes_with_the_other_filters(self, ticket_service, scenario):
        ticket_service.update_ticket(scenario["tickets"]["both"], status=TicketStatus.GROOMED)
        tickets, total = ticket_service.list_tickets(
            q="Carries both",
            status=TicketStatus.OPEN,
        )
        assert total == 0

    def test_search_matches_nothing_when_the_text_is_absent(self, ticket_service, scenario):
        tickets, total = ticket_service.list_tickets(q="zzz-no-such-text")
        assert total == 0
        assert tickets == []


class TestSearchStillCoversTheOldBehaviour:
    """The widened search did not lose the title-only behaviour."""

    def test_a_title_match_still_works(self, ticket_service, scenario):
        tickets, total = ticket_service.list_tickets(q="No labels")
        assert total == 1
        assert _titles(tickets) == {"No labels here"}
