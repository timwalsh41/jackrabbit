"""SQLModel table models for Jackrabbit.

API request/response schemas are in `schemas.py`.
"""

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel
from sqlmodel._compat import NaiveDatetime


class TicketType(StrEnum):
    EPIC = "Epic"
    STORY = "Story"
    BUG = "Bug"
    SPIKE = "Spike"


class TicketStatus(StrEnum):
    OPEN = "Open"
    GROOMED = "Groomed"
    IN_PROGRESS = "In Progress"
    READY_FOR_REVIEW = "Ready for Review"
    COMPLETE = "Complete"
    REJECTED = "Rejected"


class LinkType(StrEnum):
    PARENT = "parent"
    CHILD = "child"
    BLOCKS = "blocks"
    BLOCKED_BY = "blocked_by"
    RELATES_TO = "relates_to"


class Priority(StrEnum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


def utc_now() -> datetime:
    return datetime.now(UTC)


class Project(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    prefix: str = Field(unique=True, index=True, max_length=10)
    name: str
    description: str = ""
    color: str = "#6366f1"
    is_system: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    tickets: list["Ticket"] = Relationship(back_populates="project")


class Sprint(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    number: int = Field(unique=True, index=True)  # e.g., 2601 (auto: MAX(number)+1)
    name: str = ""
    description: str = ""
    planned_start: NaiveDatetime | None = None
    planned_end: NaiveDatetime | None = None
    planned_duration_days: int | None = None
    actual_start: NaiveDatetime | None = None
    actual_finish: NaiveDatetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    tickets: list["Ticket"] = Relationship(back_populates="sprint")


class Ticket(SQLModel, table=True):
    __table_args__ = (
        # Serial numbers are unique within a project (matches alembic migration 0001)
        UniqueConstraint("project_id", "number", name="uq_ticket_project_number"),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    sprint_id: int | None = Field(default=None, foreign_key="sprint.id", index=True)
    number: int = Field(index=True)  # Number within project
    type: TicketType = TicketType.STORY
    status: TicketStatus = TicketStatus.OPEN
    priority: Priority = Priority.MEDIUM
    title: str
    description: str = ""
    story_points: int | None = None
    approach: str = ""
    files_to_change: str = ""
    test_plan: str = ""
    validation_steps: str = ""
    branch_name: str | None = None
    pr_url: str | None = None
    original_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    completed_at: NaiveDatetime | None = None

    project: Project | None = Relationship(back_populates="tickets")
    sprint: Sprint | None = Relationship(back_populates="tickets")

    @property
    def full_id(self) -> str:
        """Human-readable zero-padded ticket ID like 'WEB-003' (requires project)."""
        prefix = self.project.prefix if self.project else "UNK"
        return f"{prefix}-{self.number:03d}"

    incoming_links: list["TicketLink"] = Relationship(
        back_populates="target", sa_relationship_kwargs={"foreign_keys": "TicketLink.target_id"}
    )
    outgoing_links: list["TicketLink"] = Relationship(
        back_populates="source", sa_relationship_kwargs={"foreign_keys": "TicketLink.source_id"}
    )
    transitions: list["Transition"] = Relationship(back_populates="ticket")


class TicketLink(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    source_id: int = Field(foreign_key="ticket.id", index=True)
    target_id: int = Field(foreign_key="ticket.id", index=True)
    link_type: LinkType
    created_at: datetime = Field(default_factory=utc_now)

    source: Ticket = Relationship(
        back_populates="outgoing_links",
        sa_relationship_kwargs={"foreign_keys": "TicketLink.source_id"},
    )
    target: Ticket = Relationship(
        back_populates="incoming_links",
        sa_relationship_kwargs={"foreign_keys": "TicketLink.target_id"},
    )


class Transition(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    ticket_id: int = Field(foreign_key="ticket.id", index=True)
    from_status: TicketStatus | None = None
    to_status: TicketStatus
    reason: str | None = None
    at: datetime = Field(default_factory=utc_now)

    ticket: Ticket = Relationship(back_populates="transitions")
