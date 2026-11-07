"""Integration tests for acceptance-criteria editing in the ticket detail view."""

import httpx


async def _create_story(client: httpx.AsyncClient, criteria: list[str]) -> dict:
    response = await client.post(
        "/api/v1/tickets",
        json={"project_id": 1, "title": "Inline criteria editor", "type": "Story"},
    )
    assert response.status_code == 201, response.text
    ticket = response.json()
    if criteria:
        response = await client.patch(
            f"/api/v1/tickets/{ticket['id']}", json={"criteria": criteria}
        )
        assert response.status_code == 200, response.text
    return ticket


async def _transition(
    client: httpx.AsyncClient, ticket_id: int, to_status: str, **fields: object
) -> httpx.Response:
    return await client.post(
        f"/api/v1/tickets/{ticket_id}/transition",
        json={"to_status": to_status, **fields},
    )


class TestCriteriaEditorRoute:
    async def test_editor_prefills_criteria_for_open_ticket(
        self, client_with_seeds: httpx.AsyncClient
    ):
        ticket = await _create_story(client_with_seeds, ["First criterion", "Second criterion"])

        response = await client_with_seeds.get(f"/tickets/{ticket['id']}/criteria/edit")

        assert response.status_code == 200
        assert 'value="First criterion"' in response.text
        assert 'value="Second criterion"' in response.text
        assert 'class="text-red-500"' not in response.text
        assert "At least one criterion is required for Story tickets." in response.text
        assert "Cancel" in response.text
        assert "Save" in response.text

    async def test_editor_is_available_for_groomed_ticket(
        self, client_with_seeds: httpx.AsyncClient
    ):
        ticket = await _create_story(client_with_seeds, ["Groomed criterion"])
        groomed = await _transition(
            client_with_seeds,
            ticket["id"],
            "Groomed",
            approach="Approach",
            files_to_change="files.py",
            test_plan="Plan",
            validation_steps="Steps",
            criteria=["Groomed criterion"],
        )
        assert groomed.status_code == 200, groomed.text

        response = await client_with_seeds.get(f"/tickets/{ticket['id']}/criteria/edit")

        assert response.status_code == 200
        assert 'value="Groomed criterion"' in response.text

    async def test_add_action_appends_and_marks_last_row_for_focus(
        self, client_with_seeds: httpx.AsyncClient
    ):
        ticket = await _create_story(client_with_seeds, ["Existing criterion"])

        response = await client_with_seeds.get(f"/tickets/{ticket['id']}/criteria/edit?add=true")

        assert response.status_code == 200
        assert 'value="Existing criterion"' in response.text
        assert 'data-criteria-focus-last="true"' in response.text
        assert "data-original-criteria=" in response.text
        assert response.text.count('name="criteria"') == 2

    async def test_patch_replaces_and_trims_criteria(self, client_with_seeds: httpx.AsyncClient):
        ticket = await _create_story(client_with_seeds, ["Old criterion", "Remove this"])

        response = await client_with_seeds.patch(
            f"/tickets/{ticket['id']}/criteria", json={"criteria": [" First ", "Second"]}
        )

        assert response.status_code == 200, response.text
        assert "First" in response.text
        assert "Second" in response.text
        assert "Old criterion" not in response.text
        rows = (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/criteria")).json()
        assert [row["text"] for row in rows] == ["First", "Second"]

        unchanged = await client_with_seeds.patch(
            f"/tickets/{ticket['id']}/criteria", json={"criteria": ["First", "Second"]}
        )
        assert unchanged.status_code == 200, unchanged.text
        unchanged_rows = (
            await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/criteria")
        ).json()
        assert [row["id"] for row in unchanged_rows] == [row["id"] for row in rows]

    async def test_patch_accepts_an_empty_criteria_list(self, client_with_seeds: httpx.AsyncClient):
        ticket = await _create_story(client_with_seeds, ["Remove me"])

        response = await client_with_seeds.patch(
            f"/tickets/{ticket['id']}/criteria", json={"criteria": []}
        )

        assert response.status_code == 200, response.text
        assert "No acceptance criteria yet" in response.text
        assert (
            await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/criteria")
        ).json() == []

    async def test_patch_rejects_locked_criteria_with_conflict(
        self, client_with_seeds: httpx.AsyncClient
    ):
        ticket = await _create_story(client_with_seeds, ["Locked criterion"])
        groomed = await _transition(
            client_with_seeds,
            ticket["id"],
            "Groomed",
            approach="Approach",
            files_to_change="files.py",
            test_plan="Plan",
            validation_steps="Steps",
            criteria=["Locked criterion"],
        )
        assert groomed.status_code == 200, groomed.text
        started = await _transition(
            client_with_seeds,
            ticket["id"],
            "In Progress",
            branch_name="feature/criteria-editor",
        )
        assert started.status_code == 200, started.text

        response = await client_with_seeds.patch(
            f"/tickets/{ticket['id']}/criteria", json={"criteria": ["Changed"]}
        )

        assert response.status_code == 409
        assert "Criteria are locked" in response.json()["detail"]

    async def test_editor_is_unavailable_once_ticket_is_in_progress(
        self, client_with_seeds: httpx.AsyncClient
    ):
        ticket = await _create_story(client_with_seeds, ["Locked criterion"])
        groomed = await _transition(
            client_with_seeds,
            ticket["id"],
            "Groomed",
            approach="Approach",
            files_to_change="files.py",
            test_plan="Plan",
            validation_steps="Steps",
            criteria=["Locked criterion"],
        )
        assert groomed.status_code == 200, groomed.text
        started = await _transition(
            client_with_seeds,
            ticket["id"],
            "In Progress",
            branch_name="feature/criteria-editor",
        )
        assert started.status_code == 200, started.text

        response = await client_with_seeds.get(f"/tickets/{ticket['id']}/criteria/edit")

        assert response.status_code == 400
        assert "Criteria are locked" in response.json()["detail"]
