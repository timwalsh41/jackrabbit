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

        # The row's Sprint cell (8th td, after the labels column) now shows the
        # sprint number
        expect(page.locator(f"#ticket-row-{tid} td:nth-child(8)")).to_contain_text(
            sprint_number, timeout=10000
        )

    def test_board_link_in_sprints_list_opens_board(
        self, page: Page, base_url: str, seeded_projects, make_sprint
    ):
        """JRB-031: the Board action in the Sprints list opens the sprint board."""
        sprint = make_sprint()
        page.goto(f"{base_url}/sprints")
        page.wait_for_load_state("networkidle")

        page.click(f"#sprint-row-{sprint['id']} a:has-text('Board')")
        page.wait_for_load_state("networkidle")

        # The canonical board URL renders with its status columns
        assert f"/sprints/{sprint['id']}/detail" in page.url
        expect(page.locator("#column-open")).to_be_visible(timeout=10000)
        expect(page.locator("body")).to_contain_text("E2E Sprint", timeout=10000)

    def test_ticket_detail_sprint_link_opens_board(
        self, page: Page, base_url: str, seeded_projects, make_ticket, make_sprint
    ):
        """JRB-031: the sprint link on the ticket detail page opens the sprint board."""
        sprint = make_sprint()
        ticket = make_ticket(title="Sprint Link Ticket")

        import httpx

        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            resp = client.post(f"/api/v1/sprints/{sprint['id']}/tickets/{ticket['id']}")
            assert resp.status_code == 200

        page.goto(f"{base_url}/ticket/{ticket['id']}")
        page.wait_for_load_state("networkidle")

        page.click("#sprint-section a")
        page.wait_for_load_state("networkidle")

        assert f"/sprints/{sprint['id']}/detail" in page.url
        expect(page.locator("#column-open")).to_be_visible(timeout=10000)
        expect(page.locator("body")).to_contain_text("Sprint Link Ticket", timeout=10000)

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

        page.goto(f"{base_url}/sprints/{sprint['id']}/detail")
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
        page.goto(f"{base_url}/sprints/{sprint['id']}/detail")
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
        page.goto(f"{base_url}/sprints/{sprint['id']}/detail")
        page.wait_for_load_state("networkidle")
        open_col = page.locator("#column-open")
        groomed_col = page.locator("#column-groomed")
        expect(open_col).to_contain_text("Status Move Ticket", timeout=10000)
        assert "Status Move Ticket" not in groomed_col.inner_text()

        # Story/Bug grooming is gated on at least one criterion (ADR-0025);
        # the modal criteria editor is JRB-023 scope, so the row is seeded
        # via the API here.
        with httpx.Client(base_url=base_url, timeout=30.0) as api:
            resp = api.post(f"/api/v1/tickets/{tid}/criteria", json={"text": "It works"})
            assert resp.status_code == 201, resp.text

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
        page.fill("input[name='criteria']", "Sprint move criterion")
        page.click("#groom-form button[type='submit']")
        expect(page.locator("#ticket-content span:has-text('Groomed')").first).to_be_visible(
            timeout=10000
        )

        # The Sprint view now shows the ticket in the Groomed column
        page.goto(f"{base_url}/sprints/{sprint['id']}/detail")
        page.wait_for_load_state("networkidle")
        groomed_col = page.locator("#column-groomed")
        open_col = page.locator("#column-open")
        expect(groomed_col).to_contain_text("Status Move Ticket", timeout=10000)
        assert "Status Move Ticket" not in open_col.inner_text()

    def test_completed_sprint_not_offered_in_backlog_menu(
        self, page: Page, base_url: str, seeded_projects, make_ticket, make_sprint
    ):
        """JRB-030: the Move to Sprint menu offers only assignable sprints."""
        sprint = make_sprint()
        ticket = make_ticket(title="Menu Exclusion Ticket")
        tid = ticket["id"]

        import httpx

        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            client.post(
                f"/api/v1/sprints/{sprint['id']}/transition", json={"to_status": "In Progress"}
            )
            client.post(
                f"/api/v1/sprints/{sprint['id']}/transition", json={"to_status": "Complete"}
            )

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector(f"#ticket-row-{tid}", state="visible", timeout=10000)
        page.click(f"#move-to-sprint-{tid}")
        dropdown = page.locator(f"#move-to-sprint-dropdown-{tid}")
        expect(dropdown).to_be_visible(timeout=10000)
        assert dropdown.locator(f"button:has-text('{sprint['number']}')").count() == 0

    def test_assign_to_completed_sprint_from_detail_refused(
        self, page: Page, base_url: str, seeded_projects, make_ticket, make_sprint
    ):
        """JRB-030: assigning from the detail view to a sprint that completed
        in the meantime is refused and the refusal explains why."""
        sprint = make_sprint()
        ticket = make_ticket(title="Stale Sprint Ticket")
        tid = ticket["id"]

        import httpx

        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            # In Progress so the detail page offers it at render time...
            client.post(
                f"/api/v1/sprints/{sprint['id']}/transition", json={"to_status": "In Progress"}
            )

        page.goto(f"{base_url}/ticket/{tid}")
        page.wait_for_load_state("networkidle")
        page.select_option(f"#assign-sprint-select-{tid}", str(sprint["id"]))

        # ...then the sprint completes elsewhere while the page is open.
        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            client.post(
                f"/api/v1/sprints/{sprint['id']}/transition", json={"to_status": "Complete"}
            )

        page.click("#sprint-section button[type='submit']")
        expect(page.locator("#transition-error")).to_contain_text("Complete", timeout=10000)

        # The ticket stays unassigned.
        page.goto(f"{base_url}/ticket/{tid}")
        page.wait_for_load_state("networkidle")
        expect(page.locator("#sprint-section")).to_contain_text("Unassigned", timeout=10000)

    def _open_sprint_edit_modal(self, page: Page, base_url: str, sprint_id: int) -> None:
        page.goto(f"{base_url}/sprints")
        page.wait_for_load_state("networkidle")
        page.click(f"#sprint-row-{sprint_id} a:has-text('Edit')")
        page.wait_for_selector("#sprint-modal #sprint-form", state="visible", timeout=10000)

    def test_start_sprint_from_board(self, page: Page, base_url: str, seeded_projects, make_sprint):
        """Start Sprint on the board flips the persisted status to In Progress
        and records the history row (JRB-029)."""
        sprint = make_sprint()
        page.goto(f"{base_url}/sprint/{sprint['id']}")
        page.wait_for_load_state("networkidle")
        expect(page.locator("#sprint-detail-content")).to_contain_text("Not Started")

        page.click("button:has-text('Start Sprint')")
        expect(page.locator("#sprint-detail-content")).to_contain_text("In Progress", timeout=10000)
        # The next action (Complete Sprint) replaces Start; history shows the move
        expect(page.locator("#sprint-detail-content")).to_contain_text("Complete Sprint")
        expect(page.locator("#sprint-detail-content")).to_contain_text("Sprint History")
        expect(page.locator("#sprint-detail-content")).to_contain_text("Not Started → In Progress")

    def test_complete_then_reopen_sprint_from_board(
        self, page: Page, base_url: str, seeded_projects, make_sprint
    ):
        """Complete Sprint stamps the finish and Reopen clears it (JRB-029)."""
        sprint = make_sprint()
        import httpx

        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            client.post(
                f"/api/v1/sprints/{sprint['id']}/transition", json={"to_status": "In Progress"}
            )

        page.goto(f"{base_url}/sprint/{sprint['id']}")
        page.wait_for_load_state("networkidle")
        page.click("button:has-text('Complete Sprint')")
        expect(page.locator("#sprint-detail-content")).to_contain_text("Complete", timeout=10000)
        expect(page.locator("#sprint-detail-content")).to_contain_text("Reopen Sprint")

        page.click("button:has-text('Reopen Sprint')")
        expect(page.locator("#sprint-detail-content")).to_contain_text("In Progress", timeout=10000)

    def test_blocked_completion_shows_why(
        self, page: Page, base_url: str, seeded_projects, make_ticket, make_sprint
    ):
        """A blocked completion leaves the sprint In Progress and names the
        blocking tickets (JRB-029)."""
        sprint = make_sprint()
        ticket = make_ticket(title="Blocking E2E Ticket")
        import httpx

        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            client.post(f"/api/v1/sprints/{sprint['id']}/tickets/{ticket['id']}")
            client.post(
                f"/api/v1/sprints/{sprint['id']}/transition", json={"to_status": "In Progress"}
            )

        page.goto(f"{base_url}/sprint/{sprint['id']}")
        page.wait_for_load_state("networkidle")
        page.click("button:has-text('Complete Sprint')")
        expect(page.locator("#sprint-detail-content [role='alert']")).to_contain_text(
            "Blocking E2E Ticket", timeout=10000
        )
        # The sprint stays In Progress
        expect(page.locator("#sprint-detail-content")).to_contain_text("In Progress")

    def test_start_complete_from_sprints_list_row(
        self, page: Page, base_url: str, seeded_projects, make_sprint
    ):
        """The Sprints list row offers Start/Complete/Reopen (JRB-029)."""
        sprint = make_sprint()
        page.goto(f"{base_url}/sprints")
        page.wait_for_load_state("networkidle")
        row = page.locator(f"#sprint-row-{sprint['id']}")
        expect(row).to_contain_text("Not Started")

        row.locator("button:has-text('Start')").click()
        expect(row).to_contain_text("In Progress", timeout=10000)
        expect(row.locator("button:has-text('Complete')")).to_be_visible()

        row.locator("button:has-text('Complete')").click()
        expect(row).to_contain_text("Complete", timeout=10000)
        expect(row.locator("button:has-text('Reopen')")).to_be_visible()

        row.locator("button:has-text('Reopen')").click()
        expect(row).to_contain_text("In Progress", timeout=10000)

    def test_actual_dates_are_read_only_in_sprint_form(
        self, page: Page, base_url: str, seeded_projects, make_sprint
    ):
        """The actual date inputs are disabled in the sprint edit form (JRB-029)."""
        sprint = make_sprint()
        self._open_sprint_edit_modal(page, base_url, sprint["id"])

        assert page.locator("#sprint-modal input[name='actual_start']").is_disabled()
        assert page.locator("#sprint-modal input[name='actual_finish']").is_disabled()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
