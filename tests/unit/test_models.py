"""Tests for Jackrabbit models."""

from jackrabbit.models import (
    LinkType,
    Priority,
    TicketStatus,
    TicketType,
)
from jackrabbit.schemas import (
    ProjectCreate,
    ProjectUpdate,
    SprintCreate,
    TicketCreate,
    TicketLinkCreate,
)


def test_enums() -> None:
    """Test enum values."""
    assert TicketType.EPIC.value == "Epic"
    assert TicketType.STORY.value == "Story"
    assert TicketType.BUG.value == "Bug"
    assert TicketType.SPIKE.value == "Spike"

    assert TicketStatus.OPEN.value == "Open"
    assert TicketStatus.GROOMED.value == "Groomed"
    assert TicketStatus.IN_PROGRESS.value == "In Progress"
    assert TicketStatus.READY_FOR_REVIEW.value == "Ready for Review"
    assert TicketStatus.COMPLETE.value == "Complete"
    assert TicketStatus.REJECTED.value == "Rejected"

    assert Priority.LOW.value == "Low"
    assert Priority.MEDIUM.value == "Medium"
    assert Priority.HIGH.value == "High"
    assert Priority.CRITICAL.value == "Critical"

    assert LinkType.PARENT.value == "parent"
    assert LinkType.CHILD.value == "child"
    assert LinkType.BLOCKS.value == "blocks"
    assert LinkType.BLOCKED_BY.value == "blocked_by"
    assert LinkType.RELATES_TO.value == "relates_to"


def test_project_create_schema() -> None:
    """Test ProjectCreate schema validation."""
    project = ProjectCreate(prefix="WEB", name="Web Project")
    assert project.prefix == "WEB"
    assert project.name == "Web Project"
    assert project.description == ""
    assert project.color == "#6366f1"

    project_full = ProjectCreate(
        prefix="API",
        name="API Project",
        description="Backend API",
        color="#ff0000",
    )
    assert project_full.prefix == "API"
    assert project_full.color == "#ff0000"


def test_ticket_create_schema() -> None:
    """Test TicketCreate schema validation."""
    ticket = TicketCreate(project_id=1, title="Test ticket")
    assert ticket.project_id == 1
    assert ticket.title == "Test ticket"
    assert ticket.type == TicketType.STORY
    assert ticket.priority == Priority.MEDIUM
    assert ticket.story_points is None

    ticket_full = TicketCreate(
        project_id=1,
        title="Full ticket",
        type=TicketType.BUG,
        description="Bug description",
        priority=Priority.HIGH,
        story_points=5,
    )
    assert ticket_full.type == TicketType.BUG
    assert ticket_full.priority == Priority.HIGH
    assert ticket_full.story_points == 5


def test_sprint_create_schema() -> None:
    """Test SprintCreate schema validation."""
    sprint = SprintCreate(number=2601)
    assert sprint.number == 2601
    assert sprint.name == ""
    assert sprint.description == ""
    assert sprint.planned_start is None
    assert sprint.planned_end is None
    assert sprint.planned_duration_days is None
    assert sprint.actual_start is None
    assert sprint.actual_finish is None


def test_sprint_create_number_optional_auto_assigned() -> None:
    """SprintCreate.number is optional so the API can auto-assign MAX(number)+1."""
    sprint = SprintCreate()
    assert sprint.number is None


def test_ticket_link_create_schema() -> None:
    """Test TicketLinkCreate schema validation."""
    link = TicketLinkCreate(source_id=1, target_id=2, link_type=LinkType.BLOCKS)
    assert link.source_id == 1
    assert link.target_id == 2
    assert link.link_type == LinkType.BLOCKS


def test_project_update_schema() -> None:
    """Test ProjectUpdate schema validation."""
    # Partial update
    update = ProjectUpdate(name="New Name")
    assert update.name == "New Name"
    assert update.description is None
    assert update.color is None

    # Full update
    update_full = ProjectUpdate(
        name="Updated Project",
        description="Updated description",
        color="#ff0000",
    )
    assert update_full.name == "Updated Project"
    assert update_full.description == "Updated description"
    assert update_full.color == "#ff0000"

    # Validation: empty name should fail
    import pytest

    with pytest.raises(ValueError):
        ProjectUpdate(name="")

    # Validation: invalid color should fail
    with pytest.raises(ValueError):
        ProjectUpdate(color="not-a-color")
    with pytest.raises(ValueError):
        ProjectUpdate(color="#GGGGGG")
