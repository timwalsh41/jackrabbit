"""Integration tests for the Sprint web pages (list, new form, edit form)."""

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
