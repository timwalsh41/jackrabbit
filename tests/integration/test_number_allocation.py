"""Integration tests for JRB-037 stable ticket numbers at the API level.

Ticket numbers come from a monotone per-project counter: deleting the
highest-numbered ticket and creating a new one never reissues the number,
and each project allocates independently. The move-project endpoint
allocates from the target project's counter.
"""

from httpx import AsyncClient
from jackrabbit.models import Ticket
from sqlmodel import select


async def test_create_delete_create_does_not_reissue_number(
    client_with_seeds: AsyncClient,
) -> None:
    """Deleting the highest-numbered ticket never frees its number."""
    created = []
    for i in range(3):
        response = await client_with_seeds.post(
            "/api/v1/tickets", json={"project_id": 2, "title": f"web {i}"}
        )
        assert response.status_code == 201, response.text
        created.append(response.json())

    assert [t["number"] for t in created] == [1, 2, 3]

    # Delete the highest-numbered ticket (WEB-3).
    delete = await client_with_seeds.delete(f"/api/v1/tickets/{created[-1]['full_id']}")
    assert delete.status_code == 204

    response = await client_with_seeds.post(
        "/api/v1/tickets", json={"project_id": 2, "title": "web four"}
    )
    assert response.status_code == 201, response.text
    # WEB-3 was deleted but is never reissued.
    assert response.json()["number"] == 4


async def test_counters_are_independent_per_project(client_with_seeds: AsyncClient) -> None:
    """Each project allocates from its own counter."""
    response = await client_with_seeds.post(
        "/api/v1/tickets", json={"project_id": 2, "title": "web one"}
    )
    assert response.json()["number"] == 1
    response = await client_with_seeds.post(
        "/api/v1/tickets", json={"project_id": 3, "title": "api one"}
    )
    assert response.json()["number"] == 1
    response = await client_with_seeds.post(
        "/api/v1/tickets", json={"project_id": 2, "title": "web two"}
    )
    assert response.json()["number"] == 2


async def test_move_project_uses_target_project_counter(
    client_with_seeds: AsyncClient, test_db
) -> None:
    """move-project allocates from the target project's counter and records
    original_id/old_full_id/new_full_id."""
    for i in range(2):
        response = await client_with_seeds.post(
            "/api/v1/tickets", json={"project_id": 2, "title": f"web {i}"}
        )
        assert response.status_code == 201, response.text
    mover = await client_with_seeds.post(
        "/api/v1/tickets", json={"project_id": 3, "title": "mover"}
    )
    response = await client_with_seeds.post(
        f"/api/v1/tickets/{mover.json()['full_id']}/move-project", json={"project_id": 2}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["old_full_id"] == "API-001"
    assert body["new_full_id"] == "WEB-003"
    assert body["original_id"] == "API-001"

    ticket = test_db.exec(select(Ticket).where(Ticket.number == 3)).one()
    assert (ticket.project_id, ticket.number) == (2, 3)
