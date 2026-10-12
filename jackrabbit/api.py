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
    utc_now,
)
from jackrabbit.schemas import (
    ProjectCreate,
    ProjectRead,
    SprintCreate,
    SprintRead,
    TicketCreate,
    TicketLinkCreate,
    TicketLinkRead,
    TicketRead,
    TicketUpdate,
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


@router.get("/sprints/{sprint_id}", response_model=SprintRead)
def get_sprint(sprint_id: int, service: SprintService = Depends(get_sprint_service)) -> Sprint:
    sprint = service.get_sprint(sprint_id)
    if not sprint:
        raise HTTPException(status_code=404, detail="Sprint not found")
    return sprint


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
    )


@router.get("/tickets", response_model=list[TicketRead])
def list_tickets(
    project_id: int | None = Query(None),
    status: TicketStatus | None = Query(None),
    type: TicketType | None = Query(None),
    sprint_id: int | None = Query(None),
    service: TicketService = Depends(get_ticket_service),
) -> list[Ticket]:
    return service.list_tickets(
        project_id=project_id,
        status=status,
        type=type,
        sprint_id=sprint_id,
    )


@router.get("/tickets/{ticket_id}", response_model=TicketRead)
def get_ticket(ticket_id: int, service: TicketService = Depends(get_ticket_service)) -> Ticket:
    ticket = service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


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

    if ticket_in.status is not None:
        ticket = service.update_status(ticket, ticket_in.status)

    # Update other fields
    update_data = ticket_in.model_dump(exclude_unset=True, exclude={"status"})
    for field, value in update_data.items():
        setattr(ticket, field, value)

    ticket.updated_at = utc_now()
    service.session.add(ticket)
    service.session.commit()
    service.session.refresh(ticket)
    return ticket


# Link endpoints
@router.post("/links", response_model=TicketLinkRead, status_code=201)
def create_link(
    link_in: TicketLinkCreate,
    service: LinkService = Depends(get_link_service),
) -> TicketLink:
    return service.create_link(
        source_id=link_in.source_id,
        target_id=link_in.target_id,
        link_type=link_in.link_type,
    )


@router.delete("/links/{link_id}", status_code=204)
def delete_link(link_id: int, service: LinkService = Depends(get_link_service)) -> None:
    if not service.delete_link(link_id):
        raise HTTPException(status_code=404, detail="Link not found")


@router.get("/tickets/{ticket_id}/links", response_model=list[TicketLinkRead])
def get_ticket_links(
    ticket_id: int, service: LinkService = Depends(get_link_service)
) -> list[TicketLink]:
    return service.get_links_for_ticket(ticket_id)
