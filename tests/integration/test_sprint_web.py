"""Integration tests for the Sprint web pages (list, board, new form, edit form)."""

from pathlib import Path

from httpx import AsyncClient


async def _create_sprint(client: AsyncClient, **overrides) -> dict:
    payload = {"number": 2601, "name": "Sprint 1", **overrides}
    response = await client.post("/api/v1/sprints", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def test_sprint_list_page_shows_planned_and_actual_dates(
    client_with_seeds: AsyncClient,
) -> None:
    """GET /sprints table shows planned and actual date ranges, ticket count and status."""
    await _create_sprint(
        client_with_seeds,
        number=2601,
        name="Running Sprint",
        planned_start="2026-01-05T00:00:00",
        actual_start="2026-01-06T00:00:00",
    )

    response = await client_with_seeds.get("/sprints")
    assert response.status_code == 200
    content = response.text
    assert "2601" in content
    assert "Running Sprint" in content
    assert "2026-01-05" in content  # planned start
    assert "2026-01-06" in content  # actual start
    assert "In Progress" in content  # persisted status backfilled from actual_start
    assert 'href="/sprints/1/edit"' in content


async def test_sprint_detail_renders_board(client_with_seeds: AsyncClient) -> None:
    """JRB-031: GET /sprints/{id}/detail is the canonical URL for the sprint board."""
    sprint = await _create_sprint(client_with_seeds, number=2601, name="Board Sprint")

    response = await client_with_seeds.get(f"/sprints/{sprint['id']}/detail")
    assert response.status_code == 200
    content = response.text
    assert "Board Sprint" in content
    for column in ["Open", "Groomed", "In Progress", "Ready for Review", "Complete", "Rejected"]:
        assert column in content


async def test_legacy_sprint_url_redirects_to_canonical(
    client_with_seeds: AsyncClient,
) -> None:
    """JRB-031: GET /sprint/{id} redirects to the canonical /sprints/{id}/detail."""
    sprint = await _create_sprint(client_with_seeds, number=2602, name="Legacy URL")

    response = await client_with_seeds.get(f"/sprint/{sprint['id']}", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == f"/sprints/{sprint['id']}/detail"


async def test_legacy_sprint_url_follows_redirect_to_board(
    client_with_seeds: AsyncClient,
) -> None:
    """Following the legacy /sprint/{id} redirect lands on the sprint board."""
    sprint = await _create_sprint(client_with_seeds, number=2603, name="Followed")

    response = await client_with_seeds.get(f"/sprint/{sprint['id']}", follow_redirects=True)
    assert response.status_code == 200
    assert "Followed" in response.text


async def test_legacy_sprint_url_404_for_missing(client_with_seeds: AsyncClient) -> None:
    """The legacy redirect route still 404s for a sprint that does not exist."""
    response = await client_with_seeds.get("/sprint/999", follow_redirects=False)
    assert response.status_code == 404


async def test_sprint_list_row_has_board_link(client_with_seeds: AsyncClient) -> None:
    """JRB-031: each Sprints list row links Board to the canonical board URL."""
    sprint = await _create_sprint(client_with_seeds, number=2604, name="Linked")

    response = await client_with_seeds.get("/sprints")
    assert response.status_code == 200
    content = response.text
    assert f'href="/sprints/{sprint["id"]}/detail"' in content
    assert "Board" in content


async def test_sprint_html_stub_template_deleted() -> None:
    """JRB-031: the unused sprint.html stub board is deleted and no route renders it."""
    template = Path(__file__).parents[2] / "jackrabbit" / "templates" / "sprint.html"
    assert not template.exists()


async def test_new_sprint_form_uses_hx_post(
    client_with_seeds: AsyncClient,
) -> None:
    """GET /sprints/new form posts to the create endpoint and auto-fills the number."""
    response = await client_with_seeds.get("/sprints/new")
    assert response.status_code == 200
    content = response.text
    assert 'hx-post="/api/v1/sprints"' in content
    assert 'value="2601"' in content  # next number auto-filled


async def test_edit_sprint_form_uses_hx_patch(
    client_with_seeds: AsyncClient,
) -> None:
    """GET /sprints/{id}/edit form PATCHes to the update endpoint (not POST -> 405)."""
    sprint = await _create_sprint(
        client_with_seeds,
        number=2601,
        name="Editable",
        planned_start="2026-01-05T00:00:00",
        planned_duration_days=14,
    )

    response = await client_with_seeds.get(f"/sprints/{sprint['id']}/edit")
    assert response.status_code == 200
    content = response.text
    assert f'hx-patch="/api/v1/sprints/{sprint["id"]}"' in content
    # The form must not fall back to hx-post (the PATCH-only route would 405)
    assert 'hx-post="/api/v1/sprints/' not in content
    assert 'value="2601"' in content
    assert 'value="2026-01-05"' in content  # planned start prefilled
    assert 'name="planned_duration_days"' in content
    assert 'name="actual_start"' in content
    assert 'name="actual_finish"' in content


async def test_edit_sprint_form_404_for_missing(
    client_with_seeds: AsyncClient,
) -> None:
    response = await client_with_seeds.get("/sprints/999/edit")
    assert response.status_code == 404


async def _make_ticket_in_sprint(
    client: AsyncClient, sprint_id: int, title: str, status: str = "Open"
) -> dict:
    response = await client.post(
        "/api/v1/tickets",
        json={"project_id": 2, "title": title, "sprint_id": sprint_id, "status": status},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_sprint_edit_form_renders_actual_dates_read_only(
    client_with_seeds: AsyncClient,
) -> None:
    """The actual dates are read-only in the sprint form (JRB-029)."""
    sprint = await _create_sprint(
        client_with_seeds, actual_start="2026-01-06T00:00:00", actual_finish="2026-01-20T00:00:00"
    )

    response = await client_with_seeds.get(f"/sprints/{sprint['id']}/edit")
    assert response.status_code == 200
    content = response.text
    # Disabled, read-only inputs with the transition note
    assert "Read-only: set by the Start Sprint transition" in content
    assert "Read-only: set by the Complete Sprint transition" in content
    start_input = content.split('id="actual_start"')[1].split(">")[0]
    assert "disabled" in start_input
    assert "readonly" in start_input


async def test_sprint_board_shows_start_action_and_transition(
    client_with_seeds: AsyncClient,
) -> None:
    """The board offers Start Sprint on a Not Started sprint and the transition
    re-renders it In Progress with the action history (JRB-029)."""
    sprint = await _create_sprint(client_with_seeds, name="Board Sprint")

    response = await client_with_seeds.get(f"/sprints/{sprint['id']}/detail")
    content = response.text
    assert "Not Started" in content
    assert "Start Sprint" in content

    response = await client_with_seeds.post(
        f"/sprints/{sprint['id']}/transition",
        data={"to_status": "In Progress"},
    )
    assert response.status_code == 200
    assert "In Progress" in response.text
    assert "Complete Sprint" in response.text
    assert "Sprint History" in response.text
    assert "Not Started" in response.text  # history row shows the move


async def test_sprint_board_blocked_completion_shows_why(
    client_with_seeds: AsyncClient,
) -> None:
    """A blocked completion re-renders the board In Progress with the reason."""
    sprint = await _create_sprint(client_with_seeds, name="Blocked Board")
    await _make_ticket_in_sprint(client_with_seeds, sprint["id"], "Blocking ticket")

    await client_with_seeds.post(
        f"/sprints/{sprint['id']}/transition", data={"to_status": "In Progress"}
    )
    response = await client_with_seeds.post(
        f"/sprints/{sprint['id']}/transition", data={"to_status": "Complete"}
    )
    assert response.status_code == 200
    assert 'role="alert"' in response.text
    assert "Blocking ticket" in response.text
    assert "In Progress" in response.text

    # The persisted status is unchanged
    data = (await client_with_seeds.get(f"/api/v1/sprints/{sprint['id']}")).json()
    assert data["status"] == "In Progress"


async def test_sprint_board_reopen_action(
    client_with_seeds: AsyncClient,
) -> None:
    """A Complete sprint offers Reopen Sprint, which clears the finish date."""
    sprint = await _create_sprint(client_with_seeds, name="Reopenable")
    await client_with_seeds.post(
        f"/api/v1/sprints/{sprint['id']}/transition", json={"to_status": "In Progress"}
    )
    await client_with_seeds.post(
        f"/api/v1/sprints/{sprint['id']}/transition", json={"to_status": "Complete"}
    )

    response = await client_with_seeds.get(f"/sprints/{sprint['id']}/detail")
    assert "Reopen Sprint" in response.text

    response = await client_with_seeds.post(
        f"/sprints/{sprint['id']}/transition", data={"to_status": "In Progress"}
    )
    assert response.status_code == 200
    data = (await client_with_seeds.get(f"/api/v1/sprints/{sprint['id']}")).json()
    assert data["status"] == "In Progress"
    assert data["actual_finish"] is None


async def test_sprint_list_row_transition_swaps_row(
    client_with_seeds: AsyncClient,
) -> None:
    """The Sprints list row offers Start and the response swaps the row in."""
    sprint = await _create_sprint(client_with_seeds, name="Row Sprint")

    response = await client_with_seeds.get("/sprints", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Start" in response.text

    response = await client_with_seeds.post(
        f"/sprints/{sprint['id']}/transition?view=row",
        data={"to_status": "In Progress"},
    )
    assert response.status_code == 200
    assert f'id="sprint-row-{sprint["id"]}"' in response.text
    assert "In Progress" in response.text
    assert "Complete" in response.text  # the next action replaces Start

    # A blocked completion from the row shows the reason inline
    await _make_ticket_in_sprint(client_with_seeds, sprint["id"], "Row blocker")
    response = await client_with_seeds.post(
        f"/sprints/{sprint['id']}/transition?view=row",
        data={"to_status": "Complete"},
    )
    assert response.status_code == 200
    assert "Row blocker" in response.text
    assert "In Progress" in response.text


async def test_sprint_list_row_transitions_full_cycle(
    client_with_seeds: AsyncClient,
) -> None:
    """Start, Complete and Reopen are all offered on the Sprints list row."""
    sprint = await _create_sprint(client_with_seeds, name="Cycle Row")

    await client_with_seeds.post(
        f"/sprints/{sprint['id']}/transition?view=row", data={"to_status": "In Progress"}
    )
    response = await client_with_seeds.post(
        f"/sprints/{sprint['id']}/transition?view=row", data={"to_status": "Complete"}
    )
    assert response.status_code == 200
    assert "Reopen" in response.text

    response = await client_with_seeds.post(
        f"/sprints/{sprint['id']}/transition?view=row",
        data={"to_status": "In Progress", "reason": "rework"},
    )
    assert response.status_code == 200
    assert "In Progress" in response.text
    assert "Complete" in response.text  # the In Progress action replaces Reopen
    rows = (await client_with_seeds.get(f"/api/v1/sprints/{sprint['id']}/transitions")).json()
    assert [r["to_status"] for r in rows] == ["In Progress", "Complete", "In Progress"]
