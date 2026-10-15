"""E2E test for Reject -> Restore flow."""

import pytest
from playwright.sync_api import Page, expect


class TestRejectRestore:
    """Tests for Reject -> Restore flow."""

    def test_reject_ticket(self, page: Page, base_url: str, seeded_projects):
        """Test rejecting a ticket (In Progress -> Rejected)."""
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")

        # Find a ticket in In Progress
        in_progress_rows = page.locator("tr:has-text('In Progress')").all()

        if len(in_progress_rows) > 0:
            first_in_progress = in_progress_rows[0]
            ticket_id = first_in_progress.get_attribute("id").replace("ticket-row-", "")

            if ticket_id:
                page.goto(f"{base_url}/ticket/{ticket_id}")
                page.wait_for_load_state("networkidle")

                # Click Reject button
                page.click("button:has-text('Reject')")
                page.wait_for_selector("#ticket-modal", state="visible")

                # Fill reason
                page.fill("textarea[name='reason']", "Not needed anymore")

                # Submit
                page.click("button:has-text('Reject')")
                page.wait_for_load_state("networkidle")

                # Verify status changed to Rejected
                expect(page.locator("text=Rejected")).to_be_visible()

    def test_restore_to_groomed(self, page: Page, base_url: str, seeded_projects):
        """Test restoring a rejected ticket to Groomed (guards re-checked)."""
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")

        # Find a ticket in Rejected status
        rejected_rows = page.locator("tr:has-text('Rejected')").all()

        if len(rejected_rows) > 0:
            first_rejected = rejected_rows[0]
            ticket_id = first_rejected.get_attribute("id").replace("ticket-row-", "")

            if ticket_id:
                page.goto(f"{base_url}/ticket/{ticket_id}")
                page.wait_for_load_state("networkidle")

                # Click Groom button (restore to Groomed)
                page.click("button:has-text('Groom')")
                page.wait_for_selector("#ticket-modal", state="visible")

                # Should require grooming fields if not already filled
                # Check if grooming fields are present
                approach_field = page.locator("textarea[name='approach']")
                if approach_field.count() > 0:
                    # Fill required fields
                    page.fill("textarea[name='approach']", "Test approach")
                    page.fill("textarea[name='files_to_change']", "file1.py")
                    page.fill("textarea[name='test_plan']", "Unit tests")
                    page.fill("textarea[name='validation_steps']", "Run tests")

                # Submit
                page.click("button:has-text('Groom')")
                page.wait_for_load_state("networkidle")

                # Verify status changed to Groomed
                expect(page.locator("text=Groomed")).to_be_visible()

    def test_restore_to_open(self, page: Page, base_url: str, seeded_projects):
        """Test restoring a rejected ticket to Open (always allowed)."""
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")

        # Find a ticket in Rejected status
        rejected_rows = page.locator("tr:has-text('Rejected')").all()

        if len(rejected_rows) > 0:
            first_rejected = rejected_rows[0]
            ticket_id = first_rejected.get_attribute("id").replace("ticket-row-", "")

            if ticket_id:
                page.goto(f"{base_url}/ticket/{ticket_id}")
                page.wait_for_load_state("networkidle")

                # Click Open button (restore to Open)
                page.click("button:has-text('Open')")
                page.wait_for_selector("#ticket-modal", state="visible")

                # No fields required for Open
                page.click("button:has-text('Restore')")
                page.wait_for_load_state("networkidle")

                # Verify status changed to Open
                expect(page.locator("text=Open")).to_be_visible()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
