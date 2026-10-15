"""Unit tests for SprintService: numbering, status derivation, ticket assignment."""

from datetime import date, datetime, time, timedelta

import pytest
from jackrabbit.models import Project, TicketStatus
from jackrabbit.services import ProjectService, SprintService, TicketService
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


def day_offset(days: int) -> datetime:
    """Naive datetime `days` offset from today (sprint dates are NaiveDatetime)."""
    return datetime.combine(date.today() + timedelta(days=days), time(0, 0))


@pytest.fixture
def session():
    engine = get_test_engine()
    session = get_test_session(engine)
    yield session
    session.close()


@pytest.fixture
def sprint_service(session):
    return SprintService(session)


@pytest.fixture
def ticket_service(session):
    return TicketService(session)


@pytest.fixture
def project(session):
    return ProjectService(session).get_project_by_prefix("UNS")


class TestGetNextSprintNumber:
    def test_first_sprint_starts_at_2601(self, sprint_service):
        assert sprint_service.get_next_sprint_number() == 2601

    def test_increments_after_existing_sprint(self, sprint_service):
        sprint_service.create_sprint(number=2601, name="First")
        assert sprint_service.get_next_sprint_number() == 2602

    def test_increments_from_max_not_latest(self, sprint_service):
        sprint_service.create_sprint(number=2601)
        sprint_service.create_sprint(number=2610)
        sprint_service.create_sprint(number=2605)
        assert sprint_service.get_next_sprint_number() == 2611


class TestCreateSprintAutoAssign:
    """POST /sprints without a number auto-assigns MAX(number)+1 starting at 2601."""

    def test_auto_assigns_2601_when_empty(self, sprint_service):
        sprint = sprint_service.create_sprint()
        assert sprint.number == 2601

    def test_auto_assign_continues_past_52(self, sprint_service):
        sprint_service.create_sprint(number=2601)
        sprint_service.create_sprint(number=2652)
        sprint = sprint_service.create_sprint()
        assert sprint.number == 2653

    def test_user_can_override_number(self, sprint_service):
        sprint = sprint_service.create_sprint(number=3000)
        assert sprint.number == 3000
        # Auto-assign continues from the override
        assert sprint_service.create_sprint().number == 3001


class TestSprintStatusDerived:
    """Status is derived from actual dates (ticket 06):

    - no actual_start -> Planned
    - actual_start set, no actual_finish -> Active
    - actual_finish set -> Complete
    """

    def test_no_actual_start_is_planned(self, sprint_service):
        sprint = sprint_service.create_sprint(number=2601)
        result = sprint_service.get_sprint_with_tickets(sprint.id)
        assert result["status"] == "Planned"

    def test_planned_dates_alone_do_not_start_sprint(self, sprint_service):
        sprint = sprint_service.create_sprint(
            number=2601, planned_start=day_offset(-10), planned_end=day_offset(10)
        )
        result = sprint_service.get_sprint_with_tickets(sprint.id)
        assert result["status"] == "Planned"

    def test_actual_start_without_finish_is_active(self, sprint_service):
        sprint = sprint_service.create_sprint(number=2601, actual_start=day_offset(-5))
        result = sprint_service.get_sprint_with_tickets(sprint.id)
        assert result["status"] == "Active"

    def test_actual_finish_is_complete(self, sprint_service):
        sprint = sprint_service.create_sprint(
            number=2601, actual_start=day_offset(-20), actual_finish=day_offset(-10)
        )
        result = sprint_service.get_sprint_with_tickets(sprint.id)
        assert result["status"] == "Complete"

    def test_actual_finish_alone_is_complete(self, sprint_service):
        sprint = sprint_service.create_sprint(number=2601, actual_finish=day_offset(-1))
        result = sprint_service.get_sprint_with_tickets(sprint.id)
        assert result["status"] == "Complete"

    def test_tickets_do_not_drive_status(self, sprint_service, ticket_service, project):
        """All tickets Complete does NOT make the sprint Complete (actual_finish does)."""
        sprint = sprint_service.create_sprint(number=2601, actual_start=day_offset(-5))
        ticket_service.create_ticket(
            project_id=project.id,
            title="Done one",
            status=TicketStatus.COMPLETE,
            sprint_id=sprint.id,
        )
        result = sprint_service.get_sprint_with_tickets(sprint.id)
        assert result["status"] == "Active"

    def test_missing_sprint_returns_none(self, sprint_service):
        assert sprint_service.get_sprint_with_tickets(9999) is None

    def test_tickets_included_in_result(self, sprint_service, ticket_service, project):
        sprint = sprint_service.create_sprint(number=2601)
        ticket = ticket_service.create_ticket(
            project_id=project.id, title="In sprint", sprint_id=sprint.id
        )
        result = sprint_service.get_sprint_with_tickets(sprint.id)
        assert [t.id for t in result["tickets"]] == [ticket.id]

    def test_status_in_tickets_by_status_view(self, sprint_service, ticket_service, project):
        sprint = sprint_service.create_sprint(number=2601)
        ticket_service.create_ticket(
            project_id=project.id, title="Open one", sprint_id=sprint.id, status=TicketStatus.OPEN
        )
        result = sprint_service.get_sprint_with_tickets_by_status(sprint.id)
        assert result["status"] == "Planned"
        assert len(result["tickets_by_status"]["Open"]) == 1
        assert len(result["tickets_by_status"]["Complete"]) == 0

    def test_by_status_missing_sprint_returns_none(self, sprint_service):
        assert sprint_service.get_sprint_with_tickets_by_status(9999) is None


class TestAssignTicketToSprint:
    def test_assign_ticket(self, sprint_service, ticket_service, project):
        sprint = sprint_service.create_sprint(number=2601)
        ticket = ticket_service.create_ticket(project_id=project.id, title="Movable")
        assigned = sprint_service.assign_ticket_to_sprint(sprint.id, ticket.id)
        assert assigned.sprint_id == sprint.id

    def test_reassign_to_same_sprint_is_allowed(self, sprint_service, ticket_service, project):
        sprint = sprint_service.create_sprint(number=2601)
        ticket = ticket_service.create_ticket(
            project_id=project.id, title="Movable", sprint_id=sprint.id
        )
        assigned = sprint_service.assign_ticket_to_sprint(sprint.id, ticket.id)
        assert assigned.sprint_id == sprint.id

    def test_assign_to_other_sprint_raises(self, sprint_service, ticket_service, project):
        sprint1 = sprint_service.create_sprint(number=2601)
        sprint2 = sprint_service.create_sprint(number=2602)
        ticket = ticket_service.create_ticket(
            project_id=project.id, title="Movable", sprint_id=sprint1.id
        )
        with pytest.raises(ValueError, match="already assigned to sprint"):
            sprint_service.assign_ticket_to_sprint(sprint2.id, ticket.id)

    def test_assign_missing_sprint_raises(self, sprint_service, ticket_service, project):
        ticket = ticket_service.create_ticket(project_id=project.id, title="Movable")
        with pytest.raises(ValueError, match="not found"):
            sprint_service.assign_ticket_to_sprint(9999, ticket.id)

    def test_assign_missing_ticket_raises(self, sprint_service):
        sprint = sprint_service.create_sprint(number=2601)
        with pytest.raises(ValueError, match="not found"):
            sprint_service.assign_ticket_to_sprint(sprint.id, 9999)


class TestUnassignTicketFromSprint:
    def test_unassign_ticket(self, sprint_service, ticket_service, project):
        sprint = sprint_service.create_sprint(number=2601)
        ticket = ticket_service.create_ticket(
            project_id=project.id, title="Movable", sprint_id=sprint.id
        )
        unassigned = sprint_service.unassign_ticket_from_sprint(sprint.id, ticket.id)
        assert unassigned.sprint_id is None

    def test_unassign_from_wrong_sprint_raises(self, sprint_service, ticket_service, project):
        sprint1 = sprint_service.create_sprint(number=2601)
        sprint2 = sprint_service.create_sprint(number=2602)
        ticket = ticket_service.create_ticket(
            project_id=project.id, title="Movable", sprint_id=sprint1.id
        )
        with pytest.raises(ValueError, match="not assigned"):
            sprint_service.unassign_ticket_from_sprint(sprint2.id, ticket.id)

    def test_unassign_missing_sprint_raises(self, sprint_service, ticket_service, project):
        ticket = ticket_service.create_ticket(project_id=project.id, title="Movable")
        with pytest.raises(ValueError, match="not found"):
            sprint_service.unassign_ticket_from_sprint(9999, ticket.id)

    def test_unassign_missing_ticket_raises(self, sprint_service):
        sprint = sprint_service.create_sprint(number=2601)
        with pytest.raises(ValueError, match="not found"):
            sprint_service.unassign_ticket_from_sprint(sprint.id, 9999)


class TestSprintCrud:
    def test_create_and_get(self, sprint_service):
        sprint = sprint_service.create_sprint(number=2601, name="Sprint 1", description="First")
        fetched = sprint_service.get_sprint(sprint.id)
        assert fetched is not None
        assert fetched.number == 2601
        assert fetched.name == "Sprint 1"

    def test_get_by_number(self, sprint_service):
        sprint = sprint_service.create_sprint(number=2601)
        assert sprint_service.get_sprint_by_number(2601).id == sprint.id
        assert sprint_service.get_sprint_by_number(9999) is None

    def test_list_sprints_ordered_by_number_desc(self, sprint_service):
        sprint_service.create_sprint(number=2601)
        sprint_service.create_sprint(number=2602)
        sprint_service.create_sprint(number=2605)
        numbers = [s.number for s in sprint_service.list_sprints()]
        assert numbers == [2605, 2602, 2601]

    def test_create_with_all_fields(self, sprint_service):
        sprint = sprint_service.create_sprint(
            number=2601,
            name="Sprint 1",
            planned_start=day_offset(1),
            planned_duration_days=14,
            actual_start=day_offset(2),
            actual_finish=day_offset(16),
        )
        fetched = sprint_service.get_sprint(sprint.id)
        assert fetched.planned_duration_days == 14
        assert fetched.actual_start == day_offset(2)
        assert fetched.actual_finish == day_offset(16)

    def test_update_sprint(self, sprint_service):
        sprint = sprint_service.create_sprint(number=2601)
        updated = sprint_service.update_sprint(
            sprint.id, name="Renamed", planned_start=day_offset(1)
        )
        assert updated.name == "Renamed"
        assert updated.planned_start == day_offset(1)

    def test_update_sprint_actual_dates_and_duration(self, sprint_service):
        sprint = sprint_service.create_sprint(number=2601)
        updated = sprint_service.update_sprint(
            sprint.id,
            planned_duration_days=10,
            actual_start=day_offset(-5),
            actual_finish=day_offset(5),
        )
        assert updated.planned_duration_days == 10
        assert updated.actual_start == day_offset(-5)
        assert updated.actual_finish == day_offset(5)

    def test_update_missing_sprint_returns_none(self, sprint_service):
        assert sprint_service.update_sprint(9999, name="Nope") is None

    def test_delete_sprint(self, sprint_service):
        sprint = sprint_service.create_sprint(number=2601)
        assert sprint_service.delete_sprint(sprint.id) is True
        assert sprint_service.get_sprint(sprint.id) is None

    def test_delete_missing_sprint(self, sprint_service):
        assert sprint_service.delete_sprint(9999) is False
