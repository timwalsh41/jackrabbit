"""E2E tests for triage labels (JRB-032, ADR-0027): a triage role is set the
way an agent does — attaching the `triage:*` label by name through the generic
labels API — and renders as an ordinary label chip in the backlog row and the
ticket labels section, with no dedicated triage badge."""

import httpx
import pytest
from playwright.sync_api import Page, expect


@pytest.fixture
def set_triage_role(base_url: str):
    """Attach a triage label the way an agent does: via the labels API."""

    def _set(ticket_ref: str, name: str) -> dict:
        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            response = client.post(f"/api/v1/tickets/{ticket_ref}/labels", json={"name": name})
            assert response.status_code == 201, response.text
            return response.json()

    return _set


class TestTriageLabelIsAnOrdinaryChip:
    """A triage label renders like any other label; no special badge."""

    def test_the_ticket_page_shows_the_triage_label_as_a_chip(
        self, page: Page, base_url: str, make_ticket, set_triage_role
    ):
        ticket = make_ticket()
        set_triage_role(ticket["full_id"], "triage:ready-for-agent")

        page.goto(f"{base_url}/ticket/{ticket['id']}")
        page.wait_for_load_state("networkidle")

        # The labels section loads over HTMX.
        page.wait_for_selector("#labels-section", state="visible", timeout=10000)

        chip = page.locator('#labels-section .label-chip[data-label-name="triage:ready-for-agent"]')
        expect(chip).to_be_visible(timeout=10000)
        expect(page.locator("#labels-section [data-triage-role]")).to_have_count(0)

    def test_the_backlog_row_shows_the_triage_label_as_a_chip(
        self, page: Page, base_url: str, make_ticket, set_triage_role
    ):
        ticket = make_ticket(title="Backlog triage chip")
        set_triage_role(ticket["full_id"], "triage:needs-info")

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")

        row = page.locator(f"#ticket-row-{ticket['id']}")
        expect(row).to_be_visible(timeout=10000)
        chip = row.locator('.label-chip[data-label-name="triage:needs-info"]')
        expect(chip).to_be_visible(timeout=10000)
        expect(row.locator("[data-triage-role]")).to_have_count(0)

    def test_a_triage_label_added_from_the_ticket_page_shows_as_a_chip(
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
        expect(page.locator("#labels-section [data-triage-role]")).to_have_count(0)
