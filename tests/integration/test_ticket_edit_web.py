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


class TestEditFormCriteria:
    """The ticket-detail edit view carries the Acceptance criteria editor
    (JRB-023, ADR-0025): type-conditional asterisk header, editable rows with
    add/remove controls, pre-filled existing criteria — read-only once the
    ticket has moved past Groomed (rows are locked, ADR-0025)."""

    async def _story_with_criteria(
        self, client: httpx.AsyncClient, texts: list[str], **extra
    ) -> dict:
        payload = {
            "project_id": 1,
            "title": "Edit form criteria ticket",
            "type": "Story",
        }
        payload.update(extra)
        created = await client.post("/api/v1/tickets", json=payload)
        assert created.status_code == 201, created.text
        ticket = created.json()
        if texts:
            response = await client.patch(
                f"/api/v1/tickets/{ticket['id']}", json={"criteria": texts}
            )
            assert response.status_code == 200, response.text
        return ticket

    async def test_story_edit_form_shows_criteria_asterisk_and_prefilled_rows(
        self, client: httpx.AsyncClient
    ):
        ticket = await self._story_with_criteria(client, ["Write the report"])
        response = await get_page(client, f"/tickets/{ticket['id']}/edit")
        assert response.status_code == 200
        html = response.text
        assert "Acceptance criteria" in html
        header = html[html.index("Acceptance criteria") : html.index("Acceptance criteria") + 200]
        assert 'class="text-red-500"' in header
        assert "Add criterion" in html
        assert 'value="Write the report"' in html

    async def test_epic_edit_form_shows_plain_criteria_label(self, client: httpx.AsyncClient):
        ticket = await self._story_with_criteria(
            client, [], type="Epic", title="Epic edit criteria"
        )
        response = await get_page(client, f"/tickets/{ticket['id']}/edit")
        assert response.status_code == 200
        html = response.text
        assert "Acceptance criteria" in html
        header = html[html.index("Acceptance criteria") : html.index("Acceptance criteria") + 200]
        assert 'class="text-red-500"' not in header
        assert "Add criterion" in html

    async def test_criteria_rows_are_read_only_once_in_progress(
        self, client_with_seeds: httpx.AsyncClient
    ):
        """From In Progress onward the rows are locked (ADR-0025): the edit
        form shows them read-only and submits no criteria inputs, so saving
        other fields never trips the 409 criteria-locked guard."""
        ticket = await self._story_with_criteria(client_with_seeds, ["Locked criterion"])
        response = await client_with_seeds.post(
            f"/api/v1/tickets/{ticket['id']}/transition",
            json={
                "to_status": "Groomed",
                "approach": "Approach",
                "files_to_change": "files",
                "test_plan": "Plan",
                "validation_steps": "Steps",
                "criteria": ["Locked criterion"],
            },
        )
        assert response.status_code == 200, response.text
        response = await client_with_seeds.post(
            f"/api/v1/tickets/{ticket['id']}/transition",
            json={
                "to_status": "In Progress",
                "branch_name": "feature/edit-criteria-001",
            },
        )
        assert response.status_code == 200, response.text
        response = await get_page(client_with_seeds, f"/tickets/{ticket['id']}/edit")
        assert response.status_code == 200
        html = response.text
        assert "Locked criterion" in html
        assert 'name="criteria"' not in html
        assert "Add criterion" not in html

    async def test_editing_other_fields_leaves_criteria_rows_untouched(
        self, client_with_seeds: httpx.AsyncClient
    ):
        """The edit form omits the criteria list when the rows are unchanged,
        so a plain title save does not replace (and re-number) the rows."""
        ticket = await self._story_with_criteria(client_with_seeds, ["Untouched criterion"])
        response = await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}", json={"title": "Renamed only"}
        )
        assert response.status_code == 200, response.text
        rows = (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/criteria")).json()
        assert [row["text"] for row in rows] == ["Untouched criterion"]
        assert rows[0]["id"] is not None
