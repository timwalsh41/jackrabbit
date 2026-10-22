"""Integration tests for the Tickets API: CRUD, filtering, pagination,
transitions (guarded/unguarded), links, project move, and branch/PR handling."""

import pytest
from httpx import AsyncClient
from jackrabbit.models import Ticket, Transition
from sqlmodel import select


@pytest.fixture
async def two_projects(client_with_seeds: AsyncClient) -> dict:
    """Return ids of the seeded WEB (2) and API (3) projects."""
    return {"web": 2, "api": 3}


async def _create_ticket(
    client: AsyncClient,
    project_id: int,
    title: str,
    **kwargs,
) -> dict:
    payload = {"project_id": project_id, "title": title, **kwargs}
    response = await client.post("/api/v1/tickets", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def _transition(
    client: AsyncClient,
    ticket_id: int,
    to_status: str,
    **kwargs,
):
    payload = {"to_status": to_status, **kwargs}
    return await client.post(f"/api/v1/tickets/{ticket_id}/transition", json=payload)


class TestTicketsCRUD:
    """Ticket create/read/update/delete via the API."""

    async def test_create_ticket_returns_number_and_defaults(
        self, client_with_seeds: AsyncClient, two_projects
    ):
        ticket = await _create_ticket(
            client_with_seeds, two_projects["web"], "Write integration tests", type="Bug"
        )
        assert ticket["project_id"] == two_projects["web"]
        assert ticket["number"] == 1
        assert ticket["status"] == "Open"
        assert ticket["type"] == "Bug"
        assert ticket["priority"] == "Medium"
        assert ticket["original_id"] is None
        assert ticket["branch_name"] is None

    async def test_numbers_are_per_project(self, client_with_seeds: AsyncClient, two_projects):
        t1 = await _create_ticket(client_with_seeds, two_projects["web"], "First")
        t2 = await _create_ticket(client_with_seeds, two_projects["api"], "Second")
        assert t1["number"] == 1
        assert t2["number"] == 1

    async def test_get_ticket_with_details(self, client_with_seeds: AsyncClient, two_projects):
        created = await _create_ticket(client_with_seeds, two_projects["web"], "Detail me")
        response = await client_with_seeds.get(f"/api/v1/tickets/{created['id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Detail me"
        assert data["project_prefix"] == "WEB"
        assert data["links"] == []
        assert data["transitions"] == []

    async def test_get_nonexistent_ticket_returns_404(self, client_with_seeds: AsyncClient):
        response = await client_with_seeds.get("/api/v1/tickets/9999")
        assert response.status_code == 404

    async def test_get_ticket_by_full_id(self, client_with_seeds: AsyncClient, two_projects):
        created = await _create_ticket(client_with_seeds, two_projects["api"], "Full ID me")
        response = await client_with_seeds.get(f"/api/v1/tickets/by-id/API/{created['number']}")
        assert response.status_code == 200
        assert response.json()["id"] == created["id"]

    async def test_get_ticket_by_full_id_unknown_returns_404(self, client_with_seeds: AsyncClient):
        response = await client_with_seeds.get("/api/v1/tickets/by-id/API/999")
        assert response.status_code == 404

    async def test_patch_ticket_updates_fields(self, client_with_seeds: AsyncClient, two_projects):
        created = await _create_ticket(client_with_seeds, two_projects["web"], "Patch me")
        response = await client_with_seeds.patch(
            f"/api/v1/tickets/{created['id']}",
            json={"title": "Patched", "priority": "High", "story_points": 3},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Patched"
        assert data["priority"] == "High"
        assert data["story_points"] == 3
        # Unchanged fields stay
        assert data["project_id"] == two_projects["web"]

    async def test_patch_ticket_with_empty_sprint_id_string(
        self, client_with_seeds: AsyncClient, two_projects
    ):
        """Regression for the edit-form bug: ticket_form.html posts
        sprint_id as "" when 'No Sprint' is selected (<option value="">).
        Without the empty-string -> None validator on sprint_id this 422'd.
        It must PATCH successfully and leave sprint_id null."""
        created = await _create_ticket(client_with_seeds, two_projects["web"], "Sprintless edit")
        assert (await client_with_seeds.get(f"/api/v1/tickets/{created['id']}")).json()[
            "sprint_id"
        ] is None

        response = await client_with_seeds.patch(
            f"/api/v1/tickets/{created['id']}",
            json={"title": "Renamed via edit form", "sprint_id": ""},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["title"] == "Renamed via edit form"
        assert data["sprint_id"] is None
        assert data["status"] == "Open"

    async def test_patch_nonexistent_ticket_returns_404(self, client_with_seeds: AsyncClient):
        response = await client_with_seeds.patch("/api/v1/tickets/9999", json={"title": "nope"})
        assert response.status_code == 404


class TestPatchStatusIsGuarded:
    """PATCH with a `status` field must go through the guarded TransitionService
    (same rules as POST /transition), never the unguarded legacy update_status
    (ADR-0009): every status change writes a Transition audit record."""

    async def test_patch_guarded_status_rejected_400_and_no_change(
        self, client_with_seeds: AsyncClient, two_projects, test_db
    ):
        """Guard failure: Open ticket without a PR cannot be PATCHed to
        Ready for Review; 400, ticket unchanged, NO Transition record."""
        created = await _create_ticket(client_with_seeds, two_projects["web"], "Guard me")
        response = await client_with_seeds.patch(
            f"/api/v1/tickets/{created['id']}",
            json={"status": "Ready for Review"},
        )
        assert response.status_code == 400, response.text
        # The guard order mirrors POST /transition: Open -> Ready for Review is
        # rejected as a status skip (through Groomed).
        assert "Cannot skip statuses" in response.json()["detail"]

        data = (await client_with_seeds.get(f"/api/v1/tickets/{created['id']}")).json()
        assert data["status"] == "Open"
        assert data["transitions"] == []
        rows = list(test_db.exec(select(Transition).where(Transition.ticket_id == created["id"])))
        assert rows == []

    async def test_patch_allowed_status_succeeds_and_writes_transition(
        self, client_with_seeds: AsyncClient, two_projects, test_db
    ):
        """Allowed guarded change: Open + grooming fields -> Groomed with audit."""
        created = await _create_ticket(client_with_seeds, two_projects["web"], "Groom via PATCH")
        response = await client_with_seeds.patch(
            f"/api/v1/tickets/{created['id']}",
            json={
                "status": "Groomed",
                "approach": "Do it carefully",
                "files_to_change": "a.py, b.py",
                "test_plan": "Unit tests",
                "validation_steps": "Visual check",
                "transition_reason": "groomed from edit form",
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "Groomed"

        data = (await client_with_seeds.get(f"/api/v1/tickets/{created['id']}")).json()
        assert data["status"] == "Groomed"
        assert len(data["transitions"]) == 1
        assert data["transitions"][0]["to_status"] == "Groomed"
        assert data["transitions"][0]["reason"] == "groomed from edit form"
        rows = list(test_db.exec(select(Transition).where(Transition.ticket_id == created["id"])))
        assert len(rows) == 1
        assert rows[0].to_status.value == "Groomed"

    async def test_patch_status_sees_latest_ticket_state(
        self, client_with_seeds: AsyncClient, two_projects, test_db
    ):
        """The guarded transition evaluates the ticket's CURRENT persisted state
        (PR URL set on the record), and a PATCHed status change succeeds when
        the criteria are already met."""
        created = await _create_ticket(
            client_with_seeds,
            two_projects["api"],
            "Patch+PR",
            approach="x",
            files_to_change="x",
            test_plan="x",
            validation_steps="x",
        )
        r1 = await _transition(client_with_seeds, created["id"], "Groomed", reason="groom")
        assert r1.status_code == 200, r1.text
        r2 = await _transition(client_with_seeds, created["id"], "In Progress", reason="start")
        assert r2.status_code == 200, r2.text
        # Set the PR on the record (pr_url is not a PATCH-able field; the
        # Ready-for-Review modal provides it at transition time).
        ticket = test_db.get(Ticket, created["id"])
        ticket.pr_url = "https://github.com/o/r/pull/9"
        test_db.add(ticket)
        test_db.commit()
        response = await client_with_seeds.patch(
            f"/api/v1/tickets/{created['id']}",
            json={"status": "Ready for Review"},
        )
        assert response.status_code == 200, response.text
        data = (await client_with_seeds.get(f"/api/v1/tickets/{created['id']}")).json()
        assert data["status"] == "Ready for Review"
        assert data["pr_url"] == "https://github.com/o/r/pull/9"

    async def test_patch_same_status_is_noop_without_transition(
        self, client_with_seeds: AsyncClient, two_projects, test_db
    ):
        created = await _create_ticket(client_with_seeds, two_projects["web"], "Noop status")
        response = await client_with_seeds.patch(
            f"/api/v1/tickets/{created['id']}", json={"status": "Open"}
        )
        assert response.status_code == 200
        rows = list(test_db.exec(select(Transition).where(Transition.ticket_id == created["id"])))
        assert rows == []

    async def test_patch_backward_status_allowed_with_transition(
        self, client_with_seeds: AsyncClient, two_projects, test_db
    ):
        """Free backward: Groomed -> Open via PATCH writes an audit record."""
        created = await _create_ticket(
            client_with_seeds,
            two_projects["web"],
            "Backward",
            approach="x",
            files_to_change="x",
            test_plan="x",
            validation_steps="x",
        )
        r1 = await _transition(client_with_seeds, created["id"], "Groomed", reason="groom")
        assert r1.status_code == 200, r1.text
        response = await client_with_seeds.patch(
            f"/api/v1/tickets/{created['id']}", json={"status": "Open"}
        )
        assert response.status_code == 200
        data = (await client_with_seeds.get(f"/api/v1/tickets/{created['id']}")).json()
        assert data["status"] == "Open"
        transitions = [t["to_status"] for t in data["transitions"]]
        assert transitions == ["Groomed", "Open"]

    async def test_patch_forward_skip_rejected_400(
        self, client_with_seeds: AsyncClient, two_projects
    ):
        created = await _create_ticket(client_with_seeds, two_projects["web"], "Skip")
        response = await client_with_seeds.patch(
            f"/api/v1/tickets/{created['id']}",
            json={
                "status": "In Progress",
                "approach": "x",
                "files_to_change": "x",
                "test_plan": "x",
                "validation_steps": "x",
            },
        )
        assert response.status_code == 400
        assert "skip statuses" in response.json()["detail"]

    async def test_patch_status_htmx_guard_error_returns_400(
        self, client_with_seeds: AsyncClient, two_projects
    ):
        """HTMX edit form submissions get the 400 (form surfaces detail via JS)."""
        created = await _create_ticket(client_with_seeds, two_projects["web"], "HTMX guard")
        response = await client_with_seeds.patch(
            f"/api/v1/tickets/{created['id']}",
            content='{"status": "Ready for Review"}',
            headers={"Content-Type": "application/json", "HX-Request": "true"},
        )
        assert response.status_code == 400
        assert "Cannot skip statuses" in response.json()["detail"]

    async def test_patch_ready_for_review_without_pr_succeeds(
        self, client_with_seeds: AsyncClient, two_projects
    ):
        """The PR URL is optional: In Progress -> Ready for Review succeeds
        via PATCH with no PR URL set (guard no longer gates on it)."""
        created = await _create_ticket(
            client_with_seeds,
            two_projects["web"],
            "No PR yet",
            approach="x",
            files_to_change="x",
            test_plan="x",
            validation_steps="x",
        )
        await _transition(client_with_seeds, created["id"], "Groomed", reason="groom")
        await _transition(client_with_seeds, created["id"], "In Progress", reason="start")
        response = await client_with_seeds.patch(
            f"/api/v1/tickets/{created['id']}", json={"status": "Ready for Review"}
        )
        assert response.status_code == 200, response.text
        data = (await client_with_seeds.get(f"/api/v1/tickets/{created['id']}")).json()
        assert data["status"] == "Ready for Review"

    async def test_patch_to_rejected_then_restore(
        self, client_with_seeds: AsyncClient, two_projects
    ):
        """Reject/restore semantics through PATCH."""
        created = await _create_ticket(client_with_seeds, two_projects["web"], "Rejectable")
        response = await client_with_seeds.patch(
            f"/api/v1/tickets/{created['id']}", json={"status": "Rejected"}
        )
        assert response.status_code == 200
        assert (await client_with_seeds.get(f"/api/v1/tickets/{created['id']}")).json()[
            "status"
        ] == "Rejected"
        response = await client_with_seeds.patch(
            f"/api/v1/tickets/{created['id']}", json={"status": "Open"}
        )
        assert response.status_code == 200
        data = (await client_with_seeds.get(f"/api/v1/tickets/{created['id']}")).json()
        assert data["status"] == "Open"
        assert [t["to_status"] for t in data["transitions"]] == ["Rejected", "Open"]

    async def test_delete_ticket(self, client_with_seeds: AsyncClient, two_projects):
        created = await _create_ticket(client_with_seeds, two_projects["web"], "Delete me")
        response = await client_with_seeds.delete(f"/api/v1/tickets/{created['id']}")
        assert response.status_code == 204
        response = await client_with_seeds.get(f"/api/v1/tickets/{created['id']}")
        assert response.status_code == 404

    async def test_delete_nonexistent_ticket_returns_404(self, client_with_seeds: AsyncClient):
        response = await client_with_seeds.delete("/api/v1/tickets/9999")
        assert response.status_code == 404


class TestTicketsFiltering:
    """GET /api/v1/tickets filter parameters."""

    async def _seed(self, client: AsyncClient):
        """Seed: 2 tickets in WEB, 1 story+1 bug in API, statuses/types varied."""
        web, api = 2, 3
        groomed = await _create_ticket(
            client,
            web,
            "Groomed story",
            type="Story",
            approach="a",
            files_to_change="f",
            test_plan="t",
            validation_steps="v",
        )
        await _transition(client, groomed["id"], "Groomed", reason="groomed")
        await _create_ticket(client, web, "Open bug", type="Bug")
        await _create_ticket(client, api, "API story", type="Story")
        in_progress = await _create_ticket(
            client,
            api,
            "API bug in progress",
            type="Bug",
            approach="a",
            files_to_change="f",
            test_plan="t",
            validation_steps="v",
        )
        await _transition(client, in_progress["id"], "Groomed", reason="g")
        await _transition(client, in_progress["id"], "In Progress", reason="w")

    async def test_filter_by_project(self, client_with_seeds: AsyncClient):
        await self._seed(client_with_seeds)
        response = await client_with_seeds.get("/api/v1/tickets", params={"project_id": 2})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert all(item["project_id"] == 2 for item in data["items"])

    async def test_filter_by_status(self, client_with_seeds: AsyncClient):
        await self._seed(client_with_seeds)
        response = await client_with_seeds.get("/api/v1/tickets", params={"status": "In Progress"})
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "API bug in progress"

    async def test_filter_by_type(self, client_with_seeds: AsyncClient):
        await self._seed(client_with_seeds)
        response = await client_with_seeds.get("/api/v1/tickets", params={"type": "Bug"})
        data = response.json()
        assert data["total"] == 2
        assert all(item["type"] == "Bug" for item in data["items"])

    async def test_filter_by_search_q(self, client_with_seeds: AsyncClient):
        await self._seed(client_with_seeds)
        response = await client_with_seeds.get("/api/v1/tickets", params={"q": "API"})
        data = response.json()
        assert data["total"] == 2
        assert all("API" in item["title"] for item in data["items"])

    async def test_filter_by_sprint_id(self, client_with_seeds: AsyncClient):
        await self._seed(client_with_seeds)
        await client_with_seeds.post("/api/v1/sprints", json={"number": 2601, "name": "S"})
        sprint_id = (await client_with_seeds.get("/api/v1/sprints")).json()[0]["id"]
        # Assign the first listed ticket to the sprint
        tickets = (await client_with_seeds.get("/api/v1/tickets")).json()["items"]
        ticket_id = tickets[0]["id"]
        response = await client_with_seeds.post(f"/api/v1/sprints/{sprint_id}/tickets/{ticket_id}")
        assert response.status_code == 200

        listed = await client_with_seeds.get("/api/v1/tickets", params={"sprint_id": sprint_id})
        data = listed.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == ticket_id

    async def test_filter_sprint_id_zero_returns_unsprinted(self, client_with_seeds: AsyncClient):
        await self._seed(client_with_seeds)
        response = await client_with_seeds.get("/api/v1/tickets", params={"sprint_id": 0})
        data = response.json()
        assert data["total"] == 4  # nothing assigned yet
        assert all(item["sprint_id"] is None for item in data["items"])


class TestTicketsPagination:
    """GET /api/v1/tickets pagination and sorting."""

    async def _seed(self, client: AsyncClient):
        for i in range(5):
            await _create_ticket(client, 2, f"Ticket {i:02d}")

    async def test_pagination_pages(self, client_with_seeds: AsyncClient):
        await self._seed(client_with_seeds)
        response = await client_with_seeds.get(
            "/api/v1/tickets", params={"page": 1, "page_size": 2, "order": "asc"}
        )
        data = response.json()
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert data["total_pages"] == 3
        assert [item["title"] for item in data["items"]] == ["Ticket 00", "Ticket 01"]

        response = await client_with_seeds.get(
            "/api/v1/tickets", params={"page": 3, "page_size": 2, "order": "asc"}
        )
        data = response.json()
        assert [item["title"] for item in data["items"]] == ["Ticket 04"]

    async def test_page_beyond_total_returns_empty(self, client_with_seeds: AsyncClient):
        await self._seed(client_with_seeds)
        response = await client_with_seeds.get(
            "/api/v1/tickets", params={"page": 9, "page_size": 2}
        )
        data = response.json()
        assert data["total"] == 5
        assert data["items"] == []

    async def test_default_order_is_number_desc(self, client_with_seeds: AsyncClient):
        await self._seed(client_with_seeds)
        data = (await client_with_seeds.get("/api/v1/tickets")).json()
        numbers = [item["number"] for item in data["items"]]
        assert numbers == sorted(numbers, reverse=True)

    async def test_sort_by_title_asc(self, client_with_seeds: AsyncClient):
        await self._seed(client_with_seeds)
        data = (
            await client_with_seeds.get("/api/v1/tickets", params={"sort": "title", "order": "asc"})
        ).json()
        titles = [item["title"] for item in data["items"]]
        assert titles == sorted(titles)

    async def test_page_size_validation(self, client_with_seeds: AsyncClient):
        response = await client_with_seeds.get("/api/v1/tickets", params={"page": 0})
        assert response.status_code == 422
        response = await client_with_seeds.get("/api/v1/tickets", params={"page_size": 101})
        assert response.status_code == 422


class TestTicketsTransitions:
    """Transition endpoints: guarded and unguarded."""

    async def _groomable_ticket(self, client: AsyncClient, project_id: int = 2) -> dict:
        return await _create_ticket(
            client,
            project_id,
            "Transition me",
            approach="Do it",
            files_to_change="api.py",
            test_plan="pytest",
            validation_steps="manual",
        )

    async def test_can_transition_endpoint_guarded_and_unguarded(
        self, client_with_seeds: AsyncClient
    ):
        plain = await _create_ticket(client_with_seeds, 2, "Plain")
        groomable = await self._groomable_ticket(client_with_seeds)

        # Guarded: Open -> Groomed without fields is blocked
        blocked = await client_with_seeds.get(
            f"/api/v1/tickets/{plain['id']}/transition/can",
            params={"to_status": "Groomed"},
        )
        assert blocked.status_code == 200
        assert blocked.json()["can_transition"] is False
        assert "Approach is required" in blocked.json()["error_message"]

        # Unguarded: Open -> Rejected is always allowed
        allowed = await client_with_seeds.get(
            f"/api/v1/tickets/{groomable['id']}/transition/can",
            params={"to_status": "Rejected"},
        )
        assert allowed.json()["can_transition"] is True
        assert allowed.json()["error_message"] is None

    async def test_can_transition_nonexistent_ticket_returns_404(
        self, client_with_seeds: AsyncClient
    ):
        response = await client_with_seeds.get(
            "/api/v1/tickets/9999/transition/can", params={"to_status": "Groomed"}
        )
        assert response.status_code == 404

    async def test_guarded_transition_rejected_with_400(self, client_with_seeds: AsyncClient):
        ticket = await _create_ticket(client_with_seeds, 2, "No fields")
        response = await _transition(
            client_with_seeds, ticket["id"], "Groomed", reason="missing fields"
        )
        assert response.status_code == 400
        assert "Approach is required" in response.json()["detail"]
        # Status unchanged
        check = await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}")
        assert check.json()["status"] == "Open"

    async def test_full_lifecycle_with_branch_and_pr(self, client_with_seeds: AsyncClient):
        ticket = await self._groomable_ticket(client_with_seeds)
        ticket_id = ticket["id"]

        # Open -> Groomed
        response = await _transition(client_with_seeds, ticket_id, "Groomed", reason="groomed")
        assert response.status_code == 200
        body = response.json()
        assert body["from_status"] == "Open"
        assert body["to_status"] == "Groomed"
        assert body["full_id"] == "WEB-001"

        # Groomed -> In Progress auto-generates a branch name
        response = await _transition(client_with_seeds, ticket_id, "In Progress", reason="wip")
        assert response.status_code == 200
        data = (await client_with_seeds.get(f"/api/v1/tickets/{ticket_id}")).json()
        assert data["branch_name"] is not None
        assert data["branch_name"].endswith("-transition-me")

        # In Progress -> Ready for Review requires a PR URL (provided in request)
        response = await _transition(
            client_with_seeds,
            ticket_id,
            "Ready for Review",
            pr_url="https://github.com/test/repo/pull/42",
            reason="pr opened",
        )
        assert response.status_code == 200
        data = (await client_with_seeds.get(f"/api/v1/tickets/{ticket_id}")).json()
        assert data["pr_url"] == "https://github.com/test/repo/pull/42"

        # Ready for Review -> Complete (unguarded)
        response = await _transition(client_with_seeds, ticket_id, "Complete", reason="done")
        assert response.status_code == 200
        data = (await client_with_seeds.get(f"/api/v1/tickets/{ticket_id}")).json()
        assert data["status"] == "Complete"
        assert data["completed_at"] is not None

        # Transition audit trail is exposed on the detail endpoint
        transitions = data["transitions"]
        assert len(transitions) == 4

    async def test_backward_transition_allowed(self, client_with_seeds: AsyncClient):
        ticket = await self._groomable_ticket(client_with_seeds)
        await _transition(client_with_seeds, ticket["id"], "Groomed", reason="g")
        response = await _transition(client_with_seeds, ticket["id"], "Open", reason="back to open")
        assert response.status_code == 200
        data = (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}")).json()
        assert data["status"] == "Open"

    async def test_skip_transition_rejected(self, client_with_seeds: AsyncClient):
        ticket = await self._groomable_ticket(client_with_seeds)
        response = await _transition(client_with_seeds, ticket["id"], "In Progress")
        assert response.status_code == 400

    async def test_transition_nonexistent_ticket_returns_404(self, client_with_seeds: AsyncClient):
        response = await _transition(client_with_seeds, 9999, "Groomed")
        assert response.status_code == 404


class TestTicketsLinks:
    """Links are reachable through the ticket detail endpoint."""

    async def test_ticket_details_include_links(self, client_with_seeds: AsyncClient):
        t1 = await _create_ticket(client_with_seeds, 2, "Source")
        t2 = await _create_ticket(client_with_seeds, 2, "Target")
        response = await client_with_seeds.post(
            f"/api/v1/tickets/{t1['id']}/links",
            json={"source_id": t1["id"], "target_id": t2["id"], "link_type": "blocks"},
        )
        assert response.status_code == 201

        data = (await client_with_seeds.get(f"/api/v1/tickets/{t1['id']}")).json()
        assert len(data["links"]) == 2  # forward + inverse
        link_types = {link["link_type"] for link in data["links"]}
        assert link_types == {"blocks", "blocked_by"}


class TestTicketsProjectMove:
    """POST /api/v1/tickets/{id}/move-project."""

    async def test_move_renumbers_and_sets_original_id(self, client_with_seeds: AsyncClient):
        await _create_ticket(client_with_seeds, 2, "existing web ticket")
        moved = await _create_ticket(client_with_seeds, 3, "mover")
        response = await client_with_seeds.post(
            f"/api/v1/tickets/{moved['id']}/move-project", json={"project_id": 2}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["old_full_id"] == "API-001"
        assert data["new_full_id"] == "WEB-002"
        assert data["original_id"] == "API-001"

        check = await client_with_seeds.get(f"/api/v1/tickets/{moved['id']}")
        assert check.json()["number"] == 2
        assert check.json()["project_id"] == 2
        assert check.json()["original_id"] == "API-001"

    async def test_move_to_same_project_returns_400(self, client_with_seeds: AsyncClient):
        ticket = await _create_ticket(client_with_seeds, 2, "stay put")
        response = await client_with_seeds.post(
            f"/api/v1/tickets/{ticket['id']}/move-project", json={"project_id": 2}
        )
        assert response.status_code == 400
        assert "already in this project" in response.json()["detail"]

    async def test_move_missing_project_id_returns_400(self, client_with_seeds: AsyncClient):
        ticket = await _create_ticket(client_with_seeds, 2, "no target")
        response = await client_with_seeds.post(
            f"/api/v1/tickets/{ticket['id']}/move-project", json={}
        )
        assert response.status_code == 400

    async def test_move_nonexistent_ticket_returns_404(self, client_with_seeds: AsyncClient):
        response = await client_with_seeds.post(
            "/api/v1/tickets/9999/move-project", json={"project_id": 2}
        )
        assert response.status_code == 404

    async def test_move_nonexistent_project_returns_400(self, client_with_seeds: AsyncClient):
        ticket = await _create_ticket(client_with_seeds, 2, "nowhere")
        response = await client_with_seeds.post(
            f"/api/v1/tickets/{ticket['id']}/move-project", json={"project_id": 999}
        )
        assert response.status_code == 400
