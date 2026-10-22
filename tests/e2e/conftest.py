"""Playwright fixtures for end-to-end tests.

Options:
    --headed   Run the browser headed (default headless; also E2E_HEADED=1).
               Local usage: `pytest tests/e2e --headed`
    --cdx      Start a chrome-devtools-axi bridge alongside the tests so agents
               can attach to the same Chrome via the DevTools protocol for
               debugging (also CHROME_DEVTOOLS_AXI_ENABLED=1). Skipped cleanly
               when the `chrome-devtools-axi` binary is not installed.
"""

import os
import socket
import subprocess
import time
from collections.abc import Generator
from contextlib import closing
from pathlib import Path

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

# Repo containing these tests: the server is started from here so a
# worktree/checkout runs its own code (and, via its own temp DATA_DIR, its own
# database).
REPO_ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    """Return a port the OS just assigned to nothing.

    ADR-0020 makes ``PORT=0`` mean "pick a free port" so suites can run in
    parallel, but a detached uvicorn process cannot report the port it landed
    on, so we bind-and-release first and pass the number explicitly.
    """
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add e2e runner options."""
    group = parser.getgroup("jackrabbit-e2e")
    group.addoption(
        "--headed",
        action="store_true",
        default=False,
        help="Run the browser headed instead of headless (or set E2E_HEADED=1).",
    )
    group.addoption(
        "--cdx",
        action="store_true",
        default=False,
        help=(
            "Start a chrome-devtools-axi bridge for agent debugging via the "
            "DevTools protocol (or set CHROME_DEVTOOLS_AXI_ENABLED=1)."
        ),
    )


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every test in this directory `e2e`.

    Registering the marker without applying it bought nothing: `--strict-markers`
    only rejects *unknown* names, so the suite was still selected purely by path
    and `-m "not e2e"` matched no test. Marking from here keeps the whole
    directory selectable/deselectable from one place.
    """
    here = Path(__file__).resolve().parent
    for item in items:
        if here in Path(str(item.fspath)).resolve().parents:
            item.add_marker("e2e")


def _is_headed(request: pytest.FixtureRequest) -> bool:
    if request.config.getoption("--headed"):
        return True
    return os.environ.get("E2E_HEADED") == "1"


@pytest.fixture(scope="session")
def base_url(test_server: str) -> str:
    """Base URL of the server under test (owned by the ``test_server`` fixture)."""
    return test_server


@pytest.fixture(scope="session")
def headed(request: pytest.FixtureRequest) -> bool:
    """Whether the browser should run headed (--headed / E2E_HEADED=1)."""
    return _is_headed(request)


@pytest.fixture(scope="session")
def cdx_bridge(request: pytest.FixtureRequest, headed: bool):
    """Optional chrome-devtools-axi bridge for DevTools-protocol debugging.

    Only started when --cdx (or CHROME_DEVTOOLS_AXI_ENABLED=1) is requested;
    otherwise yields None so the suite stays independent of the CLI tool.
    """
    enabled = (
        request.config.getoption("--cdx") or os.environ.get("CHROME_DEVTOOLS_AXI_ENABLED") == "1"
    )
    if not enabled:
        yield None
        return

    try:
        from tests.cdx_helper import ChromeDevToolsAxi
    except ImportError:  # pragma: no cover - tests package always importable
        yield None
        return

    bridge = ChromeDevToolsAxi(headed=headed)
    try:
        bridge.start()
    except (FileNotFoundError, RuntimeError):
        # Agents may request cdx on machines without the tool; degrade gently
        # by continuing without the bridge (tests do not depend on it).
        yield None
        return
    yield bridge
    bridge.stop()


@pytest.fixture
def playwright() -> Generator[Playwright, None, None]:
    """Create a Playwright instance.

    Function-scoped on purpose: the sync API runs an asyncio loop on the main
    thread, and while a session-scoped instance stays alive that loop counts as
    "running", which breaks pytest-asyncio fixture setup for any async test
    that follows in the same pytest process (the full `pytest -x` gate mixes
    e2e and async integration tests). Closing it per test keeps the gate green.
    """
    with sync_playwright() as p:
        yield p


@pytest.fixture
def browser(playwright: Playwright, headed: bool) -> Generator[Browser, None, None]:
    """Create a browser instance (headed with --headed, headless by default)."""
    # Use chromium by default, but allow override
    browser_type = os.environ.get("PLAYWRIGHT_BROWSER", "chromium")
    if browser_type == "firefox":
        browser = playwright.firefox.launch(headless=not headed)
    elif browser_type == "webkit":
        browser = playwright.webkit.launch(headless=not headed)
    else:
        browser = playwright.chromium.launch(headless=not headed)
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
def authenticated_page(page: Page) -> Generator[Page, None, None]:
    """Create a page with authentication (if needed)."""
    # For now, no authentication is required
    # This fixture can be extended when auth is added
    yield page


# Fixtures for specific page objects
@pytest.fixture
def home_page(page: Page, base_url: str) -> Page:
    """Navigate to home page."""
    page.goto(f"{base_url}/")
    page.wait_for_load_state("networkidle")
    return page


@pytest.fixture
def projects_page(page: Page, base_url: str) -> Page:
    """Navigate to projects page."""
    page.goto(f"{base_url}/projects")
    page.wait_for_load_state("networkidle")
    return page


@pytest.fixture
def tickets_page(page: Page, base_url: str) -> Page:
    """Navigate to tickets page."""
    page.goto(f"{base_url}/tickets")
    page.wait_for_load_state("networkidle")
    return page


@pytest.fixture
def sprints_page(page: Page, base_url: str) -> Page:
    """Navigate to sprints page."""
    page.goto(f"{base_url}/sprints")
    page.wait_for_load_state("networkidle")
    return page


@pytest.fixture
def plan_page(page: Page, base_url: str) -> Page:
    """Navigate to plan page."""
    page.goto(f"{base_url}/plan")
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
def test_server(tmp_path_factory: pytest.TempPathFactory) -> Generator[str, None, None]:
    """Serve the app for the whole session on a throwaway database.

    Per ADR-0020 the suite owns its server. Every run gets a per-session
    ``DATA_DIR`` under pytest's temp root — never the developer's
    ``data/jackrabbit.db`` — and an ephemeral port, so two runs back to back
    see identical empty state. The previous fixture hardcoded
    ``sqlite:///./data/e2e_test.db`` (so run N+1 inherited run N's tickets and
    numbering-dependent tests failed) and only deleted the main file on
    teardown, orphaning the ``-wal``/``-shm`` sidecars in ``data/``.

    ``E2E_BASE_URL`` opts out: a server already answering there is reused
    as-is, and its port is also honoured when the fixture starts its own.
    """
    import httpx

    def _healthy(url: str) -> bool:
        try:
            return httpx.get(f"{url}/health", timeout=2).status_code == 200
        except Exception:
            return False

    override = os.environ.get("E2E_BASE_URL")
    if override:
        if _healthy(override.rstrip("/")):
            yield override.rstrip("/")
            return
        port = httpx.URL(override).port or 8080
    else:
        port = _free_port()

    url = f"http://127.0.0.1:{port}"
    data_dir = tmp_path_factory.mktemp("e2e-data")
    log_path = data_dir / "server.log"

    # Inherit the ambient environment, then pin the settings that would
    # otherwise steer the server onto the developer's real database or a
    # fixed port. Popping DATABASE_URL is not enough: pydantic-settings also
    # reads the repo's .env file, so the server could still start against
    # sqlite:///./data/jackrabbit.db (seen live in the JRB-001 run). Set the
    # env var explicitly instead — env vars outrank dotenv files in Settings
    # precedence (see jackrabbit/config.py).
    env = os.environ.copy()
    env.update(
        {
            "DATA_DIR": str(data_dir),
            "DATABASE_URL": f"sqlite:///{data_dir}/jackrabbit.db",
            "PORT": str(port),
            "ENVIRONMENT": "test",
            "LOG_LEVEL": "WARNING",
        }
    )

    with log_path.open("wb") as log_file:
        proc = subprocess.Popen(
            ["uv", "run", "python", "-m", "jackrabbit.main"],
            env=env,
            cwd=REPO_ROOT,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        try:
            ready = False
            for _ in range(60):
                if _healthy(url):
                    ready = True
                    break
                if proc.poll() is not None:  # exited early: no point waiting
                    break
                time.sleep(0.5)
            if not ready:
                if proc.poll() is None:
                    proc.terminate()
                raise RuntimeError(
                    f"e2e test server failed to start on {url} "
                    f"(database under {data_dir}); server log:\n"
                    f"{log_path.read_text(errors='replace')[-2000:]}"
                )
            # Hermeticity check (JRB-006): init_db() runs in the server's
            # lifespan, so by the time /health answers the database must exist
            # in the throwaway data dir. If it doesn't, the server's settings
            # were redirected elsewhere (e.g. a .env we failed to outrank) and
            # running the suite could mutate the developer's real database.
            if not (data_dir / "jackrabbit.db").exists():
                proc.terminate()
                raise RuntimeError(
                    f"e2e server is not using its throwaway database: expected "
                    f"{data_dir}/jackrabbit.db to exist after startup. "
                    f"Refusing to run tests against an unknown database; "
                    f"server log:\n"
                    f"{log_path.read_text(errors='replace')[-2000:]}"
                )
            yield url
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:  # pragma: no cover - hung server
                    proc.kill()
                    proc.wait(timeout=5)

    # `data_dir` is owned by pytest's tmp_path_factory, so the SQLite file and
    # its WAL sidecars disappear with the run — nothing is written to ./data.


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
