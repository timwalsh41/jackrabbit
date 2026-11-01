"""Integration tests for the full-page Ticket Edit form (web routes).

Covers JRB-014: from the ticket edit view, Save and Cancel must return to
the ticket detail view (``/tickets/{id}``) instead of the backlog, and the
back-navigation links must point at the ticket detail. The New Ticket form
(``/tickets/new``) keeps its backlog back-links, since there is no detail
page to return to yet.
"""

import json

import httpx
import pytest
from jackrabbit.models import Priority, TicketType


@pytest.fixture
def client(client_with_seeds: httpx.AsyncClient) -> httpx.AsyncClient:
    """Seeded HTTP client for this module."""
    return client_with_seeds


async def create_ticket(client: httpx.AsyncClient, **overrides) -> dict:
    payload = {
        "project_id": 1,
        "title": "Edit redirect ticket",
        "type": TicketType.STORY,
        "priority": Priority.MEDIUM,
        "description": "A ticket for the edit redirect tests",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/tickets", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def get_page(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """GET as a browser would (HTML accept header)."""
    return await client.get(url, headers={"accept": "text/html"})


class TestEditFormBackLinks:
    async def test_edit_page_back_link_points_to_ticket_detail(self, client: httpx.AsyncClient):
        ticket = await create_ticket(client)
        response = await get_page(client, f"/tickets/{ticket['id']}/edit")
        assert response.status_code == 200
        assert "<html" in response.text.lower()
        assert "← Back to Ticket Detail" in response.text
        assert f'href="/tickets/{ticket["id"]}"' in response.text
        assert "← Back to Backlog" not in response.text

    async def test_edit_page_cancel_points_to_ticket_detail(self, client: httpx.AsyncClient):
        ticket = await create_ticket(client)
        response = await get_page(client, f"/tickets/{ticket['id']}/edit")
        assert response.status_code == 200
        # The form's Cancel link must go back to the ticket detail page.
        cancel = f'<a href="/tickets/{ticket["id"]}"\n                   class="px-4 py-2'
        assert cancel in response.text

    async def test_top_nav_backlog_link_still_present(self, client: httpx.AsyncClient):
        """The top link bar keeps a direct route to the backlog."""
        ticket = await create_ticket(client)
        response = await get_page(client, f"/tickets/{ticket['id']}/edit")
        assert response.status_code == 200
        assert '<a href="/backlog" class="text-gray-700' in response.text

    async def test_new_ticket_form_keeps_backlog_links(self, client: httpx.AsyncClient):
        response = await get_page(client, "/tickets/new")
        assert response.status_code == 200
        assert "← Back to Backlog" in response.text
        assert "← Back to Ticket Detail" not in response.text
        assert '<a href="/backlog"\n                   class="px-4 py-2' in response.text


class TestEditSaveRedirect:
    async def test_patch_htmx_form_target_redirects_to_ticket_detail(
        self, client_with_seeds: httpx.AsyncClient
    ):
        """A full-page edit PATCH (hx-target="this", not a ticket row) must
        answer with HX-Redirect to the ticket detail page."""
        ticket = await create_ticket(client_with_seeds)
        payload = {"title": "Renamed via full-page edit", "priority": Priority.HIGH.value}
        r = await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}",
            content=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "HX-Request": "true",
                "HX-Target": "ticket-form",
            },
        )
        assert r.status_code == 200, r.text
        assert r.headers.get("HX-Redirect") == f"/tickets/{ticket['id']}"

    async def test_patch_htmx_row_target_still_returns_row(
        self, client_with_seeds: httpx.AsyncClient
    ):
        """The modal edit flow (row target) keeps swapping the row in place."""
        ticket = await create_ticket(client_with_seeds)
        payload = {"title": "Renamed via modal edit"}
        r = await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}",
            content=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "HX-Request": "true",
                "HX-Target": f"ticket-row-{ticket['id']}",
            },
        )
        assert r.status_code == 200, r.text
        assert "HX-Redirect" not in r.headers
        assert f'hx-get="/tickets/{ticket["id"]}/edit"' in r.text

    async def test_patch_without_htmx_returns_json(self, client_with_seeds: httpx.AsyncClient):
        ticket = await create_ticket(client_with_seeds)
        payload = {"title": "Renamed via plain PATCH"}
        r = await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}",
            content=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["title"] == "Renamed via plain PATCH"
        assert "HX-Redirect" not in r.headers
