"""Unit tests for the label service: identity, name rules, attach/detach/replace."""

import pytest
from jackrabbit.labels import label_color
from jackrabbit.models import Project, TicketType
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
def label_service(session):
    return LabelService(session)


@pytest.fixture
def ticket_service(session):
    return TicketService(session)


@pytest.fixture
def project_service(session):
    return ProjectService(session)


@pytest.fixture
def ticket(ticket_service, project_service):
    """A plain ticket to hang labels off."""
    project = project_service.get_project_by_prefix("UNS")
    return ticket_service.create_ticket(project_id=project.id, title="Label me")


class TestLabelIdentity:
    """A label's identity is case-insensitive; the first spelling is kept."""

    def test_same_name_different_case_is_one_label(self, label_service):
        label, created = label_service.find_or_create("Backend")
        assert created is True

        same, created_again = label_service.find_or_create("backend")
        assert created_again is False
        assert same.id == label.id

    def test_first_spelling_is_preserved(self, label_service):
        label, _ = label_service.find_or_create("Backend")
        same, _ = label_service.find_or_create("BACKEND")
        assert same.name == "Backend"

    def test_names_are_trimmed(self, label_service):
        label, _ = label_service.find_or_create("  Backend  ")
        assert label.name == "Backend"

        same, created = label_service.find_or_create("backend")
        assert created is False
        assert same.id == label.id

    def test_colour_is_derived_from_the_identity_key(self, label_service):
        label, _ = label_service.find_or_create("Backend")
        same, _ = label_service.find_or_create("backend")
        assert label.color == same.color
        assert label.color.startswith("#")


class TestLabelNameRules:
    """Names are trimmed, at most 50 characters, and restricted to a charset."""

    def test_empty_name_is_rejected(self, label_service):
        with pytest.raises(ValueError, match="empty"):
            label_service.find_or_create("   ")

    def test_name_longer_than_50_characters_is_rejected(self, label_service):
        with pytest.raises(ValueError, match="50"):
            label_service.find_or_create("x" * 51)

    def test_name_of_exactly_50_characters_is_accepted(self, label_service):
        label, created = label_service.find_or_create("x" * 50)
        assert created is True
        assert len(label.name) == 50

    @pytest.mark.parametrize(
        "name",
        [
            "back/end",
            "back,end",
            "back.end",
            "emoji🐛",
            "label!",
            "semi;colon",
        ],
    )
    def test_disallowed_characters_are_rejected(self, label_service, name):
        with pytest.raises(ValueError):
            label_service.find_or_create(name)

    @pytest.mark.parametrize(
        "name",
        [
            "Backend",
            "triage:ready-for-agent",
            "needs review",
            "under_score",
            "kebab-case",
            "release 2026",
            "v2",
        ],
    )
    def test_allowed_names_are_accepted(self, label_service, name):
        label, created = label_service.find_or_create(name)
        assert created is True
        assert label.name == name

    def test_rejection_explains_the_rule(self, label_service):
        with pytest.raises(ValueError) as excinfo:
            label_service.find_or_create("back/end")
        message = str(excinfo.value)
        assert "letters" in message
        assert "digits" in message
        assert "spaces" in message
        assert "hyphens" in message
        assert "underscores" in message
        assert "colons" in message


class TestLabelColour:
    """A label's colour is derived from its identity key, never stored."""

    def test_colour_is_derived_from_the_identity_key(self, label_service):
        label, _ = label_service.find_or_create("Backend")
        assert label.color == label_color("backend")

    def test_colour_is_stable(self):
        # The browser mirrors this derivation, so the value is pinned here.
        assert label_color("backend") == "#10b981"
        assert label_color("triage:ready-for-agent") == "#f97316"


class TestAttachDetach:
    """Attaching creates on demand; detaching removes the attachment only."""

    def test_attach_creates_the_label_on_demand(self, label_service, ticket):
        label = label_service.attach(ticket.id, "Backend")
        assert label.id is not None
        assert label.name == "Backend"
        assert [label.name for label in label_service.labels_for_ticket(ticket.id)] == ["Backend"]

    def test_attach_existing_label_attaches_it(self, label_service, ticket):
        first = label_service.attach(ticket.id, "Backend")
        second = label_service.attach(ticket.id, "backend")
        assert second.id == first.id
        assert len(label_service.list_labels()) == 1

    def test_attach_is_idempotent(self, label_service, ticket):
        label_service.attach(ticket.id, "Backend")
        label_service.attach(ticket.id, "Backend")
        assert len(label_service.labels_for_ticket(ticket.id)) == 1

    def test_detach_removes_the_attachment(self, label_service, ticket):
        label = label_service.attach(ticket.id, "Backend")
        assert label_service.detach(ticket.id, label.id) is True
        assert label_service.labels_for_ticket(ticket.id) == []
        # The label itself stays in the registry (unused labels persist).
        assert len(label_service.list_labels()) == 1

    def test_detach_unknown_label_returns_false(self, label_service, ticket):
        assert label_service.detach(ticket.id, 9999) is False

    def test_detach_a_label_attached_to_another_ticket(
        self, label_service, ticket, ticket_service, project_service
    ):
        project = project_service.get_project_by_prefix("UNS")
        other = ticket_service.create_ticket(project_id=project.id, title="Other")
        label = label_service.attach(ticket.id, "Backend")
        assert label_service.detach(other.id, label.id) is False
        assert len(label_service.labels_for_ticket(ticket.id)) == 1


class TestReplace:
    """Updating a ticket's labels replaces the whole set."""

    def test_replace_swaps_the_whole_set(self, label_service, ticket):
        label_service.replace(ticket.id, ["Backend", "Frontend"])
        labels = label_service.labels_for_ticket(ticket.id)
        assert {label.name for label in labels} == {"Backend", "Frontend"}

        label_service.replace(ticket.id, ["Backend"])
        labels = label_service.labels_for_ticket(ticket.id)
        assert [label.name for label in labels] == ["Backend"]

    def test_replace_with_no_names_clears_the_labels(self, label_service, ticket):
        label_service.replace(ticket.id, ["Backend"])
        label_service.replace(ticket.id, [])
        assert label_service.labels_for_ticket(ticket.id) == []

    def test_replace_keeps_the_first_spelling_of_existing_labels(self, label_service, ticket):
        label_service.attach(ticket.id, "Backend")
        label_service.replace(ticket.id, ["backend"])
        assert [label.name for label in label_service.labels_for_ticket(ticket.id)] == ["Backend"]

    def test_replace_creates_missing_labels(self, label_service, ticket):
        label_service.replace(ticket.id, ["Backend", "Docs"])
        assert len(label_service.list_labels()) == 2


class TestAnyTicketType:
    """Any ticket may carry any label, and any number of them."""

    @pytest.mark.parametrize(
        "ticket_type",
        [TicketType.EPIC, TicketType.STORY, TicketType.BUG, TicketType.SPIKE],
    )
    def test_every_ticket_type_can_carry_labels(
        self, label_service, ticket_service, project_service, ticket_type
    ):
        project = project_service.get_project_by_prefix("UNS")
        typed = ticket_service.create_ticket(
            project_id=project.id, title=f"A {ticket_type.value}", type=ticket_type
        )
        label_service.attach(typed.id, "Backend")
        assert [label.name for label in label_service.labels_for_ticket(typed.id)] == ["Backend"]

    def test_a_ticket_can_carry_many_labels(self, label_service, ticket):
        names = ["Backend", "Frontend", "triage:ready-for-agent", "release 2026"]
        label_service.replace(ticket.id, names)
        assert len(label_service.labels_for_ticket(ticket.id)) == len(names)


class TestRegistry:
    """The vocabulary is readable, with a usage count per label."""

    def test_list_labels_returns_the_whole_registry(self, label_service, ticket):
        label_service.attach(ticket.id, "Backend")
        label_service.attach(ticket.id, "Frontend")
        assert {label.name for label in label_service.list_labels()} == {"Backend", "Frontend"}

    def test_usage_counts_are_reported_per_label(
        self, label_service, ticket, ticket_service, project_service
    ):
        project = project_service.get_project_by_prefix("UNS")
        other = ticket_service.create_ticket(project_id=project.id, title="Other")
        label_service.attach(ticket.id, "Backend")
        label_service.attach(other.id, "Backend")
        label_service.attach(other.id, "Frontend")

        usage = {
            entry["label"].name: entry["usage_count"]
            for entry in label_service.list_labels_with_usage()
        }
        assert usage == {"Backend": 2, "Frontend": 1}

    def test_unused_labels_are_not_in_the_in_use_list(self, label_service, ticket):
        label_service.attach(ticket.id, "Backend")
        label_service.find_or_create("Typo")
        assert [label.name for label in label_service.list_labels_in_use()] == ["Backend"]
        # ... but the unused label stays in the registry.
        assert {label.name for label in label_service.list_labels()} == {"Backend", "Typo"}

    def test_registry_is_empty_to_begin_with(self, label_service):
        assert label_service.list_labels() == []
        assert label_service.list_labels_with_usage() == []


class TestTicketDeletion:
    """Deleting a ticket removes its label attachments and leaves nothing behind."""

    def test_deleting_a_ticket_removes_its_attachments(self, label_service, ticket_service, ticket):
        label_service.attach(ticket.id, "Backend")
        assert ticket_service.delete_ticket(ticket.id) is True

        assert label_service.labels_for_ticket(ticket.id) == []
        # The label itself survives (unused labels persist) with a zero count.
        usage = {
            entry["label"].name: entry["usage_count"]
            for entry in label_service.list_labels_with_usage()
        }
        assert usage == {"Backend": 0}

    def test_no_attachment_rows_are_left_behind(
        self, session, label_service, ticket_service, ticket
    ):
        from jackrabbit.models import TicketLabel
        from sqlmodel import select

        label_service.attach(ticket.id, "Backend")
        ticket_service.delete_ticket(ticket.id)

        rows = session.exec(select(TicketLabel)).all()
        assert rows == []
