"""E2E test for Epic -> Story Linking flow.

Self-contained: creates its own Epic and Stories via the API factory, links them
through the UI, and verifies the Epic detail page and Plan view.
"""

import pytest
from playwright.sync_api import Page, expect


class TestEpicStoryLinking:
    """Tests for Epic -> Story linking flow."""

    @pytest.fixture
    def epic_with_stories(self, make_ticket):
        """Create an Epic with 3 Story children (unlinked) via API."""
        epic = make_ticket(title="Epic: User Authentication", ticket_type="Epic")
        stories = [
            make_ticket(title=f"Story: Auth Part {i + 1}", ticket_type="Story") for i in range(3)
        ]
        return epic, stories

    def test_create_epic_and_stories_via_ui(self, page: Page, base_url: str, seeded_projects):
        """Test creating an Epic and Stories through the Backlog UI."""
        unique_epic = "UI Epic: Sign On"
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")

        # Create Epic ticket
        page.click("button:has-text('New Ticket'), a:has-text('New Ticket')")
        page.wait_for_selector("#ticket-modal form", state="visible", timeout=10000)

        page.fill("input[name='title']", unique_epic)
        page.select_option("select[name='type']", "Epic")
        page.select_option("select[name='priority']", "High")
        page.select_option("select[name='project_id']", "1")  # UNS project
        page.fill("textarea[name='description']", "Epic for sign-on system")

        page.click("button:has-text('Create Ticket')")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)

        # Epic appears in backlog
        expect(
            page.locator(f"#tickets-table-body tr:has-text('{unique_epic}')").first
        ).to_be_visible(timeout=10000)

        # Create 3 Story tickets
        for i in range(3):
            story_title = f"UI Story: Sign On Part {i + 1}"
            page.click("button:has-text('New Ticket'), a:has-text('New Ticket')")
            page.wait_for_selector("#ticket-modal form", state="visible", timeout=10000)

            page.fill("input[name='title']", story_title)
            page.select_option("select[name='type']", "Story")
            page.select_option("select[name='priority']", "Medium")
            page.select_option("select[name='project_id']", "1")
            page.fill("textarea[name='description']", f"Story {i + 1} description")

            page.click("button:has-text('Create Ticket')")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(1500)

            expect(
                page.locator(f"#tickets-table-body tr:has-text('{story_title}')").first
            ).to_be_visible(timeout=10000)

    def test_link_stories_to_epic(
        self, page: Page, base_url: str, seeded_projects, epic_with_stories
    ):
        """Link all 3 Stories as children of the Epic via the link modal."""
        epic, stories = epic_with_stories

        page.goto(f"{base_url}/ticket/{epic['id']}")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#ticket-content", state="visible", timeout=10000)

        for story in stories:
            # Open the link modal
            page.click("button:has-text('Add Link')")
            page.wait_for_selector("#ticket-modal form", state="visible", timeout=10000)

            # Epic is the parent; story is the child target
            page.select_option("select[name='link_type']", "parent")

            # Search for the story by its full ID prefix (UNS-NNN)
            story_ref = f"UNS-{story['number']:03d}"
            page.fill("input[name='target_search']", story_ref)
            # Wait for search result and click it (sets hidden target_id)
            page.wait_for_selector(".ticket-search-result", timeout=10000)
            page.click(".ticket-search-result >> nth=0")
            page.wait_for_timeout(300)

            # Submit the link
            page.click("#ticket-modal button[type='submit']")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(1000)

        # Reload the Epic page and verify all 3 children are shown
        page.goto(f"{base_url}/ticket/{epic['id']}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        for story in stories:
            story_ref = f"UNS-{story['number']:03d}"
            expect(page.locator("#links-section-container")).to_contain_text(story_ref)

    def test_epic_detail_shows_children(
        self, page: Page, base_url: str, seeded_projects, epic_with_stories
    ):
        """Epic detail page shows the Links section with children."""
        epic, stories = epic_with_stories
        # Link one story via API so the section has content
        import httpx

        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            client.post(
                f"/api/v1/tickets/{stories[0]['id']}/links",
                json={
                    "link_type": "parent",
                    "target_id": epic["id"],
                },
            )

        page.goto(f"{base_url}/ticket/{epic['id']}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        # Links section is visible and shows the child relationship
        expect(page.locator("#links-section-container")).to_be_visible()
        expect(page.locator("#links-section-container")).to_contain_text("child")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
