"""End-to-end coverage for pasting clipboard images into ticket descriptions (JRB-027).

The three description editors (new-ticket modal, full-page edit form, backlog
row-edit modal) plus the full-page new-ticket form must accept a pasted image,
upload it, insert a markdown reference at the caret, and ultimately render it
as an inline image on the ticket detail page. Unsupported and oversized images
must show a clear error and insert nothing; ordinary text paste must keep
working.

Playwright has no native clipboard-image API, so the paste is simulated the
way the browser would deliver it: a ClipboardEvent carrying a DataTransfer
with an image File, dispatched on the textarea. This exercises the exact
handler path (event target filtering, upload fetch, caret insertion, error
banner) that a real Ctrl+V would.
"""

import base64
import struct
import zlib

import httpx
import pytest
from playwright.sync_api import Page, expect

NEW_TICKET_SELECTORS = {
    "textarea": "#ticket-modal textarea[data-description-editor]",
}


def _png_bytes(width: int = 2, height: int = 2, rgba=(255, 0, 0, 255)) -> bytes:
    """Build a minimal valid PNG (no Pillow dependency)."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(rgba) * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def _paste_bytes_as_file(page: Page, selector: str, data: bytes, filename: str, mime: str) -> None:
    """Dispatch a paste event whose clipboard holds one file, like Ctrl+V."""
    encoded = base64.b64encode(data).decode()
    page.evaluate(
        """([selector, b64, filename, mime]) => {
            const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
            const file = new File([bytes], filename, { type: mime });
            const dt = new DataTransfer();
            dt.items.add(file);
            const target = document.querySelector(selector);
            target.focus();
            const event = new ClipboardEvent("paste", {
                clipboardData: dt, bubbles: true, cancelable: true
            });
            target.dispatchEvent(event);
        }""",
        [selector, encoded, filename, mime],
    )


def _paste_oversized_file(page: Page, selector: str) -> None:
    """Dispatch a paste whose clipboard file exceeds the 10 MiB client limit.

    The payload is built in the browser: shipping 10 MiB through evaluate's
    base64 bridge would dominate the test. One byte over the limit is enough
    to trip the client-side size check (which matches the server limit).
    """
    page.evaluate(
        """(selector) => {
            const file = new File(
                [new Uint8Array(10 * 1024 * 1024 + 1)], "big.png", { type: "image/png" }
            );
            const dt = new DataTransfer();
            dt.items.add(file);
            const target = document.querySelector(selector);
            target.focus();
            target.dispatchEvent(new ClipboardEvent("paste", {
                clipboardData: dt, bubbles: true, cancelable: true
            }));
        }""",
        selector,
    )


def _wait_for_image_reference(page: Page, selector: str) -> None:
    """Wait until the textarea carries an inserted markdown image reference."""
    page.wait_for_function(
        """(selector) => {
            const value = document.querySelector(selector).value;
            return /!\\[image\\]\\(\\/images\\/[0-9a-f]{32}\\.(png|jpg|gif|webp)\\)/.test(value);
        }""",
        arg=selector,
        timeout=10000,
    )


@pytest.fixture
def png() -> bytes:
    return _png_bytes()


class TestPasteIntoNewTicketModal:
    def test_paste_upload_and_create(self, page: Page, base_url: str, seeded_projects, png: bytes):
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        page.click("button:has-text('New Ticket'), a:has-text('New Ticket')")
        page.wait_for_selector("#ticket-modal form", state="visible", timeout=10000)

        selector = NEW_TICKET_SELECTORS["textarea"]
        _paste_bytes_as_file(page, selector, png, "shot.png", "image/png")
        _wait_for_image_reference(page, selector)
        # No error banner.
        assert page.locator("#ticket-modal [data-image-error]").is_hidden()

        title = "Pasted image modal ticket"
        page.fill("input[name='title']", title)
        page.click("button:has-text('Create Ticket')")
        expect(page.locator(f"#tickets-table-body tr:has-text('{title}')").first).to_be_visible(
            timeout=10000
        )

        # The saved description carries the app-hosted reference.
        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            tickets = client.get("/api/v1/tickets", params={"search": title}).json()
            matches = [t for t in tickets["items"] if t["title"] == title]
            assert matches, "created ticket not found via API"
            description = matches[0]["description"]
        assert "![](image)" not in description
        assert description.startswith("![image](/images/")

    def test_text_paste_still_works_in_modal(self, page: Page, base_url: str, seeded_projects):
        """Ordinary text paste keeps working (real clipboard + Ctrl+V).

        Synthetic paste events do not trigger the browser's default text
        insertion, so the pass-through path is exercised with a real
        clipboard write and keyboard paste.
        """
        page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=base_url)
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        page.click("button:has-text('New Ticket'), a:has-text('New Ticket')")
        page.wait_for_selector("#ticket-modal form", state="visible", timeout=10000)

        selector = NEW_TICKET_SELECTORS["textarea"]
        page.click(selector)
        page.evaluate("navigator.clipboard.writeText('plain pasted text')")
        page.keyboard.press("Control+V")

        page.wait_for_function(
            """(selector) => {
                const el = document.querySelector(selector);
                return el && el.value === 'plain pasted text';
            }""",
            arg=selector,
            timeout=10000,
        )

    def test_unsupported_image_shows_error_and_inserts_nothing(
        self, page: Page, base_url: str, seeded_projects
    ):
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        page.click("button:has-text('New Ticket'), a:has-text('New Ticket')")
        page.wait_for_selector("#ticket-modal form", state="visible", timeout=10000)

        selector = NEW_TICKET_SELECTORS["textarea"]
        # Claims to be a PNG but its bytes are not any supported image format.
        _paste_bytes_as_file(page, selector, b"not really a png", "faked.png", "image/png")

        banner = page.locator("#ticket-modal [data-image-error]")
        expect(banner).to_be_visible(timeout=10000)
        expect(banner).to_contain_text("Unsupported image type")
        value = page.evaluate(f"document.querySelector('{selector}').value")
        assert "![image](/images/" not in value

    def test_oversized_image_shows_error_and_inserts_nothing(
        self, page: Page, base_url: str, seeded_projects
    ):
        """An image over the 10 MiB limit is rejected before any upload."""
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        page.click("button:has-text('New Ticket'), a:has-text('New Ticket')")
        page.wait_for_selector("#ticket-modal form", state="visible", timeout=10000)

        selector = NEW_TICKET_SELECTORS["textarea"]
        _paste_oversized_file(page, selector)

        banner = page.locator("#ticket-modal [data-image-error]")
        expect(banner).to_be_visible(timeout=10000)
        expect(banner).to_contain_text("too large")
        value = page.evaluate(f"document.querySelector('{selector}').value")
        assert value == ""


class TestPasteIntoFullPageNewForm:
    def test_paste_into_full_page_new_ticket_form(
        self, page: Page, base_url: str, seeded_projects, png: bytes
    ):
        """GET /tickets/new without an HX-Request header renders the full-page
        form (ticket_form.html) — a fourth description-editor surface that must
        take the paste like the modal variant of the same form."""
        page.goto(f"{base_url}/tickets/new")
        page.wait_for_load_state("networkidle")

        selector = "#ticket-form textarea[data-description-editor]"
        _paste_bytes_as_file(page, selector, png, "shot.png", "image/png")
        _wait_for_image_reference(page, selector)
        assert page.locator("#ticket-form [data-image-error]").is_hidden()


class TestPasteIntoFullPageEditForm:
    def test_paste_save_and_render(
        self, page: Page, base_url: str, seeded_projects, make_ticket, png: bytes
    ):
        ticket = make_ticket(title="Full-page paste ticket")
        page.goto(f"{base_url}/tickets/{ticket['id']}/edit")
        page.wait_for_load_state("networkidle")

        selector = "#ticket-form textarea[data-description-editor]"
        _paste_bytes_as_file(page, selector, png, "shot.png", "image/png")
        _wait_for_image_reference(page, selector)

        page.click("button:has-text('Save Changes')")
        page.wait_for_url(f"**/tickets/{ticket['id']}", timeout=15000)

        prose = page.locator("#ticket-fields-section .prose")
        expect(prose).to_be_visible(timeout=10000)
        img = prose.locator("img")
        expect(img).to_have_count(1)
        src = img.get_attribute("src")
        assert src is not None and src.startswith("/images/")
        # The stored image actually loads in the browser.
        page.wait_for_function(
            """() => {
                const img = document.querySelector('#ticket-fields-section .prose img');
                return img && img.complete && img.naturalWidth > 0;
            }""",
            timeout=10000,
        )


class TestPasteIntoRowEditModal:
    def test_paste_save_and_render(
        self, page: Page, base_url: str, seeded_projects, make_ticket, png: bytes
    ):
        ticket = make_ticket(title="Row-edit paste ticket")
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")

        row = page.locator(f"#tickets-table-body tr:has-text('{ticket['title']}')")
        row.locator("button[title='Edit']").click()
        page.wait_for_selector("#ticket-edit-form", state="visible", timeout=10000)

        selector = "#ticket-edit-form textarea[data-description-editor]"
        _paste_bytes_as_file(page, selector, png, "shot.png", "image/png")
        _wait_for_image_reference(page, selector)
        assert page.locator("#ticket-edit-form [data-image-error]").is_hidden()

        page.click("#ticket-edit-form button:has-text('Save Changes')")
        # The modal closes on success; the row swap carries the saved state.
        expect(page.locator("#ticket-edit-form")).not_to_be_visible(timeout=10000)

        page.goto(f"{base_url}/tickets/{ticket['id']}")
        page.wait_for_load_state("networkidle")
        prose = page.locator("#ticket-fields-section .prose")
        expect(prose).to_be_visible(timeout=10000)
        img = prose.locator("img")
        expect(img).to_have_count(1)
        src = img.get_attribute("src")
        assert src is not None and src.startswith("/images/")


class TestUnsafeImageReferenceDoesNotLoad:
    def test_remote_image_reference_stays_literal_text(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        """A remote (non app-hosted) image URL in a description must not
        become an <img> or fetch remote content in the browser (AC-3)."""
        import uuid

        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            ticket = client.post(
                "/api/v1/tickets",
                json={
                    "project_id": seeded_projects[0]["id"],
                    "title": f"Unsafe ref {uuid.uuid4().hex[:8]}",
                    "type": "Story",
                    "description": (
                        "look ![x](https://evil.example.com/track.png) now\n"
                        "<img src=x onerror=alert(1)>"
                    ),
                },
            ).json()

        page.goto(f"{base_url}/tickets/{ticket['id']}")
        page.wait_for_load_state("networkidle")
        prose = page.locator("#ticket-fields-section .prose")
        expect(prose).to_be_visible(timeout=10000)
        assert prose.locator("img").count() == 0
        # The markup is visible as literal text; no script ran (console_errors
        # fixture would fail the test on an alert/error otherwise).
        body = prose.inner_text()
        assert "![x](https://evil.example.com/track.png)" in body
