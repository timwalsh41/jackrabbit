"""Integration tests for the Ticket Links API: all five link types, inverses,
symmetric relates_to, delete with inverse cleanup, and blocker queries."""

import pytest
from httpx import AsyncClient


async def _ticket(
    client: AsyncClient, title: str, project_id: int = 2, type_: str = "Story"
) -> dict:
    response = await client.post(
        "/api/v1/tickets", json={"project_id": project_id, "title": title, "type": type_}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _link(client: AsyncClient, source_id: int, target_id: int, link_type: str):
    return await client.post(
        f"/api/v1/tickets/{source_id}/links",
        json={"source_id": source_id, "target_id": target_id, "link_type": link_type},
    )


async def _links_of(client: AsyncClient, ticket_id: int) -> set[tuple[str, int, int]]:
    """Set of (link_type, source_id, target_id) visible from a ticket."""
    response = await client.get(f"/api/v1/tickets/{ticket_id}/links")
    assert response.status_code == 200
    return {(link["link_type"], link["source_id"], link["target_id"]) for link in response.json()}


@pytest.fixture
async def tickets(client_with_seeds: AsyncClient) -> dict:
    """Three tickets in WEB: an epic, a story, and a bug."""
    return {
        "epic": await _ticket(client_with_seeds, "Epic A", type_="Epic"),
        "story": await _ticket(client_with_seeds, "Story B"),
        "bug": await _ticket(client_with_seeds, "Bug C", type_="Bug"),
    }


class TestCreateAllLinkTypes:
    """POST /api/v1/tickets/{id}/links for each of the five types."""

    async def test_parent_child_with_inverse(self, client_with_seeds: AsyncClient, tickets):
        # parent: source must be an Epic (the epic is the parent of the story)
        response = await _link(
            client_with_seeds, tickets["epic"]["id"], tickets["story"]["id"], "parent"
        )
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["source_id"] == tickets["epic"]["id"]
        assert data["target_id"] == tickets["story"]["id"]
        assert data["link_type"] == "parent"

        visible = await _links_of(client_with_seeds, tickets["story"]["id"])
        assert ("parent", tickets["epic"]["id"], tickets["story"]["id"]) in visible
        assert ("child", tickets["story"]["id"], tickets["epic"]["id"]) in visible

    async def test_child_with_inverse(self, client_with_seeds: AsyncClient, tickets):
        response = await _link(
            client_with_seeds, tickets["story"]["id"], tickets["epic"]["id"], "child"
        )
        assert response.status_code == 201
        visible = await _links_of(client_with_seeds, tickets["story"]["id"])
        assert ("child", tickets["story"]["id"], tickets["epic"]["id"]) in visible
        assert ("parent", tickets["epic"]["id"], tickets["story"]["id"]) in visible

    async def test_blocks_with_inverse(self, client_with_seeds: AsyncClient, tickets):
        response = await _link(
            client_with_seeds, tickets["bug"]["id"], tickets["story"]["id"], "blocks"
        )
        assert response.status_code == 201
        visible = await _links_of(client_with_seeds, tickets["bug"]["id"])
        assert ("blocks", tickets["bug"]["id"], tickets["story"]["id"]) in visible
        assert ("blocked_by", tickets["story"]["id"], tickets["bug"]["id"]) in visible

    async def test_blocked_by_with_inverse(self, client_with_seeds: AsyncClient, tickets):
        response = await _link(
            client_with_seeds, tickets["story"]["id"], tickets["bug"]["id"], "blocked_by"
        )
        assert response.status_code == 201
        visible = await _links_of(client_with_seeds, tickets["story"]["id"])
        assert ("blocked_by", tickets["story"]["id"], tickets["bug"]["id"]) in visible
        assert ("blocks", tickets["bug"]["id"], tickets["story"]["id"]) in visible

    async def test_relates_to_is_symmetric(self, client_with_seeds: AsyncClient, tickets):
        response = await _link(
            client_with_seeds, tickets["story"]["id"], tickets["bug"]["id"], "relates_to"
        )
        assert response.status_code == 201
        data = response.json()
        assert data["link_type"] == "relates_to"

        # Symmetric: both directions visible
        from_story = await _links_of(client_with_seeds, tickets["story"]["id"])
        from_bug = await _links_of(client_with_seeds, tickets["bug"]["id"])
        assert ("relates_to", tickets["story"]["id"], tickets["bug"]["id"]) in from_story
        assert ("relates_to", tickets["bug"]["id"], tickets["story"]["id"]) in from_bug

    async def test_duplicate_link_is_idempotent(self, client_with_seeds: AsyncClient, tickets):
        first = await _link(
            client_with_seeds, tickets["story"]["id"], tickets["bug"]["id"], "relates_to"
        )
        second = await _link(
            client_with_seeds, tickets["story"]["id"], tickets["bug"]["id"], "relates_to"
        )
        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["id"] == second.json()["id"]

        visible = await _links_of(client_with_seeds, tickets["story"]["id"])
        assert len([lnk for lnk in visible if lnk[0] == "relates_to"]) == 2  # both directions

    async def test_self_link_rejected(self, client_with_seeds: AsyncClient, tickets):
        response = await _link(
            client_with_seeds, tickets["story"]["id"], tickets["story"]["id"], "relates_to"
        )
        assert response.status_code == 400
        assert "itself" in response.json()["detail"]

    async def test_parent_requires_epic_source(self, client_with_seeds: AsyncClient, tickets):
        response = await _link(
            client_with_seeds, tickets["story"]["id"], tickets["bug"]["id"], "parent"
        )
        assert response.status_code == 400
        assert "Epic" in response.json()["detail"]

    async def test_child_requires_epic_target(self, client_with_seeds: AsyncClient, tickets):
        response = await _link(
            client_with_seeds, tickets["story"]["id"], tickets["bug"]["id"], "child"
        )
        assert response.status_code == 400
        assert "Epic" in response.json()["detail"]

    async def test_nonexistent_source_returns_404(self, client_with_seeds: AsyncClient, tickets):
        response = await client_with_seeds.post(
            "/api/v1/tickets/9999/links",
            json={
                "source_id": 9999,
                "target_id": tickets["story"]["id"],
                "link_type": "relates_to",
            },
        )
        assert response.status_code == 404

    async def test_nonexistent_target_returns_404(self, client_with_seeds: AsyncClient, tickets):
        response = await _link(client_with_seeds, tickets["story"]["id"], 9999, "relates_to")
        assert response.status_code == 404


class TestDeleteLinks:
    """DELETE /api/v1/tickets/{source_id}/links/{link_id}."""

    async def test_delete_removes_inverse_too(self, client_with_seeds: AsyncClient, tickets):
        link = (
            await _link(client_with_seeds, tickets["epic"]["id"], tickets["story"]["id"], "parent")
        ).json()
        response = await client_with_seeds.delete(
            f"/api/v1/tickets/{tickets['story']['id']}/links/{link['id']}"
        )
        assert response.status_code == 204
        visible = await _links_of(client_with_seeds, tickets["story"]["id"])
        assert visible == set()

    async def test_delete_relates_to_removes_both_directions(
        self, client_with_seeds: AsyncClient, tickets
    ):
        link = (
            await _link(
                client_with_seeds, tickets["story"]["id"], tickets["bug"]["id"], "relates_to"
            )
        ).json()
        response = await client_with_seeds.delete(
            f"/api/v1/tickets/{tickets['bug']['id']}/links/{link['id']}"
        )
        assert response.status_code == 204
        assert await _links_of(client_with_seeds, tickets["story"]["id"]) == set()
        assert await _links_of(client_with_seeds, tickets["bug"]["id"]) == set()

    async def test_delete_via_either_side(self, client_with_seeds: AsyncClient, tickets):
        """The link belongs to both endpoints: deleting via the inverse side works."""
        link = (
            await _link(client_with_seeds, tickets["epic"]["id"], tickets["story"]["id"], "parent")
        ).json()
        # Delete via the story (the inverse link's source)
        response = await client_with_seeds.delete(
            f"/api/v1/tickets/{tickets['story']['id']}/links/{link['id']}"
        )
        assert response.status_code == 204
        assert await _links_of(client_with_seeds, tickets["story"]["id"]) == set()

    async def test_delete_link_of_other_ticket_returns_404(
        self, client_with_seeds: AsyncClient, tickets
    ):
        """A link not touching the given ticket is not found from that ticket."""
        link = (
            await _link(client_with_seeds, tickets["epic"]["id"], tickets["story"]["id"], "parent")
        ).json()
        response = await client_with_seeds.delete(
            f"/api/v1/tickets/{tickets['bug']['id']}/links/{link['id']}"
        )
        assert response.status_code == 404

    async def test_delete_nonexistent_link_returns_404(
        self, client_with_seeds: AsyncClient, tickets
    ):
        response = await client_with_seeds.delete(
            f"/api/v1/tickets/{tickets['story']['id']}/links/9999"
        )
        assert response.status_code == 404

    async def test_delete_nonexistent_ticket_returns_404(self, client_with_seeds: AsyncClient):
        response = await client_with_seeds.delete("/api/v1/tickets/9999/links/1")
        assert response.status_code == 404


class TestBlockerQueries:
    """GET /api/v1/tickets/{id}/blockers and /blocked."""

    async def test_blockers_and_blocked(self, client_with_seeds: AsyncClient, tickets):
        # bug blocks story
        await _link(client_with_seeds, tickets["bug"]["id"], tickets["story"]["id"], "blocks")

        blockers = await client_with_seeds.get(f"/api/v1/tickets/{tickets['story']['id']}/blockers")
        assert blockers.status_code == 200
        data = blockers.json()
        assert len(data) == 1
        assert data[0]["source_id"] == tickets["bug"]["id"]
        assert data[0]["target_id"] == tickets["story"]["id"]
        assert data[0]["link_type"] == "blocks"

        blocked = await client_with_seeds.get(f"/api/v1/tickets/{tickets['bug']['id']}/blocked")
        assert blocked.status_code == 200
        data = blocked.json()
        assert len(data) == 1
        assert data[0]["source_id"] == tickets["bug"]["id"]

    async def test_no_blockers_returns_empty(self, client_with_seeds: AsyncClient, tickets):
        response = await client_with_seeds.get(f"/api/v1/tickets/{tickets['story']['id']}/blockers")
        assert response.status_code == 200
        assert response.json() == []

    async def test_relates_to_does_not_count_as_blocker(
        self, client_with_seeds: AsyncClient, tickets
    ):
        await _link(client_with_seeds, tickets["story"]["id"], tickets["bug"]["id"], "relates_to")
        response = await client_with_seeds.get(f"/api/v1/tickets/{tickets['story']['id']}/blockers")
        assert response.json() == []


async def test_create_link_htmx_returns_links_section(
    client_with_seeds: AsyncClient,
) -> None:
    """HTMX create-link requests swap the refreshed links section in place."""
    epic = (
        await client_with_seeds.post(
            "/api/v1/tickets", json={"project_id": 2, "title": "Epic X", "type": "Epic"}
        )
    ).json()
    story = (
        await client_with_seeds.post(
            "/api/v1/tickets", json={"project_id": 2, "title": "Story X", "type": "Story"}
        )
    ).json()

    response = await client_with_seeds.post(
        f"/api/v1/tickets/{epic['id']}/links",
        json={
            "source_id": epic["id"],
            "target_id": story["id"],
            "link_type": "parent",
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'id="links-section"' in response.text
    assert "Children (Stories/Bugs/Spikes)" in response.text
    # The inverse child link (targeted at the epic) is what the epic page shows;
    # the row must reference the CHILD ticket, not the epic itself.
    assert "Story X" in response.text
    assert 'title="Story X"' in response.text
    assert 'title="Epic X"' not in response.text
