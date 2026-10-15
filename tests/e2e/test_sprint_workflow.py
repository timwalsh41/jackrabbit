"""E2E test for Sprint Workflow flow.

Self-contained: creates its own sprint and ticket via API factories, then drives the
"Move to Sprint" dropdown in the Backlog UI and verifies the row updates.
"""

import time
from datetime import UTC, datetime, timedelta

import pytest
from playwright.sync_api import Page, expect


class TestSprintWorkflow:
    """Tests for the sprint workflow flow."""

    def test_create_sprint(self, page: Page, base_url: str):
        """Test creating a sprint via the New Sprint modal."""
        page.goto(f"{base_url}/sprints")
        page.wait_for_load_state("networkidle")

        # Click New Sprint button
        page.click("button:has-text('New Sprint'), a:has-text('New Sprint')")
        page.wait_for_selector("#sprint-modal form", state="visible", timeout=10000)

        # Unique sprint number to avoid conflicts
        unique_num = f"TST{int(time.time() * 1000) % 10000:04d}"
        future_start = (datetime.now(UTC) + timedelta(days=10)).strftime("%Y-%m-%d")
        future_end = (datetime.now(UTC) + timedelta(days=20)).strftime("%Y-%m-%d")

        page.fill("input[name='number']", unique_num)
        page.fill("input[name='name']", "Test Sprint")
        page.fill("textarea[name='description']", "Test sprint description")
        page.fill("input[name='planned_start']", future_start)
        page.fill("input[name='planned_end']", future_end)

        # Submit
        page.click("button:has-text('Create')")
        page.wait_for_timeout(1500)
        page.wait_for_load_state("networkidle")

        # Sprint appears in the table after HTMX refresh
        expect(page.locator("#sprints-table-body")).to_contain_text(unique_num, timeout=10000)

    def test_assign_ticket_to_sprint(
        self, page: Page, base_url: str, seeded_projects, make_ticket, make_sprint
    ):
        """Assign a ticket to a sprint via the Backlog 'Move to Sprint' dropdown."""
        sprint = make_sprint()
        ticket = make_ticket(title="Ticket For Sprint Assign")
        tid = ticket["id"]

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector(f"#ticket-row-{tid}", state="visible", timeout=10000)

        # Open the Move to Sprint dropdown
        page.click(f"#move-to-sprint-{tid}")
        page.wait_for_selector(f"#move-to-sprint-dropdown-{tid}", state="visible", timeout=10000)

        # Click the button for our sprint (matches its number)
        page.click(f"#move-to-sprint-dropdown-{tid} button:has-text('{sprint['number']}')")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)

        # The row's Sprint cell (7th td) now shows the sprint number
        expect(page.locator(f"#ticket-row-{tid} td:nth-child(7)")).to_contain_text(
            sprint["number"], timeout=10000
        )

    def test_sprint_view_shows_tickets_by_status(
        self, page: Page, base_url: str, seeded_projects, make_ticket, make_sprint
    ):
        """Sprint detail view shows tickets grouped by status columns."""
        sprint = make_sprint()
        # Create a groomed ticket and assign it to the sprint via API
        ticket = make_ticket(status="Groomed", title="Sprint Column Ticket")

        import httpx

        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            client.post(f"/api/v1/sprints/{sprint['id']}/tickets/{ticket['id']}")

        page.goto(f"{base_url}/sprint/{sprint['id']}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        # All status columns should be present
        for col in ["Open", "Groomed", "In Progress", "Ready for Review", "Complete", "Rejected"]:
            expect(page.locator(f"text={col}").first).to_be_visible(timeout=5000)

        # The groomed ticket should appear in the Groomed column area
        expect(page.locator("body")).to_contain_text("Sprint Column Ticket", timeout=10000)

    def test_sprint_status_derived(self, page: Page, base_url: str, seeded_projects, make_sprint):
        """Sprint detail shows a status badge derived from dates."""
        sprint = make_sprint()
        page.goto(f"{base_url}/sprint/{sprint['id']}")
        page.wait_for_load_state("networkidle")

        # Status badge element should be visible
        expect(
            page.locator(
                ".inline-flex.items-center.px-3.py-1.rounded-full.text-sm.font-medium"
            ).first
        ).to_be_visible(timeout=10000)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
