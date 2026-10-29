"""E2E coverage for creating a ticket and its links from the New Ticket modal."""

from playwright.sync_api import expect


class TestCreateTicketWithLinks:
    def test_new_ticket_modal_creates_and_displays_child_link(
        self, page, base_url, seeded_projects, make_ticket
    ):
        epic = make_ticket(
            project_id=seeded_projects[1]["id"],
            title="Epic: New Ticket links E2E",
            ticket_type="Epic",
        )

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        page.click("button:has-text('New Ticket')")
        page.wait_for_selector("#ticket-modal form", state="visible", timeout=10000)
        page.fill("#ticket-modal input[name='title']", "Story created with a parent link")

        links_section = page.locator("#ticket-links")
        links_section.locator("summary").click()
        page.click("#add-ticket-link")
        row = page.locator(".ticket-link-row").first
        row.locator("select[data-link-type]").select_option("child")
        row.locator("input[data-link-search]").fill(epic["title"])
        row.locator("input[data-link-search]").dispatch_event("keyup")
        result = row.locator(".ticket-search-result").first
        expect(result).to_have_attribute("data-ticket-type", "Epic", timeout=10000)
        result.click()
        expect(row.locator("[data-link-target-id]")).to_have_value(str(epic["id"]))

        page.click("#ticket-modal button:has-text('Create Ticket')")
        expect(page.locator("#ticket-modal form")).to_have_count(0, timeout=10000)
        expect(
            page.locator("tr[id^='ticket-row']").filter(has_text="Story created with a parent link")
        ).to_be_visible(timeout=10000)

        page.goto(f"{base_url}/tickets/{epic['id']}")
        page.wait_for_load_state("networkidle")
        expect(page.locator("#links-section")).to_contain_text("Story created with a parent link")

    def test_new_ticket_modal_without_link_rows_creates_plain_ticket(
        self, page, base_url, seeded_projects
    ):
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        page.click("button:has-text('New Ticket')")
        page.wait_for_selector("#ticket-modal form", state="visible", timeout=10000)
        page.fill("#ticket-modal input[name='title']", "Plain ticket without links")
        with page.expect_response(
            lambda response: response.url.endswith("/api/v1/tickets") and response.status == 201
        ) as response_info:
            page.click("#ticket-modal button:has-text('Create Ticket')")

        expect(page.locator("#ticket-modal form")).to_have_count(0, timeout=10000)
        expect(
            page.locator("tr[id^='ticket-row']").filter(has_text="Plain ticket without links")
        ).to_be_visible(timeout=10000)
        created = response_info.value.json()
        links_response = page.request.get(f"{base_url}/api/v1/tickets/{created['id']}/links")
        assert links_response.status == 200
        assert links_response.json() == []
