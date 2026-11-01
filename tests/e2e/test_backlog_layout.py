"""E2E test for the backlog table layout (JRB-015).

The shared main/nav/footer containers in base.html were widened from
max-w-7xl (1280px) to max-w-screen-2xl (1536px) and the backlog table card
changed from overflow-hidden to overflow-x-auto, so that:

- at wide viewports the ~1310px-wide 10-column table fits without clipping
  the Move to Sprint button (previously cut off at the right edge);
- at narrower viewports the table scrolls horizontally instead of being
  clipped, keeping all 10 columns reachable.
"""

import pytest
from playwright.sync_api import Browser, Page, expect

WIDE_VIEWPORT = {"width": 1920, "height": 1080}
NARROW_VIEWPORT = {"width": 1024, "height": 768}
LAST_COLUMN_TEXT = "Actions"
MOVE_TO_SPRINT = "Move to Sprint"


@pytest.fixture
def wide_page(browser: Browser) -> Page:
    context = browser.new_context(viewport=WIDE_VIEWPORT)
    page = context.new_page()
    page.set_default_timeout(30000)
    yield page
    context.close()


@pytest.fixture
def narrow_page(browser: Browser) -> Page:
    context = browser.new_context(viewport=NARROW_VIEWPORT)
    page = context.new_page()
    page.set_default_timeout(30000)
    yield page
    context.close()


class TestBacklogLayout:
    """Tests for the backlog table layout across viewport widths."""

    def test_table_extends_beyond_1280px_at_wide_viewport(
        self, wide_page: Page, base_url: str, make_ticket
    ):
        """The wider max-w-screen-2xl container lets the table exceed 1280px."""
        make_ticket(title="Wide Layout Ticket")
        wide_page.goto(f"{base_url}/backlog")
        wide_page.wait_for_load_state("networkidle")

        main = wide_page.locator("main")
        assert main.evaluate("el => el.getBoundingClientRect().width") == 1536

        table = wide_page.locator("table")
        table_width = table.evaluate("el => el.getBoundingClientRect().width")
        assert table_width > 1280, (
            f"backlog table is only {table_width}px wide at a 1920px viewport; "
            "the widened container should let the 10-column table exceed 1280px"
        )

    def test_move_to_sprint_button_not_clipped_at_wide_viewport(
        self, wide_page: Page, base_url: str, make_ticket
    ):
        """The Move to Sprint button is fully readable at a wide viewport."""
        ticket = make_ticket(title="Wide Button Ticket")
        wide_page.goto(f"{base_url}/backlog")
        wide_page.wait_for_load_state("networkidle")

        row = wide_page.locator(f"#ticket-row-{ticket['id']}")
        expect(row).to_be_visible()
        button = row.locator(f"button:has-text('{MOVE_TO_SPRINT}')")
        expect(button).to_be_visible()

        button_box = button.bounding_box()
        viewport_width = wide_page.evaluate("window.innerWidth")
        assert button_box is not None
        assert button_box["x"] + button_box["width"] <= viewport_width, (
            f"Move to Sprint button extends past the {viewport_width}px viewport "
            "(clipped as in JRB-015)"
        )
        # The full label is rendered (the sm:inline span is not display:none),
        # so the text fits inside the button rather than being truncated.
        inner_text = button.inner_text()
        assert MOVE_TO_SPRINT in inner_text
        text_width = button.evaluate(
            "el => el.querySelector('.hidden.sm\\\\:inline')?.getBoundingClientRect().width"
            " ?? el.getBoundingClientRect().width"
        )
        assert text_width > 0

    def test_table_card_horizontally_scrollable_at_narrow_viewport(
        self, narrow_page: Page, base_url: str, make_ticket
    ):
        """At a narrow viewport the table card scrolls instead of clipping."""
        make_ticket(title="Narrow Layout Ticket")
        narrow_page.goto(f"{base_url}/backlog")
        narrow_page.wait_for_load_state("networkidle")

        card = narrow_page.locator("div:has(> table.w-full)").first
        scroll_info = card.evaluate(
            "el => ({ scrollWidth: el.scrollWidth, clientWidth: el.clientWidth,"
            " overflowX: getComputedStyle(el).overflowX })"
        )
        assert scroll_info["overflowX"] == "auto", (
            "backlog table card should use overflow-x: auto so the table scrolls "
            "on narrow viewports instead of being clipped"
        )
        assert scroll_info["scrollWidth"] > scroll_info["clientWidth"], (
            "table content should overflow the card at a 1024px viewport"
        )

        # Scrolling to the far right makes the last column reachable.
        card.evaluate("el => el.scrollTo({ left: el.scrollWidth, behavior: 'instant' })")
        last_header = narrow_page.locator("table thead th").last
        expect(last_header).to_be_visible()
        assert LAST_COLUMN_TEXT.lower() in last_header.inner_text().lower()
