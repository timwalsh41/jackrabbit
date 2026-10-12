"""Integration tests for Jackrabbit API."""

import os
from collections.abc import AsyncGenerator, Generator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from jackrabbit.database import init_db
from jackrabbit.main import create_app


@pytest.fixture(scope="function")
def app() -> Generator[FastAPI, None, None]:
    """Create app with fresh database for each test."""
    os.environ["DATABASE_URL"] = "sqlite:///./data/test.db"
    app = create_app()
    init_db()
    yield app
    # Cleanup
    if os.path.exists("./data/test.db"):
        os.remove("./data/test.db")


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient) -> None:
    """Test health endpoint."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_create_project(client: AsyncClient) -> None:
    """Test creating a project via API."""
    response = await client.post(
        "/api/v1/projects",
        json={"prefix": "WEB", "name": "Web Project", "description": "Test project"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["prefix"] == "WEB"
    assert data["name"] == "Web Project"
    assert data["id"] == 1


@pytest.mark.asyncio
async def test_list_projects(client: AsyncClient) -> None:
    """Test listing projects via API."""
    # Create a project first
    await client.post("/api/v1/projects", json={"prefix": "WEB", "name": "Web Project"})

    response = await client.get("/api/v1/projects")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["prefix"] == "WEB"


@pytest.mark.asyncio
async def test_get_project(client: AsyncClient) -> None:
    """Test getting a single project."""
    await client.post("/api/v1/projects", json={"prefix": "WEB", "name": "Web Project"})

    response = await client.get("/api/v1/projects/1")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["prefix"] == "WEB"


@pytest.mark.asyncio
async def test_get_nonexistent_project(client: AsyncClient) -> None:
    """Test getting a non-existent project returns 404."""
    response = await client.get("/api/v1/projects/999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_ticket(client: AsyncClient) -> None:
    """Test creating a ticket via API."""
    # Create project first
    await client.post("/api/v1/projects", json={"prefix": "WEB", "name": "Web Project"})

    response = await client.post(
        "/api/v1/tickets",
        json={"project_id": 1, "title": "Test ticket", "type": "Bug", "priority": "High"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test ticket"
    assert data["type"] == "Bug"
    assert data["priority"] == "High"
    assert data["number"] == 1


@pytest.mark.asyncio
async def test_list_tickets(client: AsyncClient) -> None:
    """Test listing tickets via API."""
    await client.post("/api/v1/projects", json={"prefix": "WEB", "name": "Web Project"})
    await client.post("/api/v1/tickets", json={"project_id": 1, "title": "Ticket 1"})
    await client.post("/api/v1/tickets", json={"project_id": 1, "title": "Ticket 2"})

    response = await client.get("/api/v1/tickets")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_create_sprint(client: AsyncClient) -> None:
    """Test creating a sprint via API."""
    response = await client.post(
        "/api/v1/sprints",
        json={"number": "2601", "name": "Sprint 1"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["number"] == "2601"
    assert data["name"] == "Sprint 1"


@pytest.mark.asyncio
async def test_create_link(client: AsyncClient) -> None:
    """Test creating a ticket link via API."""
    await client.post("/api/v1/projects", json={"prefix": "WEB", "name": "Web Project"})
    await client.post("/api/v1/tickets", json={"project_id": 1, "title": "Ticket 1"})
    await client.post("/api/v1/tickets", json={"project_id": 1, "title": "Ticket 2"})

    response = await client.post(
        "/api/v1/links",
        json={"source_id": 1, "target_id": 2, "link_type": "blocks"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["source_id"] == 1
    assert data["target_id"] == 2
    assert data["link_type"] == "blocks"
