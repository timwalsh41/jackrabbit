"""E2E test for Backlog Filtering flow."""

import pytest
from playwright.sync_api import Page, expect


class TestBacklogFilters:
    """Tests for backlog filtering flow."""

    def test_filter_by_project(self, page: Page, base_url: str, seeded_projects):
        """Test filtering tickets by project."""
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")

        # Select WEB project from dropdown
        page.select_option("select[name='project_id']", "2")  # WEB project
        page.wait_for_load_state("networkidle")

        # Verify only WEB tickets shown
        project_cells = page.locator(".project-cell").all()
        for cell in project_cells:
            expect(cell).to_have_text("WEB")

    def test_filter_by_type(self, page: Page, base_url: str, seeded_projects):
        """Test filtering tickets by type."""
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")

        # Select Story type
        page.select_option("select[name='type']", "Story")
        page.wait_for_load_state("networkidle")

        # Verify only Story tickets shown
        type_cells = page.locator(".type-cell").all()
        for cell in type_cells:
            expect(cell).to_have_text("Story")

    def test_filter_by_status(self, page: Page, base_url: str, seeded_projects):
        """Test filtering tickets by status."""
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")

        # Select Open status
        page.select_option("select[name='status']", "Open")
        page.wait_for_load_state("networkidle")

        # Verify only Open tickets shown
        status_cells = page.locator(".status-cell").all()
        for cell in status_cells:
            expect(cell).to_have_text("Open")

    def test_filter_by_sprint(self, page: Page, base_url: str, seeded_projects):
        """Test filtering tickets by sprint."""
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")

        # Select a sprint if available
        sprint_dropdown = page.locator("select[name='sprint_id']")
        if sprint_dropdown.count() > 0:
            options = sprint_dropdown.locator("option").all()
            if len(options) > 1:
                page.select_option("select[name='sprint_id']", options[1].get_attribute("value"))
                page.wait_for_load_state("networkidle")

    def test_text_search(self, page: Page, base_url: str, seeded_projects):
        """Test text search in backlog."""
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")

        # Search for a ticket title
        page.fill("input[name='q']", "Test")
        page.wait_for_load_state("networkidle")

        # Verify results contain search term
        title_cells = page.locator(".title-cell").all()
        for cell in title_cells:
            text = cell.inner_text()
            assert "Test" in text or "test" in text.lower()

    def test_combined_filters(self, page: Page, base_url: str, seeded_projects):
        """Test combined filters (AND logic)."""
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")

        # Apply multiple filters
        page.select_option("select[name='project_id']", "2")
        page.select_option("select[name='type']", "Story")
        page.select_option("select[name='status']", "Open")
        page.wait_for_load_state("networkidle")

        # Verify all filters applied
        project_cells = page.locator(".project-cell").all()
        type_cells = page.locator(".type-cell").all()
        status_cells = page.locator(".status-cell").all()

        for cell in project_cells:
            expect(cell).to_have_text("WEB")
        for cell in type_cells:
            expect(cell).to_have_text("Story")
        for cell in status_cells:
            expect(cell).to_have_text("Open")

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
