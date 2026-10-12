"""Pydantic API schemas for Jackrabbit (request/response models).

Separate from SQLModel table classes to maintain API-First design.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from jackrabbit.models import (
    LinkType,
    Priority,
    TicketStatus,
    TicketType,
)


class ProjectBase(BaseModel):
    prefix: str
    name: str
    description: str = ""
    color: str = "#6366f1"


class ProjectCreate(ProjectBase):
    pass


class ProjectRead(ProjectBase):
    id: int
    is_system: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SprintBase(BaseModel):
    number: str
    name: str = ""
    description: str = ""
    planned_start: datetime | None = None
    planned_end: datetime | None = None


class SprintCreate(SprintBase):
    pass


class SprintRead(SprintBase):
    id: int
    actual_start: datetime | None = None
    actual_end: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TicketBase(BaseModel):
    project_id: int
    title: str
    type: TicketType = TicketType.STORY
    description: str = ""
    priority: Priority = Priority.MEDIUM
    story_points: int | None = None


class TicketCreate(TicketBase):
    pass


class TicketUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    type: TicketType | None = None
    status: TicketStatus | None = None
    priority: Priority | None = None
    story_points: int | None = None
    approach: str | None = None
    files_to_change: str | None = None
    test_plan: str | None = None
    validation_steps: str | None = None
    sprint_id: int | None = None


class TicketRead(TicketBase):
    id: int
    number: int
    status: TicketStatus
    approach: str
    files_to_change: str
    test_plan: str
    validation_steps: str
    sprint_id: int | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class TicketLinkBase(BaseModel):
    source_id: int
    target_id: int
    link_type: LinkType


class TicketLinkCreate(TicketLinkBase):
    pass


class TicketLinkRead(TicketLinkBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
