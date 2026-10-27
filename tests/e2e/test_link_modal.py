"""E2E coverage for dismissing the Create Link modal."""

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.test_epic_story import _wait_modal_settled


@pytest.mark.parametrize("dismiss_action", ["cancel", "close", "backdrop", "escape"])
def test_link_modal_dismiss_controls_close_without_refresh(
    page: Page, base_url: str, seeded_projects, make_ticket, dismiss_action: str
):
    ticket = make_ticket(ticket_type="Epic", title=f"Modal dismissal {dismiss_action}")
    page.goto(f"{base_url}/ticket/{ticket['id']}")
    page.wait_for_load_state("networkidle")
    expect(page.locator("#links-section")).to_be_visible()

    initial_url = page.url
    initial_links_html = page.locator("#links-section").inner_html()
    section_refreshes: list[str] = []
    navigations: list[str] = []
    page.on(
        "request",
        lambda request: (
            section_refreshes.append(request.url)
            if request.url.endswith(f"/tickets/{ticket['id']}/links")
            else None
        ),
    )
    page.on(
        "framenavigated",
        lambda frame: navigations.append(frame.url) if frame == page.main_frame else None,
    )

    page.get_by_role("button", name="Add Link").click()
    expect(page.locator("#link-modal")).to_be_visible()
    _wait_modal_settled(page)

    if dismiss_action == "cancel":
        page.get_by_role("button", name="Cancel").click()
    elif dismiss_action == "close":
        page.locator("#link-modal button").first.click()
    elif dismiss_action == "backdrop":
        page.locator("xpath=//*[@id='link-modal']//*[contains(@class, 'bg-black/50')]").click(
            position={"x": 10, "y": 10}
        )
    else:
        page.keyboard.press("Escape")

    expect(page.locator("#link-modal")).to_have_count(0)
    expect(page.locator("#link-modal-container")).to_be_empty()
    expect(page.locator("#links-section")).to_be_visible()
    assert page.locator("#links-section").inner_html() == initial_links_html
    assert page.url == initial_url
    assert navigations == []
    assert section_refreshes == []
