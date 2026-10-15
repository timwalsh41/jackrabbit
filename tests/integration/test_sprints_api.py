"""Integration tests for Sprint CRUD API."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient


async def test_create_sprint(
    client_with_seeds: AsyncClient,
) -> None:
    """Test creating a sprint via API."""
    response = await client_with_seeds.post(
        "/api/v1/sprints",
        json={"number": 2601, "name": "Sprint 1", "description": "First sprint"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["number"] == 2601
    assert data["name"] == "Sprint 1"
    assert data["description"] == "First sprint"
    assert data["id"] == 1


async def test_list_sprints_ordered_by_number_desc(
    client_with_seeds: AsyncClient,
) -> None:
    """Test listing sprints via API - ordered by number, descending."""
    await client_with_seeds.post("/api/v1/sprints", json={"number": 2601, "name": "Sprint 1"})
    await client_with_seeds.post("/api/v1/sprints", json={"number": 2602, "name": "Sprint 2"})
    await client_with_seeds.post("/api/v1/sprints", json={"number": 2605, "name": "Sprint 5"})

    response = await client_with_seeds.get("/api/v1/sprints")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert [s["number"] for s in data] == [2605, 2602, 2601]


async def test_create_sprint_auto_assigns_number(
    client_with_seeds: AsyncClient,
) -> None:
    """POST without a number auto-assigns MAX(number)+1 starting at 2601."""
    response = await client_with_seeds.post("/api/v1/sprints", json={"name": "First"})
    assert response.status_code == 201
    assert response.json()["number"] == 2601

    response = await client_with_seeds.post("/api/v1/sprints", json={"name": "Second"})
    assert response.status_code == 201
    assert response.json()["number"] == 2602


async def test_create_sprint_auto_assign_continues_past_52(
    client_with_seeds: AsyncClient,
) -> None:
    """Numbering continues MAX+1 past 2652 (52 sprints in)."""
    await client_with_seeds.post("/api/v1/sprints", json={"number": 2601, "name": "S1"})
    await client_with_seeds.post("/api/v1/sprints", json={"number": 2652, "name": "S52"})
    response = await client_with_seeds.post("/api/v1/sprints", json={"name": "S53"})
    assert response.status_code == 201
    assert response.json()["number"] == 2653


async def test_create_sprint_with_all_date_fields(
    client_with_seeds: AsyncClient,
) -> None:
    """planned_duration_days and actual_* fields are settable at create."""
    response = await client_with_seeds.post(
        "/api/v1/sprints",
        json={
            "number": 2601,
            "name": "Full Sprint",
            "planned_start": "2026-01-05T00:00:00",
            "planned_duration_days": 14,
            "actual_start": "2026-01-06T00:00:00",
            "actual_finish": "2026-01-20T00:00:00",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["planned_duration_days"] == 14
    assert data["actual_start"] == "2026-01-06T00:00:00"
    assert data["actual_finish"] == "2026-01-20T00:00:00"


async def test_create_sprint_accepts_empty_string_form_fields(
    client_with_seeds: AsyncClient,
) -> None:
    """HTML forms submit "" for untouched optional fields; these mean 'not set'."""
    response = await client_with_seeds.post(
        "/api/v1/sprints",
        json={
            "number": "",
            "name": "Form Sprint",
            "planned_start": "",
            "planned_end": "",
            "planned_duration_days": "",
            "actual_start": "",
            "actual_finish": "",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["number"] == 2601  # empty string number -> auto-assign
    assert data["planned_start"] is None
    assert data["planned_duration_days"] is None
    assert data["actual_start"] is None
    assert data["actual_finish"] is None


async def test_create_sprint_duplicate_number_returns_409(
    client_with_seeds: AsyncClient,
) -> None:
    """User override colliding with an existing number is a conflict, not a 500."""
    await client_with_seeds.post("/api/v1/sprints", json={"number": 2601, "name": "S1"})
    response = await client_with_seeds.post("/api/v1/sprints", json={"number": 2601, "name": "Dup"})
    assert response.status_code == 409


async def test_patch_sprint_sets_actual_dates_and_duration(
    client_with_seeds: AsyncClient,
) -> None:
    """PATCH can set planned_duration_days, actual_start and actual_finish."""
    await client_with_seeds.post("/api/v1/sprints", json={"number": 2601, "name": "Sprint 1"})
    response = await client_with_seeds.patch(
        "/api/v1/sprints/1",
        json={
            "planned_duration_days": 10,
            "actual_start": "2026-02-02T00:00:00",
            "actual_finish": "2026-02-12T00:00:00",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["planned_duration_days"] == 10
    assert data["actual_start"] == "2026-02-02T00:00:00"
    assert data["actual_finish"] == "2026-02-12T00:00:00"


async def test_get_sprint(
    client_with_seeds: AsyncClient,
) -> None:
    """Test getting a single sprint with tickets."""
    await client_with_seeds.post("/api/v1/sprints", json={"number": 2601, "name": "Sprint 1"})

    response = await client_with_seeds.get("/api/v1/sprints/1")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["number"] == 2601
    assert data["name"] == "Sprint 1"
    assert "tickets" in data
    assert data["tickets"] == []
    assert data["status"] == "Planned"


async def test_get_sprint_with_tickets(
    client_with_seeds: AsyncClient,
) -> None:
    """Test getting a sprint with tickets."""
    # Create tickets assigned to sprint (WEB project is ID 2)
    sprint_response = await client_with_seeds.post(
        "/api/v1/sprints", json={"number": 2601, "name": "Sprint 1"}
    )
    sprint_id = sprint_response.json()["id"]

    await client_with_seeds.post(
        "/api/v1/tickets", json={"project_id": 2, "title": "Ticket 1", "sprint_id": sprint_id}
    )
    await client_with_seeds.post(
        "/api/v1/tickets", json={"project_id": 2, "title": "Ticket 2", "sprint_id": sprint_id}
    )

    response = await client_with_seeds.get(f"/api/v1/sprints/{sprint_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == sprint_id
    assert len(data["tickets"]) == 2


async def test_get_sprint_returns_tickets_grouped_by_status(
    client_with_seeds: AsyncClient,
) -> None:
    """GET /api/v1/sprints/{id} returns nested tickets grouped by status (ticket 07)."""
    sprint_response = await client_with_seeds.post(
        "/api/v1/sprints", json={"number": 2601, "name": "Sprint 1"}
    )
    sprint_id = sprint_response.json()["id"]

    await client_with_seeds.post(
        "/api/v1/tickets",
        json={"project_id": 2, "title": "Open ticket", "sprint_id": sprint_id},
    )
    await client_with_seeds.post(
        "/api/v1/tickets",
        json={
            "project_id": 2,
            "title": "Done ticket",
            "sprint_id": sprint_id,
            "status": "Complete",
        },
    )

    response = await client_with_seeds.get(f"/api/v1/sprints/{sprint_id}")
    assert response.status_code == 200
    data = response.json()
    grouped = data["tickets_by_status"]
    assert set(grouped.keys()) == {
        "Open",
        "Groomed",
        "In Progress",
        "Ready for Review",
        "Complete",
        "Rejected",
    }
    assert [t["title"] for t in grouped["Open"]] == ["Open ticket"]
    assert [t["title"] for t in grouped["Complete"]] == ["Done ticket"]
    assert grouped["Groomed"] == []


async def test_get_sprint_grouped_by_status_empty_sprint(
    client_with_seeds: AsyncClient,
) -> None:
    """Sprint with no tickets returns all six empty status buckets."""
    sprint_response = await client_with_seeds.post(
        "/api/v1/sprints", json={"number": 2601, "name": "Empty"}
    )
    sprint_id = sprint_response.json()["id"]
    response = await client_with_seeds.get(f"/api/v1/sprints/{sprint_id}")
    assert response.status_code == 200
    grouped = response.json()["tickets_by_status"]
    assert set(grouped.keys()) == {
        "Open",
        "Groomed",
        "In Progress",
        "Ready for Review",
        "Complete",
        "Rejected",
    }
    assert all(v == [] for v in grouped.values())


async def test_update_sprint(
    client_with_seeds: AsyncClient,
) -> None:
    """Test updating a sprint via API."""
    await client_with_seeds.post(
        "/api/v1/sprints", json={"number": 2601, "name": "Sprint 1", "description": "Original"}
    )
    response = await client_with_seeds.patch(
        "/api/v1/sprints/1",
        json={"name": "Updated Sprint 1", "description": "Updated description"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Sprint 1"
    assert data["description"] == "Updated description"
    assert data["number"] == 2601  # Number unchanged


async def test_update_sprint_partial(
    client_with_seeds: AsyncClient,
) -> None:
    """Test partially updating a sprint via API."""
    await client_with_seeds.post("/api/v1/sprints", json={"number": 2602, "name": "Sprint 2"})
    response = await client_with_seeds.patch(
        "/api/v1/sprints/1",
        json={"name": "Sprint 2 Renamed"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Sprint 2 Renamed"


async def test_delete_sprint(
    client_with_seeds: AsyncClient,
) -> None:
    """Test deleting a sprint via API."""
    await client_with_seeds.post("/api/v1/sprints", json={"number": 2603, "name": "Sprint 3"})
    response = await client_with_seeds.delete("/api/v1/sprints/1")
    assert response.status_code == 204
    # Verify it's gone
    response = await client_with_seeds.get("/api/v1/sprints/1")
    assert response.status_code == 404


async def test_get_nonexistent_sprint(
    client_with_seeds: AsyncClient,
) -> None:
    """Test getting a non-existent sprint returns 404."""
    response = await client_with_seeds.get("/api/v1/sprints/999")
    assert response.status_code == 404


async def test_update_nonexistent_sprint(
    client_with_seeds: AsyncClient,
) -> None:
    """Test updating a non-existent sprint returns 404."""
    response = await client_with_seeds.patch("/api/v1/sprints/999", json={"name": "New Name"})
    assert response.status_code == 404


async def test_delete_nonexistent_sprint(
    client_with_seeds: AsyncClient,
) -> None:
    """Test deleting a non-existent sprint returns 404."""
    response = await client_with_seeds.delete("/api/v1/sprints/999")
    assert response.status_code == 404


async def test_get_next_sprint_number(
    client_with_seeds: AsyncClient,
) -> None:
    """Test getting next sprint number."""
    # No sprints yet - should return 2601
    response = await client_with_seeds.get("/api/v1/sprints/next-number")
    assert response.status_code == 200
    data = response.json()
    assert data["number"] == 2601

    # Create sprint 2601
    await client_with_seeds.post("/api/v1/sprints", json={"number": 2601, "name": "Sprint 1"})

    # Should return 2602
    response = await client_with_seeds.get("/api/v1/sprints/next-number")
    assert response.status_code == 200
    data = response.json()
    assert data["number"] == 2602


async def test_sprint_status_derivation_planned(
    client_with_seeds: AsyncClient,
) -> None:
    """Test sprint status derivation - Planned (no actual_start, even with planned dates)."""
    future_start = (datetime.now(UTC) + timedelta(days=10)).isoformat()
    future_end = (datetime.now(UTC) + timedelta(days=20)).isoformat()

    response = await client_with_seeds.post(
        "/api/v1/sprints",
        json={
            "number": 2601,
            "name": "Future Sprint",
            "planned_start": future_start,
            "planned_end": future_end,
        },
    )
    sprint_id = response.json()["id"]

    response = await client_with_seeds.get(f"/api/v1/sprints/{sprint_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Planned"


async def test_sprint_status_derivation_active(
    client_with_seeds: AsyncClient,
) -> None:
    """Test sprint status derivation - Active (actual_start set, no actual_finish)."""
    past_start = (datetime.now(UTC) - timedelta(days=5)).isoformat()

    response = await client_with_seeds.post(
        "/api/v1/sprints",
        json={
            "number": 2601,
            "name": "Active Sprint",
            "actual_start": past_start,
        },
    )
    sprint_id = response.json()["id"]

    response = await client_with_seeds.get(f"/api/v1/sprints/{sprint_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Active"


async def test_sprint_status_derivation_complete_by_actual_finish(
    client_with_seeds: AsyncClient,
) -> None:
    """Test sprint status derivation - Complete (actual_finish set)."""
    past_start = (datetime.now(UTC) - timedelta(days=20)).isoformat()
    past_finish = (datetime.now(UTC) - timedelta(days=10)).isoformat()

    response = await client_with_seeds.post(
        "/api/v1/sprints",
        json={
            "number": 2601,
            "name": "Completed Sprint",
            "actual_start": past_start,
            "actual_finish": past_finish,
        },
    )
    sprint_id = response.json()["id"]

    response = await client_with_seeds.get(f"/api/v1/sprints/{sprint_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Complete"


async def test_sprint_status_tickets_do_not_drive(
    client_with_seeds: AsyncClient,
) -> None:
    """All tickets Complete does NOT make the sprint Complete without actual_finish."""
    future_start = (datetime.now(UTC) + timedelta(days=10)).isoformat()
    future_end = (datetime.now(UTC) + timedelta(days=20)).isoformat()

    response = await client_with_seeds.post(
        "/api/v1/sprints",
        json={
            "number": 2601,
            "name": "All Complete Sprint",
            "planned_start": future_start,
            "planned_end": future_end,
        },
    )
    sprint_id = response.json()["id"]

    # Create tickets with COMPLETE status (WEB project is ID 2)
    await client_with_seeds.post(
        "/api/v1/tickets",
        json={"project_id": 2, "title": "Ticket 1", "sprint_id": sprint_id, "status": "Complete"},
    )
    await client_with_seeds.post(
        "/api/v1/tickets",
        json={"project_id": 2, "title": "Ticket 2", "sprint_id": sprint_id, "status": "Complete"},
    )

    response = await client_with_seeds.get(f"/api/v1/sprints/{sprint_id}")
    assert response.status_code == 200
    data = response.json()
    # Even though all tickets are complete, no actual_finish -> not Complete
    assert data["status"] == "Planned"


async def test_sprint_status_derivation_complete_via_patch(
    client_with_seeds: AsyncClient,
) -> None:
    """Finishing a sprint: PATCH actual_finish flips status Active -> Complete."""
    past_start = (datetime.now(UTC) - timedelta(days=5)).isoformat()

    response = await client_with_seeds.post(
        "/api/v1/sprints", json={"number": 2601, "name": "Sprint 1", "actual_start": past_start}
    )
    sprint_id = response.json()["id"]
    status_response = await client_with_seeds.get(f"/api/v1/sprints/{sprint_id}")
    assert status_response.json()["status"] == "Active"

    past_finish = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    response = await client_with_seeds.patch(
        f"/api/v1/sprints/{sprint_id}", json={"actual_finish": past_finish}
    )
    assert response.status_code == 200
    status_response = await client_with_seeds.get(f"/api/v1/sprints/{sprint_id}")
    assert status_response.json()["status"] == "Complete"


async def test_assign_ticket_to_sprint(
    client_with_seeds: AsyncClient,
) -> None:
    """Test assigning a ticket to a sprint via API."""
    # Create sprint
    sprint_response = await client_with_seeds.post(
        "/api/v1/sprints", json={"number": 2601, "name": "Sprint 1"}
    )
    sprint_id = sprint_response.json()["id"]

    # Create ticket without sprint (UNS project is ID 1)
    ticket_response = await client_with_seeds.post(
        "/api/v1/tickets", json={"project_id": 1, "title": "Test Ticket"}
    )
    ticket_id = ticket_response.json()["id"]

    # Assign ticket to sprint
    response = await client_with_seeds.post(f"/api/v1/sprints/{sprint_id}/tickets/{ticket_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Ticket assigned to sprint"
    assert data["ticket_id"] == ticket_id
    assert data["sprint_id"] == sprint_id

    # Verify ticket is now in sprint
    response = await client_with_seeds.get(f"/api/v1/tickets/{ticket_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["sprint_id"] == sprint_id


async def test_unassign_ticket_from_sprint(
    client_with_seeds: AsyncClient,
) -> None:
    """Test removing a ticket from a sprint via API."""
    # Create sprint
    sprint_response = await client_with_seeds.post(
        "/api/v1/sprints", json={"number": 2601, "name": "Sprint 1"}
    )
    sprint_id = sprint_response.json()["id"]

    # Create ticket assigned to sprint (UNS project is ID 1)
    ticket_response = await client_with_seeds.post(
        "/api/v1/tickets", json={"project_id": 1, "title": "Test Ticket", "sprint_id": sprint_id}
    )
    ticket_id = ticket_response.json()["id"]

    # Unassign ticket from sprint
    response = await client_with_seeds.delete(f"/api/v1/sprints/{sprint_id}/tickets/{ticket_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Ticket removed from sprint"
    assert data["ticket_id"] == ticket_id
    assert data["sprint_id"] == sprint_id

    # Verify ticket is no longer in sprint
    response = await client_with_seeds.get(f"/api/v1/tickets/{ticket_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["sprint_id"] is None


async def test_assign_ticket_already_in_another_sprint_returns_409(
    client_with_seeds: AsyncClient,
) -> None:
    """Test that assigning a ticket to a sprint when it's already in another sprint returns 409."""
    # Create two sprints
    sprint1_response = await client_with_seeds.post(
        "/api/v1/sprints", json={"number": 2601, "name": "Sprint 1"}
    )
    sprint1_id = sprint1_response.json()["id"]

    sprint2_response = await client_with_seeds.post(
        "/api/v1/sprints", json={"number": 2602, "name": "Sprint 2"}
    )
    sprint2_id = sprint2_response.json()["id"]

    # Create ticket assigned to sprint 1 (UNS project is ID 1)
    ticket_response = await client_with_seeds.post(
        "/api/v1/tickets", json={"project_id": 1, "title": "Test Ticket", "sprint_id": sprint1_id}
    )
    ticket_id = ticket_response.json()["id"]

    # Try to assign same ticket to sprint 2 - should return 409
    response = await client_with_seeds.post(f"/api/v1/sprints/{sprint2_id}/tickets/{ticket_id}")
    assert response.status_code == 409
    data = response.json()
    assert "already assigned to sprint" in data["detail"]


async def test_assign_nonexistent_ticket_to_sprint_returns_404(
    client_with_seeds: AsyncClient,
) -> None:
    """Test that assigning a non-existent ticket to a sprint returns 404."""
    sprint_response = await client_with_seeds.post(
        "/api/v1/sprints", json={"number": 2601, "name": "Sprint 1"}
    )
    sprint_id = sprint_response.json()["id"]

    response = await client_with_seeds.post(f"/api/v1/sprints/{sprint_id}/tickets/999")
    assert response.status_code == 404


async def test_assign_ticket_to_nonexistent_sprint_returns_404(
    client_with_seeds: AsyncClient,
) -> None:
    """Test that assigning a ticket to a non-existent sprint returns 404."""
    ticket_response = await client_with_seeds.post(
        "/api/v1/tickets", json={"project_id": 1, "title": "Test Ticket"}
    )
    ticket_id = ticket_response.json()["id"]

    response = await client_with_seeds.post(f"/api/v1/sprints/999/tickets/{ticket_id}")
    assert response.status_code == 404


async def test_sprint_deletion_cascades_unassigns_tickets(
    client_with_seeds: AsyncClient,
) -> None:
    """Test that deleting a sprint unassigns its tickets (sets sprint_id to NULL)."""
    sprint_response = await client_with_seeds.post(
        "/api/v1/sprints", json={"number": 2601, "name": "Sprint 1"}
    )
    sprint_id = sprint_response.json()["id"]

    # Create tickets assigned to sprint (UNS project is ID 1)
    ticket1_response = await client_with_seeds.post(
        "/api/v1/tickets", json={"project_id": 1, "title": "Ticket 1", "sprint_id": sprint_id}
    )
    ticket1_id = ticket1_response.json()["id"]

    ticket2_response = await client_with_seeds.post(
        "/api/v1/tickets", json={"project_id": 1, "title": "Ticket 2", "sprint_id": sprint_id}
    )
    ticket2_id = ticket2_response.json()["id"]

    # Delete sprint
    response = await client_with_seeds.delete(f"/api/v1/sprints/{sprint_id}")
    assert response.status_code == 204

    # Verify tickets no longer have sprint_id
    response = await client_with_seeds.get(f"/api/v1/tickets/{ticket1_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["sprint_id"] is None

    response = await client_with_seeds.get(f"/api/v1/tickets/{ticket2_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["sprint_id"] is None


async def test_get_sprint_by_status(
    client_with_seeds: AsyncClient,
) -> None:
    """Test getting sprint with tickets grouped by status."""
    sprint_response = await client_with_seeds.post(
        "/api/v1/sprints", json={"number": 2601, "name": "Sprint 1"}
    )
    sprint_id = sprint_response.json()["id"]

    # Create tickets with different statuses (UNS project is ID 1)
    await client_with_seeds.post(
        "/api/v1/tickets",
        json={"project_id": 1, "title": "Open Ticket", "sprint_id": sprint_id, "status": "Open"},
    )
    await client_with_seeds.post(
        "/api/v1/tickets",
        json={
            "project_id": 1,
            "title": "In Progress Ticket",
            "sprint_id": sprint_id,
            "status": "In Progress",
        },
    )
    await client_with_seeds.post(
        "/api/v1/tickets",
        json={
            "project_id": 1,
            "title": "Complete Ticket",
            "sprint_id": sprint_id,
            "status": "Complete",
        },
    )

    response = await client_with_seeds.get(f"/api/v1/sprints/{sprint_id}/by-status")
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
