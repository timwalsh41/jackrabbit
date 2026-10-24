"""E2E tests for the Jackrabbit application."""

from playwright.sync_api import Page, expect


class TestHomePage:
    """Tests for the home page (spec: GET / redirects to /backlog)."""

    def test_home_page_redirects_to_backlog(self, page: Page, base_url: str):
        """GET / must land on the backlog view (spec Web Routes)."""
        page.goto(base_url)
        expect(page).to_have_title("Jackrabbit - Backlog")
        expect(page.locator("nav")).to_be_visible()
        expect(page.locator("a[href*='projects']")).to_be_visible()


class TestProjectsPage:
    """Tests for the projects page."""

    def test_projects_page_loads(self, page: Page, base_url: str):
        """Test that the projects page loads."""
        page.goto(f"{base_url}/projects")
        expect(page).to_have_title("Projects - Jackrabbit")

    def test_projects_page_shows_create_button(self, page: Page, base_url: str):
        """Test that the projects page has a create project button."""
        page.goto(f"{base_url}/projects")
        expect(page.locator("a:has-text('New Project')")).to_be_visible()

    def test_create_project(self, page: Page, base_url: str):
        """Test creating a new project - just verify the form renders."""
        page.goto(f"{base_url}/projects")
        page.click("a:has-text('New Project')")
        expect(page.locator("input[name='prefix']")).to_be_visible()
        expect(page.locator("input[name='name']")).to_be_visible()
        expect(page.locator("textarea[name='description']")).to_be_visible()
        expect(page.locator("button[type='submit']:has-text('Create Project')")).to_be_visible()


class TestTicketsPage:
    """Tests for the tickets page."""

    def test_tickets_page_loads(self, page: Page, base_url: str, seeded_projects):
        """Test that the tickets page loads for a project (now via the backlog
        with ?project_id=, since the project-scoped route was removed)."""
        project = seeded_projects[0]
        page.goto(f"{base_url}/backlog?project_id={project['id']}")
        expect(page).to_have_title(f"Tickets - {project['name']} - Jackrabbit")

    def test_tickets_page_shows_create_button(self, page: Page, base_url: str, seeded_projects):
        """Test that the tickets page has a create ticket button."""
        project = seeded_projects[0]
        page.goto(f"{base_url}/backlog?project_id={project['id']}")
        expect(
            page.locator("button:has-text('New Ticket'), a:has-text('New Ticket')")
        ).to_be_visible()


class TestNavigation:
    """Tests for navigation between pages."""

    def test_navigate_home_to_projects(self, page: Page, base_url: str):
        """Test navigation from home to projects."""
        page.goto(base_url)
        page.click("nav a[href='/projects']")
        expect(page).to_have_url(f"{base_url}/projects")

    def test_navigate_projects_to_tickets(self, page: Page, base_url: str, seeded_projects):
        """Test navigation from projects to tickets (now via the project's
        "Tickets" link -> /backlog?project_id=)."""
        project = seeded_projects[0]
        page.goto(f"{base_url}/projects")
        page.click(f"a[href='/backlog?project_id={project['id']}']")
        expect(page).to_have_url(f"{base_url}/backlog?project_id={project['id']}")


class TestResponsiveDesign:
    """Tests for responsive design."""

    def test_mobile_viewport(self, mobile_page: Page, base_url: str):
        """Test that the site works on mobile viewport."""
        mobile_page.goto(base_url)
        expect(mobile_page.locator("nav")).to_be_visible()

    def test_tablet_viewport(self, tablet_page: Page, base_url: str):
        """Test that the site works on tablet viewport."""
        tablet_page.goto(base_url)
        expect(tablet_page.locator("nav")).to_be_visible()


class TestConsoleErrors:
    """Tests to ensure no console errors on page load."""

    def test_no_console_errors_on_home(self, page: Page, base_url: str, console_errors):
        """Test that the home page has no console errors."""
        page.goto(base_url)
        errors = [msg for msg in console_errors if msg.type == "error"]
        assert len(errors) == 0, f"Console errors found: {errors}"


class TestHealthEndpoint:
    """Test the health endpoint."""

    def test_health_endpoint(self, page: Page, base_url: str):
        """Test that the health endpoint returns 200."""
        response = page.request.get(f"{base_url}/health")
        assert response.ok
        assert response.json() == {"status": "ok"}
