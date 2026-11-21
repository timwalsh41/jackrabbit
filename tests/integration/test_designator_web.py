"""Integration tests for the JRB-039 designator web contract.

Web ticket routes take the project-scoped designator (``WEB-028``) exactly
like the API (JRB-038): a bare integer is the wrong-guess trap and answers
422, never a silently different ticket. Sprints are addressed by sprint
number; the legacy ``/ticket/{ref}`` and ``/sprint/{ref}`` aliases redirect
to the canonical URLs.
"""

from httpx import AsyncClient


async def _create_ticket(client: AsyncClient, project_id: int = 2, **kwargs) -> dict:
    response = await client.post("/api/v1/tickets", json={"project_id": project_id, **kwargs})
    assert response.status_code == 201, response.text
    return response.json()


async def _create_sprint(client: AsyncClient, number: int = 2601, **kwargs) -> dict:
    response = await client.post("/api/v1/sprints", json={"number": number, "name": "S", **kwargs})
    assert response.status_code == 201, response.text
    return response.json()


class TestTicketDetailByDesignator:
    async def test_detail_page_renders_at_designator(self, client_with_seeds: AsyncClient) -> None:
        ticket = await _create_ticket(client_with_seeds, title="designator page")
        response = await client_with_seeds.get(
            f"/tickets/{ticket['full_id']}", headers={"accept": "text/html"}
        )
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert ticket["full_id"] in response.text
        assert ticket["title"] in response.text

    async def test_designator_resolution_is_case_insensitive_and_padding_agnostic(
        self, client_with_seeds: AsyncClient
    ) -> None:
        ticket = await _create_ticket(client_with_seeds, title="padding")
        number = ticket["number"]
        for variant in (f"WEB-{number}", f"web-{number}", f"Web-{number:06d}"):
            response = await client_with_seeds.get(
                f"/tickets/{variant}", headers={"accept": "text/html"}
            )
            assert response.status_code == 200, (variant, response.text)
            assert ticket["title"] in response.text

    async def test_bare_integer_page_url_is_the_trap_and_answers_422(
        self, client_with_seeds: AsyncClient
    ) -> None:
        """A PK guess must 422, never silently render a different ticket."""
        web = await _create_ticket(client_with_seeds, project_id=2, title="web one")
        api = await _create_ticket(client_with_seeds, project_id=3, title="api one")
        response = await client_with_seeds.get("/tickets/1", headers={"accept": "text/html"})
        assert response.status_code == 422, response.text
        assert "designator" in response.text.lower()
        assert web["title"] not in response.text
        assert api["title"] not in response.text

    async def test_unknown_designator_is_html_404(self, client_with_seeds: AsyncClient) -> None:
        await _create_ticket(client_with_seeds, title="known")
        response = await client_with_seeds.get("/tickets/WEB-999", headers={"accept": "text/html"})
        assert response.status_code == 404
        assert "text/html" in response.headers["content-type"]
        assert "not found" in response.text.lower()

    async def test_legacy_pk_alias_redirects_to_designator_url(
        self, client_with_seeds: AsyncClient
    ) -> None:
        ticket = await _create_ticket(client_with_seeds, title="legacy")
        response = await client_with_seeds.get(
            f"/ticket/{ticket['id']}", headers={"accept": "text/html"}, follow_redirects=False
        )
        assert response.status_code == 307
        assert response.headers["location"] == f"/tickets/{ticket['full_id']}"

        followed = await client_with_seeds.get(
            f"/ticket/{ticket['id']}",
            headers={"accept": "text/html"},
            follow_redirects=True,
        )
        assert followed.status_code == 200
        assert ticket["title"] in followed.text

    async def test_legacy_designator_alias_also_redirects(
        self, client_with_seeds: AsyncClient
    ) -> None:
        ticket = await _create_ticket(client_with_seeds, title="legacy designator")
        response = await client_with_seeds.get(
            f"/ticket/{ticket['full_id']}", headers={"accept": "text/html"}, follow_redirects=False
        )
        assert response.status_code == 307
        assert response.headers["location"] == f"/tickets/{ticket['full_id']}"

    async def test_legacy_pk_alias_404s_for_unknown_pk(
        self, client_with_seeds: AsyncClient
    ) -> None:
        response = await client_with_seeds.get("/ticket/99999", headers={"accept": "text/html"})
        assert response.status_code == 404
        assert "text/html" in response.headers["content-type"]


class TestTicketSubresourcesByDesignator:
    """Every /tickets/{...} subresource route resolves the designator."""

    async def _ticket(self, client_with_seeds: AsyncClient) -> dict:
        return await _create_ticket(client_with_seeds, title="subresource")

    async def test_edit_page_accepts_designator_and_bare_int_is_422(
        self, client_with_seeds: AsyncClient
    ) -> None:
        ticket = await self._ticket(client_with_seeds)
        response = await client_with_seeds.get(
            f"/tickets/{ticket['full_id']}/edit", headers={"accept": "text/html"}
        )
        assert response.status_code == 200
        assert f'hx-patch="/api/v1/tickets/{ticket["full_id"]}"' in response.text

        trap = await client_with_seeds.get(
            f"/tickets/{ticket['id']}/edit", headers={"accept": "text/html"}
        )
        assert trap.status_code == 422

    async def test_criteria_section_accepts_designator(
        self, client_with_seeds: AsyncClient
    ) -> None:
        ticket = await self._ticket(client_with_seeds)
        response = await client_with_seeds.get(
            f"/tickets/{ticket['full_id']}/criteria", headers={"accept": "text/html"}
        )
        assert response.status_code == 200

    async def test_fields_section_accepts_designator(self, client_with_seeds: AsyncClient) -> None:
        ticket = await self._ticket(client_with_seeds)
        response = await client_with_seeds.get(
            f"/tickets/{ticket['full_id']}/fields", headers={"accept": "text/html"}
        )
        assert response.status_code == 200

    async def test_labels_section_accepts_designator(self, client_with_seeds: AsyncClient) -> None:
        ticket = await self._ticket(client_with_seeds)
        response = await client_with_seeds.get(
            f"/tickets/{ticket['full_id']}/labels", headers={"accept": "text/html"}
        )
        assert response.status_code == 200

    async def test_links_section_accepts_designator(self, client_with_seeds: AsyncClient) -> None:
        ticket = await self._ticket(client_with_seeds)
        response = await client_with_seeds.get(
            f"/tickets/{ticket['full_id']}/links", headers={"accept": "text/html"}
        )
        assert response.status_code == 200

    async def test_transition_modal_accepts_designator(
        self, client_with_seeds: AsyncClient
    ) -> None:
        ticket = await self._ticket(client_with_seeds)
        response = await client_with_seeds.get(
            f"/tickets/{ticket['full_id']}/transition/groomed/modal",
            headers={"accept": "text/html"},
        )
        assert response.status_code == 200

    async def test_sprint_section_accepts_designator(self, client_with_seeds: AsyncClient) -> None:
        ticket = await self._ticket(client_with_seeds)
        response = await client_with_seeds.get(
            f"/tickets/{ticket['full_id']}/sprint-section", headers={"accept": "text/html"}
        )
        assert response.status_code == 200


class TestSprintWebByNumber:
    async def test_detail_page_renders_at_sprint_number(
        self, client_with_seeds: AsyncClient
    ) -> None:
        sprint = await _create_sprint(client_with_seeds, name="numbered")
        response = await client_with_seeds.get(
            f"/sprints/{sprint['number']}/detail", headers={"accept": "text/html"}
        )
        assert response.status_code == 200
        assert sprint["name"] in response.text

    async def test_sprint_pk_is_not_a_sprint_url(self, client_with_seeds: AsyncClient) -> None:
        """Sprints are addressed by number; the PK value names no sprint."""
        sprint = await _create_sprint(client_with_seeds, name="by number")
        response = await client_with_seeds.get(
            f"/sprints/{sprint['id']}/detail", headers={"accept": "text/html"}
        )
        assert response.status_code == 404

    async def test_legacy_sprint_alias_redirects_to_number_url(
        self, client_with_seeds: AsyncClient
    ) -> None:
        sprint = await _create_sprint(client_with_seeds, name="legacy")
        response = await client_with_seeds.get(
            f"/sprint/{sprint['number']}", headers={"accept": "text/html"}, follow_redirects=False
        )
        assert response.status_code == 307
        assert response.headers["location"] == f"/sprints/{sprint['number']}/detail"

    async def test_legacy_sprint_pk_alias_redirects_too(
        self, client_with_seeds: AsyncClient
    ) -> None:
        """Pre-epic bookmarks used the PK; the alias still resolves them."""
        sprint = await _create_sprint(client_with_seeds, name="legacy pk")
        response = await client_with_seeds.get(
            f"/sprint/{sprint['id']}", headers={"accept": "text/html"}, follow_redirects=False
        )
        assert response.status_code == 307
        assert response.headers["location"] == f"/sprints/{sprint['number']}/detail"

    async def test_sprint_transition_by_number(self, client_with_seeds: AsyncClient) -> None:
        sprint = await _create_sprint(client_with_seeds, name="transition")
        response = await client_with_seeds.post(
            f"/sprints/{sprint['number']}/transition", data={"to_status": "In Progress"}
        )
        assert response.status_code == 200
        assert "In Progress" in response.text

    async def test_sprint_edit_by_number(self, client_with_seeds: AsyncClient) -> None:
        sprint = await _create_sprint(client_with_seeds, name="edit me")
        response = await client_with_seeds.get(
            f"/sprints/{sprint['number']}/edit", headers={"accept": "text/html"}
        )
        assert response.status_code == 200
        assert f'hx-patch="/api/v1/sprints/{sprint["number"]}"' in response.text


class TestTemplatesEmitDesignatorUrls:
    """Backlog rows and the sprint board link pages by designator/number."""

    async def test_backlog_row_links_use_designators(self, client_with_seeds: AsyncClient) -> None:
        ticket = await _create_ticket(client_with_seeds, title="row links")
        response = await client_with_seeds.get("/backlog", headers={"accept": "text/html"})
        assert response.status_code == 200
        assert f'href="/ticket/{ticket["full_id"]}"' in response.text
        assert f'href="/tickets/{ticket["id"]}"' not in response.text

    async def test_sprint_board_row_links_use_designators(
        self, client_with_seeds: AsyncClient
    ) -> None:
        sprint = await _create_sprint(client_with_seeds, name="board")
        ticket = await _create_ticket(
            client_with_seeds, title="board member", sprint_id=sprint["id"]
        )
        response = await client_with_seeds.get(
            f"/sprints/{sprint['number']}/detail", headers={"accept": "text/html"}
        )
        assert response.status_code == 200
        assert f'hx-get="/ticket/{ticket["full_id"]}"' in response.text
