"""Unit tests for SprintService: numbering, persisted lifecycle status and
manual transitions (JRB-029, ADR-0026), ticket assignment."""

from datetime import date, datetime, time, timedelta

import pytest
from jackrabbit.models import Project, SprintStatus, TicketStatus
from jackrabbit.services import (
    ProjectService,
    SprintCompletionBlockedError,
    SprintNotAssignableError,
    SprintService,
    SprintTransitionError,
    TicketService,
)
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


class TestSprintStatusPersisted:
    """Status is a persisted column, never derived from the dates (JRB-029).

    Only a transition moves it; the actual dates no longer imply anything.
    """

    def test_new_sprint_defaults_to_not_started(self, sprint_service):
        sprint = sprint_service.create_sprint(number=2601)
        assert sprint.status == SprintStatus.NOT_STARTED
        result = sprint_service.get_sprint_with_tickets(sprint.id)
        assert result["status"] == SprintStatus.NOT_STARTED

    def test_status_is_not_re_derived_from_dates_on_read(self, sprint_service):
        """Reading a sprint never derives status from its dates: a sprint
        transitioned past Complete and reopened keeps its persisted status
        even though its actual_finish is cleared (the old derivation would
        call that Active from actual_start alone)."""
        sprint = sprint_service.create_sprint(number=2601, status=SprintStatus.IN_PROGRESS)
        sprint_service.transition(sprint.id, SprintStatus.COMPLETE)
        sprint_service.transition(sprint.id, SprintStatus.IN_PROGRESS)
        reopened = sprint_service.get_sprint(sprint.id)
        assert reopened.actual_finish is None
        assert reopened.status == SprintStatus.IN_PROGRESS

    def test_create_backfills_status_from_actual_dates(self, sprint_service):
        """Create-only dates seed the status with the migration's backfill rule."""
        started = sprint_service.create_sprint(number=2601, actual_start=day_offset(-5))
        assert started.status == SprintStatus.IN_PROGRESS
        finished = sprint_service.create_sprint(
            number=2602, actual_start=day_offset(-20), actual_finish=day_offset(-10)
        )
        assert finished.status == SprintStatus.COMPLETE

    def test_create_with_explicit_status(self, sprint_service):
        sprint = sprint_service.create_sprint(number=2601, status=SprintStatus.IN_PROGRESS)
        assert sprint.status == SprintStatus.IN_PROGRESS

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
        assert result["status"] == SprintStatus.NOT_STARTED
        assert len(result["tickets_by_status"]["Open"]) == 1
        assert len(result["tickets_by_status"]["Complete"]) == 0

    def test_by_status_missing_sprint_returns_none(self, sprint_service):
        assert sprint_service.get_sprint_with_tickets_by_status(9999) is None

    def test_get_sprint_with_tickets_groups_by_status(
        self, sprint_service, ticket_service, project
    ):
        """get_sprint_with_tickets includes tickets grouped by status (ticket 07)."""
        sprint = sprint_service.create_sprint(number=2601)
        open_ticket = ticket_service.create_ticket(
            project_id=project.id, title="Open one", sprint_id=sprint.id, status=TicketStatus.OPEN
        )
        done_ticket = ticket_service.create_ticket(
            project_id=project.id,
            title="Done one",
            sprint_id=sprint.id,
            status=TicketStatus.COMPLETE,
        )
        result = sprint_service.get_sprint_with_tickets(sprint.id)
        grouped = result["tickets_by_status"]
        # All six statuses present as keys
        assert set(grouped.keys()) == {
            "Open",
            "Groomed",
            "In Progress",
            "Ready for Review",
            "Complete",
            "Rejected",
        }
        assert [t.id for t in grouped["Open"]] == [open_ticket.id]
        assert [t.id for t in grouped["Complete"]] == [done_ticket.id]
        assert grouped["Groomed"] == []

    def test_get_sprint_with_tickets_empty_groups_when_no_tickets(
        self, sprint_service, ticket_service, project
    ):
        sprint = sprint_service.create_sprint(number=2601)
        result = sprint_service.get_sprint_with_tickets(sprint.id)
        assert all(g == [] for g in result["tickets_by_status"].values())


class TestSprintTransitionLegality:
    """Only the three lifecycle moves are legal; everything else is refused
    with the sprint left unchanged (JRB-029, criterion 2)."""

    LEGAL = {
        (SprintStatus.NOT_STARTED, SprintStatus.IN_PROGRESS),
        (SprintStatus.IN_PROGRESS, SprintStatus.COMPLETE),
        (SprintStatus.COMPLETE, SprintStatus.IN_PROGRESS),
    }
    ALL = set(SprintStatus)

    @pytest.mark.parametrize("from_status", list(ALL))
    @pytest.mark.parametrize("to_status", list(ALL))
    def test_transition_matrix(self, sprint_service, from_status, to_status):
        if (from_status, to_status) in self.LEGAL:
            pytest.skip("legal move covered by TestSprintTransitionEffects")

        sprint = sprint_service.create_sprint(number=2601, status=from_status)
        with pytest.raises(SprintTransitionError):
            sprint_service.transition(sprint.id, to_status)
        # Refused moves leave the sprint unchanged
        unchanged = sprint_service.get_sprint(sprint.id)
        assert unchanged.status == from_status

    def test_transition_missing_sprint_raises(self, sprint_service):
        with pytest.raises(ValueError, match="not found"):
            sprint_service.transition(9999, SprintStatus.IN_PROGRESS)


class TestSprintTransitionEffects:
    """Accepted transitions write the dates and append history (criterion 3, 6)."""

    def test_start_sets_actual_start_overwriting_existing(
        self, sprint_service, ticket_service, project
    ):
        # Explicit NOT_STARTED with a stale date: only create may seed dates,
        # so the overwrite case needs the explicit status to bypass backfill.
        sprint = sprint_service.create_sprint(
            number=2601, actual_start=day_offset(-30), status=SprintStatus.NOT_STARTED
        )
        sprint_service.transition(sprint.id, SprintStatus.IN_PROGRESS, reason="kick off")
        started = sprint_service.get_sprint(sprint.id)
        assert started.status == SprintStatus.IN_PROGRESS
        assert started.actual_start == datetime.combine(date.today(), time(0, 0))

    def test_complete_sets_actual_finish_overwriting_existing(self, sprint_service):
        stale_finish = day_offset(-10)
        sprint = sprint_service.create_sprint(
            number=2601,
            actual_start=day_offset(-30),
            actual_finish=stale_finish,
            status=SprintStatus.IN_PROGRESS,
        )
        sprint_service.transition(sprint.id, SprintStatus.COMPLETE)
        finished = sprint_service.get_sprint(sprint.id)
        assert finished.status == SprintStatus.COMPLETE
        assert finished.actual_finish == datetime.combine(date.today(), time(0, 0))
        assert finished.actual_finish != stale_finish

    def test_reopen_clears_finish_keeps_start(self, sprint_service):
        original_start = day_offset(-30)
        sprint = sprint_service.create_sprint(
            number=2601, actual_start=original_start, status=SprintStatus.IN_PROGRESS
        )
        sprint_service.transition(sprint.id, SprintStatus.COMPLETE)
        sprint_service.transition(sprint.id, SprintStatus.IN_PROGRESS)
        reopened = sprint_service.get_sprint(sprint.id)
        assert reopened.status == SprintStatus.IN_PROGRESS
        assert reopened.actual_finish is None
        assert reopened.actual_start == original_start

    def test_every_accepted_transition_appends_one_history_row(self, sprint_service):
        sprint = sprint_service.create_sprint(number=2601)
        before = len(sprint_service.list_transitions(sprint.id))
        sprint_service.transition(sprint.id, SprintStatus.IN_PROGRESS, reason="start")
        history = sprint_service.list_transitions(sprint.id)
        assert len(history) == before + 1
        row = history[-1]
        assert row.from_status == SprintStatus.NOT_STARTED
        assert row.to_status == SprintStatus.IN_PROGRESS
        assert row.reason == "start"
        assert row.at is not None

    def test_history_starts_empty_for_backfilled_sprint(self, sprint_service):
        sprint = sprint_service.create_sprint(
            number=2601, actual_start=day_offset(-20), actual_finish=day_offset(-10)
        )
        assert sprint.status == SprintStatus.COMPLETE
        assert sprint_service.list_transitions(sprint.id) == []

    def test_transitions_ordered_oldest_first(self, sprint_service):
        sprint = sprint_service.create_sprint(number=2601)
        sprint_service.transition(sprint.id, SprintStatus.IN_PROGRESS, reason="a")
        sprint_service.transition(sprint.id, SprintStatus.COMPLETE, reason="b")
        sprint_service.transition(sprint.id, SprintStatus.IN_PROGRESS, reason="c")
        history = sprint_service.list_transitions(sprint.id)
        assert [h.reason for h in history] == ["a", "b", "c"]
        assert [h.to_status for h in history] == [
            SprintStatus.IN_PROGRESS,
            SprintStatus.COMPLETE,
            SprintStatus.IN_PROGRESS,
        ]


class TestSprintCompletionGuard:
    """Completion is refused while Open/Groomed/In Progress/Ready for Review
    tickets remain - the refusal names them; Complete/Rejected do not block
    (JRB-029, criterion 5)."""

    BLOCKING_STATUSES = [
        TicketStatus.OPEN,
        TicketStatus.GROOMED,
        TicketStatus.IN_PROGRESS,
        TicketStatus.READY_FOR_REVIEW,
    ]

    @pytest.mark.parametrize("ticket_status", BLOCKING_STATUSES)
    def test_blocking_ticket_refuses_completion(
        self, sprint_service, ticket_service, project, ticket_status
    ):
        sprint = sprint_service.create_sprint(number=2601)
        ticket_service.create_ticket(
            project_id=project.id, title="Blocker", sprint_id=sprint.id, status=ticket_status
        )
        sprint_service.transition(sprint.id, SprintStatus.IN_PROGRESS)
        with pytest.raises(SprintCompletionBlockedError, match="Blocker"):
            sprint_service.transition(sprint.id, SprintStatus.COMPLETE)
        # The sprint stays In Progress
        assert sprint_service.get_sprint(sprint.id).status == SprintStatus.IN_PROGRESS

    def test_refusal_names_the_blocking_tickets(self, sprint_service, ticket_service, project):
        sprint = sprint_service.create_sprint(number=2601)
        ticket_service.create_ticket(project_id=project.id, title="One open", sprint_id=sprint.id)
        ticket_service.create_ticket(
            project_id=project.id,
            title="One groomed",
            sprint_id=sprint.id,
            status=TicketStatus.GROOMED,
        )
        sprint_service.transition(sprint.id, SprintStatus.IN_PROGRESS)
        with pytest.raises(SprintCompletionBlockedError, match="2 ticket") as excinfo:
            sprint_service.transition(sprint.id, SprintStatus.COMPLETE)
        assert "One open" in str(excinfo.value)
        assert "One groomed" in str(excinfo.value)

    @pytest.mark.parametrize("terminal", [TicketStatus.COMPLETE, TicketStatus.REJECTED])
    def test_terminal_tickets_do_not_block_completion(
        self, sprint_service, ticket_service, project, terminal
    ):
        sprint = sprint_service.create_sprint(number=2601)
        ticket_service.create_ticket(
            project_id=project.id,
            title="Terminal one",
            sprint_id=sprint.id,
            status=terminal,
        )
        sprint_service.transition(sprint.id, SprintStatus.IN_PROGRESS)
        sprint_service.transition(sprint.id, SprintStatus.COMPLETE)
        assert sprint_service.get_sprint(sprint.id).status == SprintStatus.COMPLETE

    def test_empty_sprint_can_be_completed(self, sprint_service):
        sprint = sprint_service.create_sprint(number=2601)
        sprint_service.transition(sprint.id, SprintStatus.IN_PROGRESS)
        sprint_service.transition(sprint.id, SprintStatus.COMPLETE)
        assert sprint_service.get_sprint(sprint.id).status == SprintStatus.COMPLETE


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


class TestSprintAssignability:
    """A sprint is assignable while its persisted status is not Complete (JRB-030).

    The rule lives in SprintService; every assignment path asks it. Tickets
    already assigned keep their sprint when it completes and can still be
    unassigned from it.
    """

    def _complete(self, sprint_service: SprintService, sprint) -> None:
        sprint_service.transition(sprint.id, SprintStatus.IN_PROGRESS)
        sprint_service.transition(sprint.id, SprintStatus.COMPLETE)

    def test_assignable_sprints_exclude_completed(self, sprint_service):
        not_started = sprint_service.create_sprint(number=2601, name="Future")
        in_progress = sprint_service.create_sprint(number=2602, name="Current")
        sprint_service.transition(in_progress.id, SprintStatus.IN_PROGRESS)
        completed = sprint_service.create_sprint(number=2603, name="Done")
        self._complete(sprint_service, completed)

        numbers = [s.number for s in sprint_service.assignable_sprints()]
        assert numbers == [in_progress.number, not_started.number]
        assert completed.number not in numbers

    def test_assign_to_not_started_sprint_allowed(self, sprint_service, ticket_service, project):
        sprint = sprint_service.create_sprint(number=2601)
        ticket = ticket_service.create_ticket(project_id=project.id, title="Movable")
        assert sprint_service.assign_ticket_to_sprint(sprint.id, ticket.id).sprint_id == sprint.id

    def test_assign_to_in_progress_sprint_allowed(self, sprint_service, ticket_service, project):
        sprint = sprint_service.create_sprint(number=2601)
        sprint_service.transition(sprint.id, SprintStatus.IN_PROGRESS)
        ticket = ticket_service.create_ticket(project_id=project.id, title="Movable")
        assert sprint_service.assign_ticket_to_sprint(sprint.id, ticket.id).sprint_id == sprint.id

    def test_assign_to_completed_sprint_refused(self, sprint_service, ticket_service, project):
        sprint = sprint_service.create_sprint(number=2601, name="Done")
        self._complete(sprint_service, sprint)
        ticket = ticket_service.create_ticket(project_id=project.id, title="Late")

        with pytest.raises(SprintNotAssignableError, match="Complete and cannot take new tickets"):
            sprint_service.assign_ticket_to_sprint(sprint.id, ticket.id)
        # The refusal leaves the ticket unchanged.
        assert ticket_service.get_ticket(ticket.id).sprint_id is None

    def test_ticket_keeps_assignment_after_sprint_completes(
        self, sprint_service, ticket_service, project
    ):
        sprint = sprint_service.create_sprint(number=2601)
        # A finished ticket does not block the sprint completion (JRB-029).
        ticket = ticket_service.create_ticket(
            project_id=project.id,
            title="Already In",
            sprint_id=sprint.id,
            status=TicketStatus.COMPLETE,
        )
        self._complete(sprint_service, sprint)

        assert ticket_service.get_ticket(ticket.id).sprint_id == sprint.id
        # Re-assigning the ticket to its own (completed) sprint stays a no-op.
        assigned = sprint_service.assign_ticket_to_sprint(sprint.id, ticket.id)
        assert assigned.sprint_id == sprint.id

    def test_unassign_from_completed_sprint_allowed(self, sprint_service, ticket_service, project):
        sprint = sprint_service.create_sprint(number=2601)
        ticket = ticket_service.create_ticket(
            project_id=project.id,
            title="Movable",
            sprint_id=sprint.id,
            status=TicketStatus.COMPLETE,
        )
        self._complete(sprint_service, sprint)

        unassigned = sprint_service.unassign_ticket_from_sprint(sprint.id, ticket.id)
        assert unassigned.sprint_id is None

    def test_create_ticket_with_completed_sprint_refused(
        self, sprint_service, ticket_service, project
    ):
        sprint = sprint_service.create_sprint(number=2601)
        self._complete(sprint_service, sprint)

        with pytest.raises(SprintNotAssignableError, match="Complete and cannot take new tickets"):
            ticket_service.create_ticket(
                project_id=project.id, title="New In Done", sprint_id=sprint.id
            )
        # Nothing was created: the next number is untouched.
        assert ticket_service.create_ticket(project_id=project.id, title="After").number == 1

    def test_create_ticket_with_open_sprint_allowed(self, sprint_service, ticket_service, project):
        sprint = sprint_service.create_sprint(number=2601)
        ticket = ticket_service.create_ticket(
            project_id=project.id, title="Movable", sprint_id=sprint.id
        )
        assert ticket.sprint_id == sprint.id

    def test_update_ticket_into_completed_sprint_refused(
        self, sprint_service, ticket_service, project
    ):
        sprint = sprint_service.create_sprint(number=2601)
        other = sprint_service.create_sprint(number=2602)
        ticket = ticket_service.create_ticket(
            project_id=project.id, title="Movable", sprint_id=sprint.id
        )
        self._complete(sprint_service, other)

        with pytest.raises(SprintNotAssignableError, match="Complete and cannot take new tickets"):
            ticket_service.update_ticket(ticket, sprint_id=other.id)
        assert ticket_service.get_ticket(ticket.id).sprint_id == sprint.id

    def test_update_ticket_keeping_its_completed_sprint_allowed(
        self, sprint_service, ticket_service, project
    ):
        sprint = sprint_service.create_sprint(number=2601)
        ticket = ticket_service.create_ticket(
            project_id=project.id,
            title="Movable",
            sprint_id=sprint.id,
            status=TicketStatus.COMPLETE,
        )
        self._complete(sprint_service, sprint)

        updated = ticket_service.update_ticket(ticket, title="Renamed")
        assert updated.sprint_id == sprint.id

    def test_update_ticket_unassign_from_completed_sprint_allowed(
        self, sprint_service, ticket_service, project
    ):
        sprint = sprint_service.create_sprint(number=2601)
        ticket = ticket_service.create_ticket(
            project_id=project.id,
            title="Movable",
            sprint_id=sprint.id,
            status=TicketStatus.COMPLETE,
        )
        self._complete(sprint_service, sprint)

        updated = ticket_service.update_ticket(ticket, sprint_id=None)
        assert updated.sprint_id is None


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

    def test_update_sprint_no_longer_writes_actual_dates(self, sprint_service):
        """The actual dates are transition-owned: update_sprint cannot touch
        them, and the persisted status stays whatever the transitions made it
        (JRB-029, criterion 4)."""
        sprint = sprint_service.create_sprint(number=2601)
        updated = sprint_service.update_sprint(sprint.id, planned_duration_days=10)
        assert updated.planned_duration_days == 10
        assert updated.actual_start is None
        assert updated.actual_finish is None
        assert updated.status == SprintStatus.NOT_STARTED

    def test_update_missing_sprint_returns_none(self, sprint_service):
        assert sprint_service.update_sprint(9999, name="Nope") is None

    def test_delete_sprint(self, sprint_service):
        sprint = sprint_service.create_sprint(number=2601)
        assert sprint_service.delete_sprint(sprint.id) is True
        assert sprint_service.get_sprint(sprint.id) is None

    def test_delete_missing_sprint(self, sprint_service):
        assert sprint_service.delete_sprint(9999) is False
