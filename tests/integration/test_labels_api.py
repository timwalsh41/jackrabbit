"""Integration tests for the Labels API: the registry, attach/detach, and the
labels carried in the ticket payload."""

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


class TestLabelRegistry:
    """GET /api/v1/labels — the vocabulary with a usage count per label."""

    async def test_registry_is_empty_to_begin_with(self, client_with_seeds: AsyncClient):
        response = await client_with_seeds.get("/api/v1/labels")
        assert response.status_code == 200
        assert response.json() == []

    async def test_registry_lists_labels_with_a_usage_count(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)
        await _attach(client_with_seeds, ticket["id"], "Backend")
        await _attach(client_with_seeds, ticket["id"], "Frontend")

        response = await client_with_seeds.get("/api/v1/labels")
        assert response.status_code == 200
        data = response.json()
        assert {entry["name"] for entry in data} == {"Backend", "Frontend"}
        for entry in data:
            assert entry["usage_count"] == 1
            assert entry["color"].startswith("#")
            assert isinstance(entry["id"], int)

    async def test_usage_count_counts_the_tickets_carrying_the_label(
        self, client_with_seeds: AsyncClient
    ):
        first = await _ticket(client_with_seeds, "First")
        second = await _ticket(client_with_seeds, "Second")
        await _attach(client_with_seeds, first["id"], "Backend")
        await _attach(client_with_seeds, second["id"], "Backend")

        data = (await client_with_seeds.get("/api/v1/labels")).json()
        assert data[0]["usage_count"] == 2

    async def test_a_label_keeps_the_spelling_first_typed(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)
        await _attach(client_with_seeds, ticket["id"], "Backend")
        await _attach(client_with_seeds, ticket["id"], "backend")

        data = (await client_with_seeds.get("/api/v1/labels")).json()
        assert len(data) == 1
        assert data[0]["name"] == "Backend"


class TestAttachAndDetach:
    """POST/DELETE /api/v1/tickets/{id}/labels."""

    async def test_attach_creates_the_label_on_demand(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)
        response = await _attach(client_with_seeds, ticket["id"], "Backend")
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["name"] == "Backend"
        assert data["color"].startswith("#")

    async def test_attach_is_case_insensitive(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)
        first = await _attach(client_with_seeds, ticket["id"], "Backend")
        second = await _attach(client_with_seeds, ticket["id"], "backend")
        assert second.status_code == 201
        assert second.json()["id"] == first.json()["id"]
        assert second.json()["name"] == "Backend"

    async def test_attach_to_an_unknown_ticket_is_404(self, client_with_seeds: AsyncClient):
        response = await _attach(client_with_seeds, 9999, "Backend")
        assert response.status_code == 404

    async def test_attach_rejects_an_invalid_name(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)
        response = await _attach(client_with_seeds, ticket["id"], "back/end")
        assert response.status_code == 422
        assert "letters" in response.json()["detail"]

    async def test_attach_rejects_an_overlong_name(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)
        response = await _attach(client_with_seeds, ticket["id"], "x" * 51)
        assert response.status_code == 422
        assert "50" in response.json()["detail"]

    async def test_labels_of_a_ticket_are_readable(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)
        await _attach(client_with_seeds, ticket["id"], "Backend")
        await _attach(client_with_seeds, ticket["id"], "Frontend")

        response = await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/labels")
        assert response.status_code == 200
        assert {label["name"] for label in response.json()} == {"Backend", "Frontend"}

    async def test_detach_removes_the_label(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)
        label = (await _attach(client_with_seeds, ticket["id"], "Backend")).json()

        response = await client_with_seeds.delete(
            f"/api/v1/tickets/{ticket['id']}/labels/{label['id']}"
        )
        assert response.status_code == 204

        labels = (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/labels")).json()
        assert labels == []

    async def test_detach_an_unknown_label_is_404(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)
        response = await client_with_seeds.delete(f"/api/v1/tickets/{ticket['id']}/labels/4242")
        assert response.status_code == 404

    async def test_a_label_can_be_attached_to_any_ticket_type(self, client_with_seeds: AsyncClient):
        for ticket_type in ("Epic", "Story", "Bug", "Spike"):
            ticket = await _ticket(client_with_seeds, f"A {ticket_type}")
            response = await _attach(client_with_seeds, ticket["id"], "Backend")
            assert response.status_code == 201, response.text


class TestTicketPayload:
    """The ticket payload carries the ticket's labels."""

    async def test_ticket_detail_includes_labels(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)
        await _attach(client_with_seeds, ticket["id"], "Backend")

        response = await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}")
        assert response.status_code == 200
        labels = response.json()["labels"]
        assert [label["name"] for label in labels] == ["Backend"]
        assert labels[0]["color"].startswith("#")

    async def test_ticket_listing_includes_labels(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)
        await _attach(client_with_seeds, ticket["id"], "Backend")

        response = await client_with_seeds.get("/api/v1/tickets")
        assert response.status_code == 200
        items = {item["id"]: item for item in response.json()["items"]}
        assert [label["name"] for label in items[ticket["id"]]["labels"]] == ["Backend"]

    async def test_a_ticket_may_carry_no_labels(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)
        response = await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}")
        assert response.json()["labels"] == []


class TestCreateAndUpdateWithLabels:
    """Ticket create and update accept a set of label names."""

    async def test_create_ticket_with_labels(self, client_with_seeds: AsyncClient):
        response = await client_with_seeds.post(
            "/api/v1/tickets",
            json={
                "project_id": 2,
                "title": "With labels",
                "type": "Story",
                "labels": ["Backend", "triage:ready-for-agent"],
            },
        )
        assert response.status_code == 201, response.text
        labels = response.json()["labels"]
        assert {label["name"] for label in labels} == {"Backend", "triage:ready-for-agent"}

    async def test_create_ticket_with_an_invalid_label_is_rejected(
        self, client_with_seeds: AsyncClient
    ):
        response = await client_with_seeds.post(
            "/api/v1/tickets",
            json={"project_id": 2, "title": "Bad label", "labels": ["back/end"]},
        )
        assert response.status_code == 422
        # Nothing was created.
        items = (await client_with_seeds.get("/api/v1/tickets")).json()["items"]
        assert all(item["title"] != "Bad label" for item in items)

    async def test_update_replaces_the_whole_label_set(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)
        await _attach(client_with_seeds, ticket["id"], "Backend")
        await _attach(client_with_seeds, ticket["id"], "Frontend")

        response = await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}", json={"labels": ["Backend"]}
        )
        assert response.status_code == 200, response.text
        assert [label["name"] for label in response.json()["labels"]] == ["Backend"]

    async def test_update_with_no_labels_removes_them_all(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)
        await _attach(client_with_seeds, ticket["id"], "Backend")

        response = await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}", json={"labels": []}
        )
        assert response.status_code == 200
        assert response.json()["labels"] == []

    async def test_update_without_labels_leaves_them_alone(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)
        await _attach(client_with_seeds, ticket["id"], "Backend")

        response = await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}", json={"title": "Renamed"}
        )
        assert response.status_code == 200
        assert [label["name"] for label in response.json()["labels"]] == ["Backend"]

    async def test_update_creates_labels_that_do_not_exist_yet(
        self, client_with_seeds: AsyncClient
    ):
        ticket = await _ticket(client_with_seeds)
        response = await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}", json={"labels": ["Docs"]}
        )
        assert response.status_code == 200
        assert [label["name"] for label in response.json()["labels"]] == ["Docs"]
        registry = (await client_with_seeds.get("/api/v1/labels")).json()
        assert [entry["name"] for entry in registry] == ["Docs"]


class TestDeletingATicket:
    """Deleting a ticket removes its label attachments."""

    async def test_deleting_a_ticket_leaves_no_attachment_behind(
        self, client_with_seeds: AsyncClient
    ):
        ticket = await _ticket(client_with_seeds)
        await _attach(client_with_seeds, ticket["id"], "Backend")

        response = await client_with_seeds.delete(f"/api/v1/tickets/{ticket['id']}")
        assert response.status_code == 204

        # The label survives in the registry, with no tickets carrying it.
        registry = (await client_with_seeds.get("/api/v1/labels")).json()
        assert registry[0]["name"] == "Backend"
        assert registry[0]["usage_count"] == 0

    async def test_the_ticket_no_longer_lists_labels(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)
        await _attach(client_with_seeds, ticket["id"], "Backend")
        await client_with_seeds.delete(f"/api/v1/tickets/{ticket['id']}")

        # The ticket is gone, so its labels are no longer readable.
        response = await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/labels")
        assert response.status_code == 404


@pytest.mark.parametrize("name", ["Backend", "triage:ready-for-agent", "needs review"])
async def test_valid_names_are_accepted(client_with_seeds: AsyncClient, name: str):
    ticket = await _ticket(client_with_seeds)
    response = await _attach(client_with_seeds, ticket["id"], name)
    assert response.status_code == 201, response.text
    assert response.json()["name"] == name
