"""Integration tests for Plan API and Web endpoints."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient


async def test_get_plan_empty(client_with_seeds: AsyncClient) -> None:
    """Test getting plan when no sprints exist."""
    response = await client_with_seeds.get("/api/v1/plan")
    assert response.status_code == 200
    data = response.json()
    assert data["sprints"] == []
    assert data["unsprinted_count"] == 0


async def test_get_plan_with_sprints(client_with_seeds: AsyncClient) -> None:
    """Test getting plan with sprints and tickets."""
    # Create sprints with dates
    now = datetime.now(UTC)
    future_start = (now + timedelta(days=10)).isoformat()
    future_end = (now + timedelta(days=20)).isoformat()
    past_start = (now - timedelta(days=10)).isoformat()
    past_end = (now - timedelta(days=5)).isoformat()
    active_start = (now - timedelta(days=5)).isoformat()
    active_end = (now + timedelta(days=10)).isoformat()

    # Planned sprint (no actual_start yet)
    sprint1 = await client_with_seeds.post(
        "/api/v1/sprints",
        json={
            "number": 2601,
            "name": "Future Sprint",
            "planned_start": future_start,
            "planned_end": future_end,
        },
    )
    sprint1_id = sprint1.json()["id"]

    # Active sprint (actual_start set, no actual_finish)
    sprint2 = await client_with_seeds.post(
        "/api/v1/sprints",
        json={
            "number": 2602,
            "name": "Current Sprint",
            "planned_start": active_start,
            "planned_end": active_end,
            "actual_start": active_start,
        },
    )
    sprint2_id = sprint2.json()["id"]

    # Completed sprint (actual_finish set)
    sprint3 = await client_with_seeds.post(
        "/api/v1/sprints",
        json={
            "number": 2603,
            "name": "Past Sprint",
            "planned_start": past_start,
            "planned_end": past_end,
            "actual_start": past_start,
            "actual_finish": past_end,
        },
    )
    sprint3_id = sprint3.json()["id"]

    # Create tickets with different statuses (WEB project is ID 2)
    await client_with_seeds.post(
        "/api/v1/tickets",
        json={"project_id": 2, "title": "Open Ticket", "sprint_id": sprint1_id, "status": "Open"},
    )
    await client_with_seeds.post(
        "/api/v1/tickets",
        json={
            "project_id": 2,
            "title": "Groomed Ticket",
            "sprint_id": sprint1_id,
            "status": "Groomed",
        },
    )

    await client_with_seeds.post(
        "/api/v1/tickets",
        json={
            "project_id": 2,
            "title": "In Progress Ticket",
            "sprint_id": sprint2_id,
            "status": "In Progress",
        },
    )
    await client_with_seeds.post(
        "/api/v1/tickets",
        json={
            "project_id": 2,
            "title": "Review Ticket",
            "sprint_id": sprint2_id,
            "status": "Ready for Review",
        },
    )
    await client_with_seeds.post(
        "/api/v1/tickets",
        json={
            "project_id": 2,
            "title": "Complete Ticket",
            "sprint_id": sprint2_id,
            "status": "Complete",
        },
    )

    await client_with_seeds.post(
        "/api/v1/tickets",
        json={
            "project_id": 2,
            "title": "Done Ticket",
            "sprint_id": sprint3_id,
            "status": "Complete",
        },
    )

    # Unsprinted tickets
    await client_with_seeds.post(
        "/api/v1/tickets", json={"project_id": 2, "title": "Unsprinted 1", "status": "Open"}
    )
    await client_with_seeds.post(
        "/api/v1/tickets", json={"project_id": 2, "title": "Unsprinted 2", "status": "Open"}
    )

    response = await client_with_seeds.get("/api/v1/plan")
    assert response.status_code == 200
    data = response.json()

    assert len(data["sprints"]) == 3
    assert data["unsprinted_count"] == 2

    # Check sprints are ordered by planned_start
    assert data["sprints"][0]["number"] == 2603  # Past sprint first (earliest start)
    assert data["sprints"][1]["number"] == 2602  # Active sprint
    assert data["sprints"][2]["number"] == 2601  # Future sprint

    # Check sprint 2603 (Complete)
    sprint_2603 = next(s for s in data["sprints"] if s["number"] == 2603)
    assert sprint_2603["status"] == "Complete"
    assert sprint_2603["total_tickets"] == 1
    assert sprint_2603["ticket_counts"]["Complete"] == 1

    # Check sprint 2602 (Active)
    sprint_2602 = next(s for s in data["sprints"] if s["number"] == 2602)
    assert sprint_2602["status"] == "Active"
    assert sprint_2602["total_tickets"] == 3
    assert sprint_2602["ticket_counts"]["In_Progress"] == 1
    assert sprint_2602["ticket_counts"]["Ready_for_Review"] == 1
    assert sprint_2602["ticket_counts"]["Complete"] == 1

    # Check sprint 2601 (Planned)
    sprint_2601 = next(s for s in data["sprints"] if s["number"] == 2601)
    assert sprint_2601["status"] == "Planned"
    assert sprint_2601["total_tickets"] == 2
    assert sprint_2601["ticket_counts"]["Open"] == 1
    assert sprint_2601["ticket_counts"]["Groomed"] == 1


async def test_get_plan_with_project_filter(client_with_seeds: AsyncClient) -> None:
    """Test getting plan filtered by project."""
    now = datetime.now(UTC)
    future_start = (now + timedelta(days=10)).isoformat()
    future_end = (now + timedelta(days=20)).isoformat()

    # Create sprint
    sprint = await client_with_seeds.post(
        "/api/v1/sprints",
        json={
            "number": 2601,
            "name": "Sprint 1",
            "planned_start": future_start,
            "planned_end": future_end,
        },
    )
    sprint_id = sprint.json()["id"]

    # Create tickets for both projects in the same sprint (WEB=2, API=3)
    await client_with_seeds.post(
        "/api/v1/tickets",
        json={"project_id": 2, "title": "WEB Ticket", "sprint_id": sprint_id, "status": "Open"},
    )
    await client_with_seeds.post(
        "/api/v1/tickets",
        json={"project_id": 3, "title": "API Ticket", "sprint_id": sprint_id, "status": "Open"},
    )

    # Unsprinted tickets for both projects
    await client_with_seeds.post(
        "/api/v1/tickets", json={"project_id": 2, "title": "WEB Unsprinted", "status": "Open"}
    )
    await client_with_seeds.post(
        "/api/v1/tickets", json={"project_id": 3, "title": "API Unsprinted", "status": "Open"}
    )

    # Filter by WEB project (id=2)
    response = await client_with_seeds.get("/api/v1/plan?project_id=2")
    assert response.status_code == 200
    data = response.json()

    assert len(data["sprints"]) == 1
    assert data["sprints"][0]["total_tickets"] == 1
    assert data["sprints"][0]["ticket_counts"]["Open"] == 1
    assert data["unsprinted_count"] == 1

    # Filter by API project (id=3)
    response = await client_with_seeds.get("/api/v1/plan?project_id=3")
    assert response.status_code == 200
    data = response.json()

    assert len(data["sprints"]) == 1
    assert data["sprints"][0]["total_tickets"] == 1
    assert data["unsprinted_count"] == 1

    # No filter - all projects
    response = await client_with_seeds.get("/api/v1/plan")
    assert response.status_code == 200
    data = response.json()

    assert len(data["sprints"]) == 1
    assert data["sprints"][0]["total_tickets"] == 2
    assert data["unsprinted_count"] == 2


async def test_get_plan_sprint_without_dates(client_with_seeds: AsyncClient) -> None:
    """Test plan with sprint that has no planned dates."""
    # Sprint without dates
    sprint = await client_with_seeds.post(
        "/api/v1/sprints", json={"number": 2601, "name": "No Dates Sprint"}
    )
    sprint_id = sprint.json()["id"]

    await client_with_seeds.post(
        "/api/v1/tickets",
        json={"project_id": 2, "title": "Ticket 1", "sprint_id": sprint_id, "status": "Open"},
    )

    response = await client_with_seeds.get("/api/v1/plan")
    assert response.status_code == 200
    data = response.json()

    assert len(data["sprints"]) == 1
    assert data["sprints"][0]["status"] == "Planned"  # No dates, has tickets -> Planned
    assert data["sprints"][0]["total_tickets"] == 1


async def test_plan_web_page(client_with_seeds: AsyncClient) -> None:
    """Test GET /plan web page renders correctly."""
    response = await client_with_seeds.get("/plan")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    content = response.text
    assert "Sprint Plan" in content
    assert "No sprints yet" in content
    assert "Create Sprint" in content


async def test_plan_web_page_with_sprints(client_with_seeds: AsyncClient) -> None:
    """Test GET /plan web page with sprints."""
    now = datetime.now(UTC)
    future_start = (now + timedelta(days=10)).isoformat()
    future_end = (now + timedelta(days=20)).isoformat()

    sprint = await client_with_seeds.post(
        "/api/v1/sprints",
        json={
            "number": 2601,
            "name": "Test Sprint",
            "planned_start": future_start,
            "planned_end": future_end,
        },
    )
    sprint_id = sprint.json()["id"]

    await client_with_seeds.post(
        "/api/v1/tickets",
        json={"project_id": 2, "title": "Ticket 1", "sprint_id": sprint_id, "status": "Open"},
    )

    response = await client_with_seeds.get("/plan")
    assert response.status_code == 200
    content = response.text
    assert "Sprint Plan" in content
    assert "2601" in content
    assert "Test Sprint" in content
    assert "Planned" in content
    assert "1 tickets" in content
    assert "Open" in content


async def test_plan_web_page_project_filter(client_with_seeds: AsyncClient) -> None:
    """Test GET /plan web page with project filter."""
    response = await client_with_seeds.get("/plan?project_id=2")
    assert response.status_code == 200
    content = response.text
    assert "Sprint Plan" in content
    # Check that the WEB project is selected in dropdown
    assert 'value="2" selected' in content or 'selected="" value="2"' in content


async def test_plan_web_page_unsprinted_tickets(client_with_seeds: AsyncClient) -> None:
    """Test GET /plan web page shows unsprinted tickets."""
    await client_with_seeds.post(
        "/api/v1/tickets", json={"project_id": 2, "title": "Unsprinted 1", "status": "Open"}
    )
    await client_with_seeds.post(
        "/api/v1/tickets", json={"project_id": 2, "title": "Unsprinted 2", "status": "Open"}
    )

    response = await client_with_seeds.get("/plan")
    assert response.status_code == 200
    content = response.text
    assert "2 unsprinted tickets" in content
    assert "View backlog" in content
