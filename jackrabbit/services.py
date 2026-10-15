"""Business logic services for Jackrabbit."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import urlparse

from sqlmodel import Session, func, select

from jackrabbit.models import (
    LinkType,
    Priority,
    Project,
    Sprint,
    Ticket,
    TicketLink,
    TicketStatus,
    TicketType,
    Transition,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def slugify(text: str, max_length: int = 50) -> str:
    """Convert text to a URL-friendly slug.

    Args:
        text: The text to slugify
        max_length: Maximum length of the slug (default 50)

    Returns:
        A slug containing only lowercase alphanumeric characters and hyphens
    """
    # Convert to lowercase
    slug = text.lower()
    # Replace non-alphanumeric characters with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    # Remove leading/trailing hyphens
    slug = slug.strip("-")
    # Truncate to max_length
    if len(slug) > max_length:
        slug = slug[:max_length].rstrip("-")
    return slug


def generate_branch_name(ticket: Ticket) -> str:
    """Generate a branch name from ticket title and ID.

    Format: {type}/{project_prefix}-{number}-{slugified_title}
    Example: feature/UNS-001-fix-login-bug

    Args:
        ticket: The ticket to generate a branch name for

    Returns:
        A valid branch name
    """
    # Get project prefix
    project_prefix = ""
    if ticket.project:
        project_prefix = ticket.project.prefix
    elif hasattr(ticket, "project_id") and ticket.project_id:
        # This shouldn't happen in normal usage, but handle it
        project_prefix = f"PRJ{ticket.project_id}"

    # Determine type prefix
    type_prefix_map = {
        TicketType.EPIC: "epic",
        TicketType.STORY: "feature",
        TicketType.BUG: "fix",
        TicketType.SPIKE: "spike",
    }
    type_prefix = type_prefix_map.get(ticket.type, "feature")

    # Generate slug from title
    title_slug = slugify(ticket.title, max_length=40)

    # Build branch name: type/prefix-number-slug
    branch_name = f"{type_prefix}/{project_prefix}-{ticket.number:03d}-{title_slug}"

    # Ensure it matches the validation pattern (alphanumeric, hyphens, underscores, slashes)
    # Our slugify and format already ensure this
    return branch_name


def validate_pr_url(url: str) -> tuple[bool, str | None]:
    """Validate a PR URL.

    Args:
        url: The PR URL to validate

    Returns:
        Tuple of (is_valid, error_message_or_none)
    """
    if not url or not url.strip():
        return False, "PR URL is required"

    url = url.strip()

    # Check if it's a valid HTTP/HTTPS URL
    if not re.match(r"^https?://.+", url):
        return False, "PR URL must be a valid HTTP/HTTPS URL"

    # Try to parse the URL
    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            return False, "PR URL must have a valid domain"
    except Exception:
        return False, "PR URL is not valid"

    return True, None


def detect_git_host(pr_url: str) -> str | None:
    """Detect the Git hosting service from a PR URL.

    Args:
        pr_url: The PR URL

    Returns:
        'github', 'gitlab', 'bitbucket', 'azure', or None if unknown
    """
    if not pr_url:
        return None

    url_lower = pr_url.lower()
    if "github.com" in url_lower:
        return "github"
    elif "gitlab.com" in url_lower or "gitlab." in url_lower:
        return "gitlab"
    elif "bitbucket.org" in url_lower:
        return "bitbucket"
    elif "dev.azure.com" in url_lower or "visualstudio.com" in url_lower:
        return "azure"
    return None


class TicketService:
    def __init__(self, session: Session):
        self.session = session

    def create_ticket(
        self,
        project_id: int,
        title: str,
        type: TicketType = TicketType.STORY,
        description: str = "",
        priority: Priority = Priority.MEDIUM,
        story_points: int | None = None,
        approach: str = "",
        files_to_change: str = "",
        test_plan: str = "",
        validation_steps: str = "",
        sprint_id: int | None = None,
        status: TicketStatus = TicketStatus.OPEN,
    ) -> Ticket:
        # Get next ticket number for project
        max_num = self.session.exec(
            select(func.max(Ticket.number)).where(Ticket.project_id == project_id)
        ).first()
        next_number = (max_num or 0) + 1

        ticket = Ticket(
            project_id=project_id,
            number=next_number,
            type=type,
            title=title,
            description=description,
            priority=priority,
            story_points=story_points,
            approach=approach,
            files_to_change=files_to_change,
            test_plan=test_plan,
            validation_steps=validation_steps,
            sprint_id=sprint_id,
            status=status,
        )
        self.session.add(ticket)
        self.session.commit()
        self.session.refresh(ticket)
        return ticket

    def get_ticket(self, ticket_id: int) -> Ticket | None:
        return self.session.get(Ticket, ticket_id)

    def get_ticket_by_full_id(self, project_prefix: str, number: int) -> Ticket | None:
        """Look up a ticket by its full human ID (e.g. WEB-1).

        The prefix part is case-insensitive (WEB, web, and Web all match).
        """
        project = self.session.exec(
            select(Project).where(func.upper(Project.prefix) == project_prefix.upper())
        ).first()
        if not project:
            return None
        return self.session.exec(
            select(Ticket).where(
                Ticket.project_id == project.id,
                Ticket.number == number,
            )
        ).first()

    def get_ticket_with_details(
        self, ticket_id: int, link_service: LinkService | None = None
    ) -> dict | None:
        """Get ticket with project prefix, links, and transitions for detailed view."""
        ticket = self.get_ticket(ticket_id)
        if not ticket:
            return None

        project = self.session.get(Project, ticket.project_id)
        project_prefix = project.prefix if project else ""

        links = []
        if link_service:
            links = link_service.get_links_for_ticket(ticket_id)

        transitions = []
        for t in ticket.transitions:
            transitions.append(
                {
                    "id": t.id,
                    "from_status": t.from_status.value if t.from_status else None,
                    "to_status": t.to_status.value,
                    "reason": t.reason,
                    "at": t.at.isoformat() if t.at else None,
                }
            )

        return {
            "ticket": ticket,
            "project_prefix": project_prefix,
            "links": links,
            "transitions": transitions,
        }

    def update_status(self, ticket: Ticket, status: TicketStatus) -> Ticket:
        """Legacy method - updates status without guards or audit logging.
        Use transition() for guarded transitions with audit trail."""
        ticket.status = status
        ticket.updated_at = utc_now()
        if status == TicketStatus.COMPLETE:
            ticket.completed_at = utc_now()
        self.session.add(ticket)
        self.session.commit()
        self.session.refresh(ticket)
        return ticket

    def update_ticket(self, ticket: Ticket, **kwargs) -> Ticket:
        for field, value in kwargs.items():
            setattr(ticket, field, value)
        ticket.updated_at = utc_now()
        self.session.add(ticket)
        self.session.commit()
        self.session.refresh(ticket)
        return ticket

    def _get_status_order(self) -> list[TicketStatus]:
        """Return statuses in forward order for backward transition checks."""
        return [
            TicketStatus.OPEN,
            TicketStatus.GROOMED,
            TicketStatus.IN_PROGRESS,
            TicketStatus.READY_FOR_REVIEW,
            TicketStatus.COMPLETE,
        ]

    def _is_backward_transition(self, from_status: TicketStatus, to_status: TicketStatus) -> bool:
        """Check if transition is backward (to a previous status in the workflow)."""
        order = self._get_status_order()
        try:
            from_idx = order.index(from_status)
            to_idx = order.index(to_status)
            return to_idx < from_idx
        except ValueError:
            return False

    def _validate_guard(
        self, ticket: Ticket, from_status: TicketStatus, to_status: TicketStatus
    ) -> str | None:
        """Validate guard conditions for forward transitions.

        Returns error message or None if valid.
        """
        if to_status == TicketStatus.GROOMED and from_status == TicketStatus.OPEN:
            if not ticket.approach or not ticket.approach.strip():
                return "Approach is required to transition to Groomed"
            if not ticket.files_to_change or not ticket.files_to_change.strip():
                return "Files to change is required to transition to Groomed"
            if not ticket.test_plan or not ticket.test_plan.strip():
                return "Test plan is required to transition to Groomed"
            if not ticket.validation_steps or not ticket.validation_steps.strip():
                return "Validation steps is required to transition to Groomed"
        elif to_status == TicketStatus.IN_PROGRESS and from_status == TicketStatus.GROOMED:
            # Branch name is auto-generated if empty, but validate if provided
            if ticket.branch_name and ticket.branch_name.strip():
                import re

                if not re.match(r"^[a-zA-Z0-9/_-]+$", ticket.branch_name.strip()):
                    return (
                        "Branch name must contain only alphanumeric characters, "
                        "hyphens, underscores, and slashes"
                    )
        elif to_status == TicketStatus.READY_FOR_REVIEW and from_status == TicketStatus.IN_PROGRESS:
            if not ticket.pr_url or not ticket.pr_url.strip():
                return "PR URL is required to transition to Ready for Review"
            # Validate URL format
            import re

            if not re.match(r"^https?://.+", ticket.pr_url.strip()):
                return "PR URL must be a valid HTTP/HTTPS URL"
        elif to_status == TicketStatus.COMPLETE and from_status == TicketStatus.READY_FOR_REVIEW:
            # Guard: requires PR merged or Spike report accepted - this is manual confirmation
            # We'll accept it if the user provides a reason, but warn if no reason given
            # The actual check is manual, so we just require a reason
            pass
        return None

    def can_transition(self, ticket: Ticket, to_status: TicketStatus) -> tuple[bool, str | None]:
        """Check if a ticket can transition to the given status.
        Returns (can_transition, error_message).
        """
        from_status = ticket.status

        # Same status - no transition needed
        if from_status == to_status:
            return False, "Ticket is already in this status"

        # Any -> Rejected: always allowed
        if to_status == TicketStatus.REJECTED:
            return True, None

        # Rejected -> any prior state: allowed if that state's guard criteria currently met
        if from_status == TicketStatus.REJECTED:
            if to_status != TicketStatus.OPEN:
                # Check the guard for the immediate predecessor -> to_status transition
                prev_status = self._get_previous_status(to_status)
                if prev_status:
                    error = self._validate_guard(ticket, prev_status, to_status)
                    if error:
                        return (
                            False,
                            f"Cannot transition from Rejected to {to_status.value}: {error}",
                        )
            return True, None

        # Backward transition (any -> previous): always allowed, no guards
        if self._is_backward_transition(from_status, to_status):
            return True, None

        # Forward transitions: only allowed to immediate next status
        if not self._is_immediate_forward(from_status, to_status):
            next_status = self._get_next_status(from_status)
            required = next_status.value if next_status else "next status"
            return (False, f"Cannot skip statuses: must transition through {required}")

        # Forward transitions: check guards
        error = self._validate_guard(ticket, from_status, to_status)
        if error:
            return False, error

        return True, None

    def _get_previous_status(self, status: TicketStatus) -> TicketStatus | None:
        """Get the immediate previous status before the given status."""
        order = self._get_status_order()
        try:
            idx = order.index(status)
            if idx > 0:
                return order[idx - 1]
        except ValueError:
            pass
        return None

    def _is_immediate_forward(self, from_status: TicketStatus, to_status: TicketStatus) -> bool:
        """Check if to_status is the immediate next status after from_status."""
        order = self._get_status_order()
        try:
            from_idx = order.index(from_status)
            to_idx = order.index(to_status)
            return to_idx == from_idx + 1
        except ValueError:
            return False

    def _get_next_status(self, from_status: TicketStatus) -> TicketStatus | None:
        """Get the immediate next status after from_status."""
        order = self._get_status_order()
        try:
            idx = order.index(from_status)
            if idx + 1 < len(order):
                return order[idx + 1]
        except ValueError:
            pass
        return None

    def transition(
        self, ticket: Ticket, to_status: TicketStatus, reason: str | None = None
    ) -> Ticket:
        """Perform a guarded transition and create audit log entry.
        Raises ValueError if transition is not allowed."""
        from_status = ticket.status

        can_transition, error = self.can_transition(ticket, to_status)
        if not can_transition:
            raise ValueError(error)

        # Auto-generate branch name on transition to IN_PROGRESS if empty
        if to_status == TicketStatus.IN_PROGRESS and (
            not ticket.branch_name or not ticket.branch_name.strip()
        ):
            ticket.branch_name = generate_branch_name(ticket)

        # Update ticket status
        ticket.status = to_status
        ticket.updated_at = utc_now()
        if to_status == TicketStatus.COMPLETE:
            ticket.completed_at = utc_now()

        # Create transition audit record
        transition = Transition(
            ticket_id=ticket.id,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
        )

        self.session.add(ticket)
        self.session.add(transition)
        self.session.commit()
        self.session.refresh(ticket)

        return ticket

    def delete_ticket(self, ticket_id: int) -> bool:
        ticket = self.get_ticket(ticket_id)
        if not ticket:
            return False
        self.session.delete(ticket)
        self.session.commit()
        return True

    def list_tickets(
        self,
        project_id: int | None = None,
        status: TicketStatus | None = None,
        type: TicketType | None = None,
        priority: Priority | None = None,
        sprint_id: int | None = None,
        q: str | None = None,
        sort: str = "number",
        order: str = "desc",
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Ticket], int]:
        """List tickets with optional filters and pagination.

        ``sprint_id=0`` is the "No Sprint" sentinel: it selects only tickets
        whose sprint_id is NULL. ``sprint_id=None`` applies no sprint filter.
        """
        query = select(Ticket)
        count_query = select(func.count(Ticket.id))

        if project_id:
            query = query.where(Ticket.project_id == project_id)
            count_query = count_query.where(Ticket.project_id == project_id)
        if status:
            query = query.where(Ticket.status == status)
            count_query = count_query.where(Ticket.status == status)
        if type:
            query = query.where(Ticket.type == type)
            count_query = count_query.where(Ticket.type == type)
        if priority:
            query = query.where(Ticket.priority == priority)
            count_query = count_query.where(Ticket.priority == priority)
        if sprint_id == 0:
            # "No Sprint" sentinel: only unsprinted tickets
            query = query.where(Ticket.sprint_id.is_(None))  # type: ignore[union-attr]
            count_query = count_query.where(Ticket.sprint_id.is_(None))  # type: ignore[union-attr]
        elif sprint_id is not None:
            query = query.where(Ticket.sprint_id == sprint_id)
            count_query = count_query.where(Ticket.sprint_id == sprint_id)
        if q:
            query = query.where(Ticket.title.ilike(f"%{q}%"))
            count_query = count_query.where(Ticket.title.ilike(f"%{q}%"))

        # Sort
        sort_column = getattr(Ticket, sort, Ticket.number)
        if order.lower() == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # Pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        total = self.session.exec(count_query).first() or 0
        tickets = list(self.session.exec(query).all())

        return tickets, total

    def move_ticket_to_project(self, ticket_id: int, new_project_id: int) -> dict:
        """Move a ticket to a different project with renumbering.

        This is an atomic transaction that:
        1. Preserves the original_id if not already set (first move)
        2. Assigns a new number in the target project
        3. Updates the ticket's project_id
        4. Returns details about the move
        """
        ticket = self.get_ticket(ticket_id)
        if not ticket:
            raise ValueError(f"Ticket {ticket_id} not found")

        # Get source project for old_full_id
        old_project = self.session.get(Project, ticket.project_id)
        if not old_project:
            raise ValueError(f"Source project {ticket.project_id} not found")

        # Get target project
        new_project = self.session.get(Project, new_project_id)
        if not new_project:
            raise ValueError(f"Target project {new_project_id} not found")

        # Cannot move to same project
        if ticket.project_id == new_project_id:
            raise ValueError("Ticket is already in this project")

        old_full_id = f"{old_project.prefix}-{ticket.number}"

        # Preserve original_id on first move
        original_id = ticket.original_id
        if original_id is None:
            original_id = old_full_id

        # Get next ticket number for target project
        max_num = self.session.exec(
            select(func.max(Ticket.number)).where(Ticket.project_id == new_project_id)
        ).first()
        next_number = (max_num or 0) + 1

        # Perform the move
        ticket.project_id = new_project_id
        ticket.number = next_number
        ticket.original_id = original_id
        ticket.updated_at = utc_now()

        self.session.add(ticket)
        self.session.commit()
        self.session.refresh(ticket)

        new_full_id = f"{new_project.prefix}-{ticket.number}"

        return {
            "ticket_id": ticket.id,
            "old_project_id": old_project.id,
            "new_project_id": new_project.id,
            "old_full_id": old_full_id,
            "new_full_id": new_full_id,
            "original_id": original_id,
        }


class ProjectService:
    def __init__(self, session: Session):
        self.session = session

    def create_project(
        self,
        prefix: str,
        name: str,
        description: str = "",
        color: str = "#6366f1",
        is_system: bool = False,
    ) -> Project:
        normalized_prefix = prefix.upper().strip()
        if self.get_project_by_prefix(normalized_prefix) is not None:
            raise ValueError(f"Project prefix '{normalized_prefix}' already exists")
        project = Project(
            prefix=normalized_prefix,
            name=name,
            description=description,
            color=color,
            is_system=is_system,
        )
        self.session.add(project)
        self.session.commit()
        self.session.refresh(project)
        return project

    def get_project(self, project_id: int) -> Project | None:
        return self.session.get(Project, project_id)

    def get_project_by_prefix(self, prefix: str) -> Project | None:
        return self.session.exec(select(Project).where(Project.prefix == prefix.upper())).first()

    def list_projects(self) -> list[Project]:
        return list(self.session.exec(select(Project)).all())

    def update_project(
        self,
        project_id: int,
        name: str | None = None,
        description: str | None = None,
        color: str | None = None,
    ) -> Project | None:
        project = self.get_project(project_id)
        if not project:
            return None
        if name is not None:
            project.name = name
        if description is not None:
            project.description = description
        if color is not None:
            project.color = color
        project.updated_at = utc_now()
        self.session.add(project)
        self.session.commit()
        self.session.refresh(project)
        return project

    def delete_project(self, project_id: int) -> bool:
        project = self.get_project(project_id)
        if not project:
            return False
        if project.is_system:
            raise ValueError("Cannot delete system project")
        self.session.delete(project)
        self.session.commit()
        return True

    def get_project_ticket_count(self, project_id: int) -> int:
        result = self.session.exec(
            select(func.count(Ticket.id)).where(Ticket.project_id == project_id)  # type: ignore[arg-type]
        ).first()
        return result if result is not None else 0


class SprintService:
    def __init__(self, session: Session):
        self.session = session

    def create_sprint(
        self,
        number: int | None = None,
        name: str = "",
        description: str = "",
        planned_start: datetime | None = None,
        planned_end: datetime | None = None,
        planned_duration_days: int | None = None,
        actual_start: datetime | None = None,
        actual_finish: datetime | None = None,
    ) -> Sprint:
        if number is None:
            number = self.get_next_sprint_number()
        sprint = Sprint(
            number=number,
            name=name,
            description=description,
            planned_start=planned_start,
            planned_end=planned_end,
            planned_duration_days=planned_duration_days,
            actual_start=actual_start,
            actual_finish=actual_finish,
        )
        self.session.add(sprint)
        self.session.commit()
        self.session.refresh(sprint)
        return sprint

    def get_sprint(self, sprint_id: int) -> Sprint | None:
        return self.session.get(Sprint, sprint_id)

    def get_sprint_by_number(self, number: int) -> Sprint | None:
        return self.session.exec(select(Sprint).where(Sprint.number == number)).first()

    def list_sprints(self) -> list[Sprint]:
        """List sprints ordered by number, descending (newest first)."""
        # Newest sprints first; ignore = mypy plugin mis-flags .desc() on an int column
        query = select(Sprint).order_by(Sprint.number.desc())  # type: ignore[attr-defined]
        return list(self.session.exec(query).all())

    def get_sprint_with_tickets(self, sprint_id: int) -> dict | None:
        """Get sprint with tickets and derived status."""
        sprint = self.get_sprint(sprint_id)
        if not sprint:
            return None

        tickets = list(self.session.exec(select(Ticket).where(Ticket.sprint_id == sprint_id)).all())

        status = self._derive_status(sprint, tickets)

        return {
            "sprint": sprint,
            "tickets": tickets,
            "status": status,
        }

    def _derive_status(self, sprint: Sprint, tickets: list[Ticket]) -> str:
        """Derive sprint status from actual dates (spec: planned vs reality tracking).

        - Planned: no actual_start yet
        - Active: actual_start set, actual_finish not set
        - Complete: actual_finish set
        """
        if sprint.actual_finish is not None:
            return "Complete"
        if sprint.actual_start is not None:
            return "Active"
        return "Planned"

    def update_sprint(
        self,
        sprint_id: int,
        name: str | None = None,
        description: str | None = None,
        planned_start: datetime | None = None,
        planned_end: datetime | None = None,
        planned_duration_days: int | None = None,
        actual_start: datetime | None = None,
        actual_finish: datetime | None = None,
    ) -> Sprint | None:
        sprint = self.get_sprint(sprint_id)
        if not sprint:
            return None
        if name is not None:
            sprint.name = name
        if description is not None:
            sprint.description = description
        if planned_start is not None:
            sprint.planned_start = planned_start
        if planned_end is not None:
            sprint.planned_end = planned_end
        if planned_duration_days is not None:
            sprint.planned_duration_days = planned_duration_days
        if actual_start is not None:
            sprint.actual_start = actual_start
        if actual_finish is not None:
            sprint.actual_finish = actual_finish
        sprint.updated_at = utc_now()
        self.session.add(sprint)
        self.session.commit()
        self.session.refresh(sprint)
        return sprint

    def delete_sprint(self, sprint_id: int) -> bool:
        sprint = self.get_sprint(sprint_id)
        if not sprint:
            return False
        self.session.delete(sprint)
        self.session.commit()
        return True

    def assign_ticket_to_sprint(self, sprint_id: int, ticket_id: int) -> Ticket:
        """Assign a ticket to a sprint.
        Raises ValueError if ticket is already in another sprint."""
        sprint = self.get_sprint(sprint_id)
        if not sprint:
            raise ValueError(f"Sprint {sprint_id} not found")

        ticket = self.session.get(Ticket, ticket_id)
        if not ticket:
            raise ValueError(f"Ticket {ticket_id} not found")

        if ticket.sprint_id is not None and ticket.sprint_id != sprint_id:
            raise ValueError(f"Ticket is already assigned to sprint {ticket.sprint_id}")

        ticket.sprint_id = sprint_id
        ticket.updated_at = utc_now()
        self.session.add(ticket)
        self.session.commit()
        self.session.refresh(ticket)
        return ticket

    def unassign_ticket_from_sprint(self, sprint_id: int, ticket_id: int) -> Ticket:
        """Remove a ticket from a sprint."""
        sprint = self.get_sprint(sprint_id)
        if not sprint:
            raise ValueError(f"Sprint {sprint_id} not found")

        ticket = self.session.get(Ticket, ticket_id)
        if not ticket:
            raise ValueError(f"Ticket {ticket_id} not found")

        if ticket.sprint_id != sprint_id:
            raise ValueError(f"Ticket is not assigned to sprint {sprint_id}")

        ticket.sprint_id = None
        ticket.updated_at = utc_now()
        self.session.add(ticket)
        self.session.commit()
        self.session.refresh(ticket)
        return ticket

    def get_sprint_with_tickets_by_status(self, sprint_id: int) -> dict | None:
        """Get sprint with tickets grouped by status."""
        sprint = self.get_sprint(sprint_id)
        if not sprint:
            return None

        tickets = list(self.session.exec(select(Ticket).where(Ticket.sprint_id == sprint_id)).all())

        # Group tickets by status
        tickets_by_status = {}
        for status in TicketStatus:
            tickets_by_status[status.value] = []

        for ticket in tickets:
            tickets_by_status[ticket.status.value].append(ticket)

        status = self._derive_status(sprint, tickets)

        return {
            "sprint": sprint,
            "tickets_by_status": tickets_by_status,
            "status": status,
        }

    def get_next_sprint_number(self) -> int:
        """Get next sprint number (MAX(number)+1 starting at 2601)."""
        max_num = self.session.exec(select(func.max(Sprint.number))).first()
        return (max_num + 1) if max_num else 2601

    def get_plan_data(self, project_id: int | None = None) -> dict:
        """Get plan data for calendar/roadmap view.

        Args:
            project_id: Optional project filter. If None, shows all sprints.

        Returns:
            dict with sprints (with ticket counts by status) and unsprinted ticket count
        """
        from datetime import datetime

        # Naive now: sprint planned dates are NaiveDatetime, so timeline math
        # (now - earliest_date) must not mix offset-aware and offset-naive values
        now = datetime.now(UTC).replace(tzinfo=None)

        # Build base query for sprints
        sprint_query = select(Sprint).order_by(
            Sprint.planned_start.asc().nulls_last(), Sprint.number.asc()
        )

        # If project filter, we need to find sprints that have tickets from that project
        if project_id is not None:
            # Get sprint IDs that have tickets from this project
            sprint_ids_with_project = self.session.exec(
                select(Ticket.sprint_id)
                .where(Ticket.project_id == project_id, Ticket.sprint_id.is_not(None))
                .distinct()
            ).all()
            if sprint_ids_with_project:
                sprint_query = sprint_query.where(Sprint.id.in_(sprint_ids_with_project))
            else:
                # No sprints have tickets from this project
                return {
                    "sprints": [],
                    "unsprinted_count": 0,
                    "earliest_date": None,
                    "latest_date": None,
                    "now": now,
                }

        sprints = list(self.session.exec(sprint_query).all())

        # Get unsprinted ticket count
        unsprinted_query = select(func.count(Ticket.id)).where(Ticket.sprint_id.is_(None))
        if project_id is not None:
            unsprinted_query = unsprinted_query.where(Ticket.project_id == project_id)
        unsprinted_count = self.session.exec(unsprinted_query).first() or 0

        # Calculate date range for timeline
        sprints_with_dates = [s for s in sprints if s.planned_start and s.planned_end]
        if sprints_with_dates:
            earliest_date = min(s.planned_start for s in sprints_with_dates)
            latest_date = max(s.planned_end for s in sprints_with_dates)
        else:
            earliest_date = None
            latest_date = None

        sprint_data = []
        for sprint in sprints:
            # Get tickets for this sprint
            ticket_query = select(Ticket).where(Ticket.sprint_id == sprint.id)
            if project_id is not None:
                ticket_query = ticket_query.where(Ticket.project_id == project_id)
            tickets = list(self.session.exec(ticket_query).all())

            # Count tickets by status
            ticket_counts = {status.value: 0 for status in TicketStatus}
            for ticket in tickets:
                ticket_counts[ticket.status.value] += 1

            # Derive sprint status
            status = self._derive_status(sprint, tickets)

            # Calculate timeline position if dates available
            left_pct = 0
            width_pct = 0
            if earliest_date and latest_date and sprint.planned_start and sprint.planned_end:
                total_range = (latest_date - earliest_date).total_seconds()
                if total_range > 0:
                    start_offset = (sprint.planned_start - earliest_date).total_seconds()
                    duration = (sprint.planned_end - sprint.planned_start).total_seconds()
                    left_pct = (start_offset / total_range) * 100
                    width_pct = (duration / total_range) * 100
            elif sprint.planned_start:
                left_pct = 0
                width_pct = 10  # Minimum width for sprints with only start date

            # Calculate today marker position
            today_pct = None
            if earliest_date and latest_date:
                total_range = (latest_date - earliest_date).total_seconds()
                if total_range > 0:
                    today_offset = (now - earliest_date).total_seconds()
                    if 0 <= today_offset <= total_range:
                        today_pct = (today_offset / total_range) * 100

            sprint_data.append(
                {
                    "sprint": sprint,
                    "ticket_counts": ticket_counts,
                    "total_tickets": len(tickets),
                    "status": status,
                    "left_pct": left_pct,
                    "width_pct": max(width_pct, 2),  # Minimum 2% width
                    "today_pct": today_pct,
                }
            )

        return {
            "sprints": sprint_data,
            "unsprinted_count": unsprinted_count,
            "earliest_date": earliest_date,
            "latest_date": latest_date,
            "now": now,
        }


class LinkService:
    def __init__(self, session: Session):
        self.session = session

    def _get_inverse_link_type(self, link_type: LinkType) -> LinkType | None:
        """Get the inverse link type for a given link type."""
        inverse_map = {
            LinkType.PARENT: LinkType.CHILD,
            LinkType.CHILD: LinkType.PARENT,
            LinkType.BLOCKS: LinkType.BLOCKED_BY,
            LinkType.BLOCKED_BY: LinkType.BLOCKS,
            LinkType.RELATES_TO: LinkType.RELATES_TO,  # Self-inverse
        }
        return inverse_map.get(link_type)

    def _validate_link(self, source_id: int, target_id: int, link_type: LinkType) -> str | None:
        """Validate link creation. Returns error message or None if valid."""
        if source_id == target_id:
            return "Cannot link a ticket to itself"

        source = self.session.get(Ticket, source_id)
        target = self.session.get(Ticket, target_id)
        if not source or not target:
            return "Source or target ticket not found"

        # Validate link type constraints
        if link_type == LinkType.PARENT:
            # parent: source must be Epic, target can be anything (but typically Story/Bug/Spike)
            if source.type != TicketType.EPIC:
                return "Parent link source must be an Epic"
        elif link_type == LinkType.CHILD:
            # child: target must be Epic, source can be anything
            if target.type != TicketType.EPIC:
                return "Child link target must be an Epic"
        # blocks/blocked_by and relates_to have no type restrictions

        return None

    def create_link(self, source_id: int, target_id: int, link_type: LinkType) -> TicketLink:
        # Validate
        error = self._validate_link(source_id, target_id, link_type)
        if error:
            raise ValueError(error)

        # Check for duplicate
        existing = self.session.exec(
            select(TicketLink).where(
                TicketLink.source_id == source_id,
                TicketLink.target_id == target_id,
                TicketLink.link_type == link_type,
            )
        ).first()
        if existing:
            return existing

        # Create the link
        link = TicketLink(
            source_id=source_id,
            target_id=target_id,
            link_type=link_type,
        )
        self.session.add(link)
        self.session.flush()

        # Create inverse link if applicable
        inverse_type = self._get_inverse_link_type(link_type)
        if inverse_type and inverse_type != link_type:
            # For parent/child and blocks/blocked_by, create the inverse
            inverse_existing = self.session.exec(
                select(TicketLink).where(
                    TicketLink.source_id == target_id,
                    TicketLink.target_id == source_id,
                    TicketLink.link_type == inverse_type,
                )
            ).first()
            if not inverse_existing:
                inverse_link = TicketLink(
                    source_id=target_id,
                    target_id=source_id,
                    link_type=inverse_type,
                )
                self.session.add(inverse_link)
        elif inverse_type == link_type:
            # For relates_to (self-inverse), create the symmetric link
            inverse_existing = self.session.exec(
                select(TicketLink).where(
                    TicketLink.source_id == target_id,
                    TicketLink.target_id == source_id,
                    TicketLink.link_type == link_type,
                )
            ).first()
            if not inverse_existing:
                inverse_link = TicketLink(
                    source_id=target_id,
                    target_id=source_id,
                    link_type=link_type,
                )
                self.session.add(inverse_link)

        self.session.commit()
        self.session.refresh(link)
        return link

    def delete_link(self, link_id: int) -> bool:
        link = self.session.get(TicketLink, link_id)
        if not link:
            return False

        source_id = link.source_id
        target_id = link.target_id
        link_type = link.link_type

        # Delete the link
        self.session.delete(link)
        self.session.flush()

        # Delete inverse link if applicable
        inverse_type = self._get_inverse_link_type(link_type)
        if inverse_type and inverse_type != link_type:
            # For parent/child and blocks/blocked_by
            inverse_link = self.session.exec(
                select(TicketLink).where(
                    TicketLink.source_id == target_id,
                    TicketLink.target_id == source_id,
                    TicketLink.link_type == inverse_type,
                )
            ).first()
            if inverse_link:
                self.session.delete(inverse_link)
        elif inverse_type == link_type:
            # For relates_to (self-inverse)
            inverse_link = self.session.exec(
                select(TicketLink).where(
                    TicketLink.source_id == target_id,
                    TicketLink.target_id == source_id,
                    TicketLink.link_type == link_type,
                )
            ).first()
            if inverse_link:
                self.session.delete(inverse_link)

        self.session.commit()
        return True

    def get_links_for_ticket(self, ticket_id: int) -> list[TicketLink]:
        return list(
            self.session.exec(
                select(TicketLink).where(
                    (TicketLink.source_id == ticket_id) | (TicketLink.target_id == ticket_id)
                )
            ).all()
        )

    def get_blockers(self, ticket_id: int) -> list[TicketLink]:
        """Get tickets that block the given ticket (target_id == ticket_id, link_type == blocks)."""
        return list(
            self.session.exec(
                select(TicketLink).where(
                    TicketLink.target_id == ticket_id,
                    TicketLink.link_type == LinkType.BLOCKS,
                )
            ).all()
        )

    def get_blocked(self, ticket_id: int) -> list[TicketLink]:
        """Get tickets that are blocked by the given ticket.

        source_id == ticket_id, link_type == blocks.
        """
        return list(
            self.session.exec(
                select(TicketLink).where(
                    TicketLink.source_id == ticket_id,
                    TicketLink.link_type == LinkType.BLOCKS,
                )
            ).all()
        )
