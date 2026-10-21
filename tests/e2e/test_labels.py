"""E2E tests for labels: applying a label from the ticket page, removing it,
and setting labels in the ticket form."""

import uuid

import pytest
from playwright.sync_api import Page, expect


@pytest.fixture
def accept_dialogs(page: Page):
    """Accept htmx's confirm() prompts (Playwright dismisses them by default)."""
    page.on("dialog", lambda dialog: dialog.accept())
    return page


def _unique_label(prefix: str = "e2e-label") -> str:
    """A run-unique label name (the e2e server keeps its state for the run)."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class TestTicketPageLabels:
    """Labels applied from the ticket page."""

    def test_label_a_ticket_from_the_ticket_page(
        self, page: Page, base_url: str, make_ticket, accept_dialogs
    ):
        ticket = make_ticket()
        label = _unique_label()

        page.goto(f"{base_url}/ticket/{ticket['id']}")
        page.wait_for_load_state("networkidle")

        # The labels section loads over HTMX.
        page.wait_for_selector("#labels-section", state="visible", timeout=10000)

        page.click("#labels-section button:has-text('Add Label')")
        page.wait_for_selector("#label-modal", state="visible", timeout=10000)

        page.fill("#label_name", label)
        page.click("#label-modal button[type='submit']")

        # The chip shows up in the labels section.
        chip = page.locator(f'#labels-section .label-chip[data-label-name="{label}"]')
        expect(chip).to_be_visible(timeout=10000)

    def test_a_label_keeps_the_spelling_first_typed(
        self, page: Page, base_url: str, make_ticket, accept_dialogs
    ):
        ticket = make_ticket()
        label = _unique_label("E2E-Case")

        page.goto(f"{base_url}/ticket/{ticket['id']}")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#labels-section", state="visible", timeout=10000)

        page.click("#labels-section button:has-text('Add Label')")
        page.wait_for_selector("#label-modal", state="visible", timeout=10000)
        page.fill("#label_name", label)
        page.click("#label-modal button[type='submit']")

        chip = page.locator(f'#labels-section .label-chip[data-label-name="{label}"]')
        expect(chip).to_be_visible(timeout=10000)

        # The same label typed in a different case is the same label.
        page.click("#labels-section button:has-text('Add Label')")
        page.wait_for_selector("#label-modal", state="visible", timeout=10000)
        page.fill("#label_name", label.lower())
        page.click("#label-modal button[type='submit']")

        page.wait_for_load_state("networkidle")
        expect(page.locator("#labels-section .label-chip")).to_have_count(1, timeout=10000)

    def test_remove_a_label_from_the_ticket_page(
        self, page: Page, base_url: str, make_ticket, accept_dialogs
    ):
        ticket = make_ticket()
        label = _unique_label()

        page.goto(f"{base_url}/ticket/{ticket['id']}")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#labels-section", state="visible", timeout=10000)

        page.click("#labels-section button:has-text('Add Label')")
        page.wait_for_selector("#label-modal", state="visible", timeout=10000)
        page.fill("#label_name", label)
        page.click("#label-modal button[type='submit']")

        chip = page.locator(f'#labels-section .label-chip[data-label-name="{label}"]')
        expect(chip).to_be_visible(timeout=10000)

        chip.locator(".label-chip-remove").click()
        removed = page.locator(f'#labels-section .label-chip[data-label-name="{label}"]')
        expect(removed).to_have_count(0, timeout=10000)


class TestLabelsInTheTicketForm:
    """Labels set in the ticket form."""

    def test_create_a_ticket_with_a_label(self, page: Page, base_url: str, accept_dialogs):
        import httpx

        label = _unique_label()
        title = f"E2E labelled ticket {uuid.uuid4().hex[:8]}"

        # The backlog's "New Ticket" button opens the create form in a modal.
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        page.click("button:has-text('New Ticket')")
        page.wait_for_selector("#ticket-modal form", state="visible", timeout=10000)

        page.fill("#ticket-modal input[name='title']", title)
        page.fill("#ticket-modal textarea[name='description']", "Created by the labels e2e test")

        # Typed text is committed as a chip on Enter.
        page.fill("#ticket-modal [data-label-input]", label)
        page.press("#ticket-modal [data-label-input]", "Enter")
        expect(page.locator(f'#ticket-modal .label-chip[data-label-name="{label}"]')).to_be_visible(
            timeout=10000
        )

        page.click("#ticket-modal button[type='submit']")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            tickets = client.get("/api/v1/tickets", params={"q": title}).json()
        matching = [t for t in tickets["items"] if t["title"] == title]
        assert matching, "the ticket was not created"
        assert [item["name"] for item in matching[0]["labels"]] == [label]

    def test_edit_a_tickets_labels_in_the_edit_form(
        self, page: Page, base_url: str, make_ticket, accept_dialogs
    ):
        import httpx

        ticket = make_ticket()
        existing = _unique_label("existing")
        added = _unique_label("added")

        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            client.post(f"/api/v1/tickets/{ticket['id']}/labels", json={"name": existing})

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        page.click(f'#ticket-row-{ticket["id"]} button[title="Edit"]')
        page.wait_for_selector("#ticket-modal form", state="visible", timeout=10000)

        # The ticket's current label is shown as a chip.
        expect(
            page.locator(f'#ticket-modal .label-chip[data-label-name="{existing}"]')
        ).to_be_visible(timeout=10000)

        # A new label is committed as a chip on Enter...
        page.fill("#ticket-modal [data-label-input]", added)
        page.press("#ticket-modal [data-label-input]", "Enter")
        expect(page.locator(f'#ticket-modal .label-chip[data-label-name="{added}"]')).to_be_visible(
            timeout=10000
        )

        # ... and the existing one can be removed from the form.
        page.click(f'#ticket-modal .label-chip[data-label-name="{existing}"] .label-chip-remove')
        expect(
            page.locator(f'#ticket-modal .label-chip[data-label-name="{existing}"]')
        ).to_have_count(0, timeout=10000)

        page.click("#ticket-modal button[type='submit']")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            updated = client.get(f"/api/v1/tickets/{ticket['id']}").json()
        assert [item["name"] for item in updated["labels"]] == [added]
