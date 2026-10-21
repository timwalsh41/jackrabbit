"""Integration tests for triage roles recorded as labels: the triage API, the
ticket payload carrying the triage label, and the triage role rendered on the
ticket page and in the backlog table."""

from httpx import AsyncClient


async def _ticket(client: AsyncClient, title: str = "Triage me", project_id: int = 2) -> dict:
    response = await client.post(
        "/api/v1/tickets", json={"project_id": project_id, "title": title, "type": "Story"}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _set_role(client: AsyncClient, ticket_id: int, role: str):
    return await client.post(f"/api/v1/tickets/{ticket_id}/triage", json={"role": role})


class TestTriageVocabularyEndpoint:
    """GET /api/v1/triage/roles — the canonical roles and their labels."""

    async def test_the_five_canonical_roles_are_listed(self, client_with_seeds: AsyncClient):
        response = await client_with_seeds.get("/api/v1/triage/roles")
        assert response.status_code == 200
        assert response.json() == [
            {"role": "needs-triage", "label": "triage:needs-triage"},
            {"role": "needs-info", "label": "triage:needs-info"},
            {"role": "ready-for-agent", "label": "triage:ready-for-agent"},
            {"role": "ready-for-human", "label": "triage:ready-for-human"},
            {"role": "wontfix", "label": "triage:wontfix"},
        ]


class TestSetTriageRole:
    """POST /api/v1/tickets/{id}/triage — record the role as a label."""

    async def test_the_role_is_recorded_as_a_label(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)

        response = await _set_role(client_with_seeds, ticket["id"], "ready-for-agent")
        assert response.status_code == 200
        assert response.json()["role"] == "ready-for-agent"

        ticket_payload = (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}")).json()
        assert [label["name"] for label in ticket_payload["labels"]] == ["triage:ready-for-agent"]

    async def test_the_label_is_created_on_demand(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)

        await _set_role(client_with_seeds, ticket["id"], "wontfix")

        labels = (await client_with_seeds.get("/api/v1/labels")).json()
        assert [label["name"] for label in labels] == ["triage:wontfix"]

    async def test_an_unknown_role_is_rejected(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)

        response = await _set_role(client_with_seeds, ticket["id"], "ready-for-nobody")
        assert response.status_code == 422

        labels = (await client_with_seeds.get("/api/v1/labels")).json()
        assert labels == []

    async def test_an_unknown_ticket_is_rejected(self, client_with_seeds: AsyncClient):
        response = await client_with_seeds.post(
            "/api/v1/tickets/999999/triage", json={"role": "ready-for-agent"}
        )
        assert response.status_code == 404

    async def test_setting_a_role_replaces_the_previous_one(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)

        await _set_role(client_with_seeds, ticket["id"], "needs-triage")
        await _set_role(client_with_seeds, ticket["id"], "ready-for-human")

        ticket_payload = (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}")).json()
        assert [label["name"] for label in ticket_payload["labels"]] == ["triage:ready-for-human"]


class TestReadTriageRole:
    """GET /api/v1/tickets/{id}/triage — read the role back."""

    async def test_the_role_reads_back(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)
        await _set_role(client_with_seeds, ticket["id"], "needs-info")

        response = await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/triage")
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "needs-info"
        assert data["label"]["name"] == "triage:needs-info"

    async def test_a_ticket_without_a_role_has_none(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)

        response = await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/triage")
        assert response.status_code == 200
        assert response.json()["role"] is None

    async def test_an_unknown_ticket_is_rejected(self, client_with_seeds: AsyncClient):
        response = await client_with_seeds.get("/api/v1/tickets/999999/triage")
        assert response.status_code == 404


class TestTriageRoleIsVisible:
    """The triage role shows on the ticket page and in the backlog table."""

    async def test_the_ticket_page_shows_the_triage_role(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds)
        await _set_role(client_with_seeds, ticket["id"], "ready-for-agent")

        response = await client_with_seeds.get(f"/tickets/{ticket['id']}/labels")
        assert response.status_code == 200
        assert 'data-triage-role="ready-for-agent"' in response.text

    async def test_the_backlog_table_shows_the_triage_role(self, client_with_seeds: AsyncClient):
        ticket = await _ticket(client_with_seeds, "Backlog triage")
        await _set_role(client_with_seeds, ticket["id"], "needs-info")

        response = await client_with_seeds.get("/backlog")
        assert response.status_code == 200
        assert 'data-triage-role="needs-info"' in response.text

    async def test_a_ticket_without_a_triage_role_shows_none(self, client_with_seeds: AsyncClient):
        await _ticket(client_with_seeds, "No triage")

        response = await client_with_seeds.get("/backlog")
        assert response.status_code == 200
        assert "data-triage-role" not in response.text
