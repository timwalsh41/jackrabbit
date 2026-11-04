"""E2E tests for criterion sign-off, the Complete guard, and the criteria
checklist/history in the ticket detail view (JRB-022, ADR-0025).

Each test is self-contained: it creates its own preconditioned ticket via the
API (the make_ticket factory) and then drives the UI, so tests do not depend
on ordering or on state left behind by earlier tests.
"""

import pytest
from playwright.sync_api import Page, expect


def _criteria(base_url: str, tid: int) -> list[dict]:
    import httpx

    with httpx.Client(base_url=base_url, timeout=30.0) as api:
        return api.get(f"/api/v1/tickets/{tid}/criteria").json()


class TestCriterionChecklist:
    """The detail view renders criteria as a checklist with ticks and
    timestamps; the verifier signs off via the UI while In Progress."""

    def test_sign_off_shows_tick_timestamp_and_history(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        ticket = make_ticket(status="In Progress")
        tid = ticket["id"]

        page.goto(f"{base_url}/ticket/{tid}")
        page.wait_for_selector("#criteria-checklist .criterion-row", state="visible")

        boxes = page.locator("#criteria-checklist input[type='checkbox']")
        assert boxes.count() == 2
        for i in range(boxes.count()):
            assert boxes.nth(i).is_checked() is False
            assert boxes.nth(i).is_disabled() is False
        assert page.locator("#criteria-checklist .criterion-tick").count() == 0

        # Grooming seeded two criterion rows: both logged as "Added".
        history = page.locator("#criteria-history")
        expect(history).to_contain_text("Added")
        expect(history).to_contain_text("E2E criterion one")

        # Sign the first criterion off via the UI.
        page.check("#criteria-checklist .criterion-row >> nth=0 >> input[type='checkbox']")

        tick = page.locator("#criteria-checklist .criterion-row").first.locator(".criterion-tick")
        expect(tick).to_be_visible(timeout=10000)
        # The tick carries the verified timestamp (a localised date/time).
        expect(tick).not_to_have_text("")

        # The sign-off appended a history entry with the criterion text.
        expect(page.locator("#criteria-history")).to_contain_text("Verified")
        rows = _criteria(base_url, tid)
        assert rows[0]["verified"] is True
        assert rows[0]["verified_at"] is not None

    def test_checkboxes_are_read_only_before_work_starts(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        ticket = make_ticket(status="Groomed")
        tid = ticket["id"]

        page.goto(f"{base_url}/ticket/{tid}")
        page.wait_for_selector("#criteria-checklist .criterion-row", state="visible")

        boxes = page.locator("#criteria-checklist input[type='checkbox']")
        assert boxes.count() == 2
        for i in range(boxes.count()):
            assert boxes.nth(i).is_disabled() is True


class TestCompleteGuardUI:
    """Ready for Review -> Complete is blocked from the UI while any criterion
    is unverified, and passes once the verifier checks them all."""

    def test_complete_blocked_until_all_criteria_verified(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        ticket = make_ticket(status="Ready for Review")
        tid = ticket["id"]

        page.goto(f"{base_url}/ticket/{tid}")
        page.wait_for_selector("#transition-buttons button", state="visible")

        # Complete while a criterion is unverified: the guard rejects it.
        page.click("button:has-text('Complete')")
        page.wait_for_selector("#complete-form", state="visible")
        page.fill("#reason", "merged")
        page.click("#complete-form button[type='submit']")
        banner = page.locator("#modal-error")
        expect(banner).to_be_visible(timeout=10000)
        expect(banner).to_contain_text("verified")
        page.click("#complete-form button:has-text('Cancel')")

        # Still Ready for Review.
        expect(
            page.locator("#ticket-content span:has-text('Ready for Review')").first
        ).to_be_visible(timeout=10000)

        # The verifier signs off both criteria via the checklist.
        page.wait_for_selector("#criteria-checklist .criterion-row", state="visible")
        boxes = page.locator("#criteria-checklist input[type='checkbox']")
        assert boxes.count() == 2
        page.check("#criteria-checklist .criterion-row >> nth=0 >> input[type='checkbox']")
        expect(page.locator("#criteria-checklist .criterion-tick").first).to_be_visible()
        page.check("#criteria-checklist .criterion-row >> nth=1 >> input[type='checkbox']")
        expect(page.locator("#criteria-checklist .criterion-tick")).to_have_count(2)

        # Now Complete passes.
        page.click("button:has-text('Complete')")
        page.wait_for_selector("#complete-form", state="visible")
        page.fill("#reason", "merged")
        page.click("#complete-form button[type='submit']")
        expect(page.locator("#ticket-content span:has-text('Complete')").first).to_be_visible(
            timeout=10000
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
