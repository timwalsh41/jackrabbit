"""E2E test for Backlog Filtering flow (ticket 15, flow 5).

The Backlog filter form applies filters only when submitted (via the Filter
button, an hx-get that swaps a fresh tbody into #tickets-table-body), so every
test selects its filters and clicks Filter before asserting.
"""

import pytest
from playwright.sync_api import Page, expect


class TestBacklogFilters:
    """Tests for backlog filtering flow."""

    @staticmethod
    def _apply(page: Page) -> None:
        """Submit the filter form and wait for the tbody swap."""
        page.click("button:has-text('Filter')")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(300)

    def test_filter_by_project(self, page: Page, base_url: str, seeded_projects, make_ticket):
        """Filtering by project shows only that project's tickets."""
        web = seeded_projects[1]
        in_web = make_ticket(project_id=web["id"], title="WEB Filter Member")
        in_uns = make_ticket(project_id=1, title="UNS Filter Member")

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        page.select_option("select[name='project_id']", str(web["id"]))
        self._apply(page)

        expect(page.locator(f"#ticket-row-{in_web['id']}")).to_be_visible(timeout=10000)
        assert page.locator(f"#ticket-row-{in_uns['id']}").count() == 0

    def test_filter_by_type(self, page: Page, base_url: str, seeded_projects, make_ticket):
        """Filtering by type shows only matching tickets."""
        story = make_ticket(title="Type Filter Story", ticket_type="Story")
        bug = make_ticket(title="Type Filter Bug", ticket_type="Bug")

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        page.select_option("select[name='type']", "Story")
        self._apply(page)

        expect(page.locator(f"#ticket-row-{story['id']}")).to_be_visible(timeout=10000)
        assert page.locator(f"#ticket-row-{bug['id']}").count() == 0

    def test_filter_by_status(self, page: Page, base_url: str, seeded_projects, make_ticket):
        """Filtering by status shows only matching tickets."""
        open_ticket = make_ticket(title="Status Filter Open", status="Open")
        groomed = make_ticket(title="Status Filter Groomed", status="Groomed")

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        page.select_option("select[name='status']", "Open")
        self._apply(page)

        expect(page.locator(f"#ticket-row-{open_ticket['id']}")).to_be_visible(timeout=10000)
        assert page.locator(f"#ticket-row-{groomed['id']}").count() == 0

    def test_filter_by_sprint(
        self, page: Page, base_url: str, seeded_projects, make_ticket, make_sprint
    ):
        """Filtering by sprint shows only that sprint's tickets."""
        import httpx

        sprint = make_sprint()
        member = make_ticket(title="Sprint Member Unique")
        outsider = make_ticket(title="Sprint Outsider Unique")
        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            resp = client.post(f"/api/v1/sprints/{sprint['id']}/tickets/{member['id']}")
            assert resp.status_code == 200

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        page.select_option("select[name='sprint_id']", str(sprint["id"]))
        self._apply(page)

        expect(page.locator(f"#ticket-row-{member['id']}")).to_be_visible(timeout=10000)
        assert page.locator(f"#ticket-row-{outsider['id']}").count() == 0

    def test_text_search(self, page: Page, base_url: str, seeded_projects, make_ticket):
        """Text search matches ticket titles (and nothing else)."""
        needle = make_ticket(title="Zebra Needle Ticket")
        other = make_ticket(title="Unrelated Hippo Ticket")

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        page.fill("input[name='q']", "Zebra Needle")
        self._apply(page)

        expect(page.locator(f"#ticket-row-{needle['id']}")).to_be_visible(timeout=10000)
        assert page.locator(f"#ticket-row-{other['id']}").count() == 0

    def test_combined_filters(self, page: Page, base_url: str, seeded_projects, make_ticket):
        """Combined filters use AND logic: only the fully matching ticket remains."""
        web = seeded_projects[1]
        match = make_ticket(
            project_id=web["id"], title="AND Match Combo", ticket_type="Story", status="Open"
        )
        # Same project+type but different status
        make_ticket(
            project_id=web["id"],
            title="AND Mismatch Status",
            ticket_type="Story",
            status="Groomed",
        )

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        page.select_option("select[name='project_id']", str(web["id"]))
        page.select_option("select[name='type']", "Story")
        page.select_option("select[name='status']", "Open")
        page.fill("input[name='q']", "AND Match Combo")
        self._apply(page)

        rows = page.locator("#tickets-table-body tr")
        assert rows.count() == 1, f"expected exactly 1 row, got {rows.count()}"
        expect(page.locator(f"#ticket-row-{match['id']}")).to_be_visible()

    def test_clear_filters(self, page: Page, base_url: str, seeded_projects):
        """Test clear filters button works."""
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")

        # Apply some filters
        page.select_option("select[name='project_id']", "2")
        page.select_option("select[name='type']", "Story")
        page.wait_for_load_state("networkidle")

        # Click Clear filters
        page.click("button:has-text('Clear'), a:has-text('Clear')")
        page.wait_for_load_state("networkidle")

        # Verify filters reset
        project_dropdown = page.locator("select[name='project_id']")
        expect(project_dropdown).to_have_value("")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
