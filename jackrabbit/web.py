"""Web/UI routes for Jackrabbit (HTMX + Jinja2)."""

from enum import StrEnum
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlmodel import Session

from jackrabbit.database import get_session
from jackrabbit.markdown import render_markdown
from jackrabbit.models import (
    LinkType,
    Priority,
    Project,
    Sprint,
    Ticket,
    TicketStatus,
    TicketType,
)
from jackrabbit.schemas import ProjectCreate, ProjectUpdate
from jackrabbit.services import LinkService, ProjectService, SprintService, TicketService

router = APIRouter()

# Use default Jinja2Templates with directory - simpler and more reliable
template_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(template_dir))

# Server-side, HTML-escaping markdown renderer (HTMX-safe descriptions)
templates.env.filters["markdown"] = render_markdown

# Groomed fields editable inline on the ticket detail page (label order = display order)
GROOMED_FIELD_DEFS: list[tuple[str, str]] = [
    ("approach", "Approach"),
    ("files_to_change", "Files to Change"),
    ("test_plan", "Test Plan"),
    ("validation_steps", "Validation Steps"),
]

# Statuses whose groomed fields are frozen (no inline edits)
FIELD_EDIT_LOCKED_STATUSES = frozenset({TicketStatus.COMPLETE, TicketStatus.REJECTED})


def get_project_service(session: Session = Depends(get_session)) -> ProjectService:
    return ProjectService(session)


def get_ticket_service(session: Session = Depends(get_session)) -> TicketService:
    return TicketService(session)


def get_sprint_service(session: Session = Depends(get_session)) -> SprintService:
    return SprintService(session)


def get_link_service(session: Session = Depends(get_session)) -> LinkService:
    return LinkService(session)


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {})


@router.get("/tickets/new", response_class=HTMLResponse)
async def ticket_new(
    request: Request,
    project_id: int | None = Query(None),
    ticket_service: TicketService = Depends(get_ticket_service),
    project_service: ProjectService = Depends(get_project_service),
    sprint_service: SprintService = Depends(get_sprint_service),
) -> HTMLResponse:
    projects = project_service.list_projects()
    sprints = sprint_service.list_sprints()

    # Find UNS project for default selection
    uns_project = project_service.get_project_by_prefix("UNS")
    default_project_id = project_id or (
        uns_project.id if uns_project else (projects[0].id if projects else None)
    )

    # Return partial template for HTMX requests (modal)
    template_name = (
        "ticket_form_partial.html" if request.headers.get("HX-Request") else "ticket_form.html"
    )

    return templates.TemplateResponse(
        request,
        template_name,
        {
            "ticket": None,
            "projects": projects,
            "sprints": sprints,
            "default_project_id": default_project_id,
            "action": "/api/v1/tickets",
            "TicketType": TicketType,
            "Priority": Priority,
        },
    )


@router.get("/tickets/{ticket_id}/edit", response_class=HTMLResponse)
async def ticket_edit(
    request: Request,
    ticket_id: int,
    ticket_service: TicketService = Depends(get_ticket_service),
    project_service: ProjectService = Depends(get_project_service),
    sprint_service: SprintService = Depends(get_sprint_service),
) -> HTMLResponse:
    ticket = ticket_service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    projects = project_service.list_projects()
    sprints = sprint_service.list_sprints()

    # HTMX request (Edit button in a ticket row): return the modal partial
    # whose form hx-patches the API and swaps the updated row back in place.
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request,
            "ticket_edit_modal.html",
            {
                "ticket": ticket,
                "action": f"/api/v1/tickets/{ticket_id}",
                "TicketType": TicketType,
                "Priority": Priority,
            },
        )

    return templates.TemplateResponse(
        request,
        "ticket_form.html",
        {
            "ticket": ticket,
            "projects": projects,
            "sprints": sprints,
            "default_project_id": ticket.project_id,
            "action": f"/api/v1/tickets/{ticket_id}",
            "TicketType": TicketType,
            "Priority": Priority,
            "TicketStatus": TicketStatus,
        },
    )


@router.get("/sprint/{sprint_id}", response_class=HTMLResponse)
async def sprint_view(
    request: Request,
    sprint_id: int,
    sprint_service: SprintService = Depends(get_sprint_service),
) -> HTMLResponse:
    result = sprint_service.get_sprint_with_tickets_by_status(sprint_id)
    if not result:
        raise HTTPException(status_code=404, detail="Sprint not found")

    sprint = result["sprint"]
    tickets_by_status = result["tickets_by_status"]
    status = result["status"]

    return templates.TemplateResponse(
        request,
        "sprint_detail.html",
        {
            "sprint": sprint,
            "tickets_by_status": tickets_by_status,
            "status": status,
        },
    )


@router.get("/sprints/{sprint_id}/detail", response_class=HTMLResponse)
async def sprint_detail(
    request: Request,
    sprint_id: int,
    sprint_service: SprintService = Depends(get_sprint_service),
) -> HTMLResponse:
    result = sprint_service.get_sprint_with_tickets_by_status(sprint_id)
    if not result:
        raise HTTPException(status_code=404, detail="Sprint not found")

    sprint = result["sprint"]
    tickets_by_status = result["tickets_by_status"]
    status = result["status"]

    return templates.TemplateResponse(
        request,
        "sprint_detail.html",
        {
            "sprint": sprint,
            "tickets_by_status": tickets_by_status,
            "status": status,
        },
    )


@router.get("/plan", response_class=HTMLResponse)
async def plan(
    request: Request,
    project_id: int | None = Query(None),
    sprint_service: SprintService = Depends(get_sprint_service),
    project_service: ProjectService = Depends(get_project_service),
    link_service: LinkService = Depends(get_link_service),
) -> HTMLResponse:
    projects = project_service.list_projects()
    plan_data = sprint_service.get_plan_data(project_id=project_id)
    epics_with_children = link_service.get_epics_with_children()
    if project_id is not None:
        epics_with_children = [e for e in epics_with_children if e["epic"].project_id == project_id]
    return templates.TemplateResponse(
        request,
        "plan.html",
        {
            "projects": projects,
            "selected_project_id": project_id,
            "sprints": plan_data["sprints"],
            "unsprinted_count": plan_data["unsprinted_count"],
            "epics_with_children": epics_with_children,
        },
    )


# Link web routes
def _links_section_response(
    request: Request,
    ticket_id: int,
    ticket_service: TicketService,
    link_service: LinkService,
) -> HTMLResponse:
    """Render the links section partial (shared by the GET route and the HTMX-aware
    POST /api/v1/tickets/{id}/links endpoint, which swaps this section in place)."""
    ticket = ticket_service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    links = link_service.get_links_for_ticket(ticket_id)
    blockers = link_service.get_blockers(ticket_id)

    # Separate links by type AND side: a link row belongs to the section of its
    # semantic role relative to THIS ticket (target-side for parent/child, source-side
    # for blocks/blocked_by/relates_to), otherwise inverse rows render the wrong ticket.
    parent_links = [
        link for link in links if link.link_type == LinkType.PARENT and link.target_id == ticket_id
    ]
    child_links = [
        link for link in links if link.link_type == LinkType.CHILD and link.target_id == ticket_id
    ]
    blocks_links = [
        link for link in links if link.link_type == LinkType.BLOCKS and link.source_id == ticket_id
    ]
    blocked_by_links = [
        link
        for link in links
        if link.link_type == LinkType.BLOCKED_BY and link.source_id == ticket_id
    ]
    relates_to_links = [
        link
        for link in links
        if link.link_type == LinkType.RELATES_TO and link.source_id == ticket_id
    ]

    # Get all tickets for the modal search
    all_tickets, _ = ticket_service.list_tickets(page_size=1000)

    return templates.TemplateResponse(
        request,
        "ticket_links_section.html",
        {
            "ticket": ticket,
            "links": links,
            "parent_links": parent_links,
            "child_links": child_links,
            "blocks_links": blocks_links,
            "blocked_by_links": blocked_by_links,
            "relates_to_links": relates_to_links,
            "blockers": blockers,
            "all_tickets": all_tickets,
            "LinkType": LinkType,
            "TicketType": TicketType,
            "TicketStatus": TicketStatus,
        },
    )


@router.get("/tickets/{ticket_id}/links", response_class=HTMLResponse)
async def ticket_links_section(
    request: Request,
    ticket_id: int,
    ticket_service: TicketService = Depends(get_ticket_service),
    link_service: LinkService = Depends(get_link_service),
) -> HTMLResponse:
    return _links_section_response(request, ticket_id, ticket_service, link_service)


@router.get("/tickets/{ticket_id}/links/modal", response_class=HTMLResponse)
async def ticket_link_modal(
    request: Request,
    ticket_id: int,
    ticket_service: TicketService = Depends(get_ticket_service),
) -> HTMLResponse:
    ticket = ticket_service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Get all tickets for the modal search
    all_tickets, _ = ticket_service.list_tickets(page_size=1000)

    return templates.TemplateResponse(
        request,
        "ticket_link_modal.html",
        {
            "ticket": ticket,
            "all_tickets": all_tickets,
            "LinkType": LinkType,
            "TicketType": TicketType,
            "TicketStatus": TicketStatus,
        },
    )


# Project web routes
def _format_validation_error(exc: ValidationError) -> str:
    """Turn pydantic validation errors into a single friendly message."""
    parts = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err["loc"]) or "value"
        msg = err["msg"]
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, ") :]
        parts.append(f"{loc}: {msg}")
    return "; ".join(parts)


def _is_inline_row_request(request: Request) -> bool:
    """True when an HTMX request targets a project row (inline edit flow)."""
    target = request.headers.get("HX-Target") or ""
    return target.startswith("project-row-")


def _parse_optional_int(value: str | None, field: str = "value") -> int | None:
    """Parse an optional integer query param; empty string means "not set".

    The backlog filter form always submits every select, so unset filters
    arrive as empty strings. Typed Optional[int] params would 422 on "",
    so filters are declared as plain strings and parsed here.
    """
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"{field} must be an integer") from e


def _parse_optional_enum[E: StrEnum](
    enum_cls: type[E], value: str | None, field: str = "value"
) -> E | None:
    """Parse an optional str-Enum query param; empty string means "not set"."""
    if value is None or value == "":
        return None
    try:
        return enum_cls(value)
    except ValueError as e:
        valid = ", ".join(m.value for m in enum_cls)
        raise HTTPException(status_code=422, detail=f"{field} must be one of: {valid}") from e


def _build_backlog_context(
    ticket_service: TicketService,
    project_service: ProjectService,
    sprint_service: SprintService,
    project_id: int | None,
    status: TicketStatus | None,
    type: TicketType | None,
    priority: Priority | None,
    sprint_id: int | None,
    q: str | None,
    sort: str,
    order: str,
    page: int,
    page_size: int,
    project: Project | None = None,
) -> dict:
    """Shared context builder for /backlog and /projects/{id}/tickets."""
    tickets, total = ticket_service.list_tickets(
        project_id=project_id,
        status=status,
        type=type,
        priority=priority,
        sprint_id=sprint_id,
        q=q,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )
    total_pages = (total + page_size - 1) // page_size

    projects = project_service.list_projects()
    sprints = sprint_service.list_sprints()

    # Find UNS project for default selection
    uns_project = project_service.get_project_by_prefix("UNS")

    return {
        "tickets": tickets,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "projects": projects,
        "sprints": sprints,
        "uns_project_id": uns_project.id if uns_project else None,
        "current_filters": {
            "project_id": project_id,
            "status": status,
            "type": type,
            "priority": priority,
            "sprint_id": sprint_id,
            "q": q,
            "sort": sort,
            "order": order,
        },
        "TicketStatus": TicketStatus,
        "TicketType": TicketType,
        "Priority": Priority,
        "project": project,
    }


@router.get("/backlog", response_class=HTMLResponse)
async def backlog(
    request: Request,
    project_id: str = Query(""),
    status: str = Query(""),
    type: str = Query(""),
    priority: str = Query(""),
    sprint_id: str = Query(""),
    q: str = Query(""),
    sort: str = Query("number"),
    order: str = Query("desc"),
    page: int = Query(1),
    page_size: int = Query(50),
    ticket_service: TicketService = Depends(get_ticket_service),
    project_service: ProjectService = Depends(get_project_service),
    sprint_service: SprintService = Depends(get_sprint_service),
) -> HTMLResponse:
    context = _build_backlog_context(
        ticket_service,
        project_service,
        sprint_service,
        project_id=_parse_optional_int(project_id, "project_id"),
        status=_parse_optional_enum(TicketStatus, status, "status"),
        type=_parse_optional_enum(TicketType, type, "type"),
        priority=_parse_optional_enum(Priority, priority, "priority"),
        # sprint_id=0 is the "No Sprint" sentinel; ""/absent means no filter
        sprint_id=_parse_optional_int(sprint_id, "sprint_id"),
        q=q or None,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )

    # HTMX filter/sort/pagination requests swap only the table body rows
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "backlog_rows.html", context)

    return templates.TemplateResponse(request, "backlog.html", context)


@router.get("/projects", response_class=HTMLResponse)
async def project_list(
    request: Request,
    service: ProjectService = Depends(get_project_service),
) -> HTMLResponse:
    projects = service.list_projects()
    # Build project data with ticket counts
    project_data = []
    for project in projects:
        project_data.append(
            {
                "project": project,
                "ticket_count": service.get_project_ticket_count(project.id or 0),
            }
        )
    return templates.TemplateResponse(request, "project_list.html", {"projects": project_data})


@router.get("/projects/new", response_class=HTMLResponse)
async def project_new(request: Request) -> HTMLResponse:
    context = {"project": None, "action": "/projects"}
    # Return the bare form partial for HTMX requests (no full base template)
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "project_form_partial.html", context)
    return templates.TemplateResponse(request, "project_form.html", context)


@router.post("/projects", response_class=HTMLResponse)
async def project_create_submit(
    request: Request,
    prefix: str = Form(...),
    name: str = Form(...),
    description: str = Form(""),
    color: str = Form("#6366f1"),
    service: ProjectService = Depends(get_project_service),
) -> HTMLResponse:
    """HTMX form submit for creating a Project; returns the new row partial."""
    form_data = {
        "form_prefix": prefix,
        "form_name": name,
        "form_description": description,
        "form_color": color,
    }
    try:
        project_in = ProjectCreate(prefix=prefix, name=name, description=description, color=color)
        project = service.create_project(
            prefix=project_in.prefix,
            name=project_in.name,
            description=project_in.description,
            color=project_in.color,
        )
    except ValidationError as e:
        context = {
            "project": None,
            "action": "/projects",
            "error": _format_validation_error(e),
            **form_data,
        }
        return templates.TemplateResponse(request, "project_form_partial.html", context)
    except ValueError as e:
        context = {"project": None, "action": "/projects", "error": str(e), **form_data}
        return templates.TemplateResponse(request, "project_form_partial.html", context)

    # Success: return the row partial for the newly created Project.
    # HX-Redirect sends the user to the list where the row is visible.
    response = templates.TemplateResponse(
        request,
        "project_row.html",
        {"project": project, "ticket_count": 0},
    )
    response.headers["HX-Redirect"] = "/projects"
    return response


@router.get("/projects/{project_id}/row", response_class=HTMLResponse)
async def project_row_partial(
    request: Request,
    project_id: int,
    service: ProjectService = Depends(get_project_service),
) -> HTMLResponse:
    """Row partial for a single Project (used by inline-edit cancel/refresh)."""
    project = service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return templates.TemplateResponse(
        request,
        "project_row.html",
        {
            "project": project,
            "ticket_count": service.get_project_ticket_count(project_id),
        },
    )


@router.get("/projects/{project_id}/tickets", response_class=HTMLResponse)
async def project_tickets(
    request: Request,
    project_id: int,
    status: str = Query(""),
    type: str = Query(""),
    priority: str = Query(""),
    sprint_id: str = Query(""),
    q: str = Query(""),
    sort: str = Query("number"),
    order: str = Query("desc"),
    page: int = Query(1),
    page_size: int = Query(50),
    ticket_service: TicketService = Depends(get_ticket_service),
    project_service: ProjectService = Depends(get_project_service),
    sprint_service: SprintService = Depends(get_sprint_service),
) -> HTMLResponse:
    project = project_service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    context = _build_backlog_context(
        ticket_service,
        project_service,
        sprint_service,
        project_id=project_id,
        status=_parse_optional_enum(TicketStatus, status, "status"),
        type=_parse_optional_enum(TicketType, type, "type"),
        priority=_parse_optional_enum(Priority, priority, "priority"),
        sprint_id=_parse_optional_int(sprint_id, "sprint_id"),
        q=q or None,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
        project=project,
    )

    # HTMX filter/sort/pagination requests swap only the table body rows
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "backlog_rows.html", context)

    return templates.TemplateResponse(request, "backlog.html", context)


@router.get("/projects/{project_id}/edit", response_class=HTMLResponse)
async def project_edit(
    request: Request,
    project_id: int,
    service: ProjectService = Depends(get_project_service),
) -> HTMLResponse:
    project = service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    # Inline edit: HTMX swaps in a row-level form for this project row
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "project_edit_row.html", {"project": project})
    return templates.TemplateResponse(
        request,
        "project_form.html",
        {"project": project, "action": f"/projects/{project_id}"},
    )


@router.patch("/projects/{project_id}", response_class=HTMLResponse)
async def project_update_submit(
    request: Request,
    project_id: int,
    name: str = Form(...),
    description: str = Form(""),
    color: str = Form("#6366f1"),
    service: ProjectService = Depends(get_project_service),
) -> HTMLResponse:
    """HTMX form submit for editing a Project; returns the updated row partial."""
    project = service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    form_data = {
        "form_name": name,
        "form_description": description,
        "form_color": color,
    }
    try:
        project_in = ProjectUpdate(name=name, description=description, color=color)
        updated = service.update_project(
            project_id,
            name=project_in.name,
            description=project_in.description,
            color=project_in.color,
        )
    except ValidationError as e:
        error = _format_validation_error(e)
        if _is_inline_row_request(request):
            return templates.TemplateResponse(
                request,
                "project_edit_row.html",
                {"project": project, "error": error, **form_data},
            )
        context = {
            "project": project,
            "action": f"/projects/{project_id}",
            "error": error,
            **form_data,
        }
        return templates.TemplateResponse(request, "project_form_partial.html", context)

    if not updated:
        raise HTTPException(status_code=404, detail="Project not found")

    # Success: return the row partial. Inline edits swap the row in place;
    # full-page edits redirect back to the list.
    response = templates.TemplateResponse(
        request,
        "project_row.html",
        {
            "project": updated,
            "ticket_count": service.get_project_ticket_count(project_id),
        },
    )
    if not _is_inline_row_request(request):
        response.headers["HX-Redirect"] = "/projects"
    return response


# Sprint web routes
@router.get("/sprints", response_class=HTMLResponse)
async def sprint_list(
    request: Request,
    service: SprintService = Depends(get_sprint_service),
) -> HTMLResponse:
    sprints = service.list_sprints()
    sprint_data = []
    for sprint in sprints:
        result = service.get_sprint_with_tickets(sprint.id)
        if result:
            sprint_data.append(
                {
                    "sprint": sprint,
                    "tickets": result["tickets"],
                    "status": result["status"],
                }
            )
    # Return partial for HTMX requests
    template_name = (
        "sprint_list_partial.html" if request.headers.get("HX-Request") else "sprint_list.html"
    )
    return templates.TemplateResponse(request, template_name, {"sprints": sprint_data})


@router.get("/sprints/new", response_class=HTMLResponse)
async def sprint_new(
    request: Request,
    service: SprintService = Depends(get_sprint_service),
) -> HTMLResponse:
    next_number = service.get_next_sprint_number()

    # Return partial template for HTMX requests (modal)
    template_name = (
        "sprint_form_partial.html" if request.headers.get("HX-Request") else "sprint_form.html"
    )

    return templates.TemplateResponse(
        request,
        template_name,
        {
            "sprint": None,
            "next_number": next_number,
            "action": "/api/v1/sprints",
            "method": "post",
        },
    )


@router.get("/sprints/{sprint_id}/edit", response_class=HTMLResponse)
async def sprint_edit(
    request: Request,
    sprint_id: int,
    service: SprintService = Depends(get_sprint_service),
) -> HTMLResponse:
    sprint = service.get_sprint(sprint_id)
    if not sprint:
        raise HTTPException(status_code=404, detail="Sprint not found")
    # HTMX requests get the modal partial (targeted at the row/modal target);
    # normal navigation gets the full page. Both PATCH the update endpoint.
    template_name = (
        "sprint_form_partial.html" if request.headers.get("HX-Request") else "sprint_form.html"
    )
    return templates.TemplateResponse(
        request,
        template_name,
        {
            "sprint": sprint,
            "next_number": None,
            "action": f"/api/v1/sprints/{sprint_id}",
            "method": "patch",
        },
    )


# Move Project web routes
@router.get("/tickets/{ticket_id}/move-project/modal", response_class=HTMLResponse)
async def ticket_move_project_modal(
    request: Request,
    ticket_id: int,
    ticket_service: TicketService = Depends(get_ticket_service),
    project_service: ProjectService = Depends(get_project_service),
) -> HTMLResponse:
    ticket = ticket_service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    project = project_service.get_project(ticket.project_id)
    projects = project_service.list_projects()

    # Exclude current project
    other_projects = [p for p in projects if p.id != ticket.project_id]

    return templates.TemplateResponse(
        request,
        "ticket_move_project_modal.html",
        {
            "ticket": ticket,
            "project": project,
            "projects": other_projects,
        },
    )


@router.get("/tickets/{ticket_id}/transition/groomed/modal", response_class=HTMLResponse)
async def ticket_transition_groomed_modal(
    request: Request,
    ticket_id: int,
    ticket_service: TicketService = Depends(get_ticket_service),
) -> HTMLResponse:
    """Modal for transitioning to Groomed with approach, files_to_change,
    test_plan, validation_steps fields."""
    ticket = ticket_service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    return templates.TemplateResponse(
        request,
        "ticket_transition_groomed_modal.html",
        {
            "ticket": ticket,
        },
    )


@router.get("/tickets/{ticket_id}/transition/in-progress/modal", response_class=HTMLResponse)
async def ticket_transition_in_progress_modal(
    request: Request,
    ticket_id: int,
    ticket_service: TicketService = Depends(get_ticket_service),
) -> HTMLResponse:
    """Modal for transitioning to In Progress with branch name field."""
    ticket = ticket_service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Generate suggested branch name
    from jackrabbit.services import generate_branch_name

    suggested_branch = generate_branch_name(ticket)

    return templates.TemplateResponse(
        request,
        "ticket_transition_in_progress_modal.html",
        {
            "ticket": ticket,
            "suggested_branch": suggested_branch,
        },
    )


@router.get("/tickets/{ticket_id}/transition/ready-for-review/modal", response_class=HTMLResponse)
async def ticket_transition_ready_for_review_modal(
    request: Request,
    ticket_id: int,
    ticket_service: TicketService = Depends(get_ticket_service),
) -> HTMLResponse:
    """Modal for transitioning to Ready for Review with PR URL field."""
    ticket = ticket_service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    return templates.TemplateResponse(
        request,
        "ticket_transition_ready_for_review_modal.html",
        {
            "ticket": ticket,
        },
    )


@router.get("/tickets/search", response_class=HTMLResponse)
async def ticket_search(
    request: Request,
    q: str = Query(""),
    link_type: str = Query(""),
    source_id: int | None = Query(None),
    ticket_service: TicketService = Depends(get_ticket_service),
) -> HTMLResponse:
    """Search tickets for link modal."""
    # Get all tickets and filter by search query
    all_tickets, _ = ticket_service.list_tickets(page_size=1000)

    # Never offer the source ticket itself as a link target
    if source_id is not None:
        all_tickets = [t for t in all_tickets if t.id != source_id]

    if q:
        q_lower = q.lower()
        filtered = []
        for t in all_tickets:
            project = (
                ticket_service.session.get(ticket_service.models.Project, t.project_id)
                if hasattr(ticket_service, "models")
                else None
            )
            # Need to get project for full_id
            from jackrabbit.models import Project

            project = ticket_service.session.get(Project, t.project_id)
            full_id = f"{project.prefix}-{t.number:03d}" if project else f"UNK-{t.number:03d}"
            if q_lower in full_id.lower() or q_lower in t.title.lower():
                filtered.append(t)
        all_tickets = filtered

    # Filter by link type constraints
    if link_type:
        from jackrabbit.models import LinkType, TicketType

        if link_type == LinkType.PARENT:
            # Parent: target can be anything (but typically non-Epic)
            pass
        elif link_type == LinkType.CHILD:
            # Child: target must be Epic
            all_tickets = [t for t in all_tickets if t.type == TicketType.EPIC]
        # blocks, blocked_by, relates_to: no target type restriction

    return templates.TemplateResponse(
        request,
        "ticket_search_results.html",
        {
            "tickets": all_tickets[:20],  # Limit to 20 results
            "link_type": link_type,
        },
    )


# ---------------------------------------------------------------------------
# Ticket Detail page routes (ticket 12) — registered after /tickets/new and
# /tickets/search so the literal paths win over /tickets/{ticket_id}.
# ---------------------------------------------------------------------------


@router.get("/ticket/{ticket_id}", response_class=HTMLResponse)
@router.get("/tickets/{ticket_id}", response_class=HTMLResponse)
async def ticket_detail(
    request: Request,
    ticket_id: int,
    ticket_service: TicketService = Depends(get_ticket_service),
) -> HTMLResponse:
    """Ticket detail page (deep-linkable).

    The shell is server-rendered (header, actions, project/sprint/branch/PR
    metadata); dynamic sections load via HTMX: the ticket JSON card, the
    markdown/fields section, the sprint-assignment partial and the links
    section. Non-existent tickets render the HTML 404 page.
    """
    ticket = ticket_service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Resolve the project prefix while the session is open (plain scalars for
    # the template, so rendering never depends on lazy relationship loads).
    project = ticket_service.session.get(Project, ticket.project_id)
    project_prefix = project.prefix if project else "UNK"

    return templates.TemplateResponse(
        request,
        "ticket_detail.html",
        {
            "ticket_id": ticket.id,
            "full_id": f"{project_prefix}-{ticket.number:03d}",
            "ticket_title": ticket.title,
            "ticket_type": ticket.type.value if hasattr(ticket.type, "value") else ticket.type,
            "ticket_status": (
                ticket.status.value if hasattr(ticket.status, "value") else ticket.status
            ),
            "ticket_priority": (
                ticket.priority.value if hasattr(ticket.priority, "value") else ticket.priority
            ),
            "ticket_story_points": ticket.story_points,
            "ticket_project_id": ticket.project_id,
            "project_prefix": project_prefix,
            "branch_name": ticket.branch_name,
            "pr_url": ticket.pr_url,
            "original_id": ticket.original_id,
        },
    )


def _fields_section_response(request: Request, ticket: Ticket) -> HTMLResponse:
    """Render the Description (markdown) + Groomed Fields section partial."""
    groomed_fields = [
        {"name": name, "label": label, "value": getattr(ticket, name) or ""}
        for name, label in GROOMED_FIELD_DEFS
    ]
    editable = ticket.status not in FIELD_EDIT_LOCKED_STATUSES
    return templates.TemplateResponse(
        request,
        "ticket_fields_section.html",
        {
            "ticket": ticket,
            "groomed_fields": groomed_fields,
            "editable": editable,
            "show_groomed": editable or any(f["value"] for f in groomed_fields),
        },
    )


@router.get("/tickets/{ticket_id}/fields", response_class=HTMLResponse)
async def ticket_fields_section(
    request: Request,
    ticket_id: int,
    ticket_service: TicketService = Depends(get_ticket_service),
) -> HTMLResponse:
    """Markdown-rendered description + collapsible groomed fields partial."""
    ticket = ticket_service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return _fields_section_response(request, ticket)


@router.get("/tickets/{ticket_id}/fields/{field_name}/edit", response_class=HTMLResponse)
async def ticket_field_edit_form(
    request: Request,
    ticket_id: int,
    field_name: str,
    ticket_service: TicketService = Depends(get_ticket_service),
) -> HTMLResponse:
    """Inline edit form for a single groomed field."""
    ticket = ticket_service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    field_def = next(((n, label) for n, label in GROOMED_FIELD_DEFS if n == field_name), None)
    if field_def is None:
        raise HTTPException(status_code=404, detail=f"Unknown field: {field_name}")
    if ticket.status in FIELD_EDIT_LOCKED_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Fields cannot be edited while the ticket is {ticket.status.value}",
        )

    return templates.TemplateResponse(
        request,
        "ticket_field_edit.html",
        {
            "ticket": ticket,
            "field": {
                "name": field_def[0],
                "label": field_def[1],
                "value": getattr(ticket, field_def[0]) or "",
            },
        },
    )


@router.patch("/tickets/{ticket_id}/fields/{field_name}", response_class=HTMLResponse)
async def ticket_field_update(
    request: Request,
    ticket_id: int,
    field_name: str,
    ticket_service: TicketService = Depends(get_ticket_service),
) -> HTMLResponse:
    """Inline save for a single groomed field (HTMX form patch).

    Returns the refreshed fields section on success; on validation failure
    re-renders the edit form with an error message.
    """
    ticket = ticket_service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    field_def = next(((n, label) for n, label in GROOMED_FIELD_DEFS if n == field_name), None)
    if field_def is None:
        raise HTTPException(status_code=404, detail=f"Unknown field: {field_name}")
    if ticket.status in FIELD_EDIT_LOCKED_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Fields cannot be edited while the ticket is {ticket.status.value}",
        )

    form = await request.form()
    raw_value = form.get("value")
    if raw_value is None:
        raise HTTPException(status_code=400, detail="value is required")

    updated = ticket_service.update_ticket(ticket, **{field_name: str(raw_value)})
    return _fields_section_response(request, updated)


def _sprint_section_response(
    request: Request, ticket: Ticket, sprint: Sprint | None, sprints: list[Sprint]
) -> HTMLResponse:
    """Render the sprint assignment partial for the ticket detail page."""
    return templates.TemplateResponse(
        request,
        "ticket_sprint_section.html",
        {"ticket": ticket, "sprint": sprint, "sprints": sprints},
    )


@router.get("/tickets/{ticket_id}/sprint-section", response_class=HTMLResponse)
async def ticket_sprint_section(
    request: Request,
    ticket_id: int,
    ticket_service: TicketService = Depends(get_ticket_service),
    sprint_service: SprintService = Depends(get_sprint_service),
) -> HTMLResponse:
    """Sprint link / 'Unassigned' + assign-to-sprint dropdown partial."""
    ticket = ticket_service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    sprint = sprint_service.get_sprint(ticket.sprint_id) if ticket.sprint_id else None
    sprints = [] if sprint else sprint_service.list_sprints()
    return _sprint_section_response(request, ticket, sprint, sprints)


@router.post("/tickets/{ticket_id}/assign-sprint", response_class=HTMLResponse)
async def ticket_assign_sprint(
    request: Request,
    ticket_id: int,
    ticket_service: TicketService = Depends(get_ticket_service),
    sprint_service: SprintService = Depends(get_sprint_service),
) -> HTMLResponse:
    """HTMX form submit: assign the ticket to the selected sprint.

    Returns the refreshed sprint section partial so the dropdown swaps to the
    sprint link in place.
    """
    ticket = ticket_service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    form = await request.form()
    raw_sprint_id = form.get("sprint_id")
    if raw_sprint_id in (None, ""):
        raise HTTPException(status_code=400, detail="sprint_id is required")
    try:
        sprint_id = int(str(raw_sprint_id))
    except ValueError as e:
        raise HTTPException(status_code=400, detail="sprint_id must be an integer") from e

    try:
        sprint_service.assign_ticket_to_sprint(sprint_id, ticket_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    sprint = sprint_service.get_sprint(sprint_id)
    return _sprint_section_response(request, ticket, sprint, [])


@router.post("/tickets/{ticket_id}/unassign-sprint", response_class=HTMLResponse)
async def ticket_unassign_sprint(
    request: Request,
    ticket_id: int,
    ticket_service: TicketService = Depends(get_ticket_service),
    sprint_service: SprintService = Depends(get_sprint_service),
) -> HTMLResponse:
    """HTMX form submit: remove the ticket from its sprint."""
    ticket = ticket_service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if ticket.sprint_id is not None:
        try:
            sprint_service.unassign_ticket_from_sprint(ticket.sprint_id, ticket_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    return _sprint_section_response(request, ticket, None, sprint_service.list_sprints())
