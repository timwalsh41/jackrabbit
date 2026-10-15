"""FastAPI API routes for Jackrabbit."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from jackrabbit.database import get_session
from jackrabbit.models import (
    Project,
    Sprint,
    Ticket,
    TicketLink,
    TicketStatus,
    TicketType,
)
from jackrabbit.schemas import (
    CanTransitionResponse,
    MoveProjectRequest,
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
)
from jackrabbit.services import (
    LinkService,
    ProjectService,
    SprintService,
    TicketService,
)

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


# Project endpoints
@router.post("/projects", response_model=ProjectRead, status_code=201)
def create_project(
    project_in: ProjectCreate,
    service: ProjectService = Depends(get_project_service),
) -> Project:
    return service.create_project(
        prefix=project_in.prefix,
        name=project_in.name,
        description=project_in.description,
        color=project_in.color,
    )


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
    return service.create_sprint(
        number=sprint_in.number,
        name=sprint_in.name,
        description=sprint_in.description,
        planned_start=sprint_in.planned_start,
        planned_end=sprint_in.planned_end,
    )


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
    status = result["status"]

    return SprintReadWithTickets(
        id=sprint.id,
        number=sprint.number,
        name=sprint.name,
        description=sprint.description,
        planned_start=sprint.planned_start,
        planned_end=sprint.planned_end,
        actual_start=sprint.actual_start,
        actual_end=sprint.actual_end,
        created_at=sprint.created_at,
        updated_at=sprint.updated_at,
        tickets=tickets,
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
        actual_start=sprint.actual_start,
        actual_end=sprint.actual_end,
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
                actual_start=sprint.actual_start,
                actual_end=sprint.actual_end,
                ticket_counts=ticket_counts_model,
                total_tickets=total_tickets,
                status=status,
            )
        )

    return PlanResponse(
        sprints=sprint_responses,
        unsprinted_count=plan_data["unsprinted_count"],
    )


@router.post("/sprints/{sprint_id}/tickets/{ticket_id}", status_code=200)
def assign_ticket_to_sprint(
    sprint_id: int,
    ticket_id: int,
    service: SprintService = Depends(get_sprint_service),
) -> dict:
    try:
        ticket = service.assign_ticket_to_sprint(sprint_id, ticket_id)
        return {
            "message": "Ticket assigned to sprint",
            "ticket_id": ticket.id,
            "sprint_id": sprint_id,
        }
    except ValueError as e:
        if "already assigned to sprint" in str(e):
            raise HTTPException(status_code=409, detail=str(e)) from e
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/sprints/{sprint_id}/tickets/{ticket_id}", status_code=200)
def unassign_ticket_from_sprint(
    sprint_id: int,
    ticket_id: int,
    service: SprintService = Depends(get_sprint_service),
) -> dict:
    try:
        ticket = service.unassign_ticket_from_sprint(sprint_id, ticket_id)
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
) -> Ticket:
    return service.create_ticket(
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


@router.get("/tickets", response_model=PaginatedResponse)
def list_tickets(
    project_id: int | None = Query(None),
    status: TicketStatus | None = Query(None),
    type: TicketType | None = Query(None),
    sprint_id: int | None = Query(None),
    q: str | None = Query(None, description="Search in title"),
    sort: str = Query(
        "number",
        description="Sort field: number, title, type, status, priority, story_points, created_at",
    ),
    order: str = Query("desc", description="Sort order: asc or desc"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    service: TicketService = Depends(get_ticket_service),
) -> PaginatedResponse:
    tickets, total = service.list_tickets(
        project_id=project_id,
        status=status,
        type=type,
        sprint_id=sprint_id,
        q=q,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )
    total_pages = (total + page_size - 1) // page_size
    return PaginatedResponse(
        items=tickets,
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
    )


@router.get("/tickets/by-id/{project_prefix}/{number}", response_model=TicketRead)
def get_ticket_by_full_id(
    project_prefix: str,
    number: int,
    service: TicketService = Depends(get_ticket_service),
) -> Ticket:
    ticket = service.get_ticket_by_full_id(project_prefix, number)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.patch("/tickets/{ticket_id}", response_model=TicketRead)
def update_ticket(
    ticket_id: int,
    ticket_in: TicketUpdate,
    service: TicketService = Depends(get_ticket_service),
) -> Ticket:
    ticket = service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    update_data = ticket_in.model_dump(exclude_unset=True)
    if "status" in update_data:
        status = update_data.pop("status")
        ticket = service.update_status(ticket, status)

    if update_data:
        ticket = service.update_ticket(ticket, **update_data)

    return ticket


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
        return TransitionResponse(
            ticket_id=ticket.id,
            from_status=from_status,
            to_status=request.to_status,
            reason=request.reason,
            at=ticket.updated_at,
            full_id=f"{ticket.project.prefix}-{ticket.number}",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# Project Move endpoints
@router.post(
    "/tickets/{ticket_id}/move-project", response_model=MoveProjectResponse, status_code=200
)
def move_ticket_project(
    ticket_id: int,
    request: MoveProjectRequest,
    service: TicketService = Depends(get_ticket_service),
) -> MoveProjectResponse:
    ticket = service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    try:
        result = service.move_ticket_to_project(ticket_id, request.project_id)
        return MoveProjectResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# Link endpoints
@router.post("/tickets/{source_id}/links", response_model=TicketLinkRead, status_code=201)
def create_link(
    source_id: int,
    link_in: TicketLinkCreate,
    service: LinkService = Depends(get_link_service),
    ticket_service: TicketService = Depends(get_ticket_service),
) -> TicketLink:
    # Verify source ticket exists
    source = ticket_service.get_ticket(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source ticket not found")

    # Verify target ticket exists
    target = ticket_service.get_ticket(link_in.target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target ticket not found")

    try:
        return service.create_link(
            source_id=source_id,
            target_id=link_in.target_id,
            link_type=link_in.link_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


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
