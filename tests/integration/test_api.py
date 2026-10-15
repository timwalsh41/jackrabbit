"""Integration tests for Jackrabbit API."""

from httpx import AsyncClient


async def test_health_endpoint(client: AsyncClient) -> None:
    """Test health endpoint."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_create_project(client_with_seeds: AsyncClient) -> None:
    """Test creating a project via API."""
    response = await client_with_seeds.post(
        "/api/v1/projects",
        json={"prefix": "DEV", "name": "Dev Project", "description": "Test project"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["prefix"] == "DEV"
    assert data["name"] == "Dev Project"
    # UNS=1, WEB=2, API=3, so this will be 4
    assert data["id"] == 4


async def test_list_projects(client_with_seeds: AsyncClient) -> None:
    """Test listing projects via API."""
    # 3 projects are already seeded (UNS, WEB, API)
    response = await client_with_seeds.get("/api/v1/projects")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert any(p["prefix"] == "WEB" for p in data)
    assert any(p["prefix"] == "API" for p in data)
    assert any(p["prefix"] == "UNS" for p in data)


async def test_get_project(client_with_seeds: AsyncClient) -> None:
    """Test getting a single project."""
    # WEB project is seeded with ID 2
    response = await client_with_seeds.get("/api/v1/projects/2")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 2
    assert data["prefix"] == "WEB"


async def test_get_nonexistent_project(client_with_seeds: AsyncClient) -> None:
    """Test getting a non-existent project returns 404."""
    response = await client_with_seeds.get("/api/v1/projects/999")
    assert response.status_code == 404


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
        "/api/v1/tickets/1/links",
        json={"source_id": 1, "target_id": 2, "link_type": "blocks"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["source_id"] == 1
    assert data["target_id"] == 2
    assert data["link_type"] == "blocks"


async def test_update_project(client_with_seeds: AsyncClient) -> None:
    """Test updating a project via API."""
    # WEB project already exists with ID 2
    response = await client_with_seeds.patch(
        "/api/v1/projects/2",
        json={
            "name": "Updated Web Project",
            "description": "Updated description",
            "color": "#ff0000",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Web Project"
    assert data["description"] == "Updated description"
    assert data["color"] == "#ff0000"
    assert data["prefix"] == "WEB"  # Prefix unchanged


async def test_update_project_partial(client_with_seeds: AsyncClient) -> None:
    """Test partially updating a project via API."""
    # API project already seeded with ID 3 (UNS=1, WEB=2, API=3)
    response = await client_with_seeds.patch(
        "/api/v1/projects/3",
        json={"name": "Backend API"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Backend API"
    assert data["prefix"] == "API"


async def test_delete_project(client_with_seeds: AsyncClient) -> None:
    """Test deleting a project via API."""
    response = await client_with_seeds.post(
        "/api/v1/projects", json={"prefix": "TMP", "name": "Temp Project"}
    )
    assert response.status_code == 201
    project_id = response.json()["id"]
    response = await client_with_seeds.delete(f"/api/v1/projects/{project_id}")
    assert response.status_code == 204
    # Verify it's gone
    response = await client_with_seeds.get(f"/api/v1/projects/{project_id}")
    assert response.status_code == 404


async def test_delete_system_project_forbidden(client_with_seeds: AsyncClient) -> None:
    """Test that UNS (system) project cannot be deleted."""
    response = await client_with_seeds.delete("/api/v1/projects/1")
    assert response.status_code == 403
    data = response.json()
    assert "system" in data["detail"].lower()


async def test_create_project_validation_prefix(client: AsyncClient) -> None:
    """Test project prefix validation."""
    # Too short
    response = await client.post("/api/v1/projects", json={"prefix": "W", "name": "Test"})
    assert response.status_code == 422
    # Too long
    response = await client.post("/api/v1/projects", json={"prefix": "WEBAPP12345", "name": "Test"})
    assert response.status_code == 422
    # Non-alphabetic
    response = await client.post("/api/v1/projects", json={"prefix": "WEB1", "name": "Test"})
    assert response.status_code == 422


async def test_create_project_validation_name(client: AsyncClient) -> None:
    """Test project name validation."""
    response = await client.post("/api/v1/projects", json={"prefix": "WEB", "name": ""})
    assert response.status_code == 422


async def test_create_project_validation_color(client: AsyncClient) -> None:
    """Test project color validation."""
    response = await client.post(
        "/api/v1/projects", json={"prefix": "WEB", "name": "Test", "color": "red"}
    )
    assert response.status_code == 422
    response = await client.post(
        "/api/v1/projects", json={"prefix": "WEB", "name": "Test", "color": "#GGGGGG"}
    )
    assert response.status_code == 422
    response = await client.post(
        "/api/v1/projects", json={"prefix": "WEB", "name": "Test", "color": "#12345"}
    )
    assert response.status_code == 422


async def test_create_project_duplicate_prefix_conflict(client_with_seeds: AsyncClient) -> None:
    """Duplicate project prefix returns 409, not a 500 IntegrityError."""
    # WEB is seeded by the fixture
    response = await client_with_seeds.post(
        "/api/v1/projects",
        json={"prefix": "WEB", "name": "Duplicate Web", "description": "dup"},
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


async def test_create_project_duplicate_prefix_case_insensitive_conflict(
    client_with_seeds: AsyncClient,
) -> None:
    """Lowercase duplicate prefix is normalized then rejected as 409."""
    response = await client_with_seeds.post(
        "/api/v1/projects",
        json={"prefix": "web", "name": "Lowercase Dup"},
    )
    assert response.status_code == 409


async def test_update_project_validation(client: AsyncClient) -> None:
    """Test project update validation."""
    await client.post("/api/v1/projects", json={"prefix": "WEB", "name": "Web Project"})
    # Invalid color
    response = await client.patch("/api/v1/projects/2", json={"color": "not-a-color"})
    assert response.status_code == 422
    # Empty name
    response = await client.patch("/api/v1/projects/2", json={"name": ""})
    assert response.status_code == 422
