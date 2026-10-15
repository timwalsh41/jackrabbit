"""Integration tests for Sprint CRUD API."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient


def test_create_sprint(client_with_seeds: TestClient) -> None:
    """Test creating a sprint via API."""
    response = client_with_seeds.post(
        "/api/v1/sprints",
        json={"number": "2601", "name": "Sprint 1", "description": "First sprint"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["number"] == "2601"
    assert data["name"] == "Sprint 1"
    assert data["description"] == "First sprint"
    assert data["id"] == 1


def test_list_sprints(client_with_seeds: TestClient) -> None:
    """Test listing sprints via API."""
    client_with_seeds.post("/api/v1/sprints", json={"number": "2601", "name": "Sprint 1"})
    client_with_seeds.post("/api/v1/sprints", json={"number": "2602", "name": "Sprint 2"})

    response = client_with_seeds.get("/api/v1/sprints")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["number"] == "2601"
    assert data[1]["number"] == "2602"


def test_get_sprint(client_with_seeds: TestClient) -> None:
    """Test getting a single sprint with tickets."""
    client_with_seeds.post("/api/v1/sprints", json={"number": "2601", "name": "Sprint 1"})

    response = client_with_seeds.get("/api/v1/sprints/1")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["number"] == "2601"
    assert data["name"] == "Sprint 1"
    assert "tickets" in data
    assert data["tickets"] == []
    assert data["status"] == "Planned"


def test_get_sprint_with_tickets(client_with_seeds: TestClient) -> None:
    """Test getting a sprint with tickets."""
    # Create tickets assigned to sprint (WEB project is ID 2)
    sprint_response = client_with_seeds.post(
        "/api/v1/sprints", json={"number": "2601", "name": "Sprint 1"}
    )
    sprint_id = sprint_response.json()["id"]

    client_with_seeds.post(
        "/api/v1/tickets", json={"project_id": 2, "title": "Ticket 1", "sprint_id": sprint_id}
    )
    client_with_seeds.post(
        "/api/v1/tickets", json={"project_id": 2, "title": "Ticket 2", "sprint_id": sprint_id}
    )

    response = client_with_seeds.get(f"/api/v1/sprints/{sprint_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == sprint_id
    assert len(data["tickets"]) == 2


def test_update_sprint(client_with_seeds: TestClient) -> None:
    """Test updating a sprint via API."""
    client_with_seeds.post(
        "/api/v1/sprints", json={"number": "2601", "name": "Sprint 1", "description": "Original"}
    )
    response = client_with_seeds.patch(
        "/api/v1/sprints/1",
        json={"name": "Updated Sprint 1", "description": "Updated description"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Sprint 1"
    assert data["description"] == "Updated description"
    assert data["number"] == "2601"  # Number unchanged


def test_update_sprint_partial(client_with_seeds: TestClient) -> None:
    """Test partially updating a sprint via API."""
    client_with_seeds.post("/api/v1/sprints", json={"number": "2602", "name": "Sprint 2"})
    response = client_with_seeds.patch(
        "/api/v1/sprints/1",
        json={"name": "Sprint 2 Renamed"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Sprint 2 Renamed"


def test_delete_sprint(client_with_seeds: TestClient) -> None:
    """Test deleting a sprint via API."""
    client_with_seeds.post("/api/v1/sprints", json={"number": "2603", "name": "Sprint 3"})
    response = client_with_seeds.delete("/api/v1/sprints/1")
    assert response.status_code == 204
    # Verify it's gone
    response = client_with_seeds.get("/api/v1/sprints/1")
    assert response.status_code == 404


def test_get_nonexistent_sprint(client_with_seeds: TestClient) -> None:
    """Test getting a non-existent sprint returns 404."""
    response = client_with_seeds.get("/api/v1/sprints/999")
    assert response.status_code == 404


def test_update_nonexistent_sprint(client_with_seeds: TestClient) -> None:
    """Test updating a non-existent sprint returns 404."""
    response = client_with_seeds.patch("/api/v1/sprints/999", json={"name": "New Name"})
    assert response.status_code == 404


def test_delete_nonexistent_sprint(client_with_seeds: TestClient) -> None:
    """Test deleting a non-existent sprint returns 404."""
    response = client_with_seeds.delete("/api/v1/sprints/999")
    assert response.status_code == 404


def test_get_next_sprint_number(client_with_seeds: TestClient) -> None:
    """Test getting next sprint number."""
    # No sprints yet - should return 2601
    response = client_with_seeds.get("/api/v1/sprints/next-number")
    assert response.status_code == 200
    data = response.json()
    assert data["number"] == "2601"

    # Create sprint 2601
    client_with_seeds.post("/api/v1/sprints", json={"number": "2601", "name": "Sprint 1"})

    # Should return 2602
    response = client_with_seeds.get("/api/v1/sprints/next-number")
    assert response.status_code == 200
    data = response.json()
    assert data["number"] == "2602"


def test_sprint_status_derivation_planned(client_with_seeds: TestClient) -> None:
    """Test sprint status derivation - Planned (future dates)."""
    future_start = (datetime.now(UTC) + timedelta(days=10)).isoformat()
    future_end = (datetime.now(UTC) + timedelta(days=20)).isoformat()

    response = client_with_seeds.post(
        "/api/v1/sprints",
        json={
            "number": "2601",
            "name": "Future Sprint",
            "planned_start": future_start,
            "planned_end": future_end,
        },
    )
    sprint_id = response.json()["id"]

    response = client_with_seeds.get(f"/api/v1/sprints/{sprint_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Planned"


def test_sprint_status_derivation_active(client_with_seeds: TestClient) -> None:
    """Test sprint status derivation - Active (current dates)."""
    past_start = (datetime.now(UTC) - timedelta(days=5)).isoformat()
    future_end = (datetime.now(UTC) + timedelta(days=10)).isoformat()

    response = client_with_seeds.post(
        "/api/v1/sprints",
        json={
            "number": "2601",
            "name": "Active Sprint",
            "planned_start": past_start,
            "planned_end": future_end,
        },
    )
    sprint_id = response.json()["id"]

    response = client_with_seeds.get(f"/api/v1/sprints/{sprint_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Active"


def test_sprint_status_derivation_complete_by_date(client_with_seeds: TestClient) -> None:
    """Test sprint status derivation - Complete (past end date)."""
    past_start = (datetime.now(UTC) - timedelta(days=20)).isoformat()
    past_end = (datetime.now(UTC) - timedelta(days=10)).isoformat()

    response = client_with_seeds.post(
        "/api/v1/sprints",
        json={
            "number": "2601",
            "name": "Completed Sprint",
            "planned_start": past_start,
            "planned_end": past_end,
        },
    )
    sprint_id = response.json()["id"]

    response = client_with_seeds.get(f"/api/v1/sprints/{sprint_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Complete"


def test_sprint_status_derivation_complete_by_tickets(client_with_seeds: TestClient) -> None:
    """Test sprint status derivation - Complete (all tickets complete)."""
    future_start = (datetime.now(UTC) + timedelta(days=10)).isoformat()
    future_end = (datetime.now(UTC) + timedelta(days=20)).isoformat()

    response = client_with_seeds.post(
        "/api/v1/sprints",
        json={
            "number": "2601",
            "name": "All Complete Sprint",
            "planned_start": future_start,
            "planned_end": future_end,
        },
    )
    sprint_id = response.json()["id"]

    # Create tickets with COMPLETE status (WEB project is ID 2)
    client_with_seeds.post(
        "/api/v1/tickets",
        json={"project_id": 2, "title": "Ticket 1", "sprint_id": sprint_id, "status": "Complete"},
    )
    client_with_seeds.post(
        "/api/v1/tickets",
        json={"project_id": 2, "title": "Ticket 2", "sprint_id": sprint_id, "status": "Complete"},
    )

    response = client_with_seeds.get(f"/api/v1/sprints/{sprint_id}")
    assert response.status_code == 200
    data = response.json()
    # Even though dates are in future, all tickets complete -> Complete
    assert data["status"] == "Complete"


def test_assign_ticket_to_sprint(client_with_seeds: TestClient) -> None:
    """Test assigning a ticket to a sprint via API."""
    # Create sprint
    sprint_response = client_with_seeds.post(
        "/api/v1/sprints", json={"number": "2601", "name": "Sprint 1"}
    )
    sprint_id = sprint_response.json()["id"]

    # Create ticket without sprint (UNS project is ID 1)
    ticket_response = client_with_seeds.post(
        "/api/v1/tickets", json={"project_id": 1, "title": "Test Ticket"}
    )
    ticket_id = ticket_response.json()["id"]

    # Assign ticket to sprint
    response = client_with_seeds.post(f"/api/v1/sprints/{sprint_id}/tickets/{ticket_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Ticket assigned to sprint"
    assert data["ticket_id"] == ticket_id
    assert data["sprint_id"] == sprint_id

    # Verify ticket is now in sprint
    response = client_with_seeds.get(f"/api/v1/tickets/{ticket_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["sprint_id"] == sprint_id


def test_unassign_ticket_from_sprint(client_with_seeds: TestClient) -> None:
    """Test removing a ticket from a sprint via API."""
    # Create sprint
    sprint_response = client_with_seeds.post(
        "/api/v1/sprints", json={"number": "2601", "name": "Sprint 1"}
    )
    sprint_id = sprint_response.json()["id"]

    # Create ticket assigned to sprint (UNS project is ID 1)
    ticket_response = client_with_seeds.post(
        "/api/v1/tickets", json={"project_id": 1, "title": "Test Ticket", "sprint_id": sprint_id}
    )
    ticket_id = ticket_response.json()["id"]

    # Unassign ticket from sprint
    response = client_with_seeds.delete(f"/api/v1/sprints/{sprint_id}/tickets/{ticket_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Ticket removed from sprint"
    assert data["ticket_id"] == ticket_id
    assert data["sprint_id"] == sprint_id

    # Verify ticket is no longer in sprint
    response = client_with_seeds.get(f"/api/v1/tickets/{ticket_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["sprint_id"] is None


def test_assign_ticket_already_in_another_sprint_returns_409(client_with_seeds: TestClient) -> None:
    """Test that assigning a ticket to a sprint when it's already in another sprint returns 409."""
    # Create two sprints
    sprint1_response = client_with_seeds.post(
        "/api/v1/sprints", json={"number": "2601", "name": "Sprint 1"}
    )
    sprint1_id = sprint1_response.json()["id"]

    sprint2_response = client_with_seeds.post(
        "/api/v1/sprints", json={"number": "2602", "name": "Sprint 2"}
    )
    sprint2_id = sprint2_response.json()["id"]

    # Create ticket assigned to sprint 1 (UNS project is ID 1)
    ticket_response = client_with_seeds.post(
        "/api/v1/tickets", json={"project_id": 1, "title": "Test Ticket", "sprint_id": sprint1_id}
    )
    ticket_id = ticket_response.json()["id"]

    # Try to assign same ticket to sprint 2 - should return 409
    response = client_with_seeds.post(f"/api/v1/sprints/{sprint2_id}/tickets/{ticket_id}")
    assert response.status_code == 409
    data = response.json()
    assert "already assigned to sprint" in data["detail"]


def test_assign_nonexistent_ticket_to_sprint_returns_404(client_with_seeds: TestClient) -> None:
    """Test that assigning a non-existent ticket to a sprint returns 404."""
    sprint_response = client_with_seeds.post(
        "/api/v1/sprints", json={"number": "2601", "name": "Sprint 1"}
    )
    sprint_id = sprint_response.json()["id"]

    response = client_with_seeds.post(f"/api/v1/sprints/{sprint_id}/tickets/999")
    assert response.status_code == 404


def test_assign_ticket_to_nonexistent_sprint_returns_404(client_with_seeds: TestClient) -> None:
    """Test that assigning a ticket to a non-existent sprint returns 404."""
    ticket_response = client_with_seeds.post(
        "/api/v1/tickets", json={"project_id": 1, "title": "Test Ticket"}
    )
    ticket_id = ticket_response.json()["id"]

    response = client_with_seeds.post(f"/api/v1/sprints/999/tickets/{ticket_id}")
    assert response.status_code == 404


def test_sprint_deletion_cascades_unassigns_tickets(client_with_seeds: TestClient) -> None:
    """Test that deleting a sprint unassigns its tickets (sets sprint_id to NULL)."""
    sprint_response = client_with_seeds.post(
        "/api/v1/sprints", json={"number": "2601", "name": "Sprint 1"}
    )
    sprint_id = sprint_response.json()["id"]

    # Create tickets assigned to sprint (UNS project is ID 1)
    ticket1_response = client_with_seeds.post(
        "/api/v1/tickets", json={"project_id": 1, "title": "Ticket 1", "sprint_id": sprint_id}
    )
    ticket1_id = ticket1_response.json()["id"]

    ticket2_response = client_with_seeds.post(
        "/api/v1/tickets", json={"project_id": 1, "title": "Ticket 2", "sprint_id": sprint_id}
    )
    ticket2_id = ticket2_response.json()["id"]

    # Delete sprint
    response = client_with_seeds.delete(f"/api/v1/sprints/{sprint_id}")
    assert response.status_code == 204

    # Verify tickets no longer have sprint_id
    response = client_with_seeds.get(f"/api/v1/tickets/{ticket1_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["sprint_id"] is None

    response = client_with_seeds.get(f"/api/v1/tickets/{ticket2_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["sprint_id"] is None


def test_get_sprint_by_status(client_with_seeds: TestClient) -> None:
    """Test getting sprint with tickets grouped by status."""
    sprint_response = client_with_seeds.post(
        "/api/v1/sprints", json={"number": "2601", "name": "Sprint 1"}
    )
    sprint_id = sprint_response.json()["id"]

    # Create tickets with different statuses (UNS project is ID 1)
    client_with_seeds.post(
        "/api/v1/tickets",
        json={"project_id": 1, "title": "Open Ticket", "sprint_id": sprint_id, "status": "Open"},
    )
    client_with_seeds.post(
        "/api/v1/tickets",
        json={
            "project_id": 1,
            "title": "In Progress Ticket",
            "sprint_id": sprint_id,
            "status": "In Progress",
        },
    )
    client_with_seeds.post(
        "/api/v1/tickets",
        json={
            "project_id": 1,
            "title": "Complete Ticket",
            "sprint_id": sprint_id,
            "status": "Complete",
        },
    )

    response = client_with_seeds.get(f"/api/v1/sprints/{sprint_id}/by-status")
    assert response.status_code == 200
    data = response.json()

    assert data["id"] == sprint_id
    assert "tickets_by_status" in data
    assert len(data["tickets_by_status"]["Open"]) == 1
    assert len(data["tickets_by_status"]["In Progress"]) == 1
    assert len(data["tickets_by_status"]["Complete"]) == 1
    assert len(data["tickets_by_status"]["Groomed"]) == 0
    assert len(data["tickets_by_status"]["Ready for Review"]) == 0
    assert len(data["tickets_by_status"]["Rejected"]) == 0
