"""Unit tests for structured acceptance criteria (JRB-021, ADR-0025).

Covers the CriterionService CRUD surface (status-gated to Open/Groomed) and
the criterion requirement on the Groomed transition gate.
"""

import pytest
from jackrabbit.models import (
    Project,
    TicketCriterion,
    TicketStatus,
)
from jackrabbit.services import (
    CriterionLockedError,
    CriterionService,
    TicketService,
)
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
def criterion_service(session):
    return CriterionService(session)


@pytest.fixture
def project_id(session):
    return 1


@pytest.fixture
def open_story(session, ticket_service, project_id):
    """A Story ticket in OPEN status."""
    return ticket_service.create_ticket(project_id=project_id, title="Build the thing")


class TestCriterionCrud:
    """CriterionService add/list/update/delete on an editable ticket."""

    def test_add_assigns_sequential_positions(self, criterion_service, open_story):
        first = criterion_service.add_criterion(open_story, "It works")
        second = criterion_service.add_criterion(open_story, "It is tested")
        assert first.position == 0
        assert second.position == 1
        assert first.verified is False
        assert first.verified_at is None

    def test_add_trims_whitespace(self, criterion_service, open_story):
        row = criterion_service.add_criterion(open_story, "  It works  ")
        assert row.text == "It works"

    def test_add_rejects_blank_text(self, criterion_service, open_story):
        with pytest.raises(ValueError, match="Criterion text is required"):
            criterion_service.add_criterion(open_story, "   ")

    def test_list_orders_by_position(self, criterion_service, open_story):
        criterion_service.add_criterion(open_story, "It is tested")
        first = criterion_service.add_criterion(open_story, "It works")
        criterion_service.update_criterion(open_story, first.id, position=2)
        rows = criterion_service.list_criteria(open_story)
        assert [row.text for row in rows] == ["It is tested", "It works"]

    def test_update_text(self, criterion_service, open_story):
        row = criterion_service.add_criterion(open_story, "It works")
        updated = criterion_service.update_criterion(open_story, row.id, text="It still works")
        assert updated is not None
        assert updated.text == "It still works"

    def test_update_position(self, criterion_service, open_story):
        first = criterion_service.add_criterion(open_story, "It works")
        criterion_service.add_criterion(open_story, "It is tested")
        updated = criterion_service.update_criterion(open_story, first.id, position=5)
        assert updated is not None
        assert updated.position == 5
        assert [row.text for row in criterion_service.list_criteria(open_story)] == [
            "It is tested",
            "It works",
        ]

    def test_update_rejects_blank_text(self, criterion_service, open_story):
        row = criterion_service.add_criterion(open_story, "It works")
        with pytest.raises(ValueError, match="Criterion text is required"):
            criterion_service.update_criterion(open_story, row.id, text="  ")

    def test_update_unknown_criterion_returns_none(self, criterion_service, open_story):
        assert criterion_service.update_criterion(open_story, 9999, text="Nope") is None

    def test_delete_removes_the_row(self, criterion_service, open_story):
        row = criterion_service.add_criterion(open_story, "It works")
        assert criterion_service.delete_criterion(open_story, row.id) is True
        assert criterion_service.list_criteria(open_story) == []

    def test_delete_unknown_criterion_returns_false(self, criterion_service, open_story):
        assert criterion_service.delete_criterion(open_story, 9999) is False

    def test_delete_keeps_the_other_rows(self, criterion_service, open_story):
        first = criterion_service.add_criterion(open_story, "It works")
        second = criterion_service.add_criterion(open_story, "It is tested")
        criterion_service.delete_criterion(open_story, first.id)
        rows = criterion_service.list_criteria(open_story)
        assert [row.id for row in rows] == [second.id]


class TestCriterionLocking:
    """Rows are editable only while the ticket is Open or Groomed (ADR-0025);
    from In Progress onward they are locked."""

    def _groomed_story(self, ticket_service, open_story):
        open_story.approach = "Approach"
        open_story.files_to_change = "files"
        open_story.test_plan = "Plan"
        open_story.validation_steps = "Steps"
        return ticket_service.transition(open_story, TicketStatus.GROOMED, criteria=["It works"])

    def test_add_is_allowed_on_a_groomed_ticket(
        self, criterion_service, ticket_service, open_story
    ):
        groomed = self._groomed_story(ticket_service, open_story)
        row = criterion_service.add_criterion(groomed, "One more thing")
        assert row.position == 1

    def test_add_is_locked_once_in_progress(self, criterion_service, ticket_service, open_story):
        groomed = self._groomed_story(ticket_service, open_story)
        ticket_service.transition(groomed, TicketStatus.IN_PROGRESS, "Started work")
        with pytest.raises(CriterionLockedError, match="locked"):
            criterion_service.add_criterion(groomed, "Sneaky change")

    def test_update_is_locked_once_in_progress(self, criterion_service, ticket_service, open_story):
        groomed = self._groomed_story(ticket_service, open_story)
        row = criterion_service.list_criteria(groomed)[0]
        ticket_service.transition(groomed, TicketStatus.IN_PROGRESS, "Started work")
        with pytest.raises(CriterionLockedError, match="locked"):
            criterion_service.update_criterion(groomed, row.id, text="Silent rewrite")

    def test_delete_is_locked_once_in_progress(self, criterion_service, ticket_service, open_story):
        groomed = self._groomed_story(ticket_service, open_story)
        row = criterion_service.list_criteria(groomed)[0]
        ticket_service.transition(groomed, TicketStatus.IN_PROGRESS, "Started work")
        with pytest.raises(CriterionLockedError, match="locked"):
            criterion_service.delete_criterion(groomed, row.id)

    def test_locked_from_ready_for_review_too(self, criterion_service, ticket_service, open_story):
        groomed = self._groomed_story(ticket_service, open_story)
        ticket_service.transition(groomed, TicketStatus.IN_PROGRESS, "Started work")
        groomed.pr_url = "https://github.com/org/repo/pull/1"
        ticket_service.transition(groomed, TicketStatus.READY_FOR_REVIEW, "PR opened")
        with pytest.raises(CriterionLockedError, match="locked"):
            criterion_service.add_criterion(groomed, "Too late")

    def test_round_trip_back_to_groomed_unlocks(
        self, criterion_service, ticket_service, open_story
    ):
        """A backward transition to Groomed re-opens the rows for editing."""
        groomed = self._groomed_story(ticket_service, open_story)
        ticket_service.transition(groomed, TicketStatus.IN_PROGRESS, "Started work")
        reopened = ticket_service.transition(groomed, TicketStatus.GROOMED, "Revise contract")
        row = criterion_service.list_criteria(reopened)[0]
        updated = criterion_service.update_criterion(reopened, row.id, text="Revised criterion")
        assert updated is not None
        assert updated.text == "Revised criterion"


class TestGroomedTransitionCriteria:
    """The criteria list rides on the Groomed transition payload, atomically
    (ADR-0025): written in the same commit as the status change, or not at all."""

    def _fillable(self, ticket_service, open_story):
        """Fill the four groomed fields so the Story passes the field gate."""
        open_story.approach = "Approach"
        open_story.files_to_change = "files"
        open_story.test_plan = "Plan"
        open_story.validation_steps = "Steps"
        ticket_service.session.add(open_story)
        ticket_service.session.commit()

    def test_transition_with_criteria_persists_rows(self, ticket_service, open_story):
        self._fillable(ticket_service, open_story)
        ticket = ticket_service.transition(
            open_story,
            TicketStatus.GROOMED,
            criteria=["It works", "It is tested"],
        )
        assert ticket.status == TicketStatus.GROOMED
        rows = CriterionService(ticket_service.session).list_criteria(ticket)
        assert [row.text for row in rows] == ["It works", "It is tested"]
        assert [row.position for row in rows] == [0, 1]

    def test_transition_with_criteria_replaces_existing_rows(self, ticket_service, open_story):
        self._fillable(ticket_service, open_story)
        CriterionService(ticket_service.session).add_criterion(open_story, "Old criterion")
        ticket = ticket_service.transition(
            open_story, TicketStatus.GROOMED, criteria=["New criterion"]
        )
        rows = CriterionService(ticket_service.session).list_criteria(ticket)
        assert [row.text for row in rows] == ["New criterion"]

    def test_blank_criterion_in_payload_leaves_nothing_persisted(self, ticket_service, open_story):
        CriterionService(ticket_service.session).add_criterion(open_story, "Old criterion")
        open_story.approach = "Approach"
        open_story.files_to_change = "files"
        open_story.test_plan = "Plan"
        open_story.validation_steps = "Steps"
        ticket_service.session.add(open_story)
        ticket_service.session.commit()

        with pytest.raises(ValueError, match="Criterion text is required"):
            ticket_service.transition(open_story, TicketStatus.GROOMED, criteria=["Good", "   "])
        # Atomic: the ticket is still Open and its criteria are untouched.
        ticket_service.session.refresh(open_story)
        assert open_story.status == TicketStatus.OPEN
        rows = ticket_service.session.exec(
            select(TicketCriterion).where(TicketCriterion.ticket_id == open_story.id)  # type: ignore[arg-type]
        ).all()
        assert [row.text for row in rows] == ["Old criterion"]

    def test_guard_failure_with_criteria_leaves_nothing_persisted(self, ticket_service, open_story):
        """A guard failure after staging the criteria rolls the rows back."""
        with pytest.raises(ValueError, match="Approach is required"):
            ticket_service.transition(open_story, TicketStatus.GROOMED, criteria=["It works"])
        ticket_service.session.refresh(open_story)
        assert open_story.status == TicketStatus.OPEN
        assert (
            ticket_service.session.exec(
                select(TicketCriterion).where(TicketCriterion.ticket_id == open_story.id)  # type: ignore[arg-type]
            ).all()
            == []
        )

    def test_criteria_only_accepted_on_the_groomed_transition(self, ticket_service, open_story):
        with pytest.raises(ValueError, match="Groomed"):
            ticket_service.transition(open_story, TicketStatus.IN_PROGRESS, criteria=["It works"])
