"""Unit tests for the criteria-state filter on the ticket listing service.

Covers the "criteria queryable" requirement (JRB-020, user story 17): the
``criteria_state="unverified"`` filter on ``TicketService.list_tickets``
selects the tickets carrying at least one unverified criterion row.

A ticket with zero criterion rows never matches: the filter means "work
whose done-contract is not fully signed off", and no criteria means the
contract is empty, not outstanding. Spike tickets are not exempt here — the
filter is a data query, not the Complete-transition guard.

The filter is observed through the service's public behaviour (the tickets
it returns), never through internal attributes or SQL.
"""

import pytest
from jackrabbit.models import Project, TicketStatus
from jackrabbit.services import CriterionService, ProjectService, TicketService
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
def criterion_service(session):
    return CriterionService(session)


@pytest.fixture
def ticket_service(session):
    return TicketService(session)


@pytest.fixture
def project_service(session):
    return ProjectService(session)


@pytest.fixture
def scenario(ticket_service, criterion_service, project_service):
    """Four tickets with different criteria states.

    - ``unverified_groomed`` is Groomed with one unverified criterion
    - ``mixed`` is In Progress with one verified and one unverified criterion
    - ``all_verified`` is In Progress with every criterion verified
    - ``zero_criteria`` is a plain Open story without criterion rows
    """
    project = project_service.get_project_by_prefix("UNS")
    assert project is not None

    def _groomed_story(title: str, criteria: list[str]):
        ticket = ticket_service.create_ticket(
            project_id=project.id,
            title=title,
            approach="Approach",
            files_to_change="files",
            test_plan="Plan",
            validation_steps="Steps",
        )
        groomed = ticket_service.transition(
            ticket, TicketStatus.GROOMED, reason="groomed", criteria=criteria
        )
        assert groomed.status == TicketStatus.GROOMED
        return groomed

    unverified_groomed = _groomed_story("Unverified grooming output", ["It works"])

    mixed = _groomed_story("Partially signed off", ["It works", "It is tested"])
    mixed = ticket_service.transition(mixed, TicketStatus.IN_PROGRESS, "Started")
    first = criterion_service.list_criteria(mixed)[0]
    criterion_service.sign_off(mixed, mixed.criteria[1].id, True)
    assert first.verified is False

    all_verified = _groomed_story("Fully signed off", ["It works"])
    all_verified = ticket_service.transition(all_verified, TicketStatus.IN_PROGRESS, "Started")
    row = criterion_service.list_criteria(all_verified)[0]
    criterion_service.sign_off(all_verified, row.id, True)

    zero_criteria = ticket_service.create_ticket(project_id=project.id, title="No criteria at all")

    return {
        "unverified_groomed": unverified_groomed,
        "mixed": mixed,
        "all_verified": all_verified,
        "zero_criteria": zero_criteria,
    }


def _titles(tickets) -> set[str]:
    return {ticket.title for ticket in tickets}


class TestCriteriaStateFilter:
    """criteria_state="unverified" selects tickets with unverified criteria."""

    def test_matches_tickets_with_an_unverified_criterion(self, ticket_service, scenario):
        tickets, total = ticket_service.list_tickets(criteria_state="unverified")
        assert total == 2
        assert _titles(tickets) == {"Unverified grooming output", "Partially signed off"}

    def test_excludes_tickets_with_every_criterion_verified(self, ticket_service, scenario):
        tickets, _ = ticket_service.list_tickets(criteria_state="unverified")
        assert "Fully signed off" not in _titles(tickets)

    def test_excludes_tickets_with_zero_criteria(self, ticket_service, scenario):
        tickets, _ = ticket_service.list_tickets(criteria_state="unverified")
        assert "No criteria at all" not in _titles(tickets)

    def test_no_filter_returns_every_ticket(self, ticket_service, scenario):
        tickets, total = ticket_service.list_tickets()
        assert total == 4
        assert _titles(tickets) == {
            "Unverified grooming output",
            "Partially signed off",
            "Fully signed off",
            "No criteria at all",
        }

    def test_composes_with_the_status_filter(self, ticket_service, scenario):
        tickets, total = ticket_service.list_tickets(
            criteria_state="unverified", status=TicketStatus.GROOMED
        )
        assert total == 1
        assert _titles(tickets) == {"Unverified grooming output"}
