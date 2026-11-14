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
import re
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


def _wait_for_image_reference(page: Page, selector: str, count: int = 1) -> None:
    """Wait until the textarea carries `count` inserted markdown references."""
    page.wait_for_function(
        """([selector, count]) => {
            const value = document.querySelector(selector).value;
            const matches =
                value.match(/!\\[image\\]\\(\\/images\\/[0-9a-f]{32}\\.(png|jpg|gif|webp)\\)/g);
            return matches !== null && matches.length === count;
        }""",
        arg=[selector, count],
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


class TestConcurrentPastes:
    def test_second_paste_while_first_pending_lands_after_first(
        self, page: Page, base_url: str, seeded_projects, make_ticket, png: bytes
    ):
        """A second paste dispatched while the first upload is still in flight.

        Both paste events fire in one synchronous JS task, so the second
        paste's caret offset is captured before the first insertion happens
        (the upload round-trip can only complete in a later task). The FIFO
        queue then inserts the first reference and must shift the queued
        second insertion by its length, so the second reference lands right
        after the first — never inside it or at the stale caret offset.

        The two pastes carry different formats (PNG, then GIF), so the
        inserted references are distinguishable and the paste order (PNG
        before GIF) is assertable.
        """
        ticket = make_ticket(title="Concurrent paste ticket")
        page.goto(f"{base_url}/tickets/{ticket['id']}/edit")
        page.wait_for_load_state("networkidle")

        selector = "#ticket-form textarea[data-description-editor]"
        png_b64 = base64.b64encode(png).decode()
        gif_b64 = base64.b64encode(b"GIF89a\x01\x00\x01\x00\x00\x00\x00;").decode()
        # Caret at 8 inside "hello world": without the offset adjustment the
        # second reference would insert at 8 — inside/at the start of the
        # markdown the first paste just inserted at 8.
        synchronous_value = page.evaluate(
            """([selector, pngB64, gifB64]) => {
                const pngBytes = Uint8Array.from(atob(pngB64), c => c.charCodeAt(0));
                const gifBytes = Uint8Array.from(atob(gifB64), c => c.charCodeAt(0));
                const target = document.querySelector(selector);
                target.focus();
                target.value = "hello world";
                target.setSelectionRange(8, 8);
                for (const [bytes, mime] of [
                    [pngBytes, "image/png"], [gifBytes, "image/gif"]
                ]) {
                    const dt = new DataTransfer();
                    dt.items.add(new File([bytes], "shot", { type: mime }));
                    target.dispatchEvent(new ClipboardEvent("paste", {
                        clipboardData: dt, bubbles: true, cancelable: true
                    }));
                }
                return target.value;
            }""",
            [selector, png_b64, gif_b64],
        )
        # Nothing is inserted synchronously: both uploads are still pending.
        assert synchronous_value == "hello world"

        _wait_for_image_reference(page, selector, count=2)
        final_value = page.evaluate(f"document.querySelector('{selector}').value")
        png_refs = re.findall(r"!\[image\]\(/images/[0-9a-f]{32}\.png\)", final_value)
        gif_refs = re.findall(r"!\[image\]\(/images/[0-9a-f]{32}\.gif\)", final_value)
        assert len(png_refs) == 1 and len(gif_refs) == 1, final_value
        # The first paste's PNG reference comes first and the second paste's
        # GIF reference right after it — neither landed at the stale caret
        # offset inside the other's markdown.
        assert final_value == "hello wo" + png_refs[0] + gif_refs[0] + "rld", final_value
        assert page.locator("#ticket-form [data-image-error]").is_hidden()

    def test_concurrent_pastes_over_selection_keep_following_text(
        self, page: Page, base_url: str, seeded_projects, make_ticket, png: bytes
    ):
        """Two pastes over the same NON-EMPTY selection while both pending.

        The first completed insertion replaces the selection ('world') with
        its reference. The second queued insertion must not replace again:
        its paste-time range was already consumed by the first insertion, so
        it collapses to insert-only right after the first reference and the
        text following the selection (' again') survives untouched.

        The selection sits before trailing prose on purpose: the bug deletes
        the text that follows the first inserted reference (the stale end
        offset spans the original selection length), which is invisible when
        the selection runs to the end of the value. Different formats (PNG,
        then GIF) make the references distinguishable and the paste order
        assertable.
        """
        ticket = make_ticket(title="Concurrent selection paste ticket")
        page.goto(f"{base_url}/tickets/{ticket['id']}/edit")
        page.wait_for_load_state("networkidle")

        selector = "#ticket-form textarea[data-description-editor]"
        png_b64 = base64.b64encode(png).decode()
        gif_b64 = base64.b64encode(b"GIF89a\x01\x00\x01\x00\x00\x00\x00;").decode()
        synchronous_value = page.evaluate(
            """([selector, pngB64, gifB64]) => {
                const pngBytes = Uint8Array.from(atob(pngB64), c => c.charCodeAt(0));
                const gifBytes = Uint8Array.from(atob(gifB64), c => c.charCodeAt(0));
                const target = document.querySelector(selector);
                target.focus();
                target.value = "hello world again";
                target.setSelectionRange(6, 11);
                for (const [bytes, mime] of [
                    [pngBytes, "image/png"], [gifBytes, "image/gif"]
                ]) {
                    const dt = new DataTransfer();
                    dt.items.add(new File([bytes], "shot", { type: mime }));
                    target.dispatchEvent(new ClipboardEvent("paste", {
                        clipboardData: dt, bubbles: true, cancelable: true
                    }));
                }
                return target.value;
            }""",
            [selector, png_b64, gif_b64],
        )
        # Nothing is inserted synchronously: both uploads are still pending.
        assert synchronous_value == "hello world again"

        _wait_for_image_reference(page, selector, count=2)
        final_value = page.evaluate(f"document.querySelector('{selector}').value")
        png_refs = re.findall(r"!\[image\]\(/images/[0-9a-f]{32}\.png\)", final_value)
        gif_refs = re.findall(r"!\[image\]\(/images/[0-9a-f]{32}\.gif\)", final_value)
        assert len(png_refs) == 1 and len(gif_refs) == 1, final_value
        # Exactly the selection replaced once by the first reference, the
        # second reference inserted right after it, and the following prose
        # (' again') intact — nothing else deleted.
        assert final_value == "hello " + png_refs[0] + gif_refs[0] + " again", final_value
        assert page.locator("#ticket-form [data-image-error]").is_hidden()

    def test_second_paste_after_replaced_selection_lands_at_net_shifted_caret(
        self, page: Page, base_url: str, seeded_projects, make_ticket, png: bytes
    ):
        """A queued paste at a caret AFTER a selection the first paste replaces.

        The first paste replaces the four-character selection [4, 8) ('XXXX')
        with its reference, shrinking the text by 4. The second paste was
        queued at caret 12 — after the selection, before trailing prose — and
        must shift by the NET delta (reference length minus the replaced 4),
        not by the reference length alone: caret 12 lands at 12 + len1 - 4 =
        8 + len1, i.e. exactly where caret 12 was, right before 'IJ'.
        Shifting by the length alone overshoots by 4 and drops the second
        reference after the trailing prose (masked at end-of-text only by
        setRangeText clamping, hence the 'IJ' tail).

        Different formats (PNG, then GIF) make the references distinguishable
        and the paste order assertable.
        """
        ticket = make_ticket(title="Net shift paste ticket")
        page.goto(f"{base_url}/tickets/{ticket['id']}/edit")
        page.wait_for_load_state("networkidle")

        selector = "#ticket-form textarea[data-description-editor]"
        png_b64 = base64.b64encode(png).decode()
        gif_b64 = base64.b64encode(b"GIF89a\x01\x00\x01\x00\x00\x00\x00;").decode()
        synchronous_value = page.evaluate(
            """([selector, pngB64, gifB64]) => {
                const pngBytes = Uint8Array.from(atob(pngB64), c => c.charCodeAt(0));
                const gifBytes = Uint8Array.from(atob(gifB64), c => c.charCodeAt(0));
                const target = document.querySelector(selector);
                target.focus();
                target.value = "abcdXXXXefghIJ";
                target.setSelectionRange(4, 8);
                const dtPng = new DataTransfer();
                dtPng.items.add(new File([pngBytes], "shot", { type: "image/png" }));
                target.dispatchEvent(new ClipboardEvent("paste", {
                    clipboardData: dtPng, bubbles: true, cancelable: true
                }));
                // Caret moves past the selection for the second paste while
                // the PNG upload is still pending.
                target.setSelectionRange(12, 12);
                const dtGif = new DataTransfer();
                dtGif.items.add(new File([gifBytes], "shot", { type: "image/gif" }));
                target.dispatchEvent(new ClipboardEvent("paste", {
                    clipboardData: dtGif, bubbles: true, cancelable: true
                }));
                return target.value;
            }""",
            [selector, png_b64, gif_b64],
        )
        # Nothing is inserted synchronously: both uploads are still pending.
        assert synchronous_value == "abcdXXXXefghIJ"

        _wait_for_image_reference(page, selector, count=2)
        final_value = page.evaluate(f"document.querySelector('{selector}').value")
        png_refs = re.findall(r"!\[image\]\(/images/[0-9a-f]{32}\.png\)", final_value)
        gif_refs = re.findall(r"!\[image\]\(/images/[0-9a-f]{32}\.gif\)", final_value)
        assert len(png_refs) == 1 and len(gif_refs) == 1, final_value
        # The selection was replaced once by the first reference and the
        # second reference sits exactly at the net-shifted caret position:
        # right where caret 12 was, before the trailing 'IJ'.
        assert final_value == "abcd" + png_refs[0] + "efgh" + gif_refs[0] + "IJ", final_value
        assert page.locator("#ticket-form [data-image-error]").is_hidden()

    def test_second_paste_starting_inside_replaced_selection_lands_after_first(
        self, page: Page, base_url: str, seeded_projects, make_ticket, png: bytes
    ):
        """A queued paste whose caret starts INSIDE the replaced selection.

        Paste 1 replaces [4, 8) ('XXXX') with its reference; paste 2 is queued
        at caret 6, inside that range. The consumed-selection rule must anchor
        the second reference immediately after the first one (at the first
        reference's executed end) — not at the shifted adjusted caret, which
        would land inside the following prose. Nothing further is deleted:
        'efgh' survives intact.
        """
        ticket = make_ticket(title="Partial overlap paste ticket")
        page.goto(f"{base_url}/tickets/{ticket['id']}/edit")
        page.wait_for_load_state("networkidle")

        selector = "#ticket-form textarea[data-description-editor]"
        png_b64 = base64.b64encode(png).decode()
        gif_b64 = base64.b64encode(b"GIF89a\x01\x00\x01\x00\x00\x00\x00;").decode()
        synchronous_value = page.evaluate(
            """([selector, pngB64, gifB64]) => {
                const pngBytes = Uint8Array.from(atob(pngB64), c => c.charCodeAt(0));
                const gifBytes = Uint8Array.from(atob(gifB64), c => c.charCodeAt(0));
                const target = document.querySelector(selector);
                target.focus();
                target.value = "abcdXXXXefgh";
                target.setSelectionRange(4, 8);
                const dtPng = new DataTransfer();
                dtPng.items.add(new File([pngBytes], "shot", { type: "image/png" }));
                target.dispatchEvent(new ClipboardEvent("paste", {
                    clipboardData: dtPng, bubbles: true, cancelable: true
                }));
                // Caret moves inside the replaced selection for the second
                // paste while the PNG upload is still pending.
                target.setSelectionRange(6, 6);
                const dtGif = new DataTransfer();
                dtGif.items.add(new File([gifBytes], "shot", { type: "image/gif" }));
                target.dispatchEvent(new ClipboardEvent("paste", {
                    clipboardData: dtGif, bubbles: true, cancelable: true
                }));
                return target.value;
            }""",
            [selector, png_b64, gif_b64],
        )
        # Nothing is inserted synchronously: both uploads are still pending.
        assert synchronous_value == "abcdXXXXefgh"

        _wait_for_image_reference(page, selector, count=2)
        final_value = page.evaluate(f"document.querySelector('{selector}').value")
        png_refs = re.findall(r"!\[image\]\(/images/[0-9a-f]{32}\.png\)", final_value)
        gif_refs = re.findall(r"!\[image\]\(/images/[0-9a-f]{32}\.gif\)", final_value)
        assert len(png_refs) == 1 and len(gif_refs) == 1, final_value
        # The second reference sits right after the first one and nothing
        # else was deleted — the following prose ('efgh') is intact.
        assert final_value == "abcd" + png_refs[0] + gif_refs[0] + "efgh", final_value
        assert page.locator("#ticket-form [data-image-error]").is_hidden()

    def test_single_paste_over_selection_replaces_it(
        self, page: Page, base_url: str, seeded_projects, make_ticket, png: bytes
    ):
        """A lone paste over a non-empty selection still replaces it.

        Guard for the concurrent-paste collapse rule: with no earlier
        completed insertion consuming the selection, the paste must behave
        like a normal replace — the selected text is gone, replaced by the
        reference, and the surrounding text survives.
        """
        ticket = make_ticket(title="Selection replace paste ticket")
        page.goto(f"{base_url}/tickets/{ticket['id']}/edit")
        page.wait_for_load_state("networkidle")

        selector = "#ticket-form textarea[data-description-editor]"
        png_b64 = base64.b64encode(png).decode()
        page.evaluate(
            """([selector, pngB64]) => {
                const pngBytes = Uint8Array.from(atob(pngB64), c => c.charCodeAt(0));
                const target = document.querySelector(selector);
                target.focus();
                target.value = "hello world again";
                target.setSelectionRange(6, 11);
                const dt = new DataTransfer();
                dt.items.add(new File([pngBytes], "shot", { type: "image/png" }));
                target.dispatchEvent(new ClipboardEvent("paste", {
                    clipboardData: dt, bubbles: true, cancelable: true
                }));
                return target.value;
            }""",
            [selector, png_b64],
        )

        _wait_for_image_reference(page, selector, count=1)
        final_value = page.evaluate(f"document.querySelector('{selector}').value")
        png_refs = re.findall(r"!\[image\]\(/images/[0-9a-f]{32}\.png\)", final_value)
        assert len(png_refs) == 1, final_value
        assert final_value == "hello " + png_refs[0] + " again", final_value
        assert page.locator("#ticket-form [data-image-error]").is_hidden()

    def test_second_paste_at_earlier_offset_lands_at_its_paste_position(
        self, page: Page, base_url: str, seeded_projects, make_ticket, png: bytes
    ):
        """A second paste at an EARLIER caret while the first is still pending.

        The first paste captures caret 8 in "hello world"; the second fires
        at caret 2 before the first upload completes. The queued second
        insertion must be shifted only by completed insertions that landed
        at or before its own paste-time start — the first reference lands at
        8, after the second's paste position, so it must not push the second
        reference away from offset 2. (Shifting by every earlier insertion
        regardless of position would drop the second reference at 8+len,
        inside/after the first markdown.)

        Different formats (PNG, then GIF) make the references distinguishable:
        the GIF reference must sit at offset 2 and the PNG reference after the
        remaining prose, i.e. 'he' + GIF + 'llo wo' + PNG + 'rld'.
        """
        ticket = make_ticket(title="Earlier offset paste ticket")
        page.goto(f"{base_url}/tickets/{ticket['id']}/edit")
        page.wait_for_load_state("networkidle")

        selector = "#ticket-form textarea[data-description-editor]"
        png_b64 = base64.b64encode(png).decode()
        gif_b64 = base64.b64encode(b"GIF89a\x01\x00\x01\x00\x00\x00\x00;").decode()
        synchronous_value = page.evaluate(
            """([selector, pngB64, gifB64]) => {
                const pngBytes = Uint8Array.from(atob(pngB64), c => c.charCodeAt(0));
                const gifBytes = Uint8Array.from(atob(gifB64), c => c.charCodeAt(0));
                const target = document.querySelector(selector);
                target.focus();
                target.value = "hello world";
                target.setSelectionRange(8, 8);
                const dtPng = new DataTransfer();
                dtPng.items.add(new File([pngBytes], "shot", { type: "image/png" }));
                target.dispatchEvent(new ClipboardEvent("paste", {
                    clipboardData: dtPng, bubbles: true, cancelable: true
                }));
                // Caret moves to 2 for the second paste while the PNG upload
                // is still pending (insertion happens in a later task).
                target.setSelectionRange(2, 2);
                const dtGif = new DataTransfer();
                dtGif.items.add(new File([gifBytes], "shot", { type: "image/gif" }));
                target.dispatchEvent(new ClipboardEvent("paste", {
                    clipboardData: dtGif, bubbles: true, cancelable: true
                }));
                return target.value;
            }""",
            [selector, png_b64, gif_b64],
        )
        # Nothing is inserted synchronously: both uploads are still pending.
        assert synchronous_value == "hello world"

        _wait_for_image_reference(page, selector, count=2)
        final_value = page.evaluate(f"document.querySelector('{selector}').value")
        png_refs = re.findall(r"!\[image\]\(/images/[0-9a-f]{32}\.png\)", final_value)
        gif_refs = re.findall(r"!\[image\]\(/images/[0-9a-f]{32}\.gif\)", final_value)
        assert len(png_refs) == 1 and len(gif_refs) == 1, final_value
        # The GIF reference sits at its paste-time offset 2 and the PNG
        # reference at its own offset 8 — the later-queued PNG insertion
        # landing after the GIF's position does not shift the GIF.
        assert final_value == "he" + gif_refs[0] + "llo wo" + png_refs[0] + "rld", final_value
        assert page.locator("#ticket-form [data-image-error]").is_hidden()


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
