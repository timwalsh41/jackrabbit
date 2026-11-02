"""E2E regression for JRB-018: the open-blocker warning and backlog badge must
disappear once every blocker reaches a terminal status (Complete or Rejected),
not only when the blocking link is deleted.

Walks the real user workflow: a story is seeded with a blocker via the app's
own API, the blocker is driven to a terminal status through the real UI
(transition modals, exactly as a user would), and the story page is reloaded
to confirm the warning and badge cleared.
"""

from playwright.sync_api import Locator, Page, expect

WARNING_TEXT = "This ticket has open blockers"


def _warning(page: Page) -> Locator:
    """The yellow blocker warning inside the story's links section."""
    return page.locator("#links-section").locator(f"text={WARNING_TEXT}")


def _backlog_badge(page: Page, title: str) -> Locator:
    """The 'N open blocker(s)' badge on the backlog row of the ticket `title`."""
    row = page.locator(f"#tickets-table-body tr:has-text('{title}')").first
    return row.locator("span[title*='open blocker']")


def _assert_terminal_blocker_clears(page: Page, base_url: str, story: dict) -> None:
    """Reload the story page and assert warning and badge are gone."""
    page.goto(f"{base_url}/ticket/{story['id']}")
    page.wait_for_load_state("networkidle")
    expect(page.locator("#links-section")).to_be_visible(timeout=10000)
    expect(_warning(page)).to_have_count(0)

    page.goto(f"{base_url}/backlog")
    page.wait_for_load_state("networkidle")
    expect(_backlog_badge(page, story["title"])).to_have_count(0)


class TestBlockerWarningTerminalBlockers:
    """JRB-018: terminal blockers (Complete/Rejected) must not warn or badge."""

    def test_completing_blocker_clears_warning_and_badge(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        """A story blocked by a ticket the user completes via the UI stops
        showing the open-blocker warning and backlog badge."""
        import httpx

        blocker = make_ticket(title="Blocker that gets completed")
        story = make_ticket(title="Story blocked by completable blocker")

        # Seed the blocks link via the app's own API (as the existing e2e
        # suite seeds data), so the story really is blocked.
        with httpx.Client(base_url=base_url, timeout=30.0) as api:
            response = api.post(
                f"/api/v1/tickets/{blocker['id']}/links",
                json={
                    "source_id": blocker["id"],
                    "target_id": story["id"],
                    "link_type": "blocks",
                },
            )
            assert response.status_code == 201, response.text

        # The story detail page shows the yellow warning ...
        page.goto(f"{base_url}/ticket/{story['id']}")
        page.wait_for_load_state("networkidle")
        expect(page.locator("#links-section")).to_be_visible(timeout=10000)
        expect(_warning(page)).to_be_visible()
        # ... and the backlog row shows the blocked badge.
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        expect(_backlog_badge(page, story["title"])).to_be_visible()

        # Complete the blocker through the real UI, transition by transition.
        page.goto(f"{base_url}/ticket/{blocker['id']}")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#transition-buttons button", state="visible", timeout=10000)

        # Open -> Groomed (modal with four required fields)
        page.click("button:has-text('Groomed')")
        page.wait_for_selector("#groom-form", state="visible", timeout=10000)
        page.fill("textarea[name='approach']", "Finish the blocker")
        page.fill("textarea[name='files_to_change']", "src/blocker.py")
        page.fill("textarea[name='test_plan']", "unit tests")
        page.fill("textarea[name='validation_steps']", "run tests")
        page.click("#groom-form button[type='submit']")
        expect(page.locator("#ticket-content span:has-text('Groomed')").first).to_be_visible(
            timeout=10000
        )

        # Groomed -> In Progress
        page.click("button:has-text('In Progress')")
        page.wait_for_selector("#in-progress-form", state="visible", timeout=10000)
        page.click("button:has-text('Start Work')")
        expect(page.locator("#ticket-content span:has-text('In Progress')").first).to_be_visible(
            timeout=10000
        )

        # In Progress -> Ready for Review (PR URL is optional)
        page.click("button:has-text('Ready for Review')")
        page.wait_for_selector("#review-form", state="visible", timeout=10000)
        page.click("button:has-text('Submit for Review')")
        expect(
            page.locator("#ticket-content span:has-text('Ready for Review')").first
        ).to_be_visible(timeout=10000)

        # Ready for Review -> Complete
        page.click("button:has-text('Complete')")
        page.wait_for_selector("#complete-form", state="visible", timeout=10000)
        page.fill("#reason", "merged")
        page.click("#complete-form button[type='submit']")
        expect(page.locator("#ticket-content span:has-text('Complete')").first).to_be_visible(
            timeout=10000
        )

        # Reload the story: the warning must be GONE (before the JRB-018 fix it
        # stayed visible even though the blocker was terminal).
        _assert_terminal_blocker_clears(page, base_url, story)

    def test_rejected_blocker_shows_no_warning_or_badge(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        """A REJECTED blocker is terminal too: no warning, no backlog badge."""
        import httpx

        blocker = make_ticket(title="Blocker that gets rejected")
        story = make_ticket(title="Story blocked by rejectable blocker")

        with httpx.Client(base_url=base_url, timeout=30.0) as api:
            response = api.post(
                f"/api/v1/tickets/{blocker['id']}/links",
                json={
                    "source_id": blocker["id"],
                    "target_id": story["id"],
                    "link_type": "blocks",
                },
            )
            assert response.status_code == 201, response.text

        # Reject the blocker through the real UI; the button prompts for a
        # reason (same mechanism test_ticket_lifecycle exercises for dialogs).
        page.goto(f"{base_url}/ticket/{blocker['id']}")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#transition-buttons button", state="visible", timeout=10000)
        page.on("dialog", lambda d: d.accept("not needed"))
        page.click("#transition-buttons button:has-text('Rejected')")
        expect(page.locator("#ticket-content span:has-text('Rejected')").first).to_be_visible(
            timeout=10000
        )

        # The story must show no warning and no badge.
        _assert_terminal_blocker_clears(page, base_url, story)
