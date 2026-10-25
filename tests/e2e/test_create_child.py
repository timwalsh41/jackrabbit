"""E2E test for the Epic-only 'Create Child' affordance (JRB-010).

Flow: open an Epic's detail page -> click Create Child -> fill the modal ->
submit -> the new child appears under Links > Children with no full page
reload, and also nests under the Epic on /plan. Regression: a Story detail
page has no Create Child button.
"""

from playwright.sync_api import expect


def _load_links_section(page) -> None:
    """Wait for the ticket detail page's HTMX-loaded links section to render.

    The Links section loads asynchronously (the ticket JSON is swapped into
    #ticket-content, the page's JS renders the links-section container, and
    htmx then GETs /tickets/{id}/links into it). Mirrors the wait pattern used
    by tests/e2e/test_epic_story.py.
    """
    page.wait_for_selector("#links-section", state="visible", timeout=10000)
    page.wait_for_timeout(500)


class TestCreateChild:
    def test_create_child_from_epic_detail(self, page, base_url, seeded_projects, make_ticket):
        epic = make_ticket(title="Epic: Create Child E2E", ticket_type="Epic")

        page.goto(f"{base_url}/tickets/{epic['id']}")
        page.wait_for_load_state("networkidle")
        _load_links_section(page)

        # Create Child button is present for an Epic
        expect(page.locator("#links-section button:has-text('Create Child')")).to_have_count(1)

        # Open the child modal
        page.click("#links-section button:has-text('Create Child')")
        page.wait_for_selector("#ticket-modal form", state="visible", timeout=10000)

        # Fill the new child (type defaults to Story, project defaults to Epic's)
        page.fill("input[name='title']", "Child story from E2E")
        page.select_option("select[name='type']", "Story")

        # Submit (no full page reload: the URL stays on the Epic detail page)
        page.click("#ticket-modal button:has-text('Create Ticket')")

        expect(page).to_have_url(f"{base_url}/tickets/{epic['id']}")

        # Modal closes (form removed from #ticket-modal)
        expect(page.locator("#ticket-modal form")).to_have_count(0, timeout=10000)

        # The new child appears under Links > Children, refreshed in place
        # (the POST swaps #links-section before the modal closes)
        expect(page.locator("#links-section")).to_contain_text("Children")
        expect(page.locator("#links-section")).to_contain_text("Child story from E2E")

        # And the new child nests under the Epic in /plan
        page.goto(f"{base_url}/plan")
        page.wait_for_load_state("networkidle")
        expect(page.locator("#plan-epics")).to_contain_text(epic["title"])
        expect(page.locator("#plan-epics")).to_contain_text("Child story from E2E")

    def test_create_child_button_on_epic_detail(self, page, base_url, seeded_projects, make_ticket):
        """The Create Child button is visible on an Epic detail page."""
        epic = make_ticket(title="Epic button check", ticket_type="Epic")
        page.goto(f"{base_url}/tickets/{epic['id']}")
        page.wait_for_load_state("networkidle")
        _load_links_section(page)
        expect(page.locator("#links-section button:has-text('Create Child')")).to_have_count(1)

    def test_no_create_child_button_on_story_detail(
        self, page, base_url, seeded_projects, make_ticket
    ):
        """Regression: a Story detail page has NO Create Child button."""
        story = make_ticket(title="Story no create-child button", ticket_type="Story")
        page.goto(f"{base_url}/tickets/{story['id']}")
        page.wait_for_load_state("networkidle")
        _load_links_section(page)
        expect(page.locator("#links-section button:has-text('Create Child')")).to_have_count(0)
