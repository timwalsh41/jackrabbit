"""Integration tests for the label web interface: the ticket page's labels
section, the add-label modal, and the labels field in the create/edit form."""

import re

import pytest
from httpx import AsyncClient


async def _ticket(client: AsyncClient, title: str = "Label me", project_id: int = 2) -> dict:
    response = await client.post(
        "/api/v1/tickets", json={"project_id": project_id, "title": title, "type": "Story"}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _attach(client: AsyncClient, ticket_id: int, name: str):
    return await client.post(f"/api/v1/tickets/{ticket_id}/labels", json={"name": name})


def _chip_names(html: str) -> list[str]:
    """The label names rendered as chips in a labels section."""
    return re.findall(r'data-label-name="([^"]*)"', html)


class TestLabelsSection:
    """GET /tickets/{id}/labels — the ticket page's labels section."""

    async def test_the_section_lists_the_tickets_labels(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)
        await _attach(client_with_seeds, ticket["id"], "Backend")

        response = await client_with_seeds.get(f"/tickets/{ticket['id']}/labels")
        assert response.status_code == 200
        assert _chip_names(response.text) == ["Backend"]

    async def test_the_section_says_so_when_there_are_no_labels(
        self, client_with_seeds: AsyncClient
    ):
        ticket = await _ticket(client_with_seeds)
        response = await client_with_seeds.get(f"/tickets/{ticket['id']}/labels")
        assert response.status_code == 200
        assert "No labels yet" in response.text

    async def test_each_chip_can_be_removed(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)
        label = (await _attach(client_with_seeds, ticket["id"], "Backend")).json()

        response = await client_with_seeds.get(f"/tickets/{ticket['id']}/labels")
        assert f'hx-delete="/api/v1/tickets/{ticket["id"]}/labels/{label["id"]}"' in response.text

    async def test_the_section_offers_the_labels_in_use_as_suggestions(
        self, client_with_seeds: AsyncClient
    ):
        other = await _ticket(client_with_seeds, "Other")
        await _attach(client_with_seeds, other["id"], "Frontend")
        ticket = await _ticket(client_with_seeds)

        response = await client_with_seeds.get(f"/tickets/{ticket['id']}/labels/modal")
        assert response.status_code == 200
        assert "Frontend" in response.text


class TestAddLabelModal:
    """GET /tickets/{id}/labels/modal — the add-label modal."""

    async def test_the_modal_has_a_name_input(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)
        response = await client_with_seeds.get(f"/tickets/{ticket['id']}/labels/modal")
        assert response.status_code == 200
        assert 'name="name"' in response.text

    async def test_the_modal_suggests_the_labels_already_in_use(
        self, client_with_seeds: AsyncClient
    ):
        other = await _ticket(client_with_seeds, "Other")
        await _attach(client_with_seeds, other["id"], "Frontend")
        ticket = await _ticket(client_with_seeds)

        response = await client_with_seeds.get(f"/tickets/{ticket['id']}/labels/modal")
        assert 'value="Frontend"' in response.text

    async def test_the_modal_posts_to_the_label_endpoint(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)
        response = await client_with_seeds.get(f"/tickets/{ticket['id']}/labels/modal")
        assert f'hx-post="/api/v1/tickets/{ticket["id"]}/labels"' in response.text


class TestHtmxAttachAndDetach:
    """The HTMX-aware label endpoints return the re-rendered labels section."""

    async def test_attaching_returns_the_refreshed_section(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)
        response = await client_with_seeds.post(
            f"/api/v1/tickets/{ticket['id']}/labels",
            json={"name": "Backend"},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert _chip_names(response.text) == ["Backend"]

    async def test_detaching_returns_the_refreshed_section(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)
        label = (await _attach(client_with_seeds, ticket["id"], "Backend")).json()

        response = await client_with_seeds.delete(
            f"/api/v1/tickets/{ticket['id']}/labels/{label['id']}",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert _chip_names(response.text) == []


class TestLabelsInTheTicketForm:
    """The create and edit forms carry a labels field."""

    async def test_the_new_ticket_form_has_a_labels_field(self, client_with_seeds: AsyncClient):
        response = await client_with_seeds.get("/tickets/new")
        assert response.status_code == 200
        assert "data-labels-field" in response.text

    async def test_the_edit_form_shows_the_current_labels(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)
        await _attach(client_with_seeds, ticket["id"], "Backend")

        response = await client_with_seeds.get(f"/tickets/{ticket['id']}/edit")
        assert response.status_code == 200
        assert 'name="labels"' in response.text
        assert 'value="Backend"' in response.text

    async def test_the_new_ticket_form_suggests_the_labels_in_use(
        self, client_with_seeds: AsyncClient
    ):
        other = await _ticket(client_with_seeds, "Other")
        await _attach(client_with_seeds, other["id"], "Frontend")

        response = await client_with_seeds.get("/tickets/new")
        assert 'value="Frontend"' in response.text


@pytest.mark.parametrize("path", ["/tickets/new"])
async def test_the_form_field_is_present(client_with_seeds: AsyncClient, path: str):
    response = await client_with_seeds.get(path)
    assert "data-label-input" in response.text
