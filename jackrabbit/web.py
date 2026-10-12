"""Web/UI routes for Jackrabbit (HTMX + Jinja2)."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()

# Use default Jinja2Templates with directory - simpler and more reliable
template_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(template_dir))


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {})


@router.get("/backlog", response_class=HTMLResponse)
async def backlog(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "backlog.html", {})


@router.get("/sprint/{sprint_id}", response_class=HTMLResponse)
async def sprint_view(request: Request, sprint_id: int) -> HTMLResponse:
    return templates.TemplateResponse(request, "sprint.html", {"sprint_id": sprint_id})


@router.get("/plan", response_class=HTMLResponse)
async def plan(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "plan.html", {})


@router.get("/ticket/{ticket_id}", response_class=HTMLResponse)
async def ticket_detail(request: Request, ticket_id: int) -> HTMLResponse:
    return templates.TemplateResponse(request, "ticket_detail.html", {"ticket_id": ticket_id})
