"""Integration tests for ticket transition web display (ticket 05).

Covers the guard-failure error display path: the ticket detail page must include
an HTMX error handler that surfaces 400 guard-failure messages in the UI, and
the transition modals must provide an error container to display them in.
"""

import httpx
import pytest


async def _create_ticket(client: httpx.AsyncClient, project_id: int = 1) -> dict:
    response = await client.post(
        "/api/v1/tickets",
        json={"project_id": project_id, "title": "Transition web display test"},
    )
    assert response.status_code in (200, 201)
    return response.json()


class TestTicketDetailErrorDisplay:
    async def test_detail_page_has_htmx_error_handler(self, client: httpx.AsyncClient):
        """The ticket detail page wires an htmx:responseError handler."""
        ticket = await _create_ticket(client)
        response = await client.get(f"/ticket/{ticket['id']}")
        assert response.status_code == 200
        assert "htmx:responseError" in response.text
        assert 'id="transition-error"' in response.text

    async def test_transition_modals_have_error_container(self, client: httpx.AsyncClient):
        """Each guarded-transition modal has a #modal-error container."""
        ticket = await _create_ticket(client)
        for slug in ("groomed", "in-progress", "ready-for-review", "complete"):
            response = await client.get(f"/tickets/{ticket['id']}/transition/{slug}/modal")
            assert response.status_code == 200, f"modal {slug} failed to render"
            assert 'id="modal-error"' in response.text, f"modal {slug} lacks #modal-error"


class TestGuardFailureErrorContract:
    @pytest.mark.usefixtures("client_with_seeds")
    async def test_guard_failure_returns_400_with_detail_for_htmx(self, client: httpx.AsyncClient):
        """A guard failure returns HTTP 400 with a non-empty string detail,
        exactly what the HTMX error handler surfaces in the UI."""
        ticket = await _create_ticket(client)
        response = await client.post(
            f"/api/v1/tickets/{ticket['id']}/transition",
            json={"to_status": "Groomed"},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert isinstance(detail, str)
        assert "Approach is required" in detail

    async def test_ready_for_review_without_pr_url_succeeds(
        self, client_with_seeds, client: httpx.AsyncClient
    ):
        """In Progress -> Ready for Review succeeds without a PR URL (optional)."""
        ticket = await _create_ticket(client)
        # Drive to In Progress via API
        await client.post(
            f"/api/v1/tickets/{ticket['id']}/transition",
            json={
                "to_status": "Groomed",
                "approach": "a",
                "files_to_change": "f",
                "test_plan": "t",
                "validation_steps": "v",
            },
        )
        await client.post(
            f"/api/v1/tickets/{ticket['id']}/transition",
            json={"to_status": "In Progress", "branch_name": "feature/test-001"},
        )
        response = await client.post(
            f"/api/v1/tickets/{ticket['id']}/transition",
            json={"to_status": "Ready for Review"},
        )
        assert response.status_code == 200

    async def test_invalid_pr_url_still_returns_400_with_detail(
        self, client_with_seeds, client: httpx.AsyncClient
    ):
        """A supplied-but-invalid PR URL is still rejected when provided."""
        ticket = await _create_ticket(client)
        # Drive to In Progress via API
        await client.post(
            f"/api/v1/tickets/{ticket['id']}/transition",
            json={
                "to_status": "Groomed",
                "approach": "a",
                "files_to_change": "f",
                "test_plan": "t",
                "validation_steps": "v",
            },
        )
        await client.post(
            f"/api/v1/tickets/{ticket['id']}/transition",
            json={"to_status": "In Progress", "branch_name": "feature/test-001"},
        )
        response = await client.post(
            f"/api/v1/tickets/{ticket['id']}/transition",
            json={"to_status": "Ready for Review", "pr_url": "not-a-url"},
        )
        assert response.status_code == 400
        assert "URL" in response.json()["detail"]


class TestGroomedModalPrefill:
    async def test_groomed_modal_prefills_gating_fields(self, client: httpx.AsyncClient):
        """The Groomed transition modal pre-fills the gating fields with
        the ticket's existing values."""
        ticket = await _create_ticket(client)
        # Patch the ticket to have values for the gating fields
        patch_payload = {
            "approach": "Existing approach",
            "files_to_change": "Existing files",
            "test_plan": "Existing test plan",
            "validation_steps": "Existing validation steps",
        }
        response = await client.patch(f"/api/v1/tickets/{ticket['id']}", json=patch_payload)
        assert response.status_code == 200, response.text

        # Fetch the modal
        response = await client.get(f"/tickets/{ticket['id']}/transition/groomed/modal")
        assert response.status_code == 200
        html = response.text
        assert "Existing approach" in html
        assert "Existing files" in html
        assert "Existing test plan" in html
        assert "Existing validation steps" in html


class TestCompleteModal:
    async def test_complete_modal_renders_with_reason_field(
        self, client_with_seeds, client: httpx.AsyncClient
    ):
        """The Complete transition modal renders with a Reason field and the
        error container, mirroring the other transition modals."""
        ticket = await _create_ticket(client)
        response = await client.get(f"/tickets/{ticket['id']}/transition/complete/modal")
        assert response.status_code == 200
        html = response.text
        assert 'name="to_status" value="Complete"' in html
        assert 'id="reason"' in html
        assert 'id="modal-error"' in html

    async def test_detail_page_uses_modal_for_complete_transition(
        self, client_with_seeds, client: httpx.AsyncClient
    ):
        """The ticket detail page routes the Complete transition through the
        modal (hx-get) instead of a browser prompt()."""
        ticket = await _create_ticket(client)
        response = await client.get(f"/ticket/{ticket['id']}")
        assert response.status_code == 200
        assert "/transition/complete/modal" in response.text


async def _create_epic_ticket(client: httpx.AsyncClient, project_id: int = 1) -> dict:
    """Create an Epic via the API (mirrors the e2e make_ticket factory)."""
    response = await client.post(
        "/api/v1/tickets",
        json={
            "project_id": project_id,
            "title": "Transition web epic test",
            "type": "Epic",
        },
    )
    assert response.status_code in (200, 201)
    return response.json()


class TestEpicTransitionModals:
    """An Epic is a planning container, so its Groomed modal must not mark the
    structured fields as HTML-required (the browser would otherwise block a
    real user grooming an Epic without them), and its In Progress modal must
    not mark the branch name as required — the backend is exempt for Epic
    (ADR-0008 / ADR-0010).
    """

    async def test_epic_groomed_modal_has_no_required_fields(self, client: httpx.AsyncClient):
        epic = await _create_epic_ticket(client)
        response = await client.get(f"/tickets/{epic['id']}/transition/groomed/modal")
        assert response.status_code == 200
        html = response.text
        # The four gating fields must not be required for an Epic.
        assert "required" not in html
        # The fields are still rendered (just optional) so the user can fill them.
        for name in ("approach", "files_to_change", "test_plan", "validation_steps"):
            assert f'name="{name}"' in html
        # The Epic-specific hint is shown instead of the red asterisks.
        assert "Epics are planning containers" in html
        assert 'text-red-500">*</span>' not in html

    async def test_story_groomed_modal_still_requires_fields(self, client: httpx.AsyncClient):
        ticket = await _create_ticket(client)
        response = await client.get(f"/tickets/{ticket['id']}/transition/groomed/modal")
        assert response.status_code == 200
        html = response.text
        assert "required" in html
        assert 'text-red-500">*</span>' in html

    async def test_epic_in_progress_modal_branch_not_required(self, client: httpx.AsyncClient):
        epic = await _create_epic_ticket(client)
        response = await client.get(f"/tickets/{epic['id']}/transition/in-progress/modal")
        assert response.status_code == 200
        html = response.text
        # The branch input must not be HTML-required for an Epic.
        assert 'name="branch_name"' in html
        assert "required" not in html
        assert "Optional for Epics" in html
