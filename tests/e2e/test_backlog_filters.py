"""E2E test for Backlog Filtering flow (ticket 15, flow 5).

The Backlog filter form applies filters only when submitted (via the Filter
button, an hx-get that swaps a fresh tbody into #tickets-table-body), so every
test selects its filters and clicks Filter before asserting.

The Project/Type/Status/Priority/Sprint filters are multi-select dropdowns:
each filter is a trigger button that opens a popover of checkboxes (the
visible checkboxes are the form controls; there is no <select>). Tests that
set a multi-select value open its popover first, then check the box.

Titles asserted against are run-unique: the `q` filter is a substring match over
titles, so a fixed title would also match the same test's leftovers in a
database that has been used before.
"""

import uuid

import pytest
from playwright.sync_api import Page, expect

# Fields whose filter is a multi-select dropdown (checkbox popover).
MULTI_FIELDS = ("project_ids", "types", "statuses", "priorities", "sprint_ids")


def _open_multiselect(page: Page, field: str) -> None:
    """Open the dropdown popover for a multi-select filter field.

    Popovers toggle on the trigger and close on an outside click, so Playwright
    must open one before interacting with its checkboxes/radios. Idempotent: if
    the popover is already open it is left open.
    """
    trigger = page.locator(f"[data-ms-field='{field}'] [data-ms-trigger]")
    if trigger.get_attribute("aria-expanded") != "true":
        trigger.click()
    page.wait_for_selector(
        f"[data-ms-field='{field}'] [data-ms-option]", state="visible", timeout=1000
    )


def _select_in_multiselect(page: Page, field: str, *values: str) -> None:
    """Open `field`'s dropdown and check each given option `value`."""
    _open_multiselect(page, field)
    for value in values:
        page.check(f"[data-ms-field='{field}'] [data-ms-option][value='{value}']")


class TestBacklogFilters:
    """Tests for backlog filtering flow."""

    @staticmethod
    def _apply(page: Page) -> None:
        """Submit the filter form and wait for the tbody swap."""
        page.click("button:has-text('Filter')")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(300)

    def test_filter_by_project(self, page: Page, base_url: str, seeded_projects, make_ticket):
        """Filtering by project shows only that project's tickets."""
        web = seeded_projects[1]
        in_web = make_ticket(project_id=web["id"], title="WEB Filter Member")
        in_uns = make_ticket(project_id=1, title="UNS Filter Member")

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        _select_in_multiselect(page, "project_ids", str(web["id"]))
        self._apply(page)

        expect(page.locator(f"#ticket-row-{in_web['id']}")).to_be_visible(timeout=10000)
        assert page.locator(f"#ticket-row-{in_uns['id']}").count() == 0

    def test_filter_by_type(self, page: Page, base_url: str, seeded_projects, make_ticket):
        """Filtering by type shows only matching tickets."""
        story = make_ticket(title="Type Filter Story", ticket_type="Story")
        bug = make_ticket(title="Type Filter Bug", ticket_type="Bug")

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        _select_in_multiselect(page, "types", "Story")
        self._apply(page)

        expect(page.locator(f"#ticket-row-{story['id']}")).to_be_visible(timeout=10000)
        assert page.locator(f"#ticket-row-{bug['id']}").count() == 0

    def test_filter_by_status(self, page: Page, base_url: str, seeded_projects, make_ticket):
        """Filtering by status shows only matching tickets."""
        open_ticket = make_ticket(title="Status Filter Open", status="Open")
        groomed = make_ticket(title="Status Filter Groomed", status="Groomed")

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        _select_in_multiselect(page, "statuses", "Open")
        self._apply(page)

        expect(page.locator(f"#ticket-row-{open_ticket['id']}")).to_be_visible(timeout=10000)
        assert page.locator(f"#ticket-row-{groomed['id']}").count() == 0

    def test_filter_by_sprint(
        self, page: Page, base_url: str, seeded_projects, make_ticket, make_sprint
    ):
        """Filtering by sprint shows only that sprint's tickets."""
        import httpx

        sprint = make_sprint()
        member = make_ticket(title="Sprint Member Unique")
        outsider = make_ticket(title="Sprint Outsider Unique")
        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            resp = client.post(f"/api/v1/sprints/{sprint['id']}/tickets/{member['id']}")
            assert resp.status_code == 200

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        _select_in_multiselect(page, "sprint_ids", str(sprint["id"]))
        self._apply(page)

        expect(page.locator(f"#ticket-row-{member['id']}")).to_be_visible(timeout=10000)
        assert page.locator(f"#ticket-row-{outsider['id']}").count() == 0

    def test_text_search(self, page: Page, base_url: str, seeded_projects, make_ticket):
        """Text search matches ticket titles (and nothing else)."""
        needle = make_ticket(title="Zebra Needle Ticket")
        other = make_ticket(title="Unrelated Hippo Ticket")

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        page.fill("input[name='q']", "Zebra Needle")
        self._apply(page)

        expect(page.locator(f"#ticket-row-{needle['id']}")).to_be_visible(timeout=10000)
        assert page.locator(f"#ticket-row-{other['id']}").count() == 0

    def test_combined_filters(self, page: Page, base_url: str, seeded_projects, make_ticket):
        """Combined filters use AND logic: only the fully matching ticket remains."""
        web = seeded_projects[1]
        needle = f"AND Match Combo {uuid.uuid4().hex[:8]}"
        match = make_ticket(project_id=web["id"], title=needle, ticket_type="Story", status="Open")
        # Same project+type but different status
        make_ticket(
            project_id=web["id"],
            title="AND Mismatch Status",
            ticket_type="Story",
            status="Groomed",
        )

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        _select_in_multiselect(page, "project_ids", str(web["id"]))
        _select_in_multiselect(page, "types", "Story")
        _select_in_multiselect(page, "statuses", "Open")
        page.fill("input[name='q']", needle)
        self._apply(page)

        rows = page.locator("#tickets-table-body tr")
        assert rows.count() == 1, f"expected exactly 1 row, got {rows.count()}"
        expect(page.locator(f"#ticket-row-{match['id']}")).to_be_visible()

    def test_filter_by_date(self, page: Page, base_url: str, seeded_projects, make_ticket):
        """Filtering by created date (US16): bounds are inclusive calendar dates.

        The date window is combined with a unique-title search so the result set
        is exactly this test's ticket: otherwise the empty-state assertion would
        only hold on a database with no other tickets in it.
        """
        from datetime import date, timedelta

        needle = f"Date Filter Member {uuid.uuid4().hex[:8]}"
        ticket = make_ticket(title=needle)

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        page.fill("input[name='q']", needle)

        # A window ending tomorrow includes the freshly created ticket.
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        page.fill("input[name='created_before']", tomorrow)
        self._apply(page)
        expect(page.locator(f"#ticket-row-{ticket['id']}")).to_be_visible(timeout=10000)

        # A window that ended two days ago excludes it (No tickets found).
        two_days_ago = (date.today() - timedelta(days=2)).isoformat()
        page.fill("input[name='created_before']", two_days_ago)
        self._apply(page)
        assert page.locator(f"#ticket-row-{ticket['id']}").count() == 0
        expect(page.locator("text=No tickets found")).to_be_visible()

        # created_after today keeps the ticket again.
        today = date.today().isoformat()
        page.fill("input[name='created_after']", today)
        page.fill("input[name='created_before']", "")
        self._apply(page)
        expect(page.locator(f"#ticket-row-{ticket['id']}")).to_be_visible(timeout=10000)

    def test_clear_filters(self, page: Page, base_url: str, seeded_projects):
        """Test clear filters button works."""
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")

        # Apply some filters
        _select_in_multiselect(page, "project_ids", "2")
        _select_in_multiselect(page, "types", "Story")
        page.wait_for_load_state("networkidle")

        # Click Clear filters
        page.click("button:has-text('Clear'), a:has-text('Clear')")
        page.wait_for_load_state("networkidle")

        # Verify filters reset: no multi-select option checkboxes remain checked.
        assert page.locator("[data-ms-field='project_ids'] [data-ms-option]:checked").count() == 0
        assert page.locator("[data-ms-field='types'] [data-ms-option]:checked").count() == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestBacklogFiltersSurviveSortingAndPaging:
    """JRB-002: the filter form carries the active filters into sort/page requests.

    Before the prefactor every sortable header and every pagination link
    restated the filter values by hand, so a filter could be dropped by an
    unrelated click. Now the requests include the filter form, so the filters
    ride along with the sort and the page.
    """

    @pytest.fixture
    def scenario(self, base_url, seeded_projects, make_ticket, make_sprint):
        """Four matching tickets in a sprint, plus two outsiders."""
        import httpx

        marker = uuid.uuid4().hex[:8]
        uns, web, _ = seeded_projects
        sprint = make_sprint()

        matching = [
            make_ticket(
                project_id=uns["id"],
                title=f"Match {marker} {suffix}",
                ticket_type="Story",
                status="Open",
                priority="Medium",
            )
            for suffix in ("A", "B", "C", "D")
        ]
        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            for ticket in matching:
                resp = client.post(f"/api/v1/sprints/{sprint['id']}/tickets/{ticket['id']}")
                assert resp.status_code == 200

        # Matches the free-text search, but differs in every other filter.
        matchable_outsider = make_ticket(
            project_id=web["id"],
            title=f"Outsider {marker}",
            ticket_type="Bug",
            status="Groomed",
            priority="Critical",
        )
        # Matches no filter of the scenario.
        other_outsider = make_ticket(
            project_id=uns["id"],
            title=f"Other {uuid.uuid4().hex[:8]}",
            ticket_type="Bug",
            status="Groomed",
            priority="Critical",
        )
        return {
            "marker": marker,
            "sprint": sprint,
            "uns": uns,
            "matching": matching,
            "matchable_outsider": matchable_outsider,
            "other_outsider": other_outsider,
        }

    @staticmethod
    def _row_ids(page: Page) -> list[int]:
        """Ids of the tickets currently listed in the backlog table."""
        ids = page.eval_on_selector_all(
            "#tickets-table-body tr[id^='ticket-row-']",
            "els => els.map(e => e.id)",
        )
        return [int(row_id.replace("ticket-row-", "")) for row_id in ids]

    @staticmethod
    def _apply(page: Page) -> None:
        page.click("button:has-text('Filter')")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(200)

    @staticmethod
    def _record_urls(page: Page) -> list[str]:
        """Collect the URLs of the requests the page makes."""
        urls: list[str] = []
        page.on("request", lambda request, urls=urls: urls.append(request.url))
        return urls

    @staticmethod
    def _last_backlog_url(urls: list[str]) -> str:
        backlog = [url for url in urls if "/backlog?" in url]
        assert backlog, f"no backlog request was issued: {urls}"
        return backlog[-1]

    @staticmethod
    def _set_filter(page: Page, name: str, value: str) -> None:
        if name in MULTI_FIELDS:
            _select_in_multiselect(page, name, value)
        else:
            page.fill(f"input[name='{name}']", value)

    def test_each_filter_survives_sorting_and_paging(self, page: Page, base_url: str, scenario):
        """Every pre-existing filter still applies after sorting and after paging."""
        from datetime import date

        marker = scenario["marker"]
        matchable_outsider = scenario["matchable_outsider"]["id"]
        other_outsider = scenario["other_outsider"]["id"]
        matching_ids = {t["id"] for t in scenario["matching"]}
        today = date.today().isoformat()

        cases = [
            # (filter, value, the ticket the filter must keep out of the list)
            ("project_ids", str(scenario["uns"]["id"]), matchable_outsider),
            ("types", "Story", matchable_outsider),
            ("statuses", "Open", matchable_outsider),
            ("priorities", "Medium", matchable_outsider),
            ("sprint_ids", str(scenario["sprint"]["id"]), matchable_outsider),
            ("q", marker, other_outsider),
            ("created_after", today, other_outsider),
            ("created_before", today, other_outsider),
        ]

        for name, value, excluded in cases:
            page.goto(f"{base_url}/backlog?page_size=3")
            page.wait_for_load_state("networkidle")
            # The free-text search isolates the scenario's tickets; the filter
            # under test is applied on top of it.
            page.fill("input[name='q']", marker)
            if name != "q":
                self._set_filter(page, name, value)
            self._apply(page)

            rows = self._row_ids(page)
            assert excluded not in rows, f"{name} filter not applied"
            assert rows, f"{name} filter left an empty list"
            assert matching_ids & set(rows), f"{name} filter hid the matching tickets"

            # Sorting a column must carry the filter along.
            urls = self._record_urls(page)
            page.click("th:has-text('Title')")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(200)
            url = self._last_backlog_url(urls)
            assert f"{name}={value}" in url, f"sorting dropped the {name} filter: {url}"
            assert "sort=title" in url
            assert "page=1" in url, "sorting must return to the first page"
            rows = self._row_ids(page)
            assert excluded not in rows, f"{name} filter dropped by sorting"
            assert matching_ids & set(rows), f"{name} filter hid the matching tickets"

            # Paging must carry the filter along as well.
            urls.clear()
            page.click("a:has-text('Next')")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(200)
            url = self._last_backlog_url(urls)
            assert f"{name}={value}" in url, f"paging dropped the {name} filter: {url}"
            assert "page=2" in url
            rows = self._row_ids(page)
            assert excluded not in rows, f"{name} filter dropped by paging"

    def test_date_filter_still_applies_after_sorting(self, page: Page, base_url: str, scenario):
        """A created-from/created-to window is still applied after sorting."""
        from datetime import date, timedelta

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        # A window that starts tomorrow excludes every ticket created so far.
        page.fill("input[name='created_after']", (date.today() + timedelta(days=1)).isoformat())
        self._apply(page)
        expect(page.locator("text=No tickets found")).to_be_visible()

        page.click("th:has-text('Title')")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(200)
        expect(page.locator("text=No tickets found")).to_be_visible()

        # A window that ended before any ticket could have been created
        # excludes them just as well. The bound is absolute on purpose: the
        # e2e server can run against a database that also holds tickets
        # created on earlier days, and "yesterday" would keep those.
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        page.fill("input[name='created_before']", "2000-01-01")
        self._apply(page)
        expect(page.locator("text=No tickets found")).to_be_visible()

    def test_project_scoped_view_keeps_working(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        """The project-scoped ticket view shares the filter form and still sorts."""
        uns, web, _ = seeded_projects
        mine = make_ticket(project_id=web["id"], title=f"Scoped {uuid.uuid4().hex[:8]}")
        elsewhere = make_ticket(project_id=uns["id"], title=f"Elsewhere {uuid.uuid4().hex[:8]}")

        page.goto(f"{base_url}/backlog?project_id={web['id']}")
        page.wait_for_load_state("networkidle")
        expect(page.locator("#backlog-filter-form")).to_be_visible()
        expect(page.locator(f"#ticket-row-{mine['id']}")).to_be_visible()
        assert page.locator(f"#ticket-row-{elsewhere['id']}").count() == 0

        # Sorting a column keeps the view scoped to the project.
        page.click("th:has-text('Title')")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(200)
        expect(page.locator(f"#ticket-row-{mine['id']}")).to_be_visible()
        assert page.locator(f"#ticket-row-{elsewhere['id']}").count() == 0

    def test_column_header_sorts_and_paging_keeps_the_sort(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        """Clicking a header sorts and returns to page one; paging keeps the sort."""
        marker = uuid.uuid4().hex[:8]
        uns = seeded_projects[0]
        # Created in an order that differs from the title order, so a lost sort
        # is visible in the rows: by number desc C, D, A, B; by title desc D, C, B, A.
        tickets = {
            suffix: make_ticket(project_id=uns["id"], title=f"{suffix}-{marker}")
            for suffix in ("B", "A", "D", "C")
        }

        page.goto(f"{base_url}/backlog?page_size=2")
        page.wait_for_load_state("networkidle")
        page.fill("input[name='q']", marker)
        self._apply(page)

        # Move to the second page first, so the sort has to return to page one.
        page.click("a:has-text('Next')")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(200)
        assert self._row_ids(page) == [tickets["A"]["id"], tickets["B"]["id"]]

        page.click("th:has-text('Title')")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(200)
        # Sorted by title, descending, and back on the first page.
        assert self._row_ids(page) == [tickets["D"]["id"], tickets["C"]["id"]]

        page.click("a:has-text('Next')")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(200)
        # Paging did not change the sort: the second page of a title-desc list.
        assert self._row_ids(page) == [tickets["B"]["id"], tickets["A"]["id"]]


class TestMultiSelectBacklogFilters:
    """E2E coverage for the multi-select backlog filter UI (include/exclude
    radios, selecting several values). The trigger/label/popover mechanics
    themselves are covered in TestMultiSelectDropdownUI."""

    @staticmethod
    def _apply(page: Page) -> None:
        page.click("button:has-text('Filter')")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(300)

    def test_select_all_checkbox_checks_every_option(
        self, page: Page, base_url: str, seeded_projects
    ):
        """The "Select all" checkbox in a dropdown selects every option."""
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        _open_multiselect(page, "project_ids")
        page.click("[data-ms-field='project_ids'] [data-ms-select-all]")
        n_options = page.locator("[data-ms-field='project_ids'] [data-ms-option]").count()
        assert n_options > 1, "need more than one project to test 'Select all'"
        n_selected = page.locator("[data-ms-field='project_ids'] [data-ms-option]:checked").count()
        assert n_selected == n_options, f"{n_selected} of {n_options} options selected"
        # Trigger label updates to the total.
        assert (
            page.locator("[data-ms-field='project_ids'] .ms-trigger-text").text_content()
            == f"{n_options} selected"
        )

    def test_exclude_radio_hides_the_selected_project(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        """Switching a filter to Exclude hides the selected project's tickets."""
        uns, web, _ = seeded_projects
        in_web = make_ticket(project_id=web["id"], title="Exclude Member")
        in_uns = make_ticket(project_id=uns["id"], title="Exclude Outsider")

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        _select_in_multiselect(page, "project_ids", str(web["id"]))
        # The Include/Exclude radio lives inside the (still open) project popover.
        page.check("input[name='project_filter_mode'][value='exclude']")
        self._apply(page)

        assert page.locator(f"#ticket-row-{in_web['id']}").count() == 0
        expect(page.locator(f"#ticket-row-{in_uns['id']}")).to_be_visible()

    def test_selecting_multiple_projects_keeps_only_those(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        """Selecting several projects in include mode shows only their tickets."""
        uns, web, api = seeded_projects
        in_web = make_ticket(project_id=web["id"], title="Multi Web")
        in_api = make_ticket(project_id=api["id"], title="Multi API")
        in_uns = make_ticket(project_id=uns["id"], title="Multi Uns")

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        _select_in_multiselect(page, "project_ids", str(web["id"]), str(api["id"]))
        self._apply(page)

        expect(page.locator(f"#ticket-row-{in_web['id']}")).to_be_visible()
        expect(page.locator(f"#ticket-row-{in_api['id']}")).to_be_visible()
        assert page.locator(f"#ticket-row-{in_uns['id']}").count() == 0


class TestMultiSelectDropdownUI:
    """Component-level coverage for the multi-select dropdown itself: the
    trigger label tracks the count, only one dropdown is open at a time, and a
    click outside closes the open dropdown."""

    @staticmethod
    def _count_selected(page: Page, field: str) -> int:
        return page.locator(f"[data-ms-field='{field}'] [data-ms-option]:checked").count()

    def test_trigger_label_starts_at_all_and_tracks_selection(
        self, page: Page, base_url: str, seeded_projects
    ):
        """The trigger reads 'All' initially, 'N selected' as options are checked,
        and back to 'All' when all are unchecked."""
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        field = "project_ids"
        label = page.locator(f"[data-ms-field='{field}'] .ms-trigger-text")
        assert label.text_content() == "All"

        web_id = str(seeded_projects[1]["id"])
        _select_in_multiselect(page, field, web_id)
        assert label.text_content() == "1 selected"

        # Unchecking returns it to "All".
        page.uncheck(f"[data-ms-field='{field}'] [data-ms-option][value='{web_id}']")
        assert label.text_content() == "All"

    def test_only_one_dropdown_open_at_a_time(self, page: Page, base_url: str):
        """Opening one dropdown closes any other that was open."""
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        _open_multiselect(page, "project_ids")
        assert self._count_selected(page, "project_ids") >= 0  # popover open
        assert page.locator(".ms-popover.ms-open").count() == 1
        # Opening a second dropdown closes the first.
        _open_multiselect(page, "types")
        assert page.locator(".ms-popover.ms-open").count() == 1
        # The project popover is no longer open.
        assert page.locator("[data-ms-field='project_ids'] .ms-popover.ms-open").count() == 0

    def test_popover_closes_on_outside_click(self, page: Page, base_url: str):
        """Clicking outside an open dropdown closes it."""
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        _open_multiselect(page, "project_ids")
        assert page.locator(".ms-popover.ms-open").count() == 1
        # Click on an unrelated control (the Search field, which is outside).
        page.click("input[name='q']")
        expect(page.locator(".ms-popover.ms-open")).to_have_count(0)

    def test_closed_popover_still_submits_its_checked_options(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        """A checkbox checked inside a (then closed) popover is still serialized
        by HTMX when the form is submitted - this is what replaces the old
        <select multiple> list-box for form submission."""
        uns, web, _ = seeded_projects
        in_web = make_ticket(project_id=web["id"], title="Submit While Closed")
        in_uns = make_ticket(project_id=uns["id"], title="Hidden From Closed")

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        _select_in_multiselect(page, "project_ids", str(web["id"]))
        # Close the popover by clicking outside, then submit.
        page.click("input[name='q']")
        assert page.locator(".ms-popover.ms-open").count() == 0
        page.click("button:has-text('Filter')")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(300)

        expect(page.locator(f"#ticket-row-{in_web['id']}")).to_be_visible(timeout=10000)
        assert page.locator(f"#ticket-row-{in_uns['id']}").count() == 0
