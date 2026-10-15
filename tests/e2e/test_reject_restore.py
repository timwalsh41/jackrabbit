"""E2E test for Reject -> Restore flow (ticket 15, flow 6).

Self-contained: each test creates its own preconditioned ticket via the API
factory and drives the transitions through the ticket detail UI. Rejecting is
a prompt-backed direct transition; restoring from Rejected shows restore
buttons for every prior state and re-checks the Groomed guard.
"""

import httpx
import pytest
from playwright.sync_api import Page, expect


class TestRejectRestore:
    """Tests for the reject -> restore flow."""

    @staticmethod
    def _reject_via_ui(page: Page, base_url: str, tid: int) -> None:
        page.goto(f"{base_url}/ticket/{tid}")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#transition-buttons button", state="visible", timeout=10000)
        page.click("#transition-buttons button:has-text('Rejected')")
        expect(page.locator("#ticket-content span:has-text('Rejected')").first).to_be_visible(
            timeout=10000
        )

    def test_reject_from_in_progress(self, page: Page, base_url: str, seeded_projects, make_ticket):
        """A ticket at In Progress can be rejected via the Rejected button."""
        ticket = make_ticket(status="In Progress", title="Reject Me Ticket")
        tid = ticket["id"]

        # One dialog handler per test: every transition in the UI is prompt-backed.
        page.on("dialog", lambda d: d.accept("reason"))
        page.goto(f"{base_url}/ticket/{tid}")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#transition-buttons button", state="visible", timeout=10000)
        page.click("#transition-buttons button:has-text('Rejected')")

        # Badge updates to Rejected and history records the transition
        expect(page.locator("#ticket-content span:has-text('Rejected')").first).to_be_visible(
            timeout=10000
        )
        expect(page.locator("#transition-history")).to_contain_text("Rejected")

    def test_restore_to_groomed_rechecks_guards(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        """Restoring to Groomed re-checks the 4-field guard."""
        # Open ticket: the factory has NOT filled the grooming fields
        ticket = make_ticket(status="Open", title="Restore Groomed Ticket")
        tid = ticket["id"]
        self._reject_via_ui(page, base_url, tid)

        # Restore buttons for prior states are offered
        restore_row = page.locator("#transition-buttons")
        expect(restore_row).to_be_visible()
        expect(restore_row.locator("button:has-text('Groomed')")).to_be_visible()
        expect(restore_row.locator("button:has-text('Open')")).to_be_visible()

        # Guards are re-checked: without grooming fields the restore fails
        page.click("#transition-buttons button:has-text('Groomed')")
        banner = page.locator("#transition-error")
        expect(banner).to_be_visible(timeout=10000)
        expect(banner).to_contain_text("Approach is required")

        # Fill the four groomed fields via the API, then restore succeeds
        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            resp = client.patch(
                f"/api/v1/tickets/{tid}",
                json={
                    "approach": "Restore approach",
                    "files_to_change": "restore.py",
                    "test_plan": "restore tests",
                    "validation_steps": "validate restore",
                },
            )
            assert resp.status_code == 200

        page.reload()
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#transition-buttons button", state="visible", timeout=10000)
        page.click("#transition-buttons button:has-text('Groomed')")
        expect(page.locator("#ticket-content span:has-text('Groomed')").first).to_be_visible(
            timeout=10000
        )

    def test_restore_to_open_always_allowed(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        """Restoring a rejected ticket to Open never requires fields."""
        ticket = make_ticket(status="In Progress", title="Restore Open Ticket")
        tid = ticket["id"]
        self._reject_via_ui(page, base_url, tid)

        page.on("dialog", lambda d: d.accept("back to open"))
        page.click("#transition-buttons button:has-text('Open')")
        expect(page.locator("#ticket-content span:has-text('Open')").first).to_be_visible(
            timeout=10000
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
