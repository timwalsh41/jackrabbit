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
    assert "Active" in content  # derived from actual_start
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
