"""End-to-end coverage for markdown rendering of the ticket description (JRB-009).

AGENTS.md requires **appropriate and complementary unit AND end-to-end** test
coverage for any new feature or fix. The JRB-009 commit that enabled
``@tailwindcss/typography`` (so the ``prose`` class actually styles a rendered
description) only added a unit-level CSS-text grep —
``test_static_assets.py::TestTailwindBuildIsCurrent::test_stylesheet_ships_typography_for_markdown_description``
— which reads the built stylesheet and asserts the ``prose`` strings are
present. That guard is necessary but not sufficient: it passes even when the
``prose`` class never makes it onto the rendered element, or when the
stylesheet 404s in the browser.

The JRB-009 bug itself was *browser-visible*: with only Tailwind preflight
(no typography plugin) the description's ``<h1>``/``<ul>`` existed in the DOM
but were stylistically hidden (``h1..h6`` got ``font-size:inherit`` and
``ul/ol`` got ``list-style:none``), while ``<code>``/``<strong>`` kept their
browser defaults — so headings/lists "did not render" while code/bold did. A
unit test that greps the CSS file or asserts element presence in a string
cannot catch that; only a real browser reading computed styles can.

These tests drive Playwright at the ticket detail page to prove that a
markdown description renders as visible, correctly-styled HTML and stays
XSS-safe end-to-end.
"""

import httpx
import pytest
from playwright.sync_api import Page, expect

# A description exercising every supported markdown construct. The link URL is
# kept free of raw "&" so the assertions target the rendering/typography
# behavior this ticket owns (the renderer's unit tests cover URL-encoding edge
# cases); the URL is still asserted as a safe, real anchor.
MARKDOWN_DESCRIPTION = (
    "# Feature Spec\n"
    "\n"
    "A paragraph with **bold**, *italic*, and `inline code`, plus a "
    "[link](https://example.com/feature-spec).\n"
    "\n"
    "- bullet one\n"
    "- bullet two\n"
    "- bullet three\n"
    "\n"
    "1. first step\n"
    "2. second step\n"
    "\n"
    "```\n"
    "SELECT 1;\n"
    "```\n"
    "\n"
    "malicious <script>alert('xss')</script> must be escaped\n"
)


@pytest.fixture
def markdown_ticket(base_url, seeded_projects):
    """An Open ticket whose description is a markdown document.

    Created via the API (mirrors the httpx pattern in test_project_move.py) so
    the description is set at creation time and each test gets an isolated
    ticket against the session throwaway database.
    """
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        return client.post(
            "/api/v1/tickets",
            json={
                "project_id": seeded_projects[0]["id"],
                "title": "Markdown E2E Ticket",
                "type": "Story",
                "priority": "Medium",
                "description": MARKDOWN_DESCRIPTION,
            },
        ).json()


class TestMarkdownDescriptionRendering:
    """The ticket detail page renders a markdown description as real HTML."""

    def test_description_renders_markdown_structure(
        self, page: Page, base_url: str, markdown_ticket
    ):
        """Markdown renders as structured HTML, not as raw text."""
        page.goto(f"{base_url}/tickets/{markdown_ticket['id']}")
        page.wait_for_load_state("networkidle")

        # The shell loads /api/v1/tickets/{id} (JSON) over htmx, then the JS card
        # renders a #ticket-fields-section that htmx-populates from
        # GET /tickets/{id}/fields (server-side render_markdown output).
        prose = page.locator("#ticket-fields-section .prose")
        expect(prose).to_be_visible(timeout=10000)

        # Heading renders as <h1>, not literal "# Feature Spec".
        assert prose.locator("h1").inner_text() == "Feature Spec"

        # Inline formatting: bold, italic, inline code.
        assert prose.locator("strong").inner_text() == "bold"
        assert prose.locator("em").inner_text() == "italic"
        assert prose.locator("code").first.inner_text() == "inline code"

        # Link is a real anchor with a safe href.
        link = prose.locator("a").first
        expect(link).to_have_text("link")
        href = link.get_attribute("href")
        assert href is not None
        assert "example.com/feature-spec" in href

        # Lists render as <ul>/<ol> with <li> children (not "- "/"1. " text).
        assert prose.locator("ul").locator("li").count() == 3
        assert prose.locator("ul").locator("li").first.inner_text() == "bullet one"
        assert prose.locator("ol").locator("li").count() == 2

        # Fenced code block becomes <pre><code>.
        assert prose.locator("pre code").inner_text() == "SELECT 1;"

    def test_description_typography_is_visibly_styled(
        self, page: Page, base_url: str, markdown_ticket
    ):
        """Regression guard for the JRB-009 visual bug.

        With only Tailwind preflight (the bug), ``h1..h6`` inherit font-size and
        ``ul/ol`` get ``list-style:none`` — so headings/lists exist in the DOM but
        are invisible. The ``@tailwindcss/typography`` output (committed in the
        built tailwind.css) restores sized headings and bulleted lists. This test
        reads COMPUTED STYLES in a real browser, which is the only thing that
        catches the regression the CSS-text grep cannot.
        """
        page.goto(f"{base_url}/tickets/{markdown_ticket['id']}")
        page.wait_for_load_state("networkidle")

        prose = page.locator("#ticket-fields-section .prose")
        expect(prose).to_be_visible(timeout=10000)

        # The typography scope is applied to the description container.
        assert prose.evaluate("el => el.classList.contains('prose')")

        # Headings get a concrete, larger font-size than the body text
        # (preflight alone leaves font-size:inherit, so they'd match).
        h1_size = prose.locator("h1").evaluate("el => parseFloat(getComputedStyle(el).fontSize)")
        prose_size = prose.evaluate("el => parseFloat(getComputedStyle(el).fontSize)")
        assert h1_size > prose_size, (
            f"h1 font-size ({h1_size}px) is not larger than the prose body "
            f"({prose_size}px) — headings are invisible. The built tailwind.css "
            "lacks @tailwindcss/typography output; run `make build-css`."
        )

        # Unordered list items keep their bullets (preflight sets list-style:none).
        list_style = prose.locator("ul").evaluate("el => getComputedStyle(el).listStyleType")
        assert list_style == "disc", (
            f"ul list-style-type is '{list_style}', expected 'disc' — list bullets "
            "are invisible. The built tailwind.css lacks @tailwindcss/typography "
            "output; run `make build-css`."
        )

    def test_description_escapes_html_and_is_xss_safe(
        self, page: Page, base_url: str, markdown_ticket
    ):
        """Raw HTML in a description is escaped: no live <script> and the
        payload text is visible but inert."""
        page.goto(f"{base_url}/tickets/{markdown_ticket['id']}")
        page.wait_for_load_state("networkidle")

        prose = page.locator("#ticket-fields-section .prose")
        expect(prose).to_be_visible(timeout=10000)

        # No script element is ever injected into the rendered description.
        assert prose.locator("script").count() == 0

        prose_html = prose.inner_html()
        # The payload text is present but entity-escaped (visible, inert).
        assert "&lt;script&gt;" in prose_html
        assert "<script>alert('xss')</script>" not in prose_html
