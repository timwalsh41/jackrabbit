"""Playwright fixtures for end-to-end tests."""

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

# Base URL for the test server
BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8080")


@pytest.fixture(scope="session")
def base_url() -> str:
    """Provide the base URL for e2e tests."""
    return BASE_URL


@pytest.fixture(scope="session")
def playwright() -> Generator[Playwright, None, None]:
    """Create a Playwright instance."""
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright: Playwright) -> Generator[Browser, None, None]:
    """Create a browser instance."""
    # Use chromium by default, but allow override
    browser_type = os.environ.get("PLAYWRIGHT_BROWSER", "chromium")
    if browser_type == "firefox":
        browser = playwright.firefox.launch(headless=True)
    elif browser_type == "webkit":
        browser = playwright.webkit.launch(headless=True)
    else:
        browser = playwright.chromium.launch(headless=True)
    yield browser
    browser.close()


@pytest.fixture
def browser_context(browser: Browser) -> Generator[BrowserContext, None, None]:
    """Create a browser context for each test."""
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        ignore_https_errors=True,
    )
    yield context
    context.close()


@pytest.fixture
def page(browser_context: BrowserContext) -> Generator[Page, None, None]:
    """Create a page for each test."""
    page = browser_context.new_page()
    # Set default timeout
    page.set_default_timeout(30000)
    yield page
    page.close()


@pytest.fixture
def authenticated_page(page: Page, client) -> Generator[Page, None, None]:
    """Create a page with authentication (if needed)."""
    # For now, no authentication is required
    # This fixture can be extended when auth is added
    yield page


# Fixtures for specific page objects
@pytest.fixture
def home_page(page: Page) -> Page:
    """Navigate to home page."""
    page.goto(f"{BASE_URL}/")
    page.wait_for_load_state("networkidle")
    return page


@pytest.fixture
def projects_page(page: Page) -> Page:
    """Navigate to projects page."""
    page.goto(f"{BASE_URL}/projects")
    page.wait_for_load_state("networkidle")
    return page


@pytest.fixture
def tickets_page(page: Page) -> Page:
    """Navigate to tickets page."""
    page.goto(f"{BASE_URL}/tickets")
    page.wait_for_load_state("networkidle")
    return page


@pytest.fixture
def sprints_page(page: Page) -> Page:
    """Navigate to sprints page."""
    page.goto(f"{BASE_URL}/sprints")
    page.wait_for_load_state("networkidle")
    return page


@pytest.fixture
def plan_page(page: Page) -> Page:
    """Navigate to plan page."""
    page.goto(f"{BASE_URL}/plan")
    page.wait_for_load_state("networkidle")
    return page


# Helper fixture to create test data via API
@pytest.fixture
def seeded_projects(e2e_test_data):
    """Get seeded projects for e2e tests."""
    return e2e_test_data["projects"]


@pytest.fixture
def make_ticket(base_url):
    """Factory that creates a ticket via API and optionally drives it to a target status.

    Returns the created ticket dict (includes "id"). Driving to a status uses the
    same transition API the UI calls, so guards (grooming fields, branch name, PR URL)
    are satisfied exactly as they would be in the real flow.
    """
    import uuid

    import httpx

    def _make(
        project_id: int = 1,
        title: str | None = None,
        ticket_type: str = "Story",
        priority: str = "Medium",
        status: str = "Open",
    ) -> dict:
        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            ticket = client.post(
                "/api/v1/tickets",
                json={
                    "project_id": project_id,
                    "title": title or f"E2E {uuid.uuid4().hex[:8]}",
                    "type": ticket_type,
                    "priority": priority,
                    "description": "Created by E2E test factory",
                },
            ).json()
            tid = ticket["id"]

            # Drive through the status chain up to the requested status.
            if status in ("Groomed", "In Progress", "Ready for Review", "Complete"):
                client.post(
                    f"/api/v1/tickets/{tid}/transition",
                    json={
                        "to_status": "Groomed",
                        "approach": "E2E approach",
                        "files_to_change": "file.py",
                        "test_plan": "unit tests",
                        "validation_steps": "run tests",
                    },
                )
            if status in ("In Progress", "Ready for Review", "Complete"):
                client.post(
                    f"/api/v1/tickets/{tid}/transition",
                    json={
                        "to_status": "In Progress",
                        "branch_name": f"feature/{ticket['number']:03d}-e2e",
                    },
                )
            if status in ("Ready for Review", "Complete"):
                client.post(
                    f"/api/v1/tickets/{tid}/transition",
                    json={
                        "to_status": "Ready for Review",
                        "pr_url": "https://github.com/test/repo/pull/123",
                    },
                )
            if status == "Complete":
                client.post(
                    f"/api/v1/tickets/{tid}/transition",
                    json={
                        "to_status": "Complete",
                        "reason": "merged",
                    },
                )

            # Re-fetch so the returned dict reflects the final status.
            return client.get(f"/api/v1/tickets/{tid}").json()

    return _make


@pytest.fixture
def make_sprint(base_url):
    """Factory that creates a sprint via API and returns the sprint dict."""
    import httpx

    def _make(number: int | None = None) -> dict:
        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            payload = {
                "name": "E2E Sprint",
                "description": "Created by E2E test factory",
            }
            if number is not None:
                payload["number"] = number
            # number omitted -> the API auto-assigns MAX(number)+1, which is
            # unique across runs since the server database persists
            return client.post("/api/v1/sprints", json=payload).json()

    return _make


@pytest.fixture(scope="session")
def e2e_test_data(base_url):
    """Create test data for e2e tests via HTTP API against running server."""
    import httpx

    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        # Check if projects already exist
        existing_projects = {p["prefix"]: p for p in client.get("/api/v1/projects").json()}

        # Create projects if they don't exist
        if "UNS" not in existing_projects:
            uns = client.post(
                "/api/v1/projects",
                json={
                    "prefix": "UNS",
                    "name": "Unsorted",
                    "description": "Default project",
                    "color": "#9ca3af",
                    "is_system": True,
                },
            ).json()
        else:
            uns = existing_projects["UNS"]

        if "WEB" not in existing_projects:
            web = client.post(
                "/api/v1/projects",
                json={
                    "prefix": "WEB",
                    "name": "Web Application",
                    "description": "Frontend app",
                    "color": "#6366f1",
                },
            ).json()
        else:
            web = existing_projects["WEB"]

        if "API" not in existing_projects:
            api = client.post(
                "/api/v1/projects",
                json={
                    "prefix": "API",
                    "name": "Backend API",
                    "description": "API service",
                    "color": "#10b981",
                },
            ).json()
        else:
            api = existing_projects["API"]

        # Create tickets
        tickets = []
        for project in [uns, web, api]:
            for i in range(3):
                ticket = client.post(
                    "/api/v1/tickets",
                    json={
                        "project_id": project["id"],
                        "title": f"Test Ticket {i + 1} for {project['prefix']}",
                        "type": "Story",
                        "priority": "Medium",
                        "description": f"Description for ticket {i + 1}",
                    },
                ).json()
                tickets.append(ticket)

        # Create sprints
        existing_sprints = {s["number"]: s for s in client.get("/api/v1/sprints").json()}

        if 2601 not in existing_sprints:
            sprint1 = client.post(
                "/api/v1/sprints",
                json={
                    "number": 2601,
                    "name": "Sprint 2601",
                    "description": "First sprint",
                },
            ).json()
        else:
            sprint1 = existing_sprints[2601]

        if 2602 not in existing_sprints:
            sprint2 = client.post(
                "/api/v1/sprints",
                json={
                    "number": 2602,
                    "name": "Sprint 2602",
                    "description": "Second sprint",
                },
            ).json()
        else:
            sprint2 = existing_sprints[2602]

        return {
            "projects": [uns, web, api],
            "tickets": tickets,
            "sprints": [sprint1, sprint2],
        }


# Fixture to run test server (if needed for standalone e2e)
@pytest.fixture(scope="session", autouse=True)
def test_server():
    """Start the test server for e2e tests."""
    import os
    import subprocess
    import time

    import httpx

    # Check if server is already running
    try:
        response = httpx.get(f"{BASE_URL}/health", timeout=2)
        if response.status_code == 200:
            yield BASE_URL
            return
    except Exception:
        pass

    # Start server in background (from the repo containing these tests, so a
    # worktree/checkout runs its own code and its own database)
    repo_root = str(Path(__file__).resolve().parents[2])
    env = os.environ.copy()
    env["DATABASE_URL"] = "sqlite:///./data/e2e_test.db"
    env["PORT"] = str(BASE_URL.split(":")[-1].split("/")[0]) if ":" in BASE_URL else "8080"

    proc = subprocess.Popen(
        ["uv", "run", "python", "-m", "jackrabbit.main"],
        env=env,
        cwd=repo_root,
    )

    # Wait for server to be ready
    for _ in range(30):
        try:
            response = httpx.get(f"{BASE_URL}/health", timeout=1)
            if response.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.5)
    else:
        proc.terminate()
        raise RuntimeError("Test server failed to start")

    yield BASE_URL

    proc.terminate()
    proc.wait(timeout=5)

    # Cleanup
    import os

    if os.path.exists("./data/e2e_test.db"):
        os.remove("./data/e2e_test.db")


# Browser-specific fixtures for different viewports
@pytest.fixture
def mobile_page(browser: Browser) -> Generator[Page, None, None]:
    """Create a mobile viewport page."""
    context = browser.new_context(
        viewport={"width": 375, "height": 667},
        is_mobile=True,
        has_touch=True,
    )
    page = context.new_page()
    page.set_default_timeout(30000)
    yield page
    context.close()


@pytest.fixture
def tablet_page(browser: Browser) -> Generator[Page, None, None]:
    """Create a tablet viewport page."""
    context = browser.new_context(
        viewport={"width": 768, "height": 1024},
        is_mobile=True,
        has_touch=True,
    )
    page = context.new_page()
    page.set_default_timeout(30000)
    yield page
    context.close()


# Utility functions for e2e tests
class E2EHelpers:
    """Helper methods for e2e tests."""

    @staticmethod
    def wait_for_api(page: Page, url_pattern: str, method: str = "GET") -> dict:
        """Wait for an API call and return its response."""
        with page.expect_response(
            lambda r: url_pattern in r.url and r.request.method == method
        ) as response_info:
            pass
        response = response_info.value
        return response.json()

    @staticmethod
    def fill_form(page: Page, form_data: dict) -> None:
        """Fill a form with the given data."""
        for field, value in form_data.items():
            # Try different selector strategies
            selector = f"input[name='{field}'], textarea[name='{field}'], select[name='{field}']"
            if page.locator(selector).count() > 0:
                page.fill(selector, str(value))
            else:
                # Try by label
                label_selector = (
                    f"label:has-text('{field}') + input, label:has-text('{field}') + textarea"
                )
                if page.locator(label_selector).count() > 0:
                    page.fill(label_selector, str(value))

    @staticmethod
    def click_and_wait(page: Page, selector: str, wait_for: str = "networkidle") -> None:
        """Click an element and wait for navigation/load."""
        page.click(selector)
        page.wait_for_load_state(wait_for)

    @staticmethod
    def get_table_rows(page: Page, table_selector: str = "table") -> list[dict]:
        """Extract data from a table."""
        rows = page.locator(f"{table_selector} tbody tr").all()
        data = []
        for row in rows:
            cells = row.locator("td").all()
            row_data = {}
            for i, cell in enumerate(cells):
                # Use header for key if available
                header = page.locator(f"{table_selector} th").nth(i)
                key = (
                    header.inner_text().strip().lower().replace(" ", "_")
                    if header.count() > i
                    else f"col_{i}"
                )
                row_data[key] = cell.inner_text().strip()
            data.append(row_data)
        return data


@pytest.fixture
def e2e_helpers() -> E2EHelpers:
    """Provide E2E helper methods."""
    return E2EHelpers()


# Chrome DevTools Protocol helper
@pytest.fixture
def cdp_session(page: Page):
    """Create a CDP session for advanced browser interactions."""
    return page.context.new_cdp_session(page)


@pytest.fixture
def console_errors(page: Page) -> list:
    """Capture console errors during test."""
    errors = []

    def handle_console(msg):
        if msg.type == "error":
            errors.append({"text": msg.text, "location": msg.location})

    page.on("console", handle_console)
    yield errors
    page.remove_listener("console", handle_console)


@pytest.fixture
def network_failures(page: Page) -> list:
    """Capture network failures during test."""
    failures = []

    def handle_response(response):
        if response.status >= 400:
            failures.append(
                {
                    "url": response.url,
                    "status": response.status,
                    "status_text": response.status_text,
                }
            )

    page.on("response", handle_response)
    yield failures
    page.remove_listener("response", handle_response)


# Screenshot utilities
@pytest.fixture
def screenshot_on_failure(request, page: Page):
    """Take screenshot on test failure."""
    yield
    if request.node.rep_call.failed:
        # Create screenshots directory
        screenshot_dir = Path("test-results/screenshots")
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        # Save screenshot
        filename = f"{request.node.name}.png"
        page.screenshot(path=str(screenshot_dir / filename), full_page=True)


# For async tests
@pytest.fixture
async def async_page(browser: Browser):
    """Create an async page for async tests."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        yield page
        await context.close()
        await browser.close()
