"""E2E tests for the backlog's label filter (JRB-003).

The browser tier drives the real interface: the collapsible labels panel in
the filter bar, the match-mode control, the labels column of the backlog
table and the widened search box.

Label names and ticket titles are run-unique: the e2e server keeps its state
for the whole run, so a fixed name would also match an earlier test's ticket.
"""

import uuid

import httpx
from playwright.sync_api import Page, expect


def _unique(prefix: str) -> str:
    """A run-unique name (the e2e database persists for the whole run)."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _label_id(base_url: str, name: str) -> int:
    """The id of a label in the registry."""
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        response = client.get("/api/v1/labels")
        assert response.status_code == 200
        for label in response.json():
            if label["name"] == name:
                return int(label["id"])
    raise AssertionError(f"label {name!r} is not in the registry")


def _attach(base_url: str, ticket_id: int, name: str) -> None:
    """Attach a label to a ticket (the label is created on demand)."""
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        response = client.post(f"/api/v1/tickets/{ticket_id}/labels", json={"name": name})
        assert response.status_code == 201


def _open_labels_panel(page: Page) -> None:
    """Expand the collapsible labels panel (it is collapsed by default)."""
    if page.locator("#labels-filter-panel[open]").count() == 0:
        page.click("#labels-filter-panel summary")
        page.wait_for_timeout(200)


def _check_label(page: Page, label_id: int) -> None:
    """Tick the checkbox of a label in the filter panel."""
    _open_labels_panel(page)
    page.check(f'input[name="label_ids"][value="{label_id}"]')


def _apply(page: Page) -> None:
    """Submit the filter form and wait for the table body to be swapped."""
    page.click("button:has-text('Filter')")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(300)


def _match_mode(page: Page, mode: str) -> None:
    """Choose the match mode of the label filter."""
    page.select_option("select[name='label_match']", mode)


class TestLabelFilter:
    """Filtering the backlog by label."""

    def test_filter_by_one_label(self, page: Page, base_url: str, make_ticket):
        """Only the tickets carrying the selected label are listed."""
        label = _unique("e2e-one-label")
        labelled = make_ticket(title=_unique("One label member"))
        other = make_ticket(title=_unique("One label outsider"))
        _attach(base_url, labelled["id"], label)

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        _check_label(page, _label_id(base_url, label))
        _apply(page)

        expect(page.locator(f"#ticket-row-{labelled['id']}")).to_be_visible(timeout=10000)
        assert page.locator(f"#ticket-row-{other['id']}").count() == 0

    def test_filter_by_several_labels_matching_all(self, page: Page, base_url: str, make_ticket):
        """In "all" mode a ticket must carry every selected label."""
        first = _unique("e2e-all-first")
        second = _unique("e2e-all-second")
        both = make_ticket(title=_unique("Carries both"))
        only_first = make_ticket(title=_unique("Carries the first"))
        only_second = make_ticket(title=_unique("Carries the second"))
        _attach(base_url, both["id"], first)
        _attach(base_url, both["id"], second)
        _attach(base_url, only_first["id"], first)
        _attach(base_url, only_second["id"], second)

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        _check_label(page, _label_id(base_url, first))
        _check_label(page, _label_id(base_url, second))
        _match_mode(page, "all")
        _apply(page)

        expect(page.locator(f"#ticket-row-{both['id']}")).to_be_visible(timeout=10000)
        assert page.locator(f"#ticket-row-{only_first['id']}").count() == 0
        assert page.locator(f"#ticket-row-{only_second['id']}").count() == 0

    def test_filter_by_several_labels_matching_any(self, page: Page, base_url: str, make_ticket):
        """In "any" mode a ticket carrying one of the labels is enough."""
        first = _unique("e2e-any-first")
        second = _unique("e2e-any-second")
        both = make_ticket(title=_unique("Carries both"))
        only_first = make_ticket(title=_unique("Carries the first"))
        only_second = make_ticket(title=_unique("Carries the second"))
        _attach(base_url, both["id"], first)
        _attach(base_url, both["id"], second)
        _attach(base_url, only_first["id"], first)
        _attach(base_url, only_second["id"], second)

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        _check_label(page, _label_id(base_url, first))
        _check_label(page, _label_id(base_url, second))
        _match_mode(page, "any")
        _apply(page)

        expect(page.locator(f"#ticket-row-{both['id']}")).to_be_visible(timeout=10000)
        expect(page.locator(f"#ticket-row-{only_first['id']}")).to_be_visible(timeout=10000)
        expect(page.locator(f"#ticket-row-{only_second['id']}")).to_be_visible(timeout=10000)

    def test_the_match_mode_defaults_to_all(self, page: Page, base_url: str, make_ticket):
        """Without touching the control, every selected label must be present."""
        first = _unique("e2e-default-first")
        second = _unique("e2e-default-second")
        both = make_ticket(title=_unique("Carries both"))
        only_first = make_ticket(title=_unique("Carries the first"))
        _attach(base_url, both["id"], first)
        _attach(base_url, both["id"], second)
        _attach(base_url, only_first["id"], first)

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        _check_label(page, _label_id(base_url, first))
        _check_label(page, _label_id(base_url, second))
        _apply(page)

        expect(page.locator(f"#ticket-row-{both['id']}")).to_be_visible(timeout=10000)
        assert page.locator(f"#ticket-row-{only_first['id']}").count() == 0

    def test_the_labels_column_shows_why_a_row_matched(
        self, page: Page, base_url: str, make_ticket
    ):
        """The table shows the labels of every listed ticket."""
        label = _unique("e2e-column")
        ticket = make_ticket(title=_unique("Column member"))
        _attach(base_url, ticket["id"], label)

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        _check_label(page, _label_id(base_url, label))
        _apply(page)

        chip = page.locator(f'#ticket-row-{ticket["id"]} .label-chip[data-label-name="{label}"]')
        expect(chip).to_be_visible(timeout=10000)


class TestSearchByLabelName:
    """The search box finds a ticket by the name of one of its labels."""

    def test_find_a_ticket_by_searching_for_its_label_name(
        self, page: Page, base_url: str, make_ticket
    ):
        label = _unique("e2e-searchable")
        ticket = make_ticket(title=_unique("Findable by label"))
        other = make_ticket(title=_unique("Not findable by label"))
        _attach(base_url, ticket["id"], label)

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        page.fill("input[name='q']", label)
        _apply(page)

        expect(page.locator(f"#ticket-row-{ticket['id']}")).to_be_visible(timeout=10000)
        assert page.locator(f"#ticket-row-{other['id']}").count() == 0

    def test_the_search_field_is_relabelled(self, page: Page, base_url: str):
        """The field is labelled "Search", not "Search Title"."""
        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        expect(page.locator("label[for='q']")).to_have_text("Search")


class TestLabelFilterSurvivesSortingAndPaging:
    """The label filter is not dropped by an unrelated click."""

    def test_the_filter_survives_sorting(self, page: Page, base_url: str, make_ticket):
        label = _unique("e2e-sort")
        member = make_ticket(title=_unique("Sorted member"))
        outsider = make_ticket(title=_unique("Sorted outsider"))
        _attach(base_url, member["id"], label)

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        _check_label(page, _label_id(base_url, label))
        _apply(page)
        expect(page.locator(f"#ticket-row-{member['id']}")).to_be_visible(timeout=10000)

        page.click("th:has-text('Title')")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(300)

        expect(page.locator(f"#ticket-row-{member['id']}")).to_be_visible(timeout=10000)
        assert page.locator(f"#ticket-row-{outsider['id']}").count() == 0

    def test_the_filter_survives_paging(self, page: Page, base_url: str, make_ticket):
        label = _unique("e2e-page")
        first = make_ticket(title=_unique("Paged member A"))
        second = make_ticket(title=_unique("Paged member B"))
        outsider = make_ticket(title=_unique("Paged outsider"))
        _attach(base_url, first["id"], label)
        _attach(base_url, second["id"], label)

        page.goto(f"{base_url}/backlog?page_size=1")
        page.wait_for_load_state("networkidle")
        _check_label(page, _label_id(base_url, label))
        _apply(page)

        page.click("a:has-text('Next')")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(300)

        assert page.locator(f"#ticket-row-{outsider['id']}").count() == 0
        rows = page.locator("#tickets-table-body tr[id^='ticket-row-']")
        assert rows.count() == 1

    def test_the_filter_state_is_in_the_url(self, page: Page, base_url: str, make_ticket):
        """The filter state is in the URL, so the view can be bookmarked."""
        label = _unique("e2e-url")
        member = make_ticket(title=_unique("Bookmarked member"))
        _attach(base_url, member["id"], label)
        label_id = _label_id(base_url, label)

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        _check_label(page, label_id)
        _apply(page)

        assert f"label_ids={label_id}" in page.url

        # The bookmarked URL restores the filter.
        page.goto(page.url)
        page.wait_for_load_state("networkidle")
        expect(page.locator(f"#ticket-row-{member['id']}")).to_be_visible(timeout=10000)
        expect(page.locator(f'input[name="label_ids"][value="{label_id}"]')).to_be_checked()


class TestProjectScopedLabelFilter:
    """The project-scoped ticket view offers the same label filter."""

    def test_the_project_view_filters_by_label(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        label = _unique("e2e-project")
        uns, web, _ = seeded_projects
        member = make_ticket(project_id=web["id"], title=_unique("Scoped member"))
        elsewhere = make_ticket(project_id=uns["id"], title=_unique("Scoped outsider"))
        _attach(base_url, member["id"], label)

        page.goto(f"{base_url}/projects/{web['id']}/tickets")
        page.wait_for_load_state("networkidle")
        _check_label(page, _label_id(base_url, label))
        _apply(page)

        expect(page.locator(f"#ticket-row-{member['id']}")).to_be_visible(timeout=10000)
        assert page.locator(f"#ticket-row-{elsewhere['id']}").count() == 0
