"""E2E test for Project Move flow.

Self-contained: creates a ticket in a known project, moves it via the Move Project
modal, and verifies the new prefix plus the "Formerly" badge.
"""

import httpx
import pytest
from playwright.sync_api import Page, expect


def _numbers_in_project(client: httpx.Client, project_id: int) -> list[int]:
    """Every ticket serial in one project, following pagination.

    ``GET /api/v1/tickets`` defaults to page_size=50, so scanning a single
    unfiltered page silently under-counts once a database holds more than 50
    tickets — which is exactly what made this test depend on the suite's
    accumulated state. Filtering by project and paging through the result keeps
    the expectations true against a database in any state.
    """
    numbers: list[int] = []
    page = 1
    while True:
        body = client.get(
            "/api/v1/tickets",
            params={"project_id": project_id, "page": page, "page_size": 100},
        ).json()
        numbers.extend(ticket["number"] for ticket in body["items"])
        if not body["items"] or page >= body["total_pages"]:
            return numbers
        page += 1


class TestProjectMove:
    """Tests for the project move flow."""

    def test_move_ticket_between_projects(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        """Move a ticket from UNS to WEB and verify the new ID + Formerly badge."""
        # projects: [uns, web, api] -> WEB is index 1
        web = seeded_projects[1]
        ticket = make_ticket(project_id=1, title="Ticket To Move")
        tid = ticket["id"]

        page.goto(f"{base_url}/ticket/{tid}")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#ticket-content", state="visible", timeout=10000)

        # Original ID should show UNS prefix
        original_id = page.locator(".ticket-id").inner_text()
        assert "UNS-" in original_id, f"Expected UNS prefix, got {original_id}"

        # Open the Move Project modal
        page.click("button:has-text('Move Project')")
        page.wait_for_selector("#ticket-modal form", state="visible", timeout=10000)

        # Select target project (WEB) by its real id
        page.select_option("select[name='project_id']", str(web["id"]))

        # Submit
        page.click("#ticket-modal button[type='submit']")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)

        # New ticket ID should show WEB prefix
        expect(page.locator(".ticket-id")).to_contain_text("WEB-", timeout=10000)

        # "Formerly" badge shows the original ID
        expect(page.locator("text=Formerly").first).to_be_visible(timeout=10000)

    def test_chained_moves_preserve_original_id(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        """After two moves, original_id still points to the very first ID."""
        web = seeded_projects[1]
        api = seeded_projects[2]
        ticket = make_ticket(project_id=1, title="Chained Move Ticket")
        tid = ticket["id"]

        # Move UNS -> WEB -> API via the API
        import httpx

        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            first = client.post(
                f"/api/v1/tickets/{tid}/move-project",
                json={
                    "project_id": web["id"],
                },
            ).json()
            second = client.post(
                f"/api/v1/tickets/{tid}/move-project",
                json={
                    "project_id": api["id"],
                },
            ).json()

        # original_id should be preserved from the FIRST move (not overwritten)
        assert second.get("original_id") == first.get("original_id"), (
            f"original_id changed across chained moves: "
            f"{first.get('original_id')} -> {second.get('original_id')}"
        )

        # UI should show API prefix and the original Formerly badge
        page.goto(f"{base_url}/ticket/{tid}")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#ticket-content", state="visible", timeout=10000)

        expect(page.locator(".ticket-id")).to_contain_text("API-")
        expect(page.locator("text=Formerly").first).to_be_visible()

    def test_move_back_renumbers_next_available(self, page: Page, base_url: str, seeded_projects):
        """Move back to the source project gets the next available number.

        Scenario (MSC/WEB per ticket 15 flow 3): a ticket created in MSC takes
        MSC's next available serial; moving it to WEB renumbers it to WEB's next
        available serial; a filler ticket then re-occupies the serial the move
        freed; moving the original back must therefore yield the next
        available serial in MSC, with ``original_id`` still pointing at the
        serial it was created with.

        Every expectation is derived from the projects' live numbering, so the
        test holds against an empty database and a database already carrying
        prior runs' tickets alike.
        """
        web = seeded_projects[1]

        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            existing = {p["prefix"]: p for p in client.get("/api/v1/projects").json()}
            msc = (
                existing.get("MSC")
                or client.post(
                    "/api/v1/projects",
                    json={"prefix": "MSC", "name": "Misc", "description": "move-test"},
                ).json()
            )
            msc_numbers = _numbers_in_project(client, msc["id"])
            web_numbers = _numbers_in_project(client, web["id"])
            expected_msc_number = max(msc_numbers, default=0) + 1

            ticket = client.post(
                "/api/v1/tickets",
                json={"project_id": msc["id"], "title": "Move Back Ticket"},
            ).json()
            assert ticket["number"] == expected_msc_number

            # Move to WEB -> next available number in WEB
            move_resp = client.post(
                f"/api/v1/tickets/{ticket['id']}/move-project",
                json={"project_id": web["id"]},
            )
            assert move_resp.status_code == 200, move_resp.text
            expected_web_number = max(web_numbers, default=0) + 1
            moved = client.get(f"/api/v1/tickets/{ticket['id']}").json()
            assert moved["number"] == expected_web_number
            assert moved["original_id"] == f"MSC-{expected_msc_number:03d}"

            # Filler ticket re-occupies the serial the move freed (dense renumbering):
            # the moved ticket held MSC's highest serial, so the filler lands on it.
            freed_number = expected_msc_number
            filler = client.post(
                "/api/v1/tickets",
                json={"project_id": msc["id"], "title": "MSC Filler"},
            ).json()
            assert filler["number"] == freed_number, (
                "dense renumbering should reuse the freed serial"
            )

            # Snapshot MSC numbering before the move-back so the expected serial
            # (max + 1, per ADR-0005) does not depend on the move already applied.
            expected_back_number = max(_numbers_in_project(client, msc["id"]), default=0) + 1

            # Move the original back via the UI modal
        page.goto(f"{base_url}/ticket/{ticket['id']}")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#ticket-content", state="visible", timeout=10000)
        expect(page.locator(".ticket-id")).to_contain_text(f"WEB-{expected_web_number:03d}")
        expect(page.locator("text=Formerly").first).to_be_visible()

        page.click("button:has-text('Move Project')")
        page.wait_for_selector("#ticket-modal form", state="visible", timeout=10000)
        page.select_option("select[name='project_id']", str(msc["id"]))
        page.click("#ticket-modal button[type='submit']")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)

        # Next available in MSC (the filler holds the freed serial) -> one above it
        expect(page.locator(".ticket-id")).to_contain_text(
            f"MSC-{expected_back_number:03d}", timeout=10000
        )
        # original_id still points at the serial the ticket was created with
        expect(page.locator(f"text=Formerly MSC-{expected_msc_number:03d}").first).to_be_visible()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
