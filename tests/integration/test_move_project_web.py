"""Integration tests for the ticket project-move web flow (ticket 09).

Covers:
- GET /tickets/{id}/move-project/modal: project dropdown excludes the current project
- The modal form posts urlencoded form data to the move-project API endpoint
- After a move, the ticket detail reflects the new project and shows original_id
"""

import pytest
from httpx import AsyncClient
from jackrabbit.services import TicketService


@pytest.fixture
async def uns_ticket(test_db, seeded_projects):
    """A ticket in the UNS project."""
    ticket_service = TicketService(test_db)
    return ticket_service.create_ticket(project_id=seeded_projects[0].id, title="Movable ticket")


@pytest.mark.asyncio
async def test_move_modal_excludes_current_project(client_with_seeds: AsyncClient, uns_ticket):
    """The modal dropdown lists other projects but not the ticket's current one."""
    response = await client_with_seeds.get(f"/tickets/{uns_ticket.id}/move-project/modal")
    assert response.status_code == 200

    body = response.text
    # Modal form posts to the move endpoint for this ticket
    assert f"/api/v1/tickets/{uns_ticket.id}/move-project" in body
    # Current project (UNS) is excluded from the dropdown options
    uns_id = uns_ticket.project_id
    assert f'<option value="{uns_id}">UNS' not in body
    assert "WEB" in body and "API" in body


@pytest.mark.asyncio
async def test_move_modal_unknown_ticket_404(client_with_seeds: AsyncClient):
    response = await client_with_seeds.get("/tickets/99999/move-project/modal")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_htmx_form_move_updates_ticket(
    client_with_seeds: AsyncClient, test_db, uns_ticket, seeded_projects
):
    """Simulate the htmx form submission (urlencoded body) and verify the move."""
    web = seeded_projects[1]
    response = await client_with_seeds.post(
        f"/api/v1/tickets/{uns_ticket.id}/move-project",
        data={"project_id": str(web.id)},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["new_full_id"] == "WEB-1"
    assert data["original_id"] == "UNS-1"

    # Ticket detail now shows the new project and preserved original_id
    detail = await client_with_seeds.get(f"/api/v1/tickets/{uns_ticket.id}")
    assert detail.status_code == 200
    assert detail.json()["project_id"] == web.id
    assert detail.json()["original_id"] == "UNS-1"


@pytest.mark.asyncio
async def test_move_modal_move_missing_project_returns_400(
    client_with_seeds: AsyncClient, uns_ticket
):
    response = await client_with_seeds.post(
        f"/api/v1/tickets/{uns_ticket.id}/move-project",
        data={"project_id": ""},
    )
    assert response.status_code == 400
