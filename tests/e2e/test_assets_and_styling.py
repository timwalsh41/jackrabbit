"""E2E proof that the UI renders from local assets, offline-capable.

Complements tests/unit/test_static_assets.py (which reads the templates). These
checks run in a real browser, so they catch the failure mode the DOM-only suite
could not: a stylesheet that 404s or a CDN that is unreachable still leaves the
markup intact and text assertions passing, while every page renders unstyled.
"""

from urllib.parse import urlparse

import pytest
from playwright.sync_api import Page, Response, expect

LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]", "testserver"}

# Tailwind v3 defaults asserted here: bg-gray-50 (#f9fafb) on <body>,
# bg-indigo-600 (#4f46e5) on .btn-primary.
BODY_BG = "rgb(249, 250, 251)"
INDIGO_600 = "rgb(79, 70, 229)"

# Reports any element that is laid out, empty, and covers (almost) the whole
# viewport -- i.e. an invisible sheet sitting between the user and the page.
FULL_VIEWPORT_SCAN = """() => Array.from(document.querySelectorAll('body *'))
    .filter(el => {
        const s = getComputedStyle(el);
        if (s.display === 'none' || s.visibility === 'hidden') return false;
        if (s.position !== 'fixed') return false;
        const r = el.getBoundingClientRect();
        return el.childElementCount === 0
            && r.width >= window.innerWidth * 0.9
            && r.height >= window.innerHeight * 0.9;
    })
    .map(el => `${el.tagName}#${el.id}.${el.className}`)"""


def _off_hosts(urls: list[str]) -> list[str]:
    return [
        url
        for url in urls
        if urlparse(url).scheme in {"http", "https"} and urlparse(url).hostname not in LOCAL_HOSTS
    ]


class TestNoExternalRequests:
    def test_every_request_goes_to_the_app(
        self, page: Page, base_url: str, seeded_projects
    ) -> None:
        """A page load must not reach out to any third-party host."""
        seen: list[str] = []
        page.context.on("request", lambda request: seen.append(request.url))

        for path in ("/backlog", "/projects", "/sprints", "/plan"):
            page.goto(f"{base_url}{path}")
            page.wait_for_load_state("networkidle")

        offenders = _off_hosts(seen)
        assert offenders == [], f"browser fetched non-local assets: {offenders}"
        assert any("/static/css/tailwind.css" in url for url in seen), (
            "the built stylesheet was never requested"
        )

    @pytest.mark.parametrize("path", ["/backlog", "/projects", "/plan"])
    def test_no_failed_subresources(self, page: Page, base_url: str, path: str) -> None:
        """A 404'd <link>/<script> is otherwise invisible to text assertions."""
        failures: list[str] = []

        def _record(response: Response) -> None:
            if response.status >= 400:
                failures.append(f"{response.status} {response.url}")

        page.on("response", _record)
        page.goto(f"{base_url}{path}")
        page.wait_for_load_state("networkidle")
        assert failures == [], f"page load produced failed requests: {failures}"


class TestStylingIsApplied:
    def test_stylesheet_parsed_and_populated(self, page: Page, base_url: str) -> None:
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        rule_count = page.evaluate(
            """() => Array.from(document.styleSheets)
                   .reduce((total, sheet) => total + (sheet.cssRules?.length ?? 0), 0)"""
        )
        assert rule_count > 200, f"only {rule_count} CSS rules loaded — stylesheet missing or empty"

    def test_body_background_and_button_are_styled(self, page: Page, base_url: str) -> None:
        """Concrete computed styles: proves Tailwind utilities actually applied."""
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")

        assert page.evaluate("() => getComputedStyle(document.body).backgroundColor") == BODY_BG
        primary = page.locator(".btn-primary").first
        expect(primary).to_be_visible()
        assert primary.evaluate("el => getComputedStyle(el).backgroundColor") == INDIGO_600, (
            ".btn-primary is unstyled — build the CSS or check frontend/input.css"
        )
        assert primary.evaluate("el => getComputedStyle(el).display") in {
            "inline-flex",
            "flex",
        }, "a flex item is blockified, so either is correct once CSS applies"

    def test_htmx_and_json_enc_extension_are_available(self, page: Page, base_url: str) -> None:
        """Vendored htmx replaces the CDN copy; interactions depend on both files."""
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        expect(page.locator("#tickets-table-body")).to_be_attached()

        assert page.evaluate("() => typeof window.htmx === 'object'") is True
        assert page.evaluate("() => htmx.version") == "1.9.10"
        # defineExtension is the API the vendored json-enc.js calls at load time.
        assert page.evaluate("() => typeof htmx.defineExtension === 'function'") is True
        scripts = page.evaluate("() => Array.from(document.scripts).map(s => s.src)")
        assert any("/static/vendor/htmx.min.js" in src for src in scripts), (
            f"htmx is not loaded from /static: {scripts}"
        )
        assert any("/static/vendor/htmx-json-enc.js" in src for src in scripts), (
            f"json-enc extension is not loaded — form posts would not send JSON: {scripts}"
        )


class TestNoPhantomOverlay:
    """Guards the bug class the missing stylesheet had been hiding.

    An empty modal mount carrying ``fixed inset-0 z-50`` is harmless while no CSS
    loads, but covers the whole viewport and swallows every click once styling is
    applied -- and DOM/text assertions cannot see any of it.
    """

    @pytest.mark.parametrize("path", ["/backlog", "/projects", "/sprints", "/plan"])
    def test_no_full_viewport_element_covers_the_page_at_load(
        self, page: Page, base_url: str, path: str
    ) -> None:
        page.goto(f"{base_url}{path}")
        page.wait_for_load_state("networkidle")

        offenders = page.evaluate(FULL_VIEWPORT_SCAN)
        assert offenders == [], f"empty full-viewport overlays block clicks: {offenders}"

    def test_ticket_detail_has_no_phantom_overlay(
        self, page: Page, base_url: str, make_ticket
    ) -> None:
        """Ticket detail is the page that carried the empty overlay mount."""
        ticket = make_ticket(status="Open")
        page.goto(f"{base_url}/ticket/{ticket['id']}")
        page.wait_for_load_state("networkidle")

        offenders = page.evaluate(FULL_VIEWPORT_SCAN)
        assert offenders == [], f"empty full-viewport overlays block clicks: {offenders}"

    def test_ticket_detail_action_button_receives_the_click(
        self, page: Page, base_url: str, make_ticket
    ) -> None:
        """The modal-trigger button must get the click, and open the dialog.

        Targets "Groomed →" deliberately: the other button on an Open ticket is
        "Rejected", which is a direct transition behind a window.prompt().
        """
        ticket = make_ticket(status="Open")
        page.goto(f"{base_url}/ticket/{ticket['id']}")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#transition-buttons button", state="visible", timeout=10000)

        button = page.locator("#transition-buttons button:has-text('Groomed')")
        expect(button).to_have_count(1)
        box = button.bounding_box()
        assert box is not None, "transition button has no layout box"
        topmost = page.evaluate(
            """([x, y]) => {
                   const el = document.elementFromPoint(x, y);
                   return el ? el.tagName : 'null';
               }""",
            [box["x"] + box["width"] / 2, box["y"] + box["height"] / 2],
        )
        assert topmost == "BUTTON", f"clicks at that point land on {topmost}, not the action button"

        button.click(timeout=5000)
        # The dialog arrives asynchronously over htmx; expect() retries, and the
        # mount collapses to zero height (its dialog is position:fixed), so the
        # form is the observable contract here.
        expect(page.locator("#ticket-modal form")).to_be_visible()
        # ...and the :empty guard must have lifted once content arrived
        assert (
            page.evaluate("() => getComputedStyle(document.getElementById('ticket-modal')).display")
            != "none"
        ), ":empty guard still applies with a dialog in the mount"
