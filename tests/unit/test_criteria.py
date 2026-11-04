"""Unit tests for structured acceptance criteria (JRB-021/JRB-022, ADR-0025).

Covers the CriterionService CRUD surface (status-gated to Open/Groomed), the
criterion requirement on the Groomed transition gate, verifier sign-off
(status-gated to In Progress/Ready for Review), the Complete guard, and the
criterion audit history.
"""

from typing import cast

import pytest
from jackrabbit.models import (
    Project,
    TicketCriterion,
    TicketCriterionHistory,
    TicketStatus,
    TicketType,
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


class TestCriterionSignOff:
    """Verifier sign-off flips verified/verified_at; allowed only while the
    ticket is In Progress or Ready for Review (ADR-0025)."""

    def _story_in_progress(self, criterion_service, ticket_service, open_story):
        open_story.approach = "Approach"
        open_story.files_to_change = "files"
        open_story.test_plan = "Plan"
        open_story.validation_steps = "Steps"
        ticket = ticket_service.transition(
            open_story, TicketStatus.GROOMED, criteria=["It works", "It is tested"]
        )
        return ticket_service.transition(ticket, TicketStatus.IN_PROGRESS, "Started work")

    def test_sign_off_sets_verified_and_verified_at(
        self, criterion_service, ticket_service, open_story
    ):
        ticket = self._story_in_progress(criterion_service, ticket_service, open_story)
        row = criterion_service.list_criteria(ticket)[0]
        signed = criterion_service.sign_off(ticket, row.id, True)
        assert signed is not None
        assert signed.verified is True
        assert signed.verified_at is not None

    def test_sign_off_is_allowed_while_ready_for_review(
        self, criterion_service, ticket_service, open_story
    ):
        ticket = self._story_in_progress(criterion_service, ticket_service, open_story)
        ticket.pr_url = "https://github.com/org/repo/pull/1"
        ticket = ticket_service.transition(ticket, TicketStatus.READY_FOR_REVIEW, "PR opened")
        row = criterion_service.list_criteria(ticket)[0]
        signed = criterion_service.sign_off(ticket, row.id, True)
        assert signed is not None
        assert signed.verified is True

    def test_unverify_clears_the_timestamp(self, criterion_service, ticket_service, open_story):
        ticket = self._story_in_progress(criterion_service, ticket_service, open_story)
        row = criterion_service.list_criteria(ticket)[0]
        criterion_service.sign_off(ticket, row.id, True)
        reopened = criterion_service.sign_off(ticket, row.id, False)
        assert reopened is not None
        assert reopened.verified is False
        assert reopened.verified_at is None

    def test_sign_off_is_rejected_while_groomed(
        self, criterion_service, ticket_service, open_story
    ):
        open_story.approach = "Approach"
        open_story.files_to_change = "files"
        open_story.test_plan = "Plan"
        open_story.validation_steps = "Steps"
        ticket = ticket_service.transition(open_story, TicketStatus.GROOMED, criteria=["It works"])
        row = criterion_service.list_criteria(ticket)[0]
        with pytest.raises(CriterionLockedError, match="signed off"):
            criterion_service.sign_off(ticket, row.id, True)

    def test_sign_off_is_rejected_once_complete(
        self, criterion_service, ticket_service, open_story
    ):
        ticket = self._story_in_progress(criterion_service, ticket_service, open_story)
        for row in criterion_service.list_criteria(ticket):
            criterion_service.sign_off(ticket, cast(int, row.id), True)
        ticket = ticket_service.transition(ticket, TicketStatus.READY_FOR_REVIEW, "PR opened")
        ticket = ticket_service.transition(ticket, TicketStatus.COMPLETE, "Merged")
        row = criterion_service.list_criteria(ticket)[0]
        with pytest.raises(CriterionLockedError, match="signed off"):
            criterion_service.sign_off(ticket, cast(int, row.id), False)

    def test_sign_off_unknown_criterion_returns_none(
        self, criterion_service, ticket_service, open_story
    ):
        ticket = self._story_in_progress(criterion_service, ticket_service, open_story)
        assert criterion_service.sign_off(ticket, 9999, True) is None


class TestCompleteGuard:
    """Ready for Review -> Complete fails while any criterion is unverified;
    Spike and zero-criterion tickets are exempt (ADR-0025)."""

    def _groomed_story(self, ticket_service, open_story, criteria, to_in_progress=True):
        open_story.approach = "Approach"
        open_story.files_to_change = "files"
        open_story.test_plan = "Plan"
        open_story.validation_steps = "Steps"
        ticket = ticket_service.transition(open_story, TicketStatus.GROOMED, criteria=criteria)
        if to_in_progress:
            ticket = ticket_service.transition(ticket, TicketStatus.IN_PROGRESS, "Started work")
        return ticket

    def _to_ready_for_review(self, ticket_service, ticket):
        ticket.pr_url = "https://github.com/org/repo/pull/1"
        return ticket_service.transition(ticket, TicketStatus.READY_FOR_REVIEW, "PR opened")

    def test_complete_fails_while_a_criterion_is_unverified(
        self, criterion_service, ticket_service, open_story
    ):
        ticket = self._to_ready_for_review(
            ticket_service,
            self._groomed_story(ticket_service, open_story, ["It works", "It is tested"]),
        )
        rows = criterion_service.list_criteria(ticket)
        criterion_service.sign_off(ticket, cast(int, rows[0].id), True)
        with pytest.raises(ValueError, match="verified"):
            ticket_service.transition(ticket, TicketStatus.COMPLETE, "Merged")
        assert ticket.status == TicketStatus.READY_FOR_REVIEW

    def test_complete_passes_once_all_criteria_are_verified(
        self, criterion_service, ticket_service, open_story
    ):
        ticket = self._to_ready_for_review(
            ticket_service, self._groomed_story(ticket_service, open_story, ["It works"])
        )
        for row in criterion_service.list_criteria(ticket):
            criterion_service.sign_off(ticket, cast(int, row.id), True)
        completed = ticket_service.transition(ticket, TicketStatus.COMPLETE, "Merged")
        assert completed.status == TicketStatus.COMPLETE
        assert completed.completed_at is not None

    def test_zero_criterion_ticket_is_exempt(self, criterion_service, ticket_service, open_story):
        """A ticket whose rows were removed while Groomed has no gate to satisfy."""
        ticket = self._groomed_story(
            ticket_service, open_story, ["Temporary"], to_in_progress=False
        )
        row = criterion_service.list_criteria(ticket)[0]
        criterion_service.delete_criterion(ticket, cast(int, row.id))
        ticket_service.transition(ticket, TicketStatus.IN_PROGRESS, "Started work")
        ticket = self._to_ready_for_review(ticket_service, ticket)
        completed = ticket_service.transition(ticket, TicketStatus.COMPLETE, "Merged")
        assert completed.status == TicketStatus.COMPLETE

    def test_spike_is_exempt(self, ticket_service, project_id):
        """A Spike completes without any criterion rows (ADR-0025 exemption)."""
        spike = ticket_service.create_ticket(
            project_id=project_id, title="Research spike", type=TicketType.SPIKE
        )
        ticket_service.transition(spike, TicketStatus.GROOMED, "spike")
        ticket_service.transition(spike, TicketStatus.IN_PROGRESS, "Started")
        ticket_service.transition(spike, TicketStatus.READY_FOR_REVIEW, "Report drafted")
        completed = ticket_service.transition(spike, TicketStatus.COMPLETE, "Report accepted")
        assert completed.status == TicketStatus.COMPLETE

    def test_epic_with_no_criteria_completes(self, ticket_service, project_id):
        epic = ticket_service.create_ticket(
            project_id=project_id, title="Planning epic", type=TicketType.EPIC
        )
        ticket_service.transition(epic, TicketStatus.GROOMED, "planning")
        ticket_service.transition(epic, TicketStatus.IN_PROGRESS, "Started")
        ticket_service.transition(epic, TicketStatus.READY_FOR_REVIEW, "Done planning")
        completed = ticket_service.transition(epic, TicketStatus.COMPLETE, "Merged")
        assert completed.status == TicketStatus.COMPLETE


class TestCriterionHistory:
    """Every criterion add, edit, and sign-off appends a history entry with a
    timestamp and the criterion text (ADR-0025)."""

    def _history(self, session, ticket):
        return list(
            session.exec(
                select(TicketCriterionHistory).where(
                    TicketCriterionHistory.ticket_id == ticket.id  # type: ignore[arg-type]
                )
            ).all()
        )

    def test_add_appends_an_added_entry(self, criterion_service, session, open_story):
        row = criterion_service.add_criterion(open_story, "It works")
        entries = self._history(session, open_story)
        assert len(entries) == 1
        assert entries[0].event == "added"
        assert entries[0].text == row.text
        assert entries[0].at is not None

    def test_edit_appends_an_edited_entry(self, criterion_service, session, open_story):
        row = criterion_service.add_criterion(open_story, "It works")
        criterion_service.update_criterion(open_story, row.id, text="It works end to end")
        entries = self._history(session, open_story)
        assert [e.event for e in entries] == ["added", "edited"]
        assert entries[1].text == "It works end to end"

    def test_noop_update_appends_nothing(self, criterion_service, session, open_story):
        row = criterion_service.add_criterion(open_story, "It works")
        criterion_service.update_criterion(open_story, row.id, text="It works")
        assert [e.event for e in self._history(session, open_story)] == ["added"]

    def test_sign_off_appends_a_verified_entry(
        self, criterion_service, session, ticket_service, open_story
    ):
        open_story.approach = "Approach"
        open_story.files_to_change = "files"
        open_story.test_plan = "Plan"
        open_story.validation_steps = "Steps"
        ticket = ticket_service.transition(open_story, TicketStatus.GROOMED, criteria=["It works"])
        ticket = ticket_service.transition(ticket, TicketStatus.IN_PROGRESS, "Started")
        row = criterion_service.list_criteria(ticket)[0]
        criterion_service.sign_off(ticket, cast(int, row.id), True)
        events = [e.event for e in self._history(session, ticket)]
        assert events == ["added", "verified"]

    def test_groomed_payload_rows_log_added_entries(
        self, criterion_service, session, ticket_service, open_story
    ):
        open_story.approach = "Approach"
        open_story.files_to_change = "files"
        open_story.test_plan = "Plan"
        open_story.validation_steps = "Steps"
        ticket = ticket_service.transition(
            open_story, TicketStatus.GROOMED, criteria=["First", "Second"]
        )
        entries = self._history(session, ticket)
        assert [e.event for e in entries] == ["added", "added"]
        assert [e.text for e in entries] == ["First", "Second"]

    def test_failed_transition_rolls_history_back(
        self, criterion_service, session, ticket_service, open_story
    ):
        """History rows staged with a failed Groomed transition are rolled back."""
        open_story.approach = "Approach"
        open_story.files_to_change = "files"
        open_story.test_plan = "Plan"
        open_story.validation_steps = "Steps"
        # A blank criterion fails validation after staging; nothing persists.
        with pytest.raises(ValueError, match="Criterion text is required"):
            ticket_service.transition(open_story, TicketStatus.GROOMED, criteria=["Good", "   "])
        assert self._history(session, open_story) == []
