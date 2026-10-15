"""Helper module for chrome-devtools-axi integration with Playwright tests."""

import json
import os
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page


class ChromeDevToolsAxi:
    """Wrapper for chrome-devtools-axi CLI commands."""

    def __init__(
        self,
        port: int = 9224,
        session: str = "default",
        headed: bool = False,
        channel: str = "stable",
        browser_url: str | None = None,
        user_data_dir: str | None = None,
        chrome_args: str | None = None,
        mcp_path: str | None = None,
    ):
        self.port = port
        self.session = session
        self.headed = headed
        self.channel = channel
        self.browser_url = browser_url
        self.user_data_dir = user_data_dir
        self.chrome_args = chrome_args
        self.mcp_path = mcp_path
        self._process: subprocess.Popen | None = None
        self._bridge_ready = False

    def _env(self) -> dict[str, str]:
        """Build environment variables for chrome-devtools-axi."""
        env = os.environ.copy()
        env["CHROME_DEVTOOLS_AXI_PORT"] = str(self.port)
        env["CHROME_DEVTOOLS_AXI_SESSION"] = self.session
        if self.headed:
            env["CHROME_DEVTOOLS_AXI_HEADED"] = "1"
        env["CHROME_DEVTOOLS_AXI_CHANNEL"] = self.channel
        if self.browser_url:
            env["CHROME_DEVTOOLS_AXI_BROWSER_URL"] = self.browser_url
        if self.user_data_dir:
            env["CHROME_DEVTOOLS_AXI_USER_DATA_DIR"] = self.user_data_dir
        if self.chrome_args:
            env["CHROME_DEVTOOLS_AXI_CHROME_ARGS"] = self.chrome_args
        if self.mcp_path:
            env["CHROME_DEVTOOLS_AXI_MCP_PATH"] = self.mcp_path
        return env

    def start(self, timeout: int = 30000) -> None:
        """Start the chrome-devtools-axi bridge."""
        if self._process is not None:
            return

        env = self._env()
        # Use "run" command which starts the bridge and keeps it running
        self._process = subprocess.Popen(
            ["chrome-devtools-axi", "run"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for bridge to be ready
        start_time = time.time()
        while time.time() - start_time < timeout / 1000:
            try:
                # Try to connect via the HTTP endpoint
                import urllib.request

                response = urllib.request.urlopen(
                    f"http://localhost:{self.port}/json/version", timeout=1
                )
                if response.status == 200:
                    self._bridge_ready = True
                    break
            except Exception:
                pass
            time.sleep(0.2)

        if not self._bridge_ready:
            self.stop()
            raise RuntimeError(f"chrome-devtools-axi bridge failed to start on port {self.port}")

    def stop(self) -> None:
        """Stop the chrome-devtools-axi bridge."""
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
            self._process = None
            self._bridge_ready = False

    def run_command(self, command: str, args: list[str] = None) -> dict[str, Any]:
        """Run a chrome-devtools-axi command and return parsed JSON output."""
        if not self._bridge_ready:
            self.start()

        cmd = ["chrome-devtools-axi", command]
        if args:
            cmd.extend(args)

        env = self._env()
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            raise RuntimeError(f"chrome-devtools-axi {command} failed: {result.stderr}")

        # Try to parse as JSON
        try:
            return json.loads(result.stdout) if result.stdout.strip() else {}
        except json.JSONDecodeError:
            return {"raw_output": result.stdout}

    def open(self, url: str) -> dict[str, Any]:
        """Open a URL in the browser."""
        return self.run_command("open", [url])

    def snapshot(self) -> dict[str, Any]:
        """Take a snapshot of the current page."""
        return self.run_command("snapshot")

    def screenshot(self, path: str) -> dict[str, Any]:
        """Take a screenshot and save to path."""
        return self.run_command("screenshot", [path])

    def click(self, selector: str) -> dict[str, Any]:
        """Click an element by selector."""
        return self.run_command("click", [selector])

    def fill(self, selector: str, text: str) -> dict[str, Any]:
        """Fill an input element."""
        return self.run_command("fill", [selector, text])

    def type(self, text: str) -> dict[str, Any]:
        """Type text."""
        return self.run_command("type", [text])

    def press(self, key: str) -> dict[str, Any]:
        """Press a key."""
        return self.run_command("press", [key])

    def wait(self, ms_or_text: str) -> dict[str, Any]:
        """Wait for milliseconds or text to appear."""
        return self.run_command("wait", [ms_or_text])

    def eval(self, js: str) -> dict[str, Any]:
        """Evaluate JavaScript in the page."""
        return self.run_command("eval", [js])

    def console(self) -> dict[str, Any]:
        """Get console messages."""
        return self.run_command("console")

    def network(self) -> dict[str, Any]:
        """Get network requests."""
        return self.run_command("network")

    def lighthouse(self) -> dict[str, Any]:
        """Run Lighthouse audit."""
        return self.run_command("lighthouse")

    def perf_start(self) -> dict[str, Any]:
        """Start performance tracing."""
        return self.run_command("perf-start")

    def perf_stop(self) -> dict[str, Any]:
        """Stop performance tracing."""
        return self.run_command("perf-stop")

    def perf_insight(self, set_name: str, name: str) -> dict[str, Any]:
        """Get performance insight."""
        return self.run_command("perf-insight", [set_name, name])

    def heap_snapshot(self, path: str) -> dict[str, Any]:
        """Take a heap snapshot."""
        return self.run_command("heap", [path])

    def pages(self) -> dict[str, Any]:
        """List all pages."""
        return self.run_command("pages")

    def new_page(self, url: str) -> dict[str, Any]:
        """Create a new page."""
        return self.run_command("newpage", [url])

    def select_page(self, page_id: str) -> dict[str, Any]:
        """Select a page by ID."""
        return self.run_command("selectpage", [page_id])

    def close_page(self, page_id: str) -> dict[str, Any]:
        """Close a page by ID."""
        return self.run_command("closepage", [page_id])

    def resize(self, width: int, height: int) -> dict[str, Any]:
        """Resize the browser window."""
        return self.run_command("resize", [str(width), str(height)])

    def emulate(self, device: str) -> dict[str, Any]:
        """Emulate a device."""
        return self.run_command("emulate", [device])

    def dialog(self, action: str) -> dict[str, Any]:
        """Handle a dialog (accept/dismiss)."""
        return self.run_command("dialog", [action])

    def upload(self, selector: str, path: str) -> dict[str, Any]:
        """Upload a file."""
        return self.run_command("upload", [selector, path])

    def hover(self, selector: str) -> dict[str, Any]:
        """Hover over an element."""
        return self.run_command("hover", [selector])

    def drag(self, from_selector: str, to_selector: str) -> dict[str, Any]:
        """Drag from one element to another."""
        return self.run_command("drag", [from_selector, to_selector])

    def scroll(self, direction: str) -> dict[str, Any]:
        """Scroll the page."""
        return self.run_command("scroll", [direction])

    def back(self) -> dict[str, Any]:
        """Navigate back."""
        return self.run_command("back")

    def fill_form(self, **fields) -> dict[str, Any]:
        """Fill a form with multiple fields."""
        args = []
        for key, value in fields.items():
            args.append(f"{key}={value}")
        return self.run_command("fillform", args)


@contextmanager
def chrome_devtools_axi(
    port: int = 9224,
    session: str = "default",
    headed: bool = False,
    channel: str = "stable",
    browser_url: str | None = None,
    user_data_dir: str | None = None,
    chrome_args: str | None = None,
    mcp_path: str | None = None,
) -> ChromeDevToolsAxi:
    """Context manager for chrome-devtools-axi bridge."""
    bridge = ChromeDevToolsAxi(
        port=port,
        session=session,
        headed=headed,
        channel=channel,
        browser_url=browser_url,
        user_data_dir=user_data_dir,
        chrome_args=chrome_args,
        mcp_path=mcp_path,
    )
    try:
        bridge.start()
        yield bridge
    finally:
        bridge.stop()


class PlaywrightCDPHelper:
    """Helper for combining Playwright with Chrome DevTools Protocol via chrome-devtools-axi."""

    def __init__(self, page: Page, cdp_port: int = 9224):
        self.page = page
        self.cdp_port = cdp_port
        self._cdp_session = None

    async def connect_cdp(self):
        """Connect to the browser via CDP."""
        # Create a CDP session through Playwright
        self._cdp_session = await self.page.context.new_cdp_session(self.page)
        return self._cdp_session

    async def send_cdp_command(self, method: str, params: dict = None) -> dict:
        """Send a raw CDP command."""
        if self._cdp_session is None:
            await self.connect_cdp()
        return await self._cdp_session.send(method, params or {})

    async def get_performance_metrics(self) -> dict:
        """Get performance metrics via CDP."""
        await self.send_cdp_command("Performance.enable")
        return await self.send_cdp_command("Performance.getMetrics")

    async def get_console_messages(self) -> list:
        """Get console messages via CDP."""
        await self.send_cdp_command("Log.enable")
        # Note: CDP doesn't have a direct "get messages" command
        # Messages are received via events
        return []

    async def take_heap_snapshot(self, filepath: str) -> dict:
        """Take a heap snapshot via CDP."""
        await self.send_cdp_command("HeapProfiler.enable")
        result = await self.send_cdp_command(
            "HeapProfiler.takeHeapSnapshot", {"reportProgress": False}
        )
        # The snapshot is saved to the browser's default location
        # We'd need to retrieve it via the file system
        return result

    async def start_tracing(self, categories: list[str] = None) -> None:
        """Start tracing via CDP."""
        await self.send_cdp_command(
            "Tracing.start",
            {
                "categories": ",".join(categories) if categories else "*",
            },
        )

    async def stop_tracing(self, filepath: str) -> dict:
        """Stop tracing and save to file."""
        result = await self.send_cdp_command("Tracing.end")
        # Save trace data
        trace_data = await self.send_cdp_command("Tracing.getTraceChunks")
        with open(filepath, "w") as f:
            json.dump(trace_data, f)
        return result

    async def get_network_log(self) -> list:
        """Get network log via CDP."""
        await self.send_cdp_command("Network.enable")
        # Network events are received via events
        # This would need event listeners
        return []


def run_lighthouse_audit(url: str, output_path: str | None = None, port: int = 9224) -> dict:
    """Run a Lighthouse audit on a URL using chrome-devtools-axi."""
    with chrome_devtools_axi(port=port) as bridge:
        bridge.open(url)
        time.sleep(2)  # Wait for page load
        result = bridge.lighthouse()

        if output_path:
            Path(output_path).write_text(json.dumps(result, indent=2))

        return result


def capture_performance_trace(
    url: str, output_path: str, port: int = 9224, duration_ms: int = 5000
) -> dict:
    """Capture a performance trace for a URL."""
    with chrome_devtools_axi(port=port) as bridge:
        bridge.open(url)
        bridge.perf_start()
        time.sleep(duration_ms / 1000)
        result = bridge.perf_stop()

        # Save trace
        trace_data = bridge.eval("() => JSON.stringify(performance.getEntriesByType('navigation'))")
        Path(output_path).write_text(
            json.dumps({"trace": result, "navigation": trace_data}, indent=2)
        )

        return result


def capture_heap_snapshot(url: str, output_path: str, port: int = 9224) -> dict:
    """Capture a heap snapshot for a URL."""
    with chrome_devtools_axi(port=port) as bridge:
        bridge.open(url)
        time.sleep(2)
        result = bridge.heap_snapshot(output_path)
        return result


# Pytest fixtures for chrome-devtools-axi
@pytest.fixture(scope="session")
def cdx_bridge():
    """Provide a chrome-devtools-axi bridge for the test session."""
    bridge = ChromeDevToolsAxi()
    bridge.start()
    yield bridge
    bridge.stop()


@pytest.fixture
def cdx_bridge_port():
    """Provide a unique port for each test that needs chrome-devtools-axi."""
    import random

    # Use a port in the range 9225-9250 to avoid conflicts
    return 9224 + random.randint(1, 25)


@pytest.fixture
def cdx_bridge_per_test(cdx_bridge_port):
    """Provide a fresh chrome-devtools-axi bridge per test."""
    bridge = ChromeDevToolsAxi(port=cdx_bridge_port)
    bridge.start()
    yield bridge
    bridge.stop()


# Utility functions for common testing patterns
def wait_for_element(cdx: ChromeDevToolsAxi, selector: str, timeout: int = 5000) -> dict:
    """Wait for an element to appear using chrome-devtools-axi."""
    return cdx.eval(f"""
        () => {{
            return new Promise((resolve, reject) => {{
                const timeoutId = setTimeout(() => reject(new Error('Timeout')), {timeout});
                const observer = new MutationObserver(() => {{
                    const el = document.querySelector('{selector}');
                    if (el) {{
                        clearTimeout(timeoutId);
                        observer.disconnect();
                        resolve(el);
                    }}
                }});
                observer.observe(document.body, {{ childList: true, subtree: true }});
                // Check immediately
                const el = document.querySelector('{selector}');
                if (el) {{
                    clearTimeout(timeoutId);
                    observer.disconnect();
                    resolve(el);
                }}
            }});
        }}
    """)


def get_element_text(cdx: ChromeDevToolsAxi, selector: str) -> str:
    """Get text content of an element."""
    result = cdx.eval(f"() => document.querySelector('{selector}')?.textContent || ''")
    return result.get("raw_output", "").strip('"')


def get_element_attribute(cdx: ChromeDevToolsAxi, selector: str, attribute: str) -> str:
    """Get an attribute of an element."""
    result = cdx.eval(
        f"() => document.querySelector('{selector}')?.getAttribute('{attribute}') || ''"
    )
    return result.get("raw_output", "").strip('"')


def execute_async_js(cdx: ChromeDevToolsAxi, js: str) -> dict:
    """Execute async JavaScript and wait for promise resolution."""
    return cdx.eval(f"() => (async () => {{ {js} }})()")


# Integration with Playwright's test fixtures
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "cdx: mark test as requiring chrome-devtools-axi")
    config.addinivalue_line("markers", "lighthouse: mark test as running Lighthouse audit")
    config.addinivalue_line("markers", "performance: mark test as performance test")


# Helper for running chrome-devtools-axi commands from within Playwright tests
class CDXPageHelper:
    """Helper to run chrome-devtools-axi commands alongside Playwright page."""

    def __init__(self, page: Page, bridge: ChromeDevToolsAxi):
        self.page = page
        self.bridge = bridge

    def open_and_wait(self, url: str, wait_for: str = "networkidle") -> None:
        """Open URL with chrome-devtools-axi and wait with Playwright."""
        self.bridge.open(url)
        self.page.goto(url)
        self.page.wait_for_load_state(wait_for)

    def cdp_eval(self, js: str) -> dict:
        """Evaluate JS via chrome-devtools-axi (bypasses Playwright's context)."""
        return self.bridge.eval(js)

    def cdp_click(self, selector: str) -> dict:
        """Click via chrome-devtools-axi."""
        return self.bridge.click(selector)

    def cdp_screenshot(self, path: str) -> dict:
        """Take screenshot via chrome-devtools-axi."""
        return self.bridge.screenshot(path)

    def cdp_console(self) -> dict:
        """Get console via chrome-devtools-axi."""
        return self.bridge.console()

    def cdp_network(self) -> dict:
        """Get network via chrome-devtools-axi."""
        return self.bridge.network()


@pytest.fixture
def cdx_page_helper(page: Page, cdx_bridge_per_test: ChromeDevToolsAxi) -> CDXPageHelper:
    """Provide a CDX page helper for tests."""
    return CDXPageHelper(page, cdx_bridge_per_test)
