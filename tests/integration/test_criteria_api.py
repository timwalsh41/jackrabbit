"""Integration tests for the criteria API: CRUD on /tickets/{id}/criteria and
the criteria list on the Groomed transition payload (JRB-021, ADR-0025)."""

from httpx import AsyncClient


async def _story(client: AsyncClient, title: str = "Criteria ticket", type: str = "Story") -> dict:
    response = await client.post(
        "/api/v1/tickets", json={"project_id": 2, "title": title, "type": type}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _add(client: AsyncClient, ticket_id: int, text: str):
    return await client.post(f"/api/v1/tickets/{ticket_id}/criteria", json={"text": text})


async def _groom(client: AsyncClient, ticket_id: int, **extra):
    payload = {
        "to_status": "Groomed",
        "reason": "ready",
        "approach": "Approach",
        "files_to_change": "files",
        "test_plan": "Plan",
        "validation_steps": "Steps",
    }
    payload.update(extra)
    return await client.post(f"/api/v1/tickets/{ticket_id}/transition", json=payload)


class TestCriteriaCrud:
    """POST/GET/PATCH/DELETE /api/v1/tickets/{id}/criteria while editable."""

    async def test_add_assigns_sequential_positions(self, client_with_seeds: AsyncClient):
        ticket = await _story(client_with_seeds)
        first = await _add(client_with_seeds, ticket["id"], "It works")
        second = await _add(client_with_seeds, ticket["id"], "It is tested")
        assert first.status_code == 201
        assert first.json()["position"] == 0
        assert second.status_code == 201
        assert second.json()["position"] == 1
        assert second.json()["verified"] is False
        assert second.json()["verified_at"] is None

    async def test_add_rejects_blank_text(self, client_with_seeds: AsyncClient):
        ticket = await _story(client_with_seeds)
        response = await _add(client_with_seeds, ticket["id"], "   ")
        assert response.status_code == 422
        assert "Criterion text is required" in response.json()["detail"]

    async def test_list_orders_by_position(self, client_with_seeds: AsyncClient):
        ticket = await _story(client_with_seeds)
        first = (await _add(client_with_seeds, ticket["id"], "It is tested")).json()
        await _add(client_with_seeds, ticket["id"], "It works")
        await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}/criteria/{first['id']}", json={"position": 5}
        )
        response = await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/criteria")
        assert response.status_code == 200
        assert [row["text"] for row in response.json()] == ["It works", "It is tested"]

    async def test_update_text(self, client_with_seeds: AsyncClient):
        ticket = await _story(client_with_seeds)
        row = (await _add(client_with_seeds, ticket["id"], "It works")).json()
        response = await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}/criteria/{row['id']}", json={"text": "Revised"}
        )
        assert response.status_code == 200
        assert response.json()["text"] == "Revised"

    async def test_delete_removes_the_row(self, client_with_seeds: AsyncClient):
        ticket = await _story(client_with_seeds)
        row = (await _add(client_with_seeds, ticket["id"], "It works")).json()
        response = await client_with_seeds.delete(
            f"/api/v1/tickets/{ticket['id']}/criteria/{row['id']}"
        )
        assert response.status_code == 204
        remaining = await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/criteria")
        assert remaining.json() == []

    async def test_unknown_ticket_is_404(self, client_with_seeds: AsyncClient):
        response = await client_with_seeds.get("/api/v1/tickets/9999/criteria")
        assert response.status_code == 404
        post = await _add(client_with_seeds, 9999, "It works")
        assert post.status_code == 404

    async def test_unknown_criterion_is_404(self, client_with_seeds: AsyncClient):
        ticket = await _story(client_with_seeds)
        patch = await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}/criteria/9999", json={"text": "Nope"}
        )
        assert patch.status_code == 404
        delete = await client_with_seeds.delete(f"/api/v1/tickets/{ticket['id']}/criteria/9999")
        assert delete.status_code == 404


class TestCriteriaStatusGate:
    """Criteria are rejected from In Progress onward; allowed on Open/Groomed."""

    async def _in_progress_story(self, client_with_seeds: AsyncClient) -> dict:
        ticket = await _story(client_with_seeds)
        groomed = await _groom(client_with_seeds, ticket["id"], criteria=["It works"])
        assert groomed.status_code == 200, groomed.text
        started = await client_with_seeds.post(
            f"/api/v1/tickets/{ticket['id']}/transition", json={"to_status": "In Progress"}
        )
        assert started.status_code == 200
        return ticket

    async def test_crud_works_on_a_groomed_ticket(self, client_with_seeds: AsyncClient):
        ticket = await _story(client_with_seeds)
        groomed = await _groom(client_with_seeds, ticket["id"], criteria=["First"])
        assert groomed.status_code == 200
        added = await _add(client_with_seeds, ticket["id"], "Second")
        assert added.status_code == 201
        assert added.json()["position"] == 1

    async def test_crud_is_rejected_once_in_progress(self, client_with_seeds: AsyncClient):
        ticket = await self._in_progress_story(client_with_seeds)
        assert (await _add(client_with_seeds, ticket["id"], "Late")).status_code == 409
        rows = (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/criteria")).json()
        locked = await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}/criteria/{rows[0]['id']}", json={"text": "Rewrite"}
        )
        assert locked.status_code == 409
        delete = await client_with_seeds.delete(
            f"/api/v1/tickets/{ticket['id']}/criteria/{rows[0]['id']}"
        )
        assert delete.status_code == 409

    async def test_lock_message_explains_the_round_trip(self, client_with_seeds: AsyncClient):
        ticket = await self._in_progress_story(client_with_seeds)
        response = await _add(client_with_seeds, ticket["id"], "Late")
        assert "Groomed" in response.json()["detail"]


class TestCriteriaTransitionPayload:
    """The Groomed transition accepts a criteria list atomically."""

    async def test_grooming_with_criteria_persists_rows_in_order(
        self, client_with_seeds: AsyncClient
    ):
        ticket = await _story(client_with_seeds)
        response = await _groom(
            client_with_seeds, ticket["id"], criteria=["It works", "It is tested"]
        )
        assert response.status_code == 200
        rows = (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/criteria")).json()
        assert [row["text"] for row in rows] == ["It works", "It is tested"]
        assert [row["position"] for row in rows] == [0, 1]

    async def test_story_grooming_without_criteria_is_rejected(
        self, client_with_seeds: AsyncClient
    ):
        ticket = await _story(client_with_seeds)
        response = await _groom(client_with_seeds, ticket["id"])
        assert response.status_code == 400
        assert "acceptance criterion" in response.json()["detail"]
        assert (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}")).json()[
            "status"
        ] == "Open"

    async def test_epic_grooms_without_criteria(self, client_with_seeds: AsyncClient):
        ticket = await _story(client_with_seeds, "Planning container", type="Epic")
        response = await _groom(client_with_seeds, ticket["id"])
        assert response.status_code == 200

    async def test_spike_grooms_with_no_fields_and_no_criteria(
        self, client_with_seeds: AsyncClient
    ):
        """ADR-0008 relaxation: a Spike needs neither groomed fields nor criteria."""
        ticket = await _story(client_with_seeds, "Research spike", type="Spike")
        response = await client_with_seeds.post(
            f"/api/v1/tickets/{ticket['id']}/transition",
            json={"to_status": "Groomed", "reason": "spike"},
        )
        assert response.status_code == 200
        assert (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}")).json()[
            "status"
        ] == "Groomed"

    async def test_blank_criterion_in_payload_fails_atomically(
        self, client_with_seeds: AsyncClient
    ):
        ticket = await _story(client_with_seeds)
        response = await _groom(client_with_seeds, ticket["id"], criteria=["Good", "   "])
        assert response.status_code == 400
        assert "Criterion text is required" in response.json()["detail"]
        # Nothing persisted: status unchanged, no criteria rows.
        assert (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}")).json()[
            "status"
        ] == "Open"
        criteria = await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/criteria")
        assert criteria.json() == []

    async def test_re_grooming_replaces_the_criteria_list(self, client_with_seeds: AsyncClient):
        ticket = await _story(client_with_seeds)
        assert (await _groom(client_with_seeds, ticket["id"], criteria=["Old"])).status_code == 200
        # Round-trip back to Open, then re-groom with a revised list.
        await client_with_seeds.post(
            f"/api/v1/tickets/{ticket['id']}/transition", json={"to_status": "Open"}
        )
        response = await _groom(client_with_seeds, ticket["id"], criteria=["New one", "New two"])
        assert response.status_code == 200
        rows = (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/criteria")).json()
        assert [row["text"] for row in rows] == ["New one", "New two"]


class TestCriteriaPrecheck:
    """GET /tickets/{id}/transition/can?to_status=Groomed reflects the gate."""

    async def test_story_without_criteria_fails_the_precheck(self, client_with_seeds: AsyncClient):
        ticket = await _story(client_with_seeds)
        patched = await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}",
            json={
                "approach": "Approach",
                "files_to_change": "files",
                "test_plan": "Plan",
                "validation_steps": "Steps",
            },
        )
        assert patched.status_code == 200
        response = await client_with_seeds.get(
            f"/api/v1/tickets/{ticket['id']}/transition/can", params={"to_status": "Groomed"}
        )
        assert response.json()["can_transition"] is False
        assert "acceptance criterion" in response.json()["error_message"]

        # Adding a criterion satisfies the gate.
        await _add(client_with_seeds, ticket["id"], "It works")
        response = await client_with_seeds.get(
            f"/api/v1/tickets/{ticket['id']}/transition/can", params={"to_status": "Groomed"}
        )
        assert response.json()["can_transition"] is True

    async def test_spike_passes_the_precheck_with_nothing(self, client_with_seeds: AsyncClient):
        ticket = await _story(client_with_seeds, "Spike precheck", type="Spike")
        response = await client_with_seeds.get(
            f"/api/v1/tickets/{ticket['id']}/transition/can", params={"to_status": "Groomed"}
        )
        assert response.json()["can_transition"] is True
