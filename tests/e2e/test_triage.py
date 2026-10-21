"""E2E tests for triage roles recorded as labels: the role is set through the
API, shown on the ticket page, and shown in the backlog table."""

import httpx
import pytest
from playwright.sync_api import Page, expect


@pytest.fixture
def set_triage_role(base_url: str):
    """Record a ticket's triage role the way an agent does: through the API."""

    def _set(ticket_id: int, role: str) -> dict:
        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            response = client.post(f"/api/v1/tickets/{ticket_id}/triage", json={"role": role})
            assert response.status_code == 200, response.text
            return response.json()

    return _set


class TestTriageRoleIsVisible:
    """A ticket's triage role is visible in the interface."""

    def test_the_ticket_page_shows_the_triage_role(
        self, page: Page, base_url: str, make_ticket, set_triage_role
    ):
        ticket = make_ticket()
        set_triage_role(ticket["id"], "ready-for-agent")

        page.goto(f"{base_url}/ticket/{ticket['id']}")
        page.wait_for_load_state("networkidle")

        # The labels section loads over HTMX.
        page.wait_for_selector("#labels-section", state="visible", timeout=10000)

        badge = page.locator('#labels-section [data-triage-role="ready-for-agent"]')
        expect(badge).to_be_visible(timeout=10000)
        expect(badge).to_contain_text("ready-for-agent")

    def test_the_backlog_table_shows_the_triage_role(
        self, page: Page, base_url: str, make_ticket, set_triage_role
    ):
        ticket = make_ticket(title="Backlog triage badge")
        set_triage_role(ticket["id"], "needs-info")

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")

        row = page.locator(f"#ticket-row-{ticket['id']}")
        expect(row).to_be_visible(timeout=10000)
        badge = row.locator('[data-triage-role="needs-info"]')
        expect(badge).to_be_visible(timeout=10000)

    def test_a_ticket_without_a_triage_role_shows_no_badge(
        self, page: Page, base_url: str, make_ticket
    ):
        ticket = make_ticket(title="No triage badge")

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")

        row = page.locator(f"#ticket-row-{ticket['id']}")
        expect(row).to_be_visible(timeout=10000)
        expect(row.locator("[data-triage-role]")).to_have_count(0)


class TestTriageRoleAsALabel:
    """The role is a label, so it can be applied like any other label."""

    def test_a_triage_label_applied_from_the_ticket_page_shows_the_role(
        self, page: Page, base_url: str, make_ticket
    ):
        ticket = make_ticket()

        page.goto(f"{base_url}/ticket/{ticket['id']}")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#labels-section", state="visible", timeout=10000)

        page.click("#labels-section button:has-text('Add Label')")
        page.wait_for_selector("#label-modal", state="visible", timeout=10000)
        page.fill("#label_name", "triage:ready-for-human")
        page.click("#label-modal button[type='submit']")

        chip = page.locator('#labels-section .label-chip[data-label-name="triage:ready-for-human"]')
        expect(chip).to_be_visible(timeout=10000)

        badge = page.locator('#labels-section [data-triage-role="ready-for-human"]')
        expect(badge).to_be_visible(timeout=10000)
