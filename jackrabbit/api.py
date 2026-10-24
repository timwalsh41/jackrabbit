"""FastAPI API routes for Jackrabbit."""

from typing import Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from jackrabbit.database import get_session
from jackrabbit.labels import parse_label_ids, parse_label_match
from jackrabbit.models import (
    Priority,
    Project,
    Sprint,
    Ticket,
    TicketLink,
    TicketStatus,
    TicketType,
)
from jackrabbit.schemas import (
    CanTransitionResponse,
    LabelCreate,
    LabelRead,
    LabelWithUsage,
    MoveProjectResponse,
    PaginatedResponse,
    PlanResponse,
    PlanSprintResponse,
    PlanSprintTicketCounts,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    SprintCreate,
    SprintRead,
    SprintReadWithTickets,
    SprintReadWithTicketsByStatus,
    SprintUpdate,
    TicketCreate,
    TicketLinkCreate,
    TicketLinkRead,
    TicketRead,
    TicketReadWithDetails,
    TicketUpdate,
    TransitionRequest,
    TransitionResponse,
    TriageRead,
    TriageRoleRead,
    TriageRoleSet,
)
from jackrabbit.services import (
    ConflictError,
    LabelService,
    LinkService,
    ProjectService,
    SprintService,
    TicketService,
    TriageService,
)
from jackrabbit.triage import TRIAGE_ROLES

router = APIRouter(prefix="/api/v1")


# Dependency injection
def get_ticket_service(session: Session = Depends(get_session)) -> TicketService:
    return TicketService(session)


def get_project_service(session: Session = Depends(get_session)) -> ProjectService:
    return ProjectService(session)


def get_sprint_service(session: Session = Depends(get_session)) -> SprintService:
    return SprintService(session)


def get_link_service(session: Session = Depends(get_session)) -> LinkService:
    return LinkService(session)


def get_label_service(session: Session = Depends(get_session)) -> LabelService:
    return LabelService(session)


def get_triage_service(session: Session = Depends(get_session)) -> TriageService:
    return TriageService(session)


def _label_reads(labels: list[Any]) -> list[LabelRead]:
    """Convert label rows into their API representation."""
    return [LabelRead.model_validate(label) for label in labels]


def _ticket_read(ticket: Ticket, labels: list[Any]) -> TicketRead:
    """A ticket payload including the labels it carries."""
    read = TicketRead.model_validate(ticket)
    read.labels = _label_reads(labels)
    return read


# Project endpoints
@router.post("/projects", response_model=ProjectRead, status_code=201)
def create_project(
    project_in: ProjectCreate,
    service: ProjectService = Depends(get_project_service),
) -> Project:
    try:
        return service.create_project(
            prefix=project_in.prefix,
            name=project_in.name,
            description=project_in.description,
            color=project_in.color,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.get("/projects", response_model=list[ProjectRead])
def list_projects(service: ProjectService = Depends(get_project_service)) -> list[Project]:
    return service.list_projects()


@router.get("/projects/{project_id}", response_model=ProjectRead)
def get_project(project_id: int, service: ProjectService = Depends(get_project_service)) -> Project:
    project = service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/projects/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: int,
    project_in: ProjectUpdate,
    service: ProjectService = Depends(get_project_service),
) -> Project:
    project = service.update_project(
        project_id=project_id,
        name=project_in.name,
        description=project_in.description,
        color=project_in.color,
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(
    project_id: int,
    service: ProjectService = Depends(get_project_service),
) -> None:
    try:
        if not service.delete_project(project_id):
            raise HTTPException(status_code=404, detail="Project not found")
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


# Sprint endpoints
@router.post("/sprints", response_model=SprintRead, status_code=201)
def create_sprint(
    sprint_in: SprintCreate,
    service: SprintService = Depends(get_sprint_service),
) -> Sprint:
    try:
        return service.create_sprint(
            number=sprint_in.number,
            name=sprint_in.name,
            description=sprint_in.description,
            planned_start=sprint_in.planned_start,
            planned_end=sprint_in.planned_end,
            planned_duration_days=sprint_in.planned_duration_days,
            actual_start=sprint_in.actual_start,
            actual_finish=sprint_in.actual_finish,
        )
    except IntegrityError as e:
        service.session.rollback()
        raise HTTPException(status_code=409, detail="Sprint number already exists") from e


@router.get("/sprints", response_model=list[SprintRead])
def list_sprints(service: SprintService = Depends(get_sprint_service)) -> list[Sprint]:
    return service.list_sprints()


@router.get("/sprints/next-number")
def get_next_sprint_number(service: SprintService = Depends(get_sprint_service)) -> dict:
    return {"number": service.get_next_sprint_number()}


@router.get("/sprints/{sprint_id}", response_model=SprintReadWithTickets)
def get_sprint(
    sprint_id: int, service: SprintService = Depends(get_sprint_service)
) -> SprintReadWithTickets:
    result = service.get_sprint_with_tickets(sprint_id)
    if not result:
        raise HTTPException(status_code=404, detail="Sprint not found")

    sprint = result["sprint"]
    tickets = result["tickets"]
    tickets_by_status = result["tickets_by_status"]
    status = result["status"]

    return SprintReadWithTickets(
        id=sprint.id,
        number=sprint.number,
        name=sprint.name,
        description=sprint.description,
        planned_start=sprint.planned_start,
        planned_end=sprint.planned_end,
        planned_duration_days=sprint.planned_duration_days,
        actual_start=sprint.actual_start,
        actual_finish=sprint.actual_finish,
        created_at=sprint.created_at,
        updated_at=sprint.updated_at,
        tickets=tickets,
        tickets_by_status=tickets_by_status,
        status=status,
    )


@router.get("/sprints/{sprint_id}/by-status", response_model=SprintReadWithTicketsByStatus)
def get_sprint_by_status(
    sprint_id: int, service: SprintService = Depends(get_sprint_service)
) -> SprintReadWithTicketsByStatus:
    result = service.get_sprint_with_tickets_by_status(sprint_id)
    if not result:
        raise HTTPException(status_code=404, detail="Sprint not found")

    sprint = result["sprint"]
    tickets_by_status = result["tickets_by_status"]
    status = result["status"]

    return SprintReadWithTicketsByStatus(
        id=sprint.id,
        number=sprint.number,
        name=sprint.name,
        description=sprint.description,
        planned_start=sprint.planned_start,
        planned_end=sprint.planned_end,
        planned_duration_days=sprint.planned_duration_days,
        actual_start=sprint.actual_start,
        actual_finish=sprint.actual_finish,
        created_at=sprint.created_at,
        updated_at=sprint.updated_at,
        tickets_by_status=tickets_by_status,
        status=status,
    )


# Plan endpoint
@router.get("/plan", response_model=PlanResponse)
def get_plan(
    project_id: int | None = Query(None),
    service: SprintService = Depends(get_sprint_service),
) -> PlanResponse:
    plan_data = service.get_plan_data(project_id=project_id)

    sprint_responses = []
    for sprint_data in plan_data["sprints"]:
        sprint = sprint_data["sprint"]
        ticket_counts = sprint_data["ticket_counts"]
        total_tickets = sprint_data["total_tickets"]
        status = sprint_data["status"]

        # Convert ticket_counts to PlanSprintTicketCounts
        ticket_counts_model = PlanSprintTicketCounts(
            Open=ticket_counts.get("Open", 0),
            Groomed=ticket_counts.get("Groomed", 0),
            In_Progress=ticket_counts.get("In Progress", 0),
            Ready_for_Review=ticket_counts.get("Ready for Review", 0),
            Complete=ticket_counts.get("Complete", 0),
            Rejected=ticket_counts.get("Rejected", 0),
        )

        sprint_responses.append(
            PlanSprintResponse(
                id=sprint.id,
                number=sprint.number,
                name=sprint.name,
                description=sprint.description,
                planned_start=sprint.planned_start,
                planned_end=sprint.planned_end,
                planned_duration_days=sprint.planned_duration_days,
                actual_start=sprint.actual_start,
                actual_finish=sprint.actual_finish,
                ticket_counts=ticket_counts_model,
                total_tickets=total_tickets,
                status=status,
            )
        )

    return PlanResponse(
        sprints=sprint_responses,
        unsprinted_count=plan_data["unsprinted_count"],
    )


def _ticket_row_response(request: Request, ticket_id: int, session: Session) -> HTMLResponse:
    """Render the backlog row partial for an HTMX-swapped ticket."""
    from jackrabbit.services import SprintService, TicketService
    from jackrabbit.web import templates

    ticket = TicketService(session).get_ticket(ticket_id)
    sprints = SprintService(session).list_sprints()
    label_service = LabelService(session)
    labels_by_ticket = (
        {cast(int, ticket.id): label_service.labels_for_ticket(ticket_id)} if ticket else {}
    )
    return templates.TemplateResponse(
        request,
        "ticket_row.html",
        {
            "ticket": ticket,
            "sprints": sprints,
            "labels_by_ticket": labels_by_ticket,
        },
    )


@router.post(
    "/sprints/{sprint_id}/tickets/{ticket_id}",
    status_code=200,
    response_model=None,
)
def assign_ticket_to_sprint(
    sprint_id: int,
    ticket_id: int,
    request: Request,
    service: SprintService = Depends(get_sprint_service),
) -> dict | Response:
    try:
        ticket = service.assign_ticket_to_sprint(sprint_id, ticket_id)
        # HTMX-aware: the Backlog "Move to Sprint" dropdown swaps the refreshed
        # row in place (same pattern as the HTMX-aware PATCH /tickets).
        if request.headers.get("HX-Request"):
            return _ticket_row_response(request, ticket_id, service.session)
        return {
            "message": "Ticket assigned to sprint",
            "ticket_id": ticket.id,
            "sprint_id": sprint_id,
        }
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete(
    "/sprints/{sprint_id}/tickets/{ticket_id}",
    status_code=200,
    response_model=None,
)
def unassign_ticket_from_sprint(
    sprint_id: int,
    ticket_id: int,
    request: Request,
    service: SprintService = Depends(get_sprint_service),
) -> dict | Response:
    try:
        ticket = service.unassign_ticket_from_sprint(sprint_id, ticket_id)
        # HTMX-aware: the Backlog "Remove from Sprint" form swaps the row.
        if request.headers.get("HX-Request"):
            return _ticket_row_response(request, ticket_id, service.session)
        return {
            "message": "Ticket removed from sprint",
            "ticket_id": ticket.id,
            "sprint_id": sprint_id,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.patch("/sprints/{sprint_id}", response_model=SprintRead)
def update_sprint(
    sprint_id: int,
    sprint_in: SprintUpdate,
    service: SprintService = Depends(get_sprint_service),
) -> Sprint:
    sprint = service.update_sprint(
        sprint_id=sprint_id,
        name=sprint_in.name,
        description=sprint_in.description,
        planned_start=sprint_in.planned_start,
        planned_end=sprint_in.planned_end,
        planned_duration_days=sprint_in.planned_duration_days,
        actual_start=sprint_in.actual_start,
        actual_finish=sprint_in.actual_finish,
    )
    if not sprint:
        raise HTTPException(status_code=404, detail="Sprint not found")
    return sprint


@router.delete("/sprints/{sprint_id}", status_code=204)
def delete_sprint(
    sprint_id: int,
    service: SprintService = Depends(get_sprint_service),
) -> None:
    if not service.delete_sprint(sprint_id):
        raise HTTPException(status_code=404, detail="Sprint not found")


# Ticket endpoints
@router.post("/tickets", response_model=TicketRead, status_code=201)
def create_ticket(
    ticket_in: TicketCreate,
    service: TicketService = Depends(get_ticket_service),
    label_service: LabelService = Depends(get_label_service),
) -> TicketRead:
    # Validate the label names BEFORE creating the ticket, so an invalid name
    # leaves no half-created ticket behind.
    try:
        for name in ticket_in.labels:
            label_service.normalize_name(name)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    ticket = service.create_ticket(
        project_id=ticket_in.project_id,
        title=ticket_in.title,
        type=ticket_in.type,
        description=ticket_in.description,
        priority=ticket_in.priority,
        story_points=ticket_in.story_points,
        approach=ticket_in.approach,
        files_to_change=ticket_in.files_to_change,
        test_plan=ticket_in.test_plan,
        validation_steps=ticket_in.validation_steps,
        sprint_id=ticket_in.sprint_id,
        status=ticket_in.status,
    )

    if ticket_in.labels:
        try:
            label_service.replace(cast(int, ticket.id), ticket_in.labels)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e

    return _ticket_read(ticket, label_service.labels_for_ticket(cast(int, ticket.id)))


@router.get("/tickets", response_model=PaginatedResponse)
def list_tickets(
    # Backward-compatible single-value filters: take precedence over the
    # multi-select variants when both are present (req: backward compat).
    project_id: int | None = Query(default=None, description="Single project id (backward compat)"),
    project_ids: list[int] = Query(default=[], description="Project ids to filter by"),
    project_filter_mode: Literal["include", "exclude"] = Query(
        "include", description="Project filter mode: include or exclude"
    ),
    status: TicketStatus | None = Query(default=None),
    statuses: list[TicketStatus] = Query(default=[], description="Status values to filter by"),
    status_filter_mode: Literal["include", "exclude"] = Query(
        "include", description="Status filter mode: include or exclude"
    ),
    type: TicketType | None = Query(default=None),
    types: list[TicketType] = Query(default=[], description="Ticket types to filter by"),
    type_filter_mode: Literal["include", "exclude"] = Query(
        "include", description="Type filter mode: include or exclude"
    ),
    priority: Priority | None = Query(default=None),
    priorities: list[Priority] = Query(
        default=[], description="Priorities to filter by (include only)"
    ),
    sprint_id: int | None = Query(default=None, description="Single sprint id; 0 = No Sprint"),
    sprint_ids: list[int] = Query(default=[], description="Sprint ids to filter by; 0 = No Sprint"),
    q: str | None = Query(None, description="Search in title, description and label names"),
    label_ids: list[str] = Query(default=[], description="Label ids to filter by"),
    label_match: str = Query("all", description="Label match mode: all or any"),
    sort: str = Query(
        "number",
        description="Sort field: number, title, type, status, priority, story_points, created_at",
    ),
    order: str = Query("desc", description="Sort order: asc or desc"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    service: TicketService = Depends(get_ticket_service),
    label_service: LabelService = Depends(get_label_service),
) -> PaginatedResponse:
    try:
        parsed_label_ids = parse_label_ids(label_ids)
        match_mode = parse_label_match(label_match)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    tickets, total = service.list_tickets(
        project_id=project_id,
        project_ids=project_ids,
        project_filter_mode=project_filter_mode,
        status=status,
        statuses=statuses,
        status_filter_mode=status_filter_mode,
        type=type,
        types=types,
        type_filter_mode=type_filter_mode,
        priority=priority,
        priorities=priorities,
        sprint_id=sprint_id,
        sprint_ids=sprint_ids,
        q=q,
        label_ids=parsed_label_ids,
        label_match=match_mode,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )
    total_pages = (total + page_size - 1) // page_size
    labels_by_ticket = label_service.labels_for_tickets(
        [cast(int, t.id) for t in tickets if t.id is not None]
    )
    return PaginatedResponse(
        items=[
            _ticket_read(t, labels_by_ticket.get(cast(int, t.id), []))
            for t in tickets
            if t.id is not None
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/tickets/{ticket_id}", response_model=TicketReadWithDetails)
def get_ticket(
    ticket_id: int,
    service: TicketService = Depends(get_ticket_service),
    link_service: LinkService = Depends(get_link_service),
    label_service: LabelService = Depends(get_label_service),
) -> TicketReadWithDetails:
    result = service.get_ticket_with_details(ticket_id, link_service)
    if not result:
        raise HTTPException(status_code=404, detail="Ticket not found")

    ticket = result["ticket"]
    return TicketReadWithDetails(
        id=ticket.id,
        project_id=ticket.project_id,
        number=ticket.number,
        type=ticket.type,
        status=ticket.status,
        priority=ticket.priority,
        title=ticket.title,
        description=ticket.description,
        story_points=ticket.story_points,
        approach=ticket.approach,
        files_to_change=ticket.files_to_change,
        test_plan=ticket.test_plan,
        validation_steps=ticket.validation_steps,
        sprint_id=ticket.sprint_id,
        original_id=ticket.original_id,
        branch_name=ticket.branch_name,
        pr_url=ticket.pr_url,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        completed_at=ticket.completed_at,
        project_prefix=result["project_prefix"],
        links=result["links"],
        transitions=result["transitions"],
        labels=_label_reads(label_service.labels_for_ticket(ticket_id)),
    )


@router.get("/tickets/by-id/{project_prefix}/{number}", response_model=TicketRead)
def get_ticket_by_full_id(
    project_prefix: str,
    number: int,
    service: TicketService = Depends(get_ticket_service),
    label_service: LabelService = Depends(get_label_service),
) -> TicketRead:
    ticket = service.get_ticket_by_full_id(project_prefix, number)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return _ticket_read(ticket, label_service.labels_for_ticket(cast(int, ticket.id)))


@router.patch("/tickets/{ticket_id}", response_model=TicketRead)
def update_ticket(
    ticket_id: int,
    ticket_in: TicketUpdate,
    request: Request,
    service: TicketService = Depends(get_ticket_service),
    label_service: LabelService = Depends(get_label_service),
) -> TicketRead | Response:
    ticket = service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    update_data = ticket_in.model_dump(exclude_unset=True)

    # Labels are not a ticket column: they are applied separately, and an
    # update REPLACES the ticket's whole label set.
    new_labels = cast(list[str] | None, update_data.pop("labels", None))
    if new_labels is not None:
        try:
            for name in new_labels:
                label_service.normalize_name(name)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e

    # Status changes go through the guarded TransitionService (same rules as
    # POST /transition: guarded forward, free backward, reject/restore) so they
    # never bypass transition guards or the Transition audit trail (ADR-0009).
    # The unguarded legacy update_status() is no longer used here.
    new_status = cast(TicketStatus | None, update_data.pop("status", None))
    transition_reason = update_data.pop("transition_reason", None)

    # Apply non-status field updates FIRST: guards may depend on them (e.g. a
    # PATCH that sets approach/files/test/validation and Groomed together, or
    # pr_url + Ready for Review).
    if update_data:
        ticket = service.update_ticket(ticket, **update_data)

    if new_status is not None and new_status != ticket.status:
        try:
            ticket = service.transition(
                ticket,
                new_status,
                reason=(
                    str(transition_reason)
                    if transition_reason
                    else "Status changed via ticket edit"
                ),
            )
        except ValueError as e:
            # Guard failure (or invalid move) -> 400, ticket unchanged in DB
            raise HTTPException(status_code=400, detail=str(e)) from e

    if new_labels is not None:
        try:
            label_service.replace(ticket_id, new_labels)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e

    # HTMX-aware PATCH: the edit form hx-patches this endpoint directly.
    if request.headers.get("HX-Request"):
        from jackrabbit.services import SprintService
        from jackrabbit.web import templates

        target = request.headers.get("HX-Target") or ""
        if target.startswith("ticket-row-"):
            # Modal edit: swap the updated ticket row back in place.
            sprints = SprintService(service.session).list_sprints()
            return templates.TemplateResponse(
                request,
                "ticket_row.html",
                {
                    "ticket": ticket,
                    "sprints": sprints,
                    "labels_by_ticket": {
                        cast(int, ticket.id): label_service.labels_for_ticket(ticket_id)
                    },
                },
            )
        # Full-page edit form: send the user back to the backlog.
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = "/backlog"
        return response

    return _ticket_read(ticket, label_service.labels_for_ticket(ticket_id))


@router.delete("/tickets/{ticket_id}", status_code=204)
def delete_ticket(
    ticket_id: int,
    service: TicketService = Depends(get_ticket_service),
) -> None:
    if not service.delete_ticket(ticket_id):
        raise HTTPException(status_code=404, detail="Ticket not found")


# Transition endpoints
@router.get("/tickets/{ticket_id}/transition/can", response_model=CanTransitionResponse)
def check_can_transition(
    ticket_id: int,
    to_status: TicketStatus = Query(...),
    service: TicketService = Depends(get_ticket_service),
) -> CanTransitionResponse:
    ticket = service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    can_transition, error = service.can_transition(ticket, to_status)
    return CanTransitionResponse(can_transition=can_transition, error_message=error)


@router.post("/tickets/{ticket_id}/transition", response_model=TransitionResponse, status_code=200)
def transition_ticket(
    ticket_id: int,
    request: TransitionRequest,
    service: TicketService = Depends(get_ticket_service),
) -> TransitionResponse:
    ticket = service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    try:
        from_status = ticket.status

        # Set branch_name and pr_url if provided in request
        if request.branch_name is not None:
            ticket.branch_name = request.branch_name
        if request.pr_url is not None:
            ticket.pr_url = request.pr_url
        # Set grooming fields if provided (for Open -> Groomed transition)
        if request.approach is not None:
            ticket.approach = request.approach
        if request.files_to_change is not None:
            ticket.files_to_change = request.files_to_change
        if request.test_plan is not None:
            ticket.test_plan = request.test_plan
        if request.validation_steps is not None:
            ticket.validation_steps = request.validation_steps

        ticket = service.transition(ticket, request.to_status, request.reason)
        # ticket.project is only None for an uncommitted ticket; it was loaded
        # from the DB and transitioned, so the relationship is populated.
        project = cast(Project, ticket.project)
        return TransitionResponse(
            ticket_id=cast(int, ticket.id),
            from_status=from_status,
            to_status=request.to_status,
            reason=request.reason,
            at=ticket.updated_at,
            full_id=f"{project.prefix}-{ticket.number:03d}",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# Project Move endpoints
@router.post(
    "/tickets/{ticket_id}/move-project", response_model=MoveProjectResponse, status_code=200
)
async def move_ticket_project(
    ticket_id: int,
    request: Request,
    service: TicketService = Depends(get_ticket_service),
) -> MoveProjectResponse:
    """Move a ticket to another project (JSON or urlencoded form body).

    Accepts `project_id` (and the documented alias `target_project_id`) so both
    JSON API clients and htmx form posts work.
    """
    ticket = service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    payload = await _parse_move_payload(request)
    target_raw = payload.get("project_id", payload.get("target_project_id"))
    if target_raw is None or target_raw == "":
        raise HTTPException(status_code=400, detail="project_id is required")
    try:
        target_project_id = int(target_raw)
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail="project_id must be an integer") from e

    try:
        result = service.move_ticket_to_project(ticket_id, target_project_id)
        return MoveProjectResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


async def _parse_move_payload(request: Request) -> dict[str, Any]:
    """Parse a move request body: JSON for API clients, form data for htmx."""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail="Invalid JSON body") from e
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="JSON body must be an object")
        return body
    # Browser/htmx submissions post urlencoded (or multipart) form data
    form = await request.form()
    return dict(form)


# Link endpoints
@router.post(
    "/tickets/{source_id}/links",
    response_model=None,
    status_code=201,
)
def create_link(
    request: Request,
    source_id: int,
    link_in: TicketLinkCreate,
    service: LinkService = Depends(get_link_service),
    ticket_service: TicketService = Depends(get_ticket_service),
) -> TicketLink | HTMLResponse:
    # Verify source ticket exists
    source = ticket_service.get_ticket(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source ticket not found")

    # Verify target ticket exists
    target = ticket_service.get_ticket(link_in.target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target ticket not found")

    try:
        link = service.create_link(
            source_id=source_id,
            target_id=link_in.target_id,
            link_type=link_in.link_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # HTMX-aware: the Add Link modal swaps the refreshed links section in place
    # (same pattern as the HTMX-aware PATCH /tickets and sprint assign endpoints).
    if request.headers.get("HX-Request"):
        from jackrabbit.services import LinkService, TicketService
        from jackrabbit.web import _links_section_response

        return _links_section_response(
            request,
            source_id,
            TicketService(service.session),
            LinkService(service.session),
        )
    return link


@router.delete("/tickets/{source_id}/links/{link_id}", status_code=204)
def delete_link(
    source_id: int,
    link_id: int,
    service: LinkService = Depends(get_link_service),
    ticket_service: TicketService = Depends(get_ticket_service),
) -> None:
    # Verify source ticket exists
    source = ticket_service.get_ticket(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source ticket not found")

    # Verify link exists and belongs to this ticket
    link = service.session.get(TicketLink, link_id)
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    if link.source_id != source_id and link.target_id != source_id:
        raise HTTPException(status_code=404, detail="Link not found for this ticket")

    if not service.delete_link(link_id):
        raise HTTPException(status_code=404, detail="Link not found")


@router.get("/tickets/{ticket_id}/links", response_model=list[TicketLinkRead])
def get_ticket_links(
    ticket_id: int, service: LinkService = Depends(get_link_service)
) -> list[TicketLink]:
    return service.get_links_for_ticket(ticket_id)


@router.get("/tickets/{ticket_id}/blockers", response_model=list[TicketLinkRead])
def get_ticket_blockers(
    ticket_id: int, service: LinkService = Depends(get_link_service)
) -> list[TicketLink]:
    return service.get_blockers(ticket_id)


@router.get("/tickets/{ticket_id}/blocked", response_model=list[TicketLinkRead])
def get_ticket_blocked(
    ticket_id: int, service: LinkService = Depends(get_link_service)
) -> list[TicketLink]:
    return service.get_blocked(ticket_id)


# Label endpoints
@router.get("/labels", response_model=list[LabelWithUsage])
def list_labels(service: LabelService = Depends(get_label_service)) -> list[LabelWithUsage]:
    """The label vocabulary, with the number of tickets carrying each label."""
    return [
        LabelWithUsage(
            id=cast(int, entry["label"].id),
            name=entry["label"].name,
            color=entry["label"].color,
            usage_count=entry["usage_count"],
        )
        for entry in service.list_labels_with_usage()
    ]


@router.get("/tickets/{ticket_id}/labels", response_model=list[LabelRead])
def get_ticket_labels(
    ticket_id: int,
    service: LabelService = Depends(get_label_service),
    ticket_service: TicketService = Depends(get_ticket_service),
) -> list[LabelRead]:
    if not ticket_service.get_ticket(ticket_id):
        raise HTTPException(status_code=404, detail="Ticket not found")
    return _label_reads(service.labels_for_ticket(ticket_id))


@router.post("/tickets/{ticket_id}/labels", response_model=None, status_code=201)
def attach_label(
    request: Request,
    ticket_id: int,
    label_in: LabelCreate,
    service: LabelService = Depends(get_label_service),
    ticket_service: TicketService = Depends(get_ticket_service),
) -> LabelRead | Response:
    """Attach a label to a ticket by name, creating the label on demand."""
    if not ticket_service.get_ticket(ticket_id):
        raise HTTPException(status_code=404, detail="Ticket not found")

    try:
        label = service.attach(ticket_id, label_in.name)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    # HTMX-aware: the Add Label modal swaps the refreshed labels section in
    # place (same pattern as the links section).
    if request.headers.get("HX-Request"):
        from jackrabbit.web import _labels_section_response

        return _labels_section_response(request, ticket_id, ticket_service, service)
    return LabelRead.model_validate(label)


@router.delete("/tickets/{ticket_id}/labels/{label_id}", status_code=204, response_model=None)
def detach_label(
    request: Request,
    ticket_id: int,
    label_id: int,
    service: LabelService = Depends(get_label_service),
    ticket_service: TicketService = Depends(get_ticket_service),
) -> Response:
    """Detach a label from a ticket."""
    if not ticket_service.get_ticket(ticket_id):
        raise HTTPException(status_code=404, detail="Ticket not found")

    if not service.detach(ticket_id, label_id):
        raise HTTPException(status_code=404, detail="Label not found for this ticket")

    # HTMX-aware: the chip's remove button swaps the refreshed labels section.
    if request.headers.get("HX-Request"):
        from jackrabbit.web import _labels_section_response

        return _labels_section_response(request, ticket_id, ticket_service, service)
    return Response(status_code=204)


# Triage endpoints — a ticket's triage role is a label in the `triage:` namespace
@router.get("/triage/roles", response_model=list[TriageRoleRead])
def list_triage_roles() -> list[TriageRoleRead]:
    """The five canonical triage roles and the label that records each."""
    return [TriageRoleRead(role=role.value, label=role.label_name) for role in TRIAGE_ROLES]


@router.get("/tickets/{ticket_id}/triage", response_model=TriageRead)
def get_ticket_triage(
    ticket_id: int,
    service: TriageService = Depends(get_triage_service),
    ticket_service: TicketService = Depends(get_ticket_service),
) -> TriageRead:
    """Read a ticket's triage role (recorded as a label)."""
    if not ticket_service.get_ticket(ticket_id):
        raise HTTPException(status_code=404, detail="Ticket not found")

    role = service.role_for(ticket_id)
    if role is None:
        return TriageRead()

    label = service.label_service.find_by_name(role.label_name)
    return TriageRead(
        role=role.value,
        label=LabelRead.model_validate(label) if label is not None else None,
    )


@router.post("/tickets/{ticket_id}/triage", response_model=TriageRead)
def set_ticket_triage(
    ticket_id: int,
    role_in: TriageRoleSet,
    service: TriageService = Depends(get_triage_service),
    ticket_service: TicketService = Depends(get_ticket_service),
) -> TriageRead:
    """Record a ticket's triage role as a label, replacing any previous role."""
    if not ticket_service.get_ticket(ticket_id):
        raise HTTPException(status_code=404, detail="Ticket not found")

    try:
        role = service.set_role(ticket_id, role_in.role)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    label = service.label_service.find_by_name(role.label_name)
    return TriageRead(
        role=role.value,
        label=LabelRead.model_validate(label) if label is not None else None,
    )
