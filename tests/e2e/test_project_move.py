"""E2E test for Project Move flow.

Self-contained: creates a ticket in a known project, moves it via the Move Project
modal, and verifies the new prefix plus the "Formerly" badge.
"""

import pytest
from playwright.sync_api import Page, expect


class TestProjectMove:
    """Tests for the project move flow."""

    def test_move_ticket_between_projects(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        """Move a ticket from UNS to WEB and verify the new ID + Formerly badge."""
        # projects: [uns, web, api] -> WEB is index 1
        web = seeded_projects[1]
        ticket = make_ticket(project_id=1, title="Ticket To Move")
        tid = ticket["id"]

        page.goto(f"{base_url}/ticket/{tid}")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#ticket-content", state="visible", timeout=10000)

        # Original ID should show UNS prefix
        original_id = page.locator(".ticket-id").inner_text()
        assert "UNS-" in original_id, f"Expected UNS prefix, got {original_id}"

        # Open the Move Project modal
        page.click("button:has-text('Move Project')")
        page.wait_for_selector("#ticket-modal form", state="visible", timeout=10000)

        # Select target project (WEB) by its real id
        page.select_option("select[name='project_id']", str(web["id"]))

        # Submit
        page.click("#ticket-modal button[type='submit']")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)

        # New ticket ID should show WEB prefix
        expect(page.locator(".ticket-id")).to_contain_text("WEB-", timeout=10000)

        # "Formerly" badge shows the original ID
        expect(page.locator("text=Formerly").first).to_be_visible(timeout=10000)

    def test_chained_moves_preserve_original_id(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        """After two moves, original_id still points to the very first ID."""
        web = seeded_projects[1]
        api = seeded_projects[2]
        ticket = make_ticket(project_id=1, title="Chained Move Ticket")
        tid = ticket["id"]

        # Move UNS -> WEB -> API via the API
        import httpx

        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            first = client.post(
                f"/api/v1/tickets/{tid}/move-project",
                json={
                    "project_id": web["id"],
                },
            ).json()
            second = client.post(
                f"/api/v1/tickets/{tid}/move-project",
                json={
                    "project_id": api["id"],
                },
            ).json()

        # original_id should be preserved from the FIRST move (not overwritten)
        assert second.get("original_id") == first.get("original_id"), (
            f"original_id changed across chained moves: "
            f"{first.get('original_id')} -> {second.get('original_id')}"
        )

        # UI should show API prefix and the original Formerly badge
        page.goto(f"{base_url}/ticket/{tid}")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#ticket-content", state="visible", timeout=10000)

        expect(page.locator(".ticket-id")).to_contain_text("API-")
        expect(page.locator("text=Formerly").first).to_be_visible()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
