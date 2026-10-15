"""Pydantic API schemas for Jackrabbit (request/response models).

Separate from SQLModel table classes to maintain API-First design.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

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
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "prefix": "WEB",
                    "name": "Web Project",
                    "description": "Web application",
                    "color": "#6366f1",
                }
            ]
        }
    )

    @field_validator("prefix")
    @classmethod
    def validate_prefix(cls, v: str) -> str:
        v = v.upper().strip()
        if not v:
            raise ValueError("Prefix is required")
        if len(v) < 2 or len(v) > 10:
            raise ValueError("Prefix must be 2-10 characters")
        if not v.isalpha():
            raise ValueError("Prefix must contain only letters")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        return v

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("#") or len(v) != 7:
            raise ValueError("Color must be a hex color like #6366f1")
        try:
            int(v[1:], 16)
        except ValueError as e:
            raise ValueError("Color must be a valid hex color") from e
        return v


class ProjectRead(ProjectBase):
    id: int
    is_system: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Name cannot be empty")
        return v

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v.startswith("#") or len(v) != 7:
                raise ValueError("Color must be a hex color like #6366f1")
            try:
                int(v[1:], 16)
            except ValueError as e:
                raise ValueError("Color must be a valid hex color") from e
        return v


class _EmptyStringToNoneMixin(BaseModel):
    """Treat empty-string form fields (HTML forms submit "" for untouched
    optional inputs) as absent for optional date/int fields."""

    @field_validator(
        "planned_start",
        "planned_end",
        "actual_start",
        "actual_finish",
        "planned_duration_days",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def _empty_string_to_none(cls, v: object) -> object:
        if v == "":
            return None
        return v


class SprintBase(_EmptyStringToNoneMixin):
    number: int
    name: str = ""
    description: str = ""
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    planned_duration_days: int | None = None
    actual_start: datetime | None = None
    actual_finish: datetime | None = None


class SprintCreate(SprintBase):
    # number is optional on create: when omitted the API auto-assigns
    # MAX(number)+1 starting at 2601; clients may override it explicitly.
    number: int | None = None  # type: ignore[assignment]

    @field_validator("number", mode="before")
    @classmethod
    def _empty_number_to_none(cls, v: object) -> object:
        # An untouched number field ("") means "auto-assign"
        if v == "":
            return None
        return v


class SprintRead(SprintBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SprintUpdate(_EmptyStringToNoneMixin):
    name: str | None = None
    description: str | None = None
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    planned_duration_days: int | None = None
    actual_start: datetime | None = None
    actual_finish: datetime | None = None


class SprintReadWithTickets(SprintRead):
    tickets: list["TicketRead"] = []
    status: str = "Planned"  # Planned, Active, Complete


class SprintReadWithTicketsByStatus(SprintRead):
    tickets_by_status: dict[str, list["TicketRead"]] = {}
    status: str = "Planned"  # Planned, Active, Complete


class TicketBase(BaseModel):
    project_id: int
    title: str
    type: TicketType = TicketType.STORY
    description: str = ""
    priority: Priority = Priority.MEDIUM
    # story_points defined in subclasses to allow different validation


class TicketCreate(TicketBase):
    approach: str = ""
    files_to_change: str = ""
    test_plan: str = ""
    validation_steps: str = ""
    sprint_id: int | None = None
    status: TicketStatus = TicketStatus.OPEN
    story_points: str | int | None = None

    @field_validator("story_points", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        if v == "" or v is None:
            return None
        if isinstance(v, str):
            try:
                return int(v)
            except ValueError:
                return None
        return v


class TicketUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    type: TicketType | None = None
    status: TicketStatus | None = None
    priority: Priority | None = None
    story_points: str | int | None = None

    @field_validator("story_points", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        if v == "" or v is None:
            return None
        if isinstance(v, str):
            try:
                return int(v)
            except ValueError:
                return None
        return v

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
    original_id: str | None = None
    branch_name: str | None = None
    pr_url: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    story_points: int | None = None

    model_config = ConfigDict(from_attributes=True)


class TicketReadWithDetails(TicketRead):
    """Ticket with links and transitions for detailed view."""

    project_prefix: str
    links: list["TicketLinkRead"] = []
    transitions: list[dict] = []

    @property
    def full_id(self) -> str:
        return f"{self.project_prefix}-{self.number:03d}"


class PaginatedResponse(BaseModel):
    items: list[TicketRead]
    total: int
    page: int
    page_size: int
    total_pages: int

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


class TransitionRequest(BaseModel):
    to_status: TicketStatus
    reason: str | None = None
    branch_name: str | None = None
    pr_url: str | None = None
    # Grooming fields (required for Open -> Groomed transition)
    approach: str | None = None
    files_to_change: str | None = None
    test_plan: str | None = None
    validation_steps: str | None = None


class TransitionResponse(BaseModel):
    ticket_id: int
    from_status: TicketStatus | None
    to_status: TicketStatus
    reason: str | None
    at: datetime
    full_id: str

    model_config = ConfigDict(from_attributes=True)


class CanTransitionResponse(BaseModel):
    can_transition: bool
    error_message: str | None = None


class MoveProjectRequest(BaseModel):
    project_id: int


class MoveProjectResponse(BaseModel):
    ticket_id: int
    old_project_id: int
    new_project_id: int
    old_full_id: str
    new_full_id: str
    original_id: str | None = None

    model_config = ConfigDict(from_attributes=True)


class PlanSprintTicketCounts(BaseModel):
    Open: int = 0
    Groomed: int = 0
    In_Progress: int = 0
    Ready_for_Review: int = 0
    Complete: int = 0
    Rejected: int = 0


class PlanSprintResponse(BaseModel):
    id: int
    number: int
    name: str
    description: str
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    planned_duration_days: int | None = None
    actual_start: datetime | None = None
    actual_finish: datetime | None = None
    ticket_counts: PlanSprintTicketCounts
    total_tickets: int
    status: str

    model_config = ConfigDict(from_attributes=True)


class PlanResponse(BaseModel):
    sprints: list[PlanSprintResponse]
    unsprinted_count: int

    model_config = ConfigDict(from_attributes=True)
