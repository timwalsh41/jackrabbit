"""E2E test for Sprint Workflow flow.

Self-contained: creates its own sprint and ticket via API factories, then drives the
"Move to Sprint" dropdown in the Backlog UI and verifies the row updates.
"""

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

        # The number is auto-filled (MAX+1 starting at 2601); numbers stay unique
        # across runs because the server database persists
        unique_num = page.input_value("input[name='number']")
        assert unique_num
        future_start = (datetime.now(UTC) + timedelta(days=10)).strftime("%Y-%m-%d")
        future_end = (datetime.now(UTC) + timedelta(days=20)).strftime("%Y-%m-%d")
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
        sprint_number = str(sprint["number"])
        page.click(f"#move-to-sprint-dropdown-{tid} button:has-text('{sprint_number}')")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)

        # The row's Sprint cell (7th td) now shows the sprint number
        expect(page.locator(f"#ticket-row-{tid} td:nth-child(7)")).to_contain_text(
            sprint_number, timeout=10000
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

    def test_sprint_view_updates_on_status_change(
        self, page: Page, base_url: str, seeded_projects, make_ticket, make_sprint
    ):
        """Moving a ticket through statuses is reflected in the Sprint view columns."""
        import httpx

        sprint = make_sprint()
        ticket = make_ticket(title="Status Move Ticket")
        tid = ticket["id"]
        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            resp = client.post(f"/api/v1/sprints/{sprint['id']}/tickets/{tid}")
            assert resp.status_code == 200

        # Ticket starts in the Open column
        page.goto(f"{base_url}/sprint/{sprint['id']}")
        page.wait_for_load_state("networkidle")
        open_col = page.locator("#column-open")
        groomed_col = page.locator("#column-groomed")
        expect(open_col).to_contain_text("Status Move Ticket", timeout=10000)
        assert "Status Move Ticket" not in groomed_col.inner_text()

        # Groom it through the ticket detail UI
        page.goto(f"{base_url}/ticket/{tid}")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#transition-buttons button", state="visible", timeout=10000)
        page.click("button:has-text('Groomed')")
        page.wait_for_selector("#groom-form", state="visible", timeout=10000)
        page.fill("textarea[name='approach']", "Approach")
        page.fill("textarea[name='files_to_change']", "f.py")
        page.fill("textarea[name='test_plan']", "tests")
        page.fill("textarea[name='validation_steps']", "validate")
        page.click("#groom-form button[type='submit']")
        expect(page.locator("#ticket-content span:has-text('Groomed')").first).to_be_visible(
            timeout=10000
        )

        # The Sprint view now shows the ticket in the Groomed column
        page.goto(f"{base_url}/sprint/{sprint['id']}")
        page.wait_for_load_state("networkidle")
        groomed_col = page.locator("#column-groomed")
        open_col = page.locator("#column-open")
        expect(groomed_col).to_contain_text("Status Move Ticket", timeout=10000)
        assert "Status Move Ticket" not in open_col.inner_text()

    def _open_sprint_edit_modal(self, page: Page, base_url: str, sprint_id: int) -> None:
        page.goto(f"{base_url}/sprints")
        page.wait_for_load_state("networkidle")
        page.click(f"#sprint-row-{sprint_id} a:has-text('Edit')")
        page.wait_for_selector("#sprint-modal #sprint-form", state="visible", timeout=10000)

    def test_actual_start_makes_sprint_active(
        self, page: Page, base_url: str, seeded_projects, make_sprint
    ):
        """Setting actual_start via the sprint edit modal derives status=Active."""
        sprint = make_sprint()
        self._open_sprint_edit_modal(page, base_url, sprint["id"])

        page.fill("input[name='actual_start']", "2026-01-05")
        page.click("#sprint-form button:has-text('Save Changes')")
        # Modal closes and the list refreshes with the derived status
        page.wait_for_function(
            "document.getElementById('sprint-modal').innerText.trim() === ''",
            timeout=10000,
        )
        row = page.locator(f"#sprint-row-{sprint['id']}")
        expect(row).to_contain_text("Active", timeout=10000)

    def test_actual_finish_makes_sprint_complete(
        self, page: Page, base_url: str, seeded_projects, make_sprint
    ):
        """Setting actual_finish via the sprint edit modal derives status=Complete."""
        sprint = make_sprint()
        self._open_sprint_edit_modal(page, base_url, sprint["id"])

        page.fill("input[name='actual_start']", "2026-01-05")
        page.fill("input[name='actual_finish']", "2026-01-19")
        page.click("#sprint-form button:has-text('Save Changes')")
        page.wait_for_function(
            "document.getElementById('sprint-modal').innerText.trim() === ''",
            timeout=10000,
        )
        row = page.locator(f"#sprint-row-{sprint['id']}")
        expect(row).to_contain_text("Complete", timeout=10000)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
