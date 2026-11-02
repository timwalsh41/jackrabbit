"""E2E coverage for JRB-019: single-parent confirm flow and the parent
back-link on the ticket detail page."""

import httpx
import pytest
from playwright.sync_api import Page, expect

from tests.e2e.test_epic_story import _wait_modal_settled


@pytest.fixture
def make_link(base_url):
    """Create a link via the same API the UI calls."""

    def _make(source_id: int, target_id: int, link_type: str) -> None:
        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            response = client.post(
                f"/api/v1/tickets/{source_id}/links",
                json={
                    "source_id": source_id,
                    "target_id": target_id,
                    "link_type": link_type,
                },
            )
            assert response.status_code == 201, response.text

    return _make


@pytest.fixture
def child_of_epic(make_ticket, make_link):
    """A Story already parented to an Epic, plus a second Epic to move it to."""
    epic = make_ticket(title="Epic: First Parent", ticket_type="Epic")
    story = make_ticket(title="Story: Moved Child")
    make_link(epic["id"], story["id"], "parent")
    other_epic = make_ticket(title="Epic: Second Parent", ticket_type="Epic")
    return epic, story, other_epic


def _open_link_modal_for_child(page: Page, base_url: str, story: dict, target_epic: dict):
    """Open the Add Link modal on the story, aiming a child link at target_epic."""
    page.goto(f"{base_url}/ticket/{story['id']}")
    page.wait_for_load_state("networkidle")
    expect(page.locator("#links-section")).to_be_visible()

    page.get_by_role("button", name="Add Link").click()
    expect(page.locator("#link-modal")).to_be_visible()
    _wait_modal_settled(page)

    page.select_option("#link-modal select[name='link_type']", "child")
    page.fill("#link-modal #target_search", f"UNS-{target_epic['number']:03d}")
    page.dispatch_event("#link-modal #target_search", "keyup")
    page.wait_for_selector(".ticket-search-result", timeout=10000)
    page.click(f".ticket-search-result[data-ticket-id='{target_epic['id']}']")
    page.wait_for_timeout(300)


class TestSecondParentConfirmFlow:
    """Adding a second parent asks for confirmation before replacing (JRB-019)."""

    def test_proceed_replaces_the_parent(self, page: Page, base_url: str, child_of_epic):
        epic, story, other_epic = child_of_epic
        _open_link_modal_for_child(page, base_url, story, other_epic)

        dialogs: list[str] = []
        page.on(
            "dialog",
            lambda dialog: (dialogs.append(dialog.message), dialog.accept()),
        )

        page.click("#link-modal button[type='submit']")
        page.wait_for_selector("#link-modal", state="detached", timeout=10000)

        # The confirmation dialog named the single-parent rule
        assert dialogs, "expected a confirmation dialog on the second parent"
        assert any("only one parent" in message for message in dialogs)

        # The links section swapped in place and shows the new parent
        expect(page.locator("#links-section")).to_contain_text("Epic: Second Parent")

        # After a reload the header back-link shows the new parent too
        page.reload()
        page.wait_for_load_state("networkidle")
        expect(page.locator("#parent-backlink")).to_contain_text(f"UNS-{other_epic['number']:03d}")

    def test_cancel_keeps_the_old_parent(self, page: Page, base_url: str, child_of_epic):
        epic, story, other_epic = child_of_epic
        _open_link_modal_for_child(page, base_url, story, other_epic)

        page.on("dialog", lambda dialog: dialog.dismiss())
        page.click("#link-modal button[type='submit']")

        # Abort: the modal stays open and nothing was re-parented
        expect(page.locator("#link-modal")).to_be_visible()
        links = page.request.get(f"{base_url}/api/v1/tickets/{story['id']}/links").json()
        assert any(
            link["link_type"] == "child" and link["target_id"] == epic["id"] for link in links
        )
        assert not any(
            link["link_type"] == "child" and link["target_id"] == other_epic["id"] for link in links
        )


class TestParentBackLink:
    """The detail page links back to the ticket's parent issue (JRB-019)."""

    def test_back_link_navigates_to_parent(self, page: Page, base_url: str, child_of_epic):
        epic, story, _ = child_of_epic
        page.goto(f"{base_url}/ticket/{story['id']}")
        page.wait_for_load_state("networkidle")

        back_link = page.locator("#parent-backlink")
        expect(back_link).to_be_visible()
        expect(back_link).to_contain_text(f"UNS-{epic['number']:03d}")

        back_link.click()
        page.wait_for_url(f"**/tickets/{epic['id']}")
        expect(page.locator("#ticket-title")).to_contain_text("Epic: First Parent")

    def test_no_parent_renders_no_backlink(self, page: Page, base_url: str, make_ticket):
        story = make_ticket(title="Story: No Parent")
        page.goto(f"{base_url}/ticket/{story['id']}")
        page.wait_for_load_state("networkidle")
        expect(page.locator("#parent-backlink")).to_have_count(0)

    def test_back_to_backlog_sits_below_parent_link_left_aligned(
        self, page: Page, base_url: str, child_of_epic
    ):
        epic, story, _ = child_of_epic
        page.goto(f"{base_url}/ticket/{story['id']}")
        page.wait_for_load_state("networkidle")

        parent_box = page.locator("#parent-backlink").bounding_box()
        backlog_box = page.locator("a:has-text('← Back to Backlog')").bounding_box()
        assert parent_box is not None and backlog_box is not None
        # Parent link on top, Back to Backlog below it, left-aligned
        assert parent_box["y"] < backlog_box["y"]
        assert abs(parent_box["x"] - backlog_box["x"]) <= 1
