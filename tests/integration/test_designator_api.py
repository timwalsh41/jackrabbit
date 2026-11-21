"""Integration tests for the JRB-038 designator-only API contract.

The project-scoped designator (e.g. ``WEB-001``) is the single public
identifier: every ticket path param accepts it, bare integers are rejected,
and every ticket response self-identifies via ``project_prefix``/``full_id``.
"""

from httpx import AsyncClient


async def _create_ticket(client: AsyncClient, project_id: int = 2, **kwargs) -> dict:
    response = await client.post("/api/v1/tickets", json={"project_id": project_id, **kwargs})
    assert response.status_code == 201, response.text
    return response.json()


class TestTicketResponsesSelfIdentify:
    """Every ticket response carries project_prefix and full_id (JRB-038)."""

    async def test_create_response_carries_project_prefix_and_full_id(
        self, client_with_seeds: AsyncClient
    ) -> None:
        ticket = await _create_ticket(client_with_seeds, title="self identifying")
        assert ticket["project_prefix"] == "WEB"
        assert ticket["full_id"] == "WEB-001"
        assert ticket["id"] is not None

    async def test_list_response_items_carry_full_id(self, client_with_seeds: AsyncClient) -> None:
        first = await _create_ticket(client_with_seeds, title="one")
        second = await _create_ticket(client_with_seeds, project_id=3, title="two")
        response = await client_with_seeds.get("/api/v1/tickets")
        assert response.status_code == 200
        items = {item["id"]: item for item in response.json()["items"]}
        assert items[first["id"]]["full_id"] == first["full_id"]
        assert items[second["id"]]["full_id"] == second["full_id"]

    async def test_detail_response_full_id_matches_number(
        self, client_with_seeds: AsyncClient
    ) -> None:
        ticket = await _create_ticket(client_with_seeds, title="detail")
        response = await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}")
        assert response.status_code == 200
        assert response.json()["project_prefix"] == "WEB"
        assert response.json()["full_id"] == ticket["full_id"]

    async def test_sprint_nested_tickets_carry_full_id(
        self, client_with_seeds: AsyncClient
    ) -> None:
        ticket = await _create_ticket(client_with_seeds, title="sprint member")
        create_sprint = await client_with_seeds.post(
            "/api/v1/sprints", json={"number": 2601, "name": "Sprint 2601"}
        )
        assert create_sprint.status_code == 201, create_sprint.text
        assign = await client_with_seeds.post(
            f"/api/v1/sprints/{create_sprint.json()['id']}/tickets/{ticket['id']}"
        )
        assert assign.status_code == 200, assign.text

        # Sprint addressing by number arrives in its own cycle (JRB-038);
        # this test only covers nested ticket self-identification.
        response = await client_with_seeds.get(f"/api/v1/sprints/{create_sprint.json()['id']}")
        assert response.status_code == 200
        nested = response.json()["tickets"]
        assert nested and all(t["full_id"] for t in nested)
        assert nested[0]["full_id"] == ticket["full_id"]
