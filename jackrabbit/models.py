"""SQLModel table models for Jackrabbit.

API request/response schemas are in `schemas.py`.
"""

from datetime import UTC, datetime
from enum import StrEnum

from sqlmodel import Field, Relationship, SQLModel


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
    number: str = Field(unique=True, index=True, max_length=10)  # e.g., "2601"
    name: str = ""
    description: str = ""
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    actual_start: datetime | None = None
    actual_end: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    tickets: list["Ticket"] = Relationship(back_populates="sprint")


class Ticket(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    sprint_id: int | None = Field(default=None, foreign_key="sprint.id", index=True)
    number: int = Field(index=True)  # Number within project
    type: TicketType = Field(default=TicketType.STORY)
    status: TicketStatus = Field(default=TicketStatus.OPEN, index=True)
    priority: Priority = Field(default=Priority.MEDIUM, index=True)
    title: str
    description: str = ""
    story_points: int | None = None

    # Groomed fields
    approach: str = ""
    files_to_change: str = ""
    test_plan: str = ""
    validation_steps: str = ""

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None

    project: Project = Relationship(back_populates="tickets")
    sprint: Sprint | None = Relationship(back_populates="tickets")
    outgoing_links: list["TicketLink"] = Relationship(
        back_populates="source", sa_relationship_kwargs={"foreign_keys": "TicketLink.source_id"}
    )
    incoming_links: list["TicketLink"] = Relationship(
        back_populates="target", sa_relationship_kwargs={"foreign_keys": "TicketLink.target_id"}
    )

    @property
    def full_id(self) -> str:
        return f"{self.project.prefix}-{self.number}"


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
