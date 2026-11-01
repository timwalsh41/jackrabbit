"""E2E tests for backlog filter persistence (JRB-017).

The backlog is entered with no query params when the user returns to it from
another view (the nav link in base.html is a plain ``/backlog`` link), which is
why filter selections used to be lost. The filters are now persisted in
sessionStorage (per tab, dies with the tab - literal "for a session"
semantics): every ``htmx:pushedIntoHistory`` whose URL is a /backlog URL
stores the query string (one capture point covers filter submits, sort clicks
and pagination, since all of them use ``hx-push-url=true`` and include the
filter form); on a parameter-less backlog load the stored query populates the
filter form and re-triggers its ``hx-get``; the Clear filters link wipes the
stored key before navigating.

Patterns (multi-select helpers, run-unique titles) follow
tests/e2e/test_backlog_filters.py.
"""

import re
import uuid

from playwright.sync_api import Page, expect


def _open_multiselect(page: Page, field: str) -> None:
    """Open the dropdown popover for a multi-select filter field (idempotent)."""
    trigger = page.locator(f"[data-ms-field='{field}'] [data-ms-trigger]")
    if trigger.get_attribute("aria-expanded") != "true":
        trigger.click()
    page.wait_for_selector(
        f"[data-ms-field='{field}'] [data-ms-option]", state="visible", timeout=1000
    )


def _select_in_multiselect(page: Page, field: str, *values: str) -> None:
    """Open `field`'s dropdown, check each given option `value`, then close it."""
    _open_multiselect(page, field)
    for value in values:
        page.check(f"[data-ms-field='{field}'] [data-ms-option][value='{value}']")
    page.locator(f"[data-ms-field='{field}'] [data-ms-trigger]").click()
    expect(page.locator(f"[data-ms-field='{field}'] .ms-popover.ms-open")).to_have_count(0)


def _apply(page: Page) -> None:
    """Submit the filter form and wait for the tbody swap."""
    page.click("button:has-text('Filter')")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(300)


def _back_via_nav(page: Page) -> None:
    """Return to the backlog the way a user does: the plain nav link.

    The nav link carries no query params, so this is exactly the path that
    must restore the stashed filters.
    """
    page.click("nav a[href='/backlog']")
    page.wait_for_load_state("networkidle")
    # Give the restore-triggered hx-get (if any) time to swap the table.
    page.wait_for_timeout(500)


def _open_ticket_detail(page: Page, ticket_id: int) -> None:
    """Navigate away from the backlog to a ticket detail page."""
    page.locator(f"#ticket-row-{ticket_id} a[href='/ticket/{ticket_id}']").first.click()
    page.wait_for_load_state("networkidle")


class TestBacklogFilterPersistence:
    """Filters survive leaving the backlog and coming back within one tab."""

    def test_filters_survive_navigation_to_detail_and_back(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        """Filter, open a ticket detail, click nav Backlog -> table is filtered again."""
        suffix = uuid.uuid4().hex[:8]
        web = seeded_projects[1]
        in_web = make_ticket(project_id=web["id"], title=f"Persist Member {suffix}")
        in_uns = make_ticket(project_id=1, title=f"Persist Outsider {suffix}")

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        _select_in_multiselect(page, "project_ids", str(web["id"]))
        _apply(page)

        expect(page.locator(f"#ticket-row-{in_web['id']}")).to_be_visible(timeout=10000)
        assert page.locator(f"#ticket-row-{in_uns['id']}").count() == 0

        # Leave the backlog for a ticket detail view.
        _open_ticket_detail(page, in_web["id"])

        # Return through the plain nav link: filters must come back, and the
        # URL must carry the filter query again (hx-push-url rewrites it).
        _back_via_nav(page)
        expect(page).to_have_url(__import__("re").compile(r"project_ids="), timeout=10000)
        expect(page.locator(f"#ticket-row-{in_web['id']}")).to_be_visible(timeout=10000)
        assert page.locator(f"#ticket-row-{in_uns['id']}").count() == 0

    def test_sort_survives_navigation_and_page_resets(self, page: Page, base_url: str, make_ticket):
        """Set sort, navigate away and back -> sort/order preserved, page 1."""
        suffix = uuid.uuid4().hex[:8]
        first = make_ticket(title=f"Sort Persist A {suffix}", priority="High")
        second = make_ticket(title=f"Sort Persist B {suffix}", priority="Low")

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")

        # Click the Priority column header: sorts by priority, page resets to 1.
        page.click("th:has-text('Priority')")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(300)
        expect(page).to_have_url(__import__("re").compile(r"sort=priority"), timeout=10000)

        # Leave and come back through the nav link.
        _open_ticket_detail(page, first["id"])
        _back_via_nav(page)

        expect(page).to_have_url(__import__("re").compile(r"sort=priority"), timeout=10000)
        expect(page).to_have_url(__import__("re").compile(r"page=1"), timeout=10000)
        # The filter form is the single source of truth for the active sort:
        # after the restore its hidden sort/order fields carry the stashed
        # sort again (this is what the next filter submit / page click asks
        # the server for). Note the sort arrows in thead only render on a full
        # page load - the tbody-only swap never re-renders thead.
        expect(page.locator("#backlog-filter-form input[name='sort']")).to_have_value(
            "priority", timeout=10000
        )
        expect(page.locator("#backlog-filter-form input[name='order']")).to_have_value(
            "desc", timeout=10000
        )
        # Both tickets are still listed (sort does not filter anything away).
        expect(page.locator(f"#ticket-row-{first['id']}")).to_be_visible(timeout=10000)
        expect(page.locator(f"#ticket-row-{second['id']}")).to_be_visible(timeout=10000)

    def test_explicit_scoped_url_becomes_state_restored_on_return(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        """A full-page visit to a scoped URL is the state a later return restores.

        The URL says what it means while it is open (never overridden by the
        stash), AND it becomes the newest stashed state: a project-scoped
        backlog visited by URL, then left, must come back scoped - not
        unfiltered and not carrying some older query.
        """
        suffix = uuid.uuid4().hex[:8]
        web = seeded_projects[1]
        in_web = make_ticket(project_id=web["id"], title=f"Scoped State Member {suffix}")
        in_uns = make_ticket(project_id=1, title=f"Scoped State Outsider {suffix}")

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        _select_in_multiselect(page, "project_ids", str(web["id"]))
        _apply(page)
        expect(page.locator(f"#ticket-row-{in_web['id']}")).to_be_visible(timeout=10000)

        # Project-scoped URL: honored as-is, never replaced by the stashed
        # query - and captured into the stash as the newest state.
        page.goto(f"{base_url}/backlog?project_id=1")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(300)
        expect(page).to_have_url(f"{base_url}/backlog?project_id=1", timeout=10000)
        expect(page.locator(f"#ticket-row-{in_uns['id']}")).to_be_visible(timeout=10000)
        assert page.locator(f"#ticket-row-{in_web['id']}").count() == 0

        # Leave and come back through the plain nav link: the scoped query is
        # what must be restored (the form has no project_id field, so the
        # restore pre-checks the matching project_ids option instead).
        _open_ticket_detail(page, in_uns["id"])
        _back_via_nav(page)
        expect(page).to_have_url(re.compile(r"project_ids=1(&|$)"), timeout=10000)
        expect(page.locator(f"#ticket-row-{in_uns['id']}")).to_be_visible(timeout=10000)
        assert page.locator(f"#ticket-row-{in_web['id']}").count() == 0

    def test_back_to_older_filter_becomes_state_restored_on_return(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        """Browser Back to an older filter URL, then leave+return -> older state.

        Back between htmx-pushed filter URLs fires htmx:historyRestore (not
        htmx:pushedIntoHistory). The restore path is the state being navigated
        to, so the stash must be rewritten with it - otherwise leaving after a
        Back would resurrect the newer filters.
        """
        suffix = uuid.uuid4().hex[:8]
        web = seeded_projects[1]
        in_web = make_ticket(project_id=web["id"], title=f"Back State Member {suffix}")
        in_uns = make_ticket(project_id=1, title=f"Back State Outsider {suffix}")

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")

        # Filter 1: WEB only. This is the state we will navigate back to.
        _select_in_multiselect(page, "project_ids", str(web["id"]))
        _apply(page)
        expect(page.locator(f"#ticket-row-{in_web['id']}")).to_be_visible(timeout=10000)
        assert page.locator(f"#ticket-row-{in_uns['id']}").count() == 0

        # Filter 2 (newer history entry): WEB + UNS, so both rows show.
        _open_multiselect(page, "project_ids")
        page.check("[data-ms-field='project_ids'] [data-ms-option][value='1']")
        page.locator("[data-ms-field='project_ids'] [data-ms-trigger]").click()
        _apply(page)
        expect(page.locator(f"#ticket-row-{in_web['id']}")).to_be_visible(timeout=10000)
        expect(page.locator(f"#ticket-row-{in_uns['id']}")).to_be_visible(timeout=10000)

        # Browser Back to the older filter URL: htmx restores it via
        # htmx:historyRestore and the stash follows the restored query.
        page.go_back()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(300)
        expect(page.locator(f"#ticket-row-{in_web['id']}")).to_be_visible(timeout=10000)
        assert page.locator(f"#ticket-row-{in_uns['id']}").count() == 0

        # Leave and come back through the plain nav link: the OLDER filter
        # (WEB only) is what must be restored, not the newer two-project one.
        _open_ticket_detail(page, in_web["id"])
        _back_via_nav(page)
        expect(page).to_have_url(re.compile(rf"project_ids={web['id']}(&|$)"), timeout=10000)
        expect(page.locator(f"#ticket-row-{in_web['id']}")).to_be_visible(timeout=10000)
        assert page.locator(f"#ticket-row-{in_uns['id']}").count() == 0

    def test_clear_filters_wipes_stashed_state(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        """Clear filters -> table unfiltered and the stash is wiped."""
        suffix = uuid.uuid4().hex[:8]
        web = seeded_projects[1]
        in_web = make_ticket(project_id=web["id"], title=f"Clear Member {suffix}")
        in_uns = make_ticket(project_id=1, title=f"Clear Outsider {suffix}")

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        _select_in_multiselect(page, "project_ids", str(web["id"]))
        _apply(page)
        expect(page.locator(f"#ticket-row-{in_web['id']}")).to_be_visible(timeout=10000)

        # Clear filters: plain link to /backlog, wipes the stash first.
        page.click("a:has-text('Clear filters')")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(300)
        expect(page).to_have_url(f"{base_url}/backlog", timeout=10000)
        expect(page.locator(f"#ticket-row-{in_web['id']}")).to_be_visible(timeout=10000)
        expect(page.locator(f"#ticket-row-{in_uns['id']}")).to_be_visible(timeout=10000)

        # The wiped stash must not resurrect the filters on the next return.
        _open_ticket_detail(page, in_web["id"])
        _back_via_nav(page)
        expect(page).to_have_url(f"{base_url}/backlog", timeout=10000)
        expect(page.locator(f"#ticket-row-{in_uns['id']}")).to_be_visible(timeout=10000)

    def test_explicit_url_params_are_never_overridden(
        self, page: Page, base_url: str, seeded_projects, make_ticket
    ):
        """A URL that already carries params (project-scoped link) wins over the stash."""
        suffix = uuid.uuid4().hex[:8]
        web = seeded_projects[1]
        in_web = make_ticket(project_id=web["id"], title=f"Scoped Member {suffix}")
        in_uns = make_ticket(project_id=1, title=f"Scoped Outsider {suffix}")

        page.goto(f"{base_url}/backlog")
        page.wait_for_load_state("networkidle")
        _select_in_multiselect(page, "project_ids", str(web["id"]))
        _apply(page)
        expect(page.locator(f"#ticket-row-{in_web['id']}")).to_be_visible(timeout=10000)

        # Project-scoped URL with explicit params: honored as-is, never
        # replaced by the stashed query.
        page.goto(f"{base_url}/backlog?project_id=1")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(300)
        expect(page).to_have_url(f"{base_url}/backlog?project_id=1", timeout=10000)
        expect(page.locator(f"#ticket-row-{in_uns['id']}")).to_be_visible(timeout=10000)
        assert page.locator(f"#ticket-row-{in_web['id']}").count() == 0
