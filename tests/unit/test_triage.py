"""Unit tests for triage roles recorded as labels: the canonical vocabulary,
the triage service that records a role, and the role a ticket carries."""

import pytest
from jackrabbit.models import Project
from jackrabbit.services import LabelService, ProjectService, TicketService, TriageService
from jackrabbit.triage import (
    TRIAGE_LABEL_NAMES,
    TRIAGE_ROLES,
    TriageRole,
    is_triage_label_name,
    triage_label_name,
    triage_role_from_label_name,
    triage_role_from_labels,
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
def triage_service(session, label_service):
    return TriageService(session, label_service)


@pytest.fixture
def ticket(ticket_service, project_service):
    """A plain ticket to record a triage role on."""
    project = project_service.get_project_by_prefix("UNS")
    return ticket_service.create_ticket(project_id=project.id, title="Triage me")


class TestTriageVocabulary:
    """The five canonical roles, and the label each one is recorded as."""

    def test_there_are_five_canonical_roles(self):
        assert [role.value for role in TRIAGE_ROLES] == [
            "needs-triage",
            "needs-info",
            "ready-for-agent",
            "ready-for-human",
            "wontfix",
        ]

    def test_each_role_is_recorded_as_a_namespaced_label(self):
        assert triage_label_name("needs-triage") == "triage:needs-triage"
        assert triage_label_name("needs-info") == "triage:needs-info"
        assert triage_label_name("ready-for-agent") == "triage:ready-for-agent"
        assert triage_label_name("ready-for-human") == "triage:ready-for-human"
        assert triage_label_name("wontfix") == "triage:wontfix"

    def test_the_canonical_label_names_are_the_five_of_them(self):
        assert TRIAGE_LABEL_NAMES == (
            "triage:needs-triage",
            "triage:needs-info",
            "triage:ready-for-agent",
            "triage:ready-for-human",
            "triage:wontfix",
        )

    def test_an_unknown_role_is_rejected(self):
        with pytest.raises(ValueError):
            triage_label_name("ready-for-nobody")

    def test_a_triage_label_is_recognised_by_its_namespace(self):
        assert is_triage_label_name("triage:ready-for-agent") is True
        assert is_triage_label_name("Backend") is False

    def test_a_label_name_reads_back_as_its_role(self):
        assert triage_role_from_label_name("triage:ready-for-agent") is TriageRole.READY_FOR_AGENT
        assert triage_role_from_label_name("TRIAGE:WONTFIX") is TriageRole.WONTFIX

    def test_a_label_outside_the_namespace_records_no_role(self):
        assert triage_role_from_label_name("Backend") is None
        assert triage_role_from_label_name("triage:ready-for-nobody") is None

    def test_the_role_of_a_set_of_labels_is_the_triage_one(self):
        class _Label:
            def __init__(self, name: str):
                self.name = name

        labels = [_Label("Backend"), _Label("triage:needs-info")]
        assert triage_role_from_labels(labels) is TriageRole.NEEDS_INFO
        assert triage_role_from_labels([_Label("Backend")]) is None
        assert triage_role_from_labels([]) is None


class TestTriageService:
    """Recording and reading a ticket's triage role as a label."""

    def test_setting_a_role_attaches_the_matching_label(
        self, triage_service, label_service, ticket
    ):
        triage_service.set_role(ticket.id, "ready-for-agent")

        names = [label.name for label in label_service.labels_for_ticket(ticket.id)]
        assert names == ["triage:ready-for-agent"]

    def test_the_label_is_created_on_demand(self, triage_service, label_service, ticket):
        triage_service.set_role(ticket.id, "wontfix")

        label, created = label_service.find_or_create("triage:wontfix")
        assert created is False  # it already existed — set_role created it
        assert label.name == "triage:wontfix"

    def test_the_role_reads_back(self, triage_service, ticket):
        triage_service.set_role(ticket.id, "needs-info")
        assert triage_service.role_for(ticket.id) is TriageRole.NEEDS_INFO

    def test_a_ticket_without_a_role_has_none(self, triage_service, ticket):
        assert triage_service.role_for(ticket.id) is None

    def test_setting_a_role_replaces_the_previous_one(self, triage_service, label_service, ticket):
        triage_service.set_role(ticket.id, "needs-triage")
        triage_service.set_role(ticket.id, "ready-for-human")

        names = [label.name for label in label_service.labels_for_ticket(ticket.id)]
        assert names == ["triage:ready-for-human"]
        assert triage_service.role_for(ticket.id) is TriageRole.READY_FOR_HUMAN

    def test_other_labels_are_left_alone(self, triage_service, label_service, ticket):
        label_service.attach(ticket.id, "Backend")

        triage_service.set_role(ticket.id, "ready-for-agent")

        names = sorted(label.name for label in label_service.labels_for_ticket(ticket.id))
        assert names == ["Backend", "triage:ready-for-agent"]

    def test_an_unknown_role_is_rejected(self, triage_service, ticket):
        with pytest.raises(ValueError):
            triage_service.set_role(ticket.id, "ready-for-nobody")

        assert triage_service.role_for(ticket.id) is None

    def test_the_role_is_visible_on_the_ticket(self, triage_service, ticket):
        triage_service.set_role(ticket.id, "wontfix")

        assert ticket.triage_role is TriageRole.WONTFIX

    def test_a_ticket_without_a_triage_label_has_no_role(self, ticket):
        assert ticket.triage_role is None
