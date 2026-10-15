"""Integration tests for the full Ticket Detail page (web routes).

Covers ticket 12: GET /tickets/{id}, markdown description, sprint assignment
partial, inline groomed-field edits, delete action, and HTML 404 handling.
"""

import httpx
import pytest
from jackrabbit.models import Priority, TicketStatus, TicketType
from jackrabbit.services import SprintService


@pytest.fixture
def client(client_with_seeds: httpx.AsyncClient) -> httpx.AsyncClient:
    """Seeded HTTP client (UNS=1, WEB=2, API=3) for this module."""
    return client_with_seeds


async def create_ticket(client: httpx.AsyncClient, **overrides) -> dict:
    payload = {
        "project_id": 1,
        "title": "Detail page ticket",
        "type": TicketType.STORY,
        "priority": Priority.MEDIUM,
        "description": "A ticket for the detail page",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/tickets", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def get_page(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """GET as a browser would (HTML accept header)."""
    return await client.get(url, headers={"accept": "text/html"})


class TestTicketDetailPage:
    async def test_detail_page_renders_at_tickets_id(self, client: httpx.AsyncClient):
        ticket = await create_ticket(client)
        response = await get_page(client, f"/tickets/{ticket['id']}")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        # Header shows the zero-padded full ticket ID (MSC-005 style) and title
        expected_full_id = f"UNS-{ticket['number']:03d}"
        assert expected_full_id in response.text
        assert ticket["title"] in response.text
        assert 'id="ticket-content"' in response.text

    async def test_legacy_ticket_alias_still_works(self, client: httpx.AsyncClient):
        ticket = await create_ticket(client)
        response = await get_page(client, f"/ticket/{ticket['id']}")
        assert response.status_code == 200

    async def test_detail_page_is_deep_linkable(self, client: httpx.AsyncClient):
        """A direct hit on the URL returns the full shell (content loads via HTMX)."""
        ticket = await create_ticket(client)
        response = await get_page(client, f"/tickets/{ticket['id']}")
        assert response.status_code == 200
        assert 'id="ticket-content"' in response.text

    async def test_404_page_for_nonexistent_ticket(self, client: httpx.AsyncClient):
        response = await get_page(client, "/tickets/99999")
        assert response.status_code == 404
        assert "text/html" in response.headers["content-type"]
        assert "not found" in response.text.lower()

    async def test_404_page_for_nonexistent_ticket_legacy_route(self, client: httpx.AsyncClient):
        response = await get_page(client, "/ticket/99999")
        assert response.status_code == 404
        assert "text/html" in response.headers["content-type"]

    async def test_api_404s_stay_json(self, client: httpx.AsyncClient):
        response = await client.get("/api/v1/tickets/99999")
        assert response.status_code == 404
        assert response.json()["detail"] == "Ticket not found"


class TestDetailPageSections:
    async def test_page_has_fields_section_container(self, client: httpx.AsyncClient):
        ticket = await create_ticket(client)
        response = await get_page(client, f"/tickets/{ticket['id']}")
        assert "ticket-fields-section" in response.text

    async def test_fields_section_renders_description_markdown(self, client: httpx.AsyncClient):
        ticket = await create_ticket(client, description="# Heading\n\nSome **bold** text")
        response = await get_page(client, f"/tickets/{ticket['id']}/fields")
        assert response.status_code == 200
        assert "<h1>Heading</h1>" in response.text
        assert "<strong>bold</strong>" in response.text

    async def test_fields_section_escapes_html_in_description(self, client: httpx.AsyncClient):
        ticket = await create_ticket(client, description="evil <script>alert(1)</script> text")
        response = await get_page(client, f"/tickets/{ticket['id']}/fields")
        assert "<script>alert(1)</script>" not in response.text
        assert "&lt;script&gt;" in response.text

    async def test_groomed_fields_are_collapsible_and_present(self, client: httpx.AsyncClient):
        response = await get_page(client, "/api/v1/tickets")
        assert response.status_code == 200
        # collapsible via <details> element
        ticket = await create_ticket(
            client,
            approach="Step by step",
            files_to_change="a.py",
            test_plan="unit tests",
            validation_steps="run it",
        )
        response = await get_page(client, f"/tickets/{ticket['id']}/fields")
        assert "<details" in response.text
        assert "Approach" in response.text
        assert "Files to Change" in response.text
        assert "Test Plan" in response.text
        assert "Validation Steps" in response.text

    async def test_project_shown_as_link(self, client: httpx.AsyncClient):
        response = await get_page(client, "/api/v1/tickets")
        assert response.status_code == 200


class TestInlineFieldEditing:
    @pytest.fixture
    async def groomed(self, client: httpx.AsyncClient, seeded_projects) -> dict:
        ticket = await create_ticket(
            client,
            approach="Original approach",
            files_to_change="a.py",
            test_plan="unit",
            validation_steps="manual",
        )
        response = await client.post(
            f"/api/v1/tickets/{ticket['id']}/transition",
            json={"to_status": "Groomed", "reason": "ready"},
        )
        assert response.status_code == 200
        return ticket

    async def test_edit_form_partial(self, client: httpx.AsyncClient, groomed: dict):
        response = await get_page(client, f"/tickets/{groomed['id']}/fields/approach/edit")
        assert response.status_code == 200
        assert "Original approach" in response.text
        assert "textarea" in response.text

    async def test_patch_field_updates_value(self, client: httpx.AsyncClient, groomed: dict):
        response = await client.patch(
            f"/tickets/{groomed['id']}/fields/approach",
            content="value=New+approach+value",
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "accept": "text/html",
            },
        )
        assert response.status_code == 200
        assert "New approach value" in response.text
        # Persisted
        detail = (await client.get(f"/api/v1/tickets/{groomed['id']}")).json()
        assert detail["approach"] == "New approach value"

    async def test_patch_rejects_unknown_field(self, client: httpx.AsyncClient, groomed: dict):
        response = await client.patch(
            f"/tickets/{groomed['id']}/fields/not_a_field",
            content="x",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code in (400, 404, 422)

    async def test_edit_blocked_when_complete(self, client: httpx.AsyncClient, groomed: dict):
        # Drive forward through the guarded statuses to Complete
        for step in (
            {"to_status": "In Progress", "branch_name": "feature/branch"},
            {"to_status": "Ready for Review", "pr_url": "https://github.com/x/y/pull/1"},
            {"to_status": "Complete", "reason": "done"},
        ):
            response = await client.post(f"/api/v1/tickets/{groomed['id']}/transition", json=step)
            assert response.status_code == 200, response.text
        response = await get_page(client, f"/tickets/{groomed['id']}/fields")
        # Edit affordances removed for Complete tickets
        assert f"/tickets/{groomed['id']}/fields/approach/edit" not in response.text

        response = await client.patch(
            f"/tickets/{groomed['id']}/fields/approach",
            content="hack",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 400

    async def test_edit_blocked_when_rejected(self, client: httpx.AsyncClient, groomed: dict):
        await client.post(
            f"/api/v1/tickets/{groomed['id']}/transition",
            json={"to_status": "Rejected", "reason": "nope"},
        )
        response = await client.patch(
            f"/tickets/{groomed['id']}/fields/approach",
            content="hack",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 400

    async def test_field_edit_preserves_status(self, client: httpx.AsyncClient, groomed: dict):
        """Inline field edit must not be usable to change status."""
        response = await client.patch(
            f"/tickets/{groomed['id']}/fields/status",
            content="Complete",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code in (400, 404, 422)
        detail = (await client.get(f"/api/v1/tickets/{groomed['id']}")).json()
        assert detail["status"] == TicketStatus.GROOMED


class TestSprintAssignmentPartial:
    @pytest.fixture
    async def sprint(self, test_db) -> dict:
        service = SprintService(test_db)
        sprint = service.create_sprint(number=2601, name="Sprint 2601")
        return {"id": sprint.id, "number": sprint.number, "name": sprint.name}

    async def test_unassigned_shows_dropdown(self, client: httpx.AsyncClient, sprint: dict):
        ticket = await create_ticket(client)
        response = await get_page(client, f"/tickets/{ticket['id']}/sprint-section")
        assert response.status_code == 200
        assert "Unassigned" in response.text
        assert "assign-sprint" in response.text
        assert str(sprint["id"]) in response.text

    async def test_assign_sprint_via_htmx_partial(self, client: httpx.AsyncClient, sprint: dict):
        ticket = await create_ticket(client)
        response = await client.post(
            f"/tickets/{ticket['id']}/assign-sprint",
            content=f"sprint_id={sprint['id']}",
            headers={
                "content-type": "application/x-www-form-urlencoded",
                "accept": "text/html",
            },
        )
        assert response.status_code == 200
        assert f"/sprint/{sprint['id']}" in response.text
        # Persisted
        detail = (await client.get(f"/api/v1/tickets/{ticket['id']}")).json()
        assert detail["sprint_id"] == sprint["id"]

    async def test_assigned_section_shows_sprint_link(
        self, client: httpx.AsyncClient, sprint: dict
    ):
        ticket = await create_ticket(client)
        await client.post(
            f"/tickets/{ticket['id']}/assign-sprint",
            content=f"sprint_id={sprint['id']}",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        response = await get_page(client, f"/tickets/{ticket['id']}/sprint-section")
        assert f"/sprint/{sprint['id']}" in response.text
        assert "unassign-sprint" in response.text

    async def test_unassign_sprint_via_htmx_partial(self, client: httpx.AsyncClient, sprint: dict):
        ticket = await create_ticket(client)
        await client.post(
            f"/tickets/{ticket['id']}/assign-sprint",
            content=f"sprint_id={sprint['id']}",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        response = await client.post(
            f"/tickets/{ticket['id']}/unassign-sprint",
            headers={"accept": "text/html"},
        )
        assert response.status_code == 200
        assert "Unassigned" in response.text
        detail = (await client.get(f"/api/v1/tickets/{ticket['id']}")).json()
        assert detail["sprint_id"] is None

    async def test_assign_with_invalid_sprint(self, client: httpx.AsyncClient):
        ticket = await create_ticket(client)
        response = await client.post(
            f"/tickets/{ticket['id']}/assign-sprint",
            content="sprint_id=99999",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 400

    async def test_assign_missing_sprint_param(self, client: httpx.AsyncClient):
        ticket = await create_ticket(client)
        response = await client.post(
            f"/tickets/{ticket['id']}/assign-sprint",
            content="",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 400


class TestDetailPageActions:
    async def test_delete_action_present_with_confirm(self, client: httpx.AsyncClient):
        ticket = await create_ticket(client)
        response = await get_page(client, f"/tickets/{ticket['id']}")
        assert response.status_code == 200
        assert f'hx-delete="/api/v1/tickets/{ticket["id"]}"' in response.text
        assert "hx-confirm" in response.text

    async def test_edit_action_links_to_edit_page(self, client: httpx.AsyncClient):
        ticket = await create_ticket(client)
        response = await get_page(client, f"/tickets/{ticket['id']}")
        assert f"/tickets/{ticket['id']}/edit" in response.text

    async def test_move_project_action_present(self, client: httpx.AsyncClient):
        ticket = await create_ticket(client)
        response = await get_page(client, f"/tickets/{ticket['id']}")
        assert f"/tickets/{ticket['id']}/move-project/modal" in response.text

    async def test_project_metadata_links_to_project_tickets(self, client: httpx.AsyncClient):
        ticket = await create_ticket(client)
        response = await get_page(client, f"/tickets/{ticket['id']}")
        assert f"/projects/{ticket['project_id']}/tickets" in response.text

    async def test_transition_history_via_api_data(
        self, client: httpx.AsyncClient, seeded_projects
    ) -> None:
        """Transition history endpoint data flows through the existing API."""
        ticket = await create_ticket(client)
        response = await client.post(
            f"/api/v1/tickets/{ticket['id']}/transition",
            json={"to_status": "Rejected", "reason": "duplicate"},
        )
        assert response.status_code == 200, response.text
        detail = (await client.get(f"/api/v1/tickets/{ticket['id']}")).json()
        assert len(detail["transitions"]) == 1
        assert detail["transitions"][0]["reason"] == "duplicate"

    async def test_delete_ticket_removes_it(self, client: httpx.AsyncClient):
        ticket = await create_ticket(client)
        response = await client.delete(f"/api/v1/tickets/{ticket['id']}")
        assert response.status_code == 204
        assert (await client.get(f"/api/v1/tickets/{ticket['id']}")).status_code == 404
