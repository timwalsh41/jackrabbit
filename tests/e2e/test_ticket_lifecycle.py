"""E2E test for Ticket Lifecycle flow.

Each test is self-contained: it creates its own preconditioned ticket via the API
(factory fixtures) and then drives the UI, so tests do not depend on ordering or on
state left behind by earlier tests.
"""

import pytest
from playwright.sync_api import Page, expect


class TestTicketLifecycle:
    """Tests for the complete ticket lifecycle flow."""

    def test_ticket_title_shows_full_id_not_raw_number(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        """Verify that the ticket view displays the full ID (e.g., MSC-006)
        and does not fall back to the raw database number (e.g., 'Ticket #6')."""
        ticket = make_ticket(status="Open")
        tid = ticket["id"]

        page.goto(f"{base_url}/tickets/{tid}")
        page.wait_for_load_state("networkidle")

        # Wait for ticket content to load via HTMX
        page.wait_for_selector("#ticket-content .space-y-6", state="visible", timeout=10000)

        title_text = page.inner_text("#ticket-title")
        assert "Ticket #" not in title_text, (
            f"Raw number fallback 'Ticket #' was displayed: {title_text}"
        )

        # The title should use the full ID format (Prefix-Number)
        assert "-" in title_text, f"Full ID format (Prefix-Number) was not displayed: {title_text}"

    def test_create_ticket(self, page: Page, base_url: str, seeded_projects):
        """Test creating a ticket via the Backlog UI."""
        unique_title = "UI Created Ticket for E2E"
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")

        # Click New Ticket button
        page.click("button:has-text('New Ticket'), a:has-text('New Ticket')")
        page.wait_for_selector("#ticket-modal form", state="visible", timeout=10000)

        # Fill the form
        page.fill("input[name='title']", unique_title)
        page.select_option("select[name='type']", "Story")
        page.select_option("select[name='priority']", "High")
        page.select_option("select[name='project_id']", "1")  # UNS project
        page.fill("textarea[name='description']", "E2E test ticket description")

        # Submit
        page.click("button:has-text('Create Ticket')")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)

        # Verify ticket appears in the backlog table
        expect(
            page.locator(f"#tickets-table-body tr:has-text('{unique_title}')").first
        ).to_be_visible(timeout=10000)

    def test_groom_ticket(self, page: Page, base_url: str, seeded_projects, make_ticket):
        """Test grooming a ticket (Open -> Groomed) via the transition modal."""
        ticket = make_ticket(status="Open")
        tid = ticket["id"]

        page.goto(f"{base_url}/ticket/{tid}")
        page.wait_for_load_state("networkidle")

        # Wait for transition buttons to render, then click the Groomed button
        page.wait_for_selector("#transition-buttons button", state="visible", timeout=10000)
        page.click("button:has-text('Groomed')")
        page.wait_for_selector("#groom-form", state="visible", timeout=10000)

        # Fill the four required grooming fields
        page.fill("textarea[name='approach']", "Test approach")
        page.fill("textarea[name='files_to_change']", "file1.py, file2.py")
        page.fill("textarea[name='test_plan']", "Unit tests")
        page.fill("textarea[name='validation_steps']", "1. Run tests")

        # Submit via the form-scoped button (avoids the "Groomed →" transition button)
        page.click("#groom-form button[type='submit']")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)

        # Status badge should now show Groomed
        expect(page.locator("#ticket-content span:has-text('Groomed')").first).to_be_visible(
            timeout=10000
        )

    def test_start_ticket(self, page: Page, base_url: str, seeded_projects, make_ticket):
        """Test starting a ticket (Groomed -> In Progress)."""
        ticket = make_ticket(status="Groomed")
        tid = ticket["id"]

        page.goto(f"{base_url}/ticket/{tid}")
        page.wait_for_load_state("networkidle")

        # Wait for transition buttons, click In Progress button
        page.wait_for_selector("#transition-buttons button", state="visible", timeout=10000)
        page.click("button:has-text('In Progress')")
        page.wait_for_selector("#in-progress-form", state="visible", timeout=10000)

        # Branch name should be pre-filled
        branch_input = page.locator("input[name='branch_name']")
        value = branch_input.input_value()
        assert value and value.startswith("feature/"), (
            f"Expected branch to start with feature/, got {value}"
        )

        # Confirm
        page.click("button:has-text('Start Work')")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)

        # Status badge should now show In Progress
        expect(page.locator("#ticket-content span:has-text('In Progress')").first).to_be_visible(
            timeout=10000
        )

    def test_review_ticket(self, page: Page, base_url: str, seeded_projects, make_ticket):
        """Test reviewing a ticket (In Progress -> Ready for Review)."""
        ticket = make_ticket(status="In Progress")
        tid = ticket["id"]

        page.goto(f"{base_url}/ticket/{tid}")
        page.wait_for_load_state("networkidle")

        # Wait for transition buttons, click Ready for Review button
        page.wait_for_selector("#transition-buttons button", state="visible", timeout=10000)
        page.click("button:has-text('Ready for Review')")
        page.wait_for_selector("#review-form", state="visible", timeout=10000)

        # Fill PR URL (required field)
        page.fill("input[name='pr_url']", "https://github.com/test/repo/pull/123")

        # Submit
        page.click("button:has-text('Submit for Review')")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)

        # Status badge should now show Ready for Review
        expect(
            page.locator("#ticket-content span:has-text('Ready for Review')").first
        ).to_be_visible(timeout=10000)

    def test_complete_ticket(self, page: Page, base_url: str, seeded_projects, make_ticket):
        """Test completing a ticket (Ready for Review -> Complete)."""
        ticket = make_ticket(status="Ready for Review")
        tid = ticket["id"]

        page.goto(f"{base_url}/ticket/{tid}")
        page.wait_for_load_state("networkidle")

        # Wait for transition buttons, click Complete button (opens modal)
        page.wait_for_selector("#transition-buttons button", state="visible", timeout=10000)
        page.click("button:has-text('Complete')")
        page.wait_for_selector("#complete-form", state="visible", timeout=10000)

        # Fill the reason (optional) and submit
        page.fill("#reason", "merged")
        page.click("#complete-form button[type='submit']")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)

        # Status badge should now show Complete
        expect(page.locator("#ticket-content span:has-text('Complete')").first).to_be_visible(
            timeout=10000
        )

    def test_guard_failure_error_displayed(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        """A guarded transition that fails (400) surfaces the error message via HTMX."""
        import httpx

        ticket = make_ticket(status="Open")
        tid = ticket["id"]

        # Reject the ticket via API so the restore buttons are direct hx-post buttons
        # (Rejected -> Groomed re-checks the Groomed guard, which fails with no fields).
        with httpx.Client(base_url=base_url, timeout=30.0) as api:
            response = api.post(
                f"/api/v1/tickets/{tid}/transition",
                json={"to_status": "Rejected", "reason": "not needed"},
            )
            assert response.status_code == 200

        page.goto(f"{base_url}/ticket/{tid}")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#transition-buttons button", state="visible", timeout=10000)

        page.on("dialog", lambda d: d.accept("restore"))
        # Restore to Groomed without grooming fields -> guard fails -> 400
        page.click("#transition-buttons button:has-text('Groomed')")

        banner = page.locator("#transition-error")
        expect(banner).to_be_visible(timeout=10000)
        expect(banner).to_contain_text("Approach is required")

    def test_transition_history_recorded(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        """Test that transition history is recorded for a ticket with transitions."""
        ticket = make_ticket(status="Groomed")
        tid = ticket["id"]

        page.goto(f"{base_url}/ticket/{tid}")
        page.wait_for_load_state("networkidle")

        # Check transition history section exists and has an entry
        expect(page.locator("text=Transition History")).to_be_visible()
        # At least one transition entry should be present (Open -> Groomed)
        expect(page.locator("#transition-history").first).to_contain_text("Groomed")

    def test_full_lifecycle_buttons_badges_and_history(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        """Walk Open -> ... -> Complete: badge, history and button guards at each stage.

        The UI only renders VALID transitions, so "disables invalid next buttons"
        means the invalid next-status buttons must not be offered at all.
        """
        ticket = make_ticket(status="Open", title="Full Lifecycle Walk")
        tid = ticket["id"]

        def buttons() -> object:
            return page.locator("#transition-buttons button")

        def assert_invalid_absent(*labels: str) -> None:
            for label in labels:
                assert buttons().locator(f"button:has-text('{label}')").count() == 0, (
                    f"invalid transition button '{label}' is offered"
                )

        page.goto(f"{base_url}/ticket/{tid}")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#transition-buttons button", state="visible", timeout=10000)

        # Open: only Groomed (guarded) and Rejected may be next
        assert_invalid_absent("Complete", "Ready for Review", "In Progress")

        # --- Open -> Groomed via modal (4 fields required) ---
        page.click("button:has-text('Groomed')")
        page.wait_for_selector("#groom-form", state="visible", timeout=10000)
        page.fill("textarea[name='approach']", "Walk approach")
        page.fill("textarea[name='files_to_change']", "walk.py")
        page.fill("textarea[name='test_plan']", "walk tests")
        page.fill("textarea[name='validation_steps']", "walk validation")
        page.click("#groom-form button[type='submit']")
        expect(page.locator("#ticket-content span:has-text('Groomed')").first).to_be_visible(
            timeout=10000
        )
        expect(page.locator("#transition-history")).to_contain_text("Groomed")
        # Groomed: In Progress and Rejected only
        assert_invalid_absent("Complete", "Ready for Review")

        # --- Groomed -> In Progress (branch pre-filled) ---
        page.click("button:has-text('In Progress')")
        page.wait_for_selector("#in-progress-form", state="visible", timeout=10000)
        branch = page.locator("input[name='branch_name']").input_value()
        assert branch, "branch name should be pre-filled"
        page.click("button:has-text('Start Work')")
        expect(page.locator("#ticket-content span:has-text('In Progress')").first).to_be_visible(
            timeout=10000
        )
        expect(page.locator("#transition-history")).to_contain_text("In Progress")
        # In Progress: Ready for Review and Rejected only
        assert_invalid_absent("Complete")

        # --- In Progress -> Ready for Review (PR URL optional, can submit empty) ---
        page.click("button:has-text('Ready for Review')")
        page.wait_for_selector("#review-form", state="visible", timeout=10000)
        # Leave the PR URL field empty: the transition must not gate on it.
        page.click("button:has-text('Submit for Review')")
        expect(
            page.locator("#ticket-content span:has-text('Ready for Review')").first
        ).to_be_visible(timeout=10000)
        expect(page.locator("#transition-history")).to_contain_text("Ready for Review")

        # --- Ready for Review -> Complete (modal) ---
        page.click("button:has-text('Complete')")
        page.wait_for_selector("#complete-form", state="visible", timeout=10000)
        page.fill("#reason", "merged")
        page.click("#complete-form button[type='submit']")
        expect(page.locator("#ticket-content span:has-text('Complete')").first).to_be_visible(
            timeout=10000
        )
        expect(page.locator("#transition-history")).to_contain_text("Complete")
        # Complete: only Rejected is possible forward/backward-wise here
        assert_invalid_absent("In Progress", "Groomed", "Open")

    def test_edit_ticket_via_form_with_no_sprint(
        self,
        page: Page,
        base_url: str,
        seeded_projects,
        make_ticket,
    ):
        """Regression for the edit-form 422: editing a ticket with no sprint via
        the full-page edit form posts sprint_id="" (the 'No Sprint' option).
        Without the empty-string -> None validator this 422'd; it must succeed.
        JRB-014: after saving, the browser returns to the ticket detail page
        (not the backlog) and shows the updated title."""
        ticket = make_ticket(title="Edit me via form", status="Open")
        tid = ticket["id"]
        assert ticket["sprint_id"] is None

        page.goto(f"{base_url}/tickets/{tid}/edit")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#ticket-form", timeout=10000)

        # 'No Sprint' (option value="") is selected by default for sprintless
        page.fill("input[name='title']", "Edited via UI form")
        page.select_option("select[name='priority']", "High")

        with page.expect_navigation():
            page.click("button:has-text('Save Changes')")
        page.wait_for_load_state("networkidle")

        # JRB-014: save lands on the ticket detail page, not the backlog.
        page.wait_for_url(f"{base_url}/tickets/{tid}")
        assert "/backlog" not in page.url
        expect(page.locator("#ticket-title")).to_contain_text("Edited via UI form")

    def test_groom_epic_without_structured_fields(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        """An Epic is a planning container, so it can be groomed through the UI
        with none of the four structured fields filled (ADR-0008).

        The Groomed modal does not mark those fields HTML-required for an Epic,
        so the user can open the modal and click Groom with them blank; the
        backend is exempt and records an Open -> Groomed audit row.
        """
        epic = make_ticket(ticket_type="Epic", status="Open", title="Epic to Groom via UI")
        tid = epic["id"]

        page.goto(f"{base_url}/ticket/{tid}")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#transition-buttons button", state="visible", timeout=10000)

        # Open the Groomed modal
        page.click("button:has-text('Groomed')")
        page.wait_for_selector("#groom-form", state="visible", timeout=10000)

        # For an Epic the structured fields are optional: no required asterisks
        # and the informational hint is shown.
        assert page.locator("#groom-form .text-red-500").count() == 0
        expect(page.locator("#groom-form").locator("text=planning containers")).to_be_visible(
            timeout=5000
        )

        # Submit the modal with all four fields left blank
        page.click("#groom-form button[type='submit']")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)

        # Status badge should now show Groomed
        expect(page.locator("#ticket-content span:has-text('Groomed')").first).to_be_visible(
            timeout=10000
        )
        # Transition audit row (Open -> Groomed) recorded
        expect(page.locator("#transition-history")).to_contain_text("Groomed")


def test_groom_epic_without_structured_fields_via_api(
    page: Page, base_url: str, seeded_projects, make_ticket
):
    """The acceptance-flow check from the ticket: POST the Groomed transition
    with no structured fields on an Epic and expect 200 + status Groomed."""
    import httpx

    epic = make_ticket(ticket_type="Epic", status="Open", title="Epic API groom no-fields")
    tid = epic["id"]

    with httpx.Client(base_url=base_url, timeout=30.0) as api:
        response = api.post(
            f"/api/v1/tickets/{tid}/transition",
            json={"to_status": "Groomed"},
        )
        assert response.status_code == 200
        assert response.json()["to_status"] == "Groomed"

        # A Story without the four fields is still rejected (regression).
        story = make_ticket(ticket_type="Story", status="Open", title="Story API groom no-fields")
        response = api.post(
            f"/api/v1/tickets/{story['id']}/transition",
            json={"to_status": "Groomed"},
        )
        assert response.status_code == 400
        assert "Approach is required" in response.json()["detail"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
