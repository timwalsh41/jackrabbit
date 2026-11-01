"""E2E tests for JRB-014: full-page ticket edit returns to ticket detail.

From a ticket detail page, clicking Edit opens the full-page edit form.
Saving or cancelling must return to that ticket's detail page
(``/tickets/{id}``), never to the backlog. The New Ticket form keeps its
backlog back-links since there is no detail page yet.
"""

from playwright.sync_api import Page, expect


class TestEditSaveReturnsToDetail:
    def test_save_returns_to_ticket_detail(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        ticket = make_ticket()
        tid = ticket["id"]

        page.goto(f"{base_url}/tickets/{tid}")
        page.click(f'a[href="/tickets/{tid}/edit"]')

        # We are on the full-page edit form.
        expect(page).to_have_url(f"{base_url}/tickets/{tid}/edit")
        description = page.locator("#description")
        description.fill("Updated by E2E edit-redirect test")
        page.get_by_role("button", name="Save Changes").click()

        # Save must land back on the ticket detail page, not the backlog.
        page.wait_for_url(f"{base_url}/tickets/{tid}")
        expect(page.locator("#ticket-content")).to_contain_text("Updated by E2E edit-redirect test")
        assert "/backlog" not in page.url

    def test_cancel_returns_to_ticket_detail(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        ticket = make_ticket()
        tid = ticket["id"]

        page.goto(f"{base_url}/tickets/{tid}")
        page.click(f'a[href="/tickets/{tid}/edit"]')

        expect(page).to_have_url(f"{base_url}/tickets/{tid}/edit")
        page.get_by_role("link", name="Cancel").click()

        # Cancel must land back on the ticket detail page, not the backlog.
        page.wait_for_url(f"{base_url}/tickets/{tid}")
        assert "/backlog" not in page.url

    def test_new_ticket_cancel_still_returns_to_backlog(
        self, page: Page, base_url: str, seeded_projects
    ):
        # From the backlog the New Ticket button opens an HTMX modal; the
        # full-page New form is reached directly at /tickets/new.
        page.goto(f"{base_url}/tickets/new")
        expect(page.get_by_role("link", name="← Back to Backlog")).to_be_visible()

        page.get_by_role("link", name="Cancel").click()
        page.wait_for_url(f"{base_url}/backlog")
