"""General smoke tests for the Jackrabbit JSON API.

Detailed endpoint coverage lives in the per-resource files:
test_projects_api.py, test_tickets_api.py, test_sprints_api.py,
test_links_api.py, and test_migrations.py.
"""

from httpx import AsyncClient


async def test_health_endpoint(client: AsyncClient) -> None:
    """Test health endpoint."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_create_ticket(client_with_seeds: AsyncClient) -> None:
    """Test creating a ticket via API."""
    # UNS project already exists with ID 1
    response = await client_with_seeds.post(
        "/api/v1/tickets",
        json={"project_id": 1, "title": "Test ticket", "type": "Bug", "priority": "High"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test ticket"
    assert data["type"] == "Bug"
    assert data["priority"] == "High"
    assert data["number"] == 1


async def test_list_tickets(client_with_seeds: AsyncClient) -> None:
    """Test listing tickets via API."""
    await client_with_seeds.post("/api/v1/tickets", json={"project_id": 1, "title": "Ticket 1"})
    await client_with_seeds.post("/api/v1/tickets", json={"project_id": 1, "title": "Ticket 2"})

    response = await client_with_seeds.get("/api/v1/tickets")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


async def test_create_sprint(client_with_seeds: AsyncClient) -> None:
    """Test creating a sprint via API."""
    response = await client_with_seeds.post(
        "/api/v1/sprints",
        json={"number": 2601, "name": "Sprint 1"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["number"] == 2601
    assert data["name"] == "Sprint 1"


async def test_create_link(client_with_seeds: AsyncClient) -> None:
    """Test creating a ticket link via API."""
    # WEB project already exists with ID 2
    await client_with_seeds.post("/api/v1/tickets", json={"project_id": 2, "title": "Ticket 1"})
    await client_with_seeds.post("/api/v1/tickets", json={"project_id": 2, "title": "Ticket 2"})

    response = await client_with_seeds.post(
        "/api/v1/tickets/WEB-001/links",
        json={"target_id": "WEB-002", "link_type": "blocks"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["source_id"] == "WEB-001"
    assert data["target_id"] == "WEB-002"
    assert data["link_type"] == "blocks"
