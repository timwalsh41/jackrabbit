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
        response = await client_with_seeds.get(f"/api/v1/tickets/{ticket['full_id']}")
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
        # Sprint addressing by number is covered in its own cycle (JRB-038);
        # this test only covers nested ticket self-identification.
        assign = await client_with_seeds.post(
            f"/api/v1/sprints/{create_sprint.json()['id']}/tickets/{ticket['full_id']}"
        )
        assert assign.status_code == 200, assign.text

        # Sprint addressing by number arrives in its own cycle (JRB-038);
        # this test only covers nested ticket self-identification.
        response = await client_with_seeds.get(f"/api/v1/sprints/{create_sprint.json()['id']}")
        assert response.status_code == 200
        nested = response.json()["tickets"]
        assert nested and all(t["full_id"] for t in nested)
        assert nested[0]["full_id"] == ticket["full_id"]


class TestTicketPathParamsAreDesignators:
    """Every ticket path param accepts the designator; bare ints are rejected."""

    async def test_get_ticket_by_designator_returns_the_same_ticket(
        self, client_with_seeds: AsyncClient
    ) -> None:
        ticket = await _create_ticket(client_with_seeds, title="by designator")
        response = await client_with_seeds.get(f"/api/v1/tickets/{ticket['full_id']}")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["id"] == ticket["id"]
        assert body["title"] == ticket["title"]
        assert body["full_id"] == ticket["full_id"]

    async def test_designator_resolution_is_case_insensitive_and_padding_agnostic(
        self, client_with_seeds: AsyncClient
    ) -> None:
        ticket = await _create_ticket(client_with_seeds, title="padding")
        number = ticket["number"]
        for variant in (f"WEB-{number}", f"web-{number}", f"Web-{number:06d}"):
            response = await client_with_seeds.get(f"/api/v1/tickets/{variant}")
            assert response.status_code == 200, (variant, response.text)
            assert response.json()["id"] == ticket["id"]

    async def test_bare_integer_path_param_is_rejected(
        self, client_with_seeds: AsyncClient
    ) -> None:
        await _create_ticket(client_with_seeds, title="no bare ints")
        # The motivating wrong guess: a bare integer (PK 28 read as -028).
        response = await client_with_seeds.get("/api/v1/tickets/28")
        assert response.status_code == 422, response.text
        detail = response.json()["detail"]
        assert "designator" in detail.lower()
        # The designator form is named in the message so the client can retry.
        assert "WEB-028" in detail

    async def test_malformed_designator_is_rejected(self, client_with_seeds: AsyncClient) -> None:
        await _create_ticket(client_with_seeds, title="malformed")
        for variant in ("WEB", "WEB-", "WEB-1x", "-1", "WEB--1"):
            response = await client_with_seeds.get(f"/api/v1/tickets/{variant}")
            assert response.status_code == 422, (variant, response.text)

    async def test_unknown_prefix_or_number_is_404(self, client_with_seeds: AsyncClient) -> None:
        await _create_ticket(client_with_seeds, title="unknown")
        for variant in ("NOPE-1", "WEB-999"):
            response = await client_with_seeds.get(f"/api/v1/tickets/{variant}")
            assert response.status_code == 404, (variant, response.text)
            assert response.json()["detail"] == "Ticket not found"

    async def test_patch_transition_delete_accept_designator(
        self, client_with_seeds: AsyncClient
    ) -> None:
        ticket = await _create_ticket(client_with_seeds, title="lifecycle")
        patched = await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['full_id']}", json={"title": "renamed"}
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["title"] == "renamed"

        transition = await client_with_seeds.post(
            f"/api/v1/tickets/{ticket['full_id']}/transition",
            json={
                "to_status": "Groomed",
                "approach": "resolve via the API",
                "files_to_change": "jackrabbit/api.py",
                "test_plan": "pytest",
                "validation_steps": "pytest",
                "criteria": ["works"],
            },
        )
        assert transition.status_code == 200, transition.text

        deleted = await client_with_seeds.delete(f"/api/v1/tickets/{ticket['full_id']}")
        assert deleted.status_code == 204
        gone = await client_with_seeds.get(f"/api/v1/tickets/{ticket['full_id']}")
        assert gone.status_code == 404

    async def test_label_and_criteria_endpoints_accept_designator(
        self, client_with_seeds: AsyncClient
    ) -> None:
        ticket = await _create_ticket(client_with_seeds, title="subresources")
        designator = ticket["full_id"]
        attached = await client_with_seeds.post(
            f"/api/v1/tickets/{designator}/labels", json={"name": "bug-suspect"}
        )
        assert attached.status_code == 201, attached.text
        listed = await client_with_seeds.get(f"/api/v1/tickets/{designator}/labels")
        assert [label["name"] for label in listed.json()] == ["bug-suspect"]

        added = await client_with_seeds.post(
            f"/api/v1/tickets/{designator}/criteria", json={"text": "works"}
        )
        assert added.status_code == 201, added.text
        criterion_id = added.json()["id"]
        signed = await client_with_seeds.patch(
            f"/api/v1/tickets/{designator}/criteria/{criterion_id}",
            json={"verified": True},
        )
        assert signed.status_code == 409  # sign-off gate: ticket still Open
        removed = await client_with_seeds.delete(
            f"/api/v1/tickets/{designator}/criteria/{criterion_id}"
        )
        assert removed.status_code == 204

    async def test_link_endpoints_accept_designator(self, client_with_seeds: AsyncClient) -> None:
        epic = await _create_ticket(client_with_seeds, title="epic parent", type="Epic")
        story = await _create_ticket(client_with_seeds, title="linked story")
        created = await client_with_seeds.post(
            f"/api/v1/tickets/{story['full_id']}/links",
            json={"target_id": epic["full_id"], "link_type": "child"},
        )
        assert created.status_code == 201, created.text
        links = await client_with_seeds.get(f"/api/v1/tickets/{story['full_id']}/links")
        assert links.status_code == 200
        blockers = await client_with_seeds.get(f"/api/v1/tickets/{story['full_id']}/blockers")
        assert blockers.status_code == 200

    async def test_move_project_and_children_accept_designator(
        self, client_with_seeds: AsyncClient
    ) -> None:
        epic = await _create_ticket(client_with_seeds, title="epic", type="Epic")
        child = await client_with_seeds.post(
            f"/api/v1/tickets/{epic['full_id']}/children",
            json={"project_id": 2, "title": "child story"},
        )
        assert child.status_code == 201, child.text
        assert child.json()["full_id"] == "WEB-002"

        moved = await client_with_seeds.post(
            f"/api/v1/tickets/{child.json()['full_id']}/move-project",
            json={"project_id": 3},
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["new_full_id"] == "API-001"
