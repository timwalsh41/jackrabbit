"""Integration tests for the Backlog view and ticket create/edit web flows (ticket 04).

Covers:
- GET /backlog full page: filters, table, New Ticket button
- GET /backlog with query filters (project, type, status, priority, sprint incl. "No Sprint")
- HTMX (HX-Request) filter requests return only the table-body rows partial
- GET /tickets/new (HTMX modal + UNS pre-selected)
- GET /tickets/{id}/edit (full page and HTMX modal, hx-patch action)
- PATCH /api/v1/tickets/{id} returning the updated row for HTMX row-target requests
"""

import json
import re

import httpx
import pytest
from jackrabbit.models import Priority, Project, TicketStatus, TicketType
from jackrabbit.services import TicketService


@pytest.fixture
async def backlog_tickets(test_db, client_with_seeds):
    """Tickets with distinct priorities/statuses across projects; one assigned to a sprint."""
    from jackrabbit.services import SprintService
    from sqlmodel import select

    by_prefix = {p.prefix: p for p in test_db.exec(select(Project)).all()}
    uns, web, api = by_prefix["UNS"], by_prefix["WEB"], by_prefix["API"]
    ticket_service = TicketService(test_db)
    sprint = SprintService(test_db).create_sprint(number=2601, name="Sprint 2601")

    t_high = ticket_service.create_ticket(
        project_id=web.id,
        title="Critical outage",
        type=TicketType.BUG,
        priority=Priority.CRITICAL,
    )
    t_med = ticket_service.create_ticket(
        project_id=api.id,
        title="Add tooltip",
        type=TicketType.STORY,
        priority=Priority.MEDIUM,
    )
    t_low = ticket_service.create_ticket(
        project_id=uns.id,
        title="Investigate flaky test",
        type=TicketType.SPIKE,
        priority=Priority.LOW,
    )
    # Assign one ticket to a sprint; the rest stay unsprinted.
    ticket_service.update_ticket(t_med, sprint_id=sprint.id)
    return {"high": t_high, "medium": t_med, "low": t_low, "sprint": sprint}


async def _get(client: httpx.AsyncClient, path: str, **kwargs) -> httpx.Response:
    return await client.get(path, **kwargs)


class TestIndexRedirect:
    async def test_root_redirects_to_backlog(self, client):
        """Spec Web Routes: GET / must redirect to /backlog (no dashboard)."""
        r = await _get(client, "/", follow_redirects=False)
        assert r.status_code in (301, 302, 307)
        assert r.headers["location"].rstrip("/") == "/backlog"

    async def test_root_follows_redirect_to_backlog(self, client, backlog_tickets):
        r = await _get(client, "/", follow_redirects=True)
        assert r.status_code == 200
        assert 'id="tickets-table-body"' in r.text


class TestBacklogPageSizeCap:
    async def test_page_size_capped_at_100(self, client, backlog_tickets):
        """Web /backlog caps page_size like the JSON API (no 500/validation blowup)."""
        r = await _get(client, "/backlog", params={"page_size": 500})
        assert r.status_code == 200
        assert "Critical outage" in r.text

    async def test_page_size_min_one(self, client, backlog_tickets):
        r = await _get(client, "/backlog", params={"page_size": 0})
        assert r.status_code == 200
        # page_size=0 clamps to 1 -> 3 tickets over 3 pages
        assert "Page 1 of 3 (3 total)" in r.text

    def test_build_backlog_context_caps_page_size(self, test_db, client_with_seeds):
        """The shared builder caps page_size at 100 (unit-level check)."""
        from jackrabbit.services import ProjectService, SprintService
        from jackrabbit.web import _build_backlog_context

        ticket_service = TicketService(test_db)
        from sqlmodel import select as _select

        projects = list(test_db.exec(_select(Project)).all())
        ticket_service.create_ticket(project_id=projects[1].id, title="cap check")
        ctx = _build_backlog_context(
            ticket_service,
            ProjectService(test_db),
            SprintService(test_db),
            project_id=None,
            status=None,
            type=None,
            priority=None,
            sprint_id=None,
            q=None,
            created_after=None,
            created_before=None,
            sort="number",
            order="desc",
            page=1,
            page_size=500,
        )
        assert ctx["page_size"] == 100
        assert ctx["total_pages"] == 1


class TestBacklogPage:
    async def test_backlog_page_renders(self, client, backlog_tickets):
        r = await _get(client, "/backlog")
        assert r.status_code == 200
        assert "<html" in r.text.lower()
        assert 'id="tickets-table-body"' in r.text
        assert 'hx-get="/tickets/new"' in r.text
        # filter controls present
        assert 'name="project_id"' in r.text
        assert 'name="type"' in r.text
        assert 'name="status"' in r.text
        assert 'name="priority"' in r.text
        assert 'name="sprint_id"' in r.text
        assert 'name="q"' in r.text
        # all seeded tickets rendered as rows
        assert "Critical outage" in r.text
        assert "Add tooltip" in r.text
        assert "Investigate flaky test" in r.text

    async def test_backlog_filter_by_project(
        self, client_with_seeds, backlog_tickets, seeded_projects
    ):
        _, web, _ = seeded_projects
        r = await _get(client_with_seeds, "/backlog", params={"project_id": web.id})
        assert r.status_code == 200
        assert "Critical outage" in r.text
        assert "Add tooltip" not in r.text
        assert "Investigate flaky test" not in r.text

    async def test_backlog_filter_by_priority(self, client, backlog_tickets):
        r = await _get(client, "/backlog", params={"priority": Priority.CRITICAL.value})
        assert r.status_code == 200
        assert "Critical outage" in r.text
        assert "Add tooltip" not in r.text
        assert "Investigate flaky test" not in r.text

    async def test_backlog_filter_by_status(self, client, backlog_tickets):
        r = await _get(client, "/backlog", params={"status": TicketStatus.OPEN.value})
        assert r.status_code == 200
        assert "Critical outage" in r.text

    async def test_backlog_filter_by_type(self, client, backlog_tickets):
        r = await _get(client, "/backlog", params={"type": TicketType.SPIKE.value})
        assert r.status_code == 200
        assert "Investigate flaky test" in r.text
        assert "Critical outage" not in r.text

    async def test_backlog_filter_by_sprint(self, client, backlog_tickets):
        r = await _get(client, "/backlog", params={"sprint_id": backlog_tickets["sprint"].id})
        assert r.status_code == 200
        assert "Add tooltip" in r.text
        assert "Critical outage" not in r.text

    async def test_backlog_filter_no_sprint(self, client, backlog_tickets):
        """Selecting 'No Sprint' (sprint_id=0) shows only unsprinted tickets."""
        r = await _get(client, "/backlog", params={"sprint_id": 0})
        assert r.status_code == 200
        assert "Critical outage" in r.text
        assert "Investigate flaky test" in r.text
        assert "Add tooltip" not in r.text

    async def test_backlog_empty_form_submit_ok(self, client, backlog_tickets):
        """Submitting the filter form with all-empty selects must not 422."""
        r = await _get(
            client,
            "/backlog",
            params={
                "project_id": "",
                "type": "",
                "status": "",
                "priority": "",
                "sprint_id": "",
                "q": "",
            },
        )
        assert r.status_code == 200
        assert "Critical outage" in r.text
        assert "Add tooltip" in r.text

    async def test_backlog_htmx_returns_rows_only(self, client, backlog_tickets):
        """HTMX filter requests return only the table body rows, not the full page."""
        r = await _get(
            client,
            "/backlog",
            headers={"HX-Request": "true"},
            params={"priority": Priority.CRITICAL.value},
        )
        assert r.status_code == 200
        assert "<html" not in r.text.lower()
        assert "Critical outage" in r.text
        assert 'id="ticket-row-' in r.text

    async def test_backlog_htmx_no_results(self, client, backlog_tickets):
        r = await _get(
            client,
            "/backlog",
            headers={"HX-Request": "true"},
            params={"q": "zzz-no-such-ticket"},
        )
        assert r.status_code == 200
        assert "<html" not in r.text.lower()
        assert "No tickets found" in r.text

    async def test_backlog_search_q(self, client, backlog_tickets):
        r = await _get(client, "/backlog", params={"q": "outage"})
        assert r.status_code == 200
        assert "Critical outage" in r.text
        assert "Add tooltip" not in r.text

    async def test_backlog_date_filter_inputs_present(self, client, backlog_tickets):
        """The filter form exposes created_after / created_before date inputs (US16)."""
        r = await _get(client, "/backlog")
        assert r.status_code == 200
        assert 'name="created_after"' in r.text
        assert 'name="created_before"' in r.text
        assert 'type="date"' in r.text

    async def test_backlog_filter_created_after(self, client, test_db, backlog_tickets):
        """created_after excludes tickets created before the given date."""
        from datetime import UTC, date, datetime, timedelta

        ticket_service = TicketService(test_db)
        ticket_service.update_ticket(
            backlog_tickets["high"], created_at=datetime.now(UTC) - timedelta(days=10)
        )
        r = await _get(
            client,
            "/backlog",
            params={"created_after": (date.today() - timedelta(days=5)).isoformat()},
        )
        assert r.status_code == 200
        assert "Critical outage" not in r.text
        assert "Add tooltip" in r.text
        assert "Investigate flaky test" in r.text

    async def test_backlog_filter_created_before(self, client, test_db, backlog_tickets):
        """created_before excludes tickets created after the given date."""
        from datetime import UTC, date, datetime, timedelta

        ticket_service = TicketService(test_db)
        ticket_service.update_ticket(
            backlog_tickets["high"], created_at=datetime.now(UTC) - timedelta(days=10)
        )
        r = await _get(
            client,
            "/backlog",
            params={"created_before": (date.today() - timedelta(days=5)).isoformat()},
        )
        assert r.status_code == 200
        assert "Critical outage" in r.text
        assert "Add tooltip" not in r.text
        assert "Investigate flaky test" not in r.text

    async def test_backlog_date_filters_empty_means_no_filter(
        self, client, test_db, backlog_tickets
    ):
        """Empty-string date params (always-submitted form) must not 422 or filter."""
        from datetime import UTC, datetime, timedelta

        ticket_service = TicketService(test_db)
        ticket_service.update_ticket(
            backlog_tickets["high"], created_at=datetime.now(UTC) - timedelta(days=10)
        )
        r = await _get(client, "/backlog", params={"created_after": "", "created_before": ""})
        assert r.status_code == 200
        assert "Critical outage" in r.text

    async def test_backlog_invalid_date_returns_422(self, client, backlog_tickets):
        r = await _get(client, "/backlog", params={"created_after": "not-a-date"})
        assert r.status_code == 422

    async def test_backlog_date_filters_combined_with_other_filters(
        self, client, test_db, backlog_tickets
    ):
        """Date bounds combine with other filters (AND logic)."""
        from datetime import UTC, date, datetime, timedelta

        ticket_service = TicketService(test_db)
        ticket_service.update_ticket(
            backlog_tickets["high"], created_at=datetime.now(UTC) - timedelta(days=10)
        )
        r = await _get(
            client,
            "/backlog",
            params={
                "created_after": (date.today() - timedelta(days=5)).isoformat(),
                "type": TicketType.STORY.value,
            },
        )
        assert r.status_code == 200
        assert "Add tooltip" in r.text
        assert "Investigate flaky test" not in r.text
        assert "Critical outage" not in r.text

    async def test_backlog_htmx_date_filter_returns_rows(self, client, test_db, backlog_tickets):
        from datetime import UTC, date, datetime, timedelta

        ticket_service = TicketService(test_db)
        ticket_service.update_ticket(
            backlog_tickets["high"], created_at=datetime.now(UTC) - timedelta(days=10)
        )
        r = await _get(
            client,
            "/backlog",
            headers={"HX-Request": "true"},
            params={"created_after": (date.today() - timedelta(days=5)).isoformat()},
        )
        assert r.status_code == 200
        assert "<html" not in r.text.lower()
        assert "Critical outage" not in r.text


class TestNewTicketForm:
    async def test_new_ticket_modal_htmx(self, client_with_seeds):
        projects = (await client_with_seeds.get("/api/v1/projects")).json()
        uns_id = next(p["id"] for p in projects if p["prefix"] == "UNS")
        r = await _get(client_with_seeds, "/tickets/new", headers={"HX-Request": "true"})
        assert r.status_code == 200
        assert 'hx-post="/api/v1/tickets"' in r.text
        # UNS pre-selected
        assert f'<option value="{uns_id}" selected' in r.text

    async def test_new_ticket_full_page(self, client):
        r = await _get(client, "/tickets/new")
        assert r.status_code == 200
        assert "<html" in r.text.lower()
        assert 'hx-post="/api/v1/tickets"' in r.text


class TestEditTicketForm:
    async def test_edit_full_page_uses_patch(self, client, backlog_tickets):
        t = backlog_tickets["high"]
        r = await _get(client, f"/tickets/{t.id}/edit")
        assert r.status_code == 200
        assert f'hx-patch="/api/v1/tickets/{t.id}"' in r.text
        assert f'value="{t.title}"' in r.text

    async def test_edit_modal_htmx_targets_row(self, client, backlog_tickets):
        t = backlog_tickets["high"]
        r = await _get(client, f"/tickets/{t.id}/edit", headers={"HX-Request": "true"})
        assert r.status_code == 200
        assert f'hx-patch="/api/v1/tickets/{t.id}"' in r.text
        assert f'hx-target="#ticket-row-{t.id}"' in r.text
        assert 'hx-swap="outerHTML"' in r.text
        assert f'value="{t.title}"' in r.text

    async def test_edit_404(self, client):
        r = await _get(client, "/tickets/99999/edit")
        assert r.status_code == 404


class TestPatchReturnsRow:
    async def test_patch_htmx_row_target_returns_row_html(
        self, client_with_seeds, backlog_tickets, seeded_projects
    ):
        t = backlog_tickets["high"]
        payload = {"title": "Renamed via HTMX", "priority": Priority.HIGH.value}
        r = await client_with_seeds.patch(
            f"/api/v1/tickets/{t.id}",
            content=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "HX-Request": "true",
                "HX-Target": f"ticket-row-{t.id}",
            },
        )
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert f'id="ticket-row-{t.id}"' in r.text
        assert "Renamed via HTMX" in r.text
        assert "<html" not in r.text.lower()

    async def test_patch_htmx_other_target_redirects_to_backlog(self, client, backlog_tickets):
        t = backlog_tickets["medium"]
        payload = {"title": "Edited full page"}
        r = await client.patch(
            f"/api/v1/tickets/{t.id}",
            content=json.dumps(payload),
            headers={"Content-Type": "application/json", "HX-Request": "true"},
        )
        assert r.headers.get("HX-Redirect") == "/backlog"

    async def test_patch_json_still_returns_json(self, client, backlog_tickets):
        t = backlog_tickets["low"]
        payload = {"story_points": 3}
        r = await client.patch(
            f"/api/v1/tickets/{t.id}",
            content=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/json")
        assert r.json()["story_points"] == 3


class TestBacklogFilterFormCarriesTheFilters:
    """JRB-002: the filter form is the single source of truth for the active filters.

    The sortable headers and the pagination links must *include* the filter form
    instead of hand-listing every filter, so that no filter can be silently
    dropped when the table is sorted or paged.
    """

    FILTER_FORM_ID = "backlog-filter-form"
    FILTER_NAMES = (
        "project_id",
        "type",
        "status",
        "priority",
        "sprint_id",
        "q",
        "created_after",
        "created_before",
    )

    @staticmethod
    def _sortable_headers(html: str) -> list[str]:
        """The <th> elements that trigger a sort request."""
        return [th for th in re.findall(r"<th\b[^>]*>", html) if "hx-vals" in th]

    @staticmethod
    def _hx_vals(html: str) -> list[str]:
        """Every hx-vals payload rendered on the page."""
        return re.findall(r"hx-vals='js:(\{[^']*\})'", html)

    @staticmethod
    def _hx_vals_keys(payload: str) -> set[str]:
        """The keys of an hx-vals payload (values are not keys)."""
        return set(re.findall(r'"([a-z_]+)":', payload))

    async def test_backlog_page_has_a_filter_form_with_an_id(self, client, backlog_tickets):
        r = await _get(client, "/backlog")
        assert r.status_code == 200
        assert f'id="{self.FILTER_FORM_ID}"' in r.text

    async def test_sortable_headers_include_the_filter_form(self, client, backlog_tickets):
        r = await _get(client, "/backlog")
        headers = self._sortable_headers(r.text)
        assert len(headers) == 7, "the backlog table has seven sortable columns"
        for th in headers:
            assert f'hx-include="#{self.FILTER_FORM_ID}"' in th, th

    async def test_pagination_links_include_the_filter_form(self, client, backlog_tickets):
        # page_size=1 over three tickets gives three pages; the middle page
        # renders both the Previous and the Next link.
        r = await _get(client, "/backlog", params={"page_size": 1, "page": 2})
        assert r.status_code == 200
        links = [a for a in re.findall(r"<a\b[^>]*>", r.text) if "hx-vals" in a]
        assert len(links) == 2, "Previous and Next links"
        for link in links:
            assert f'hx-include="#{self.FILTER_FORM_ID}"' in link, link

    async def test_no_request_hand_lists_the_filters(self, client, backlog_tickets):
        """Neither the headers nor the pagination restate the filter values."""
        r = await _get(client, "/backlog", params={"page_size": 1})
        assert r.status_code == 200
        payloads = self._hx_vals(r.text)
        assert payloads, "the page still carries sort/page requests"
        for payload in payloads:
            keys = self._hx_vals_keys(payload)
            for name in self.FILTER_NAMES:
                assert name not in keys, payload

    async def test_headers_specify_sort_order_and_first_page(self, client, backlog_tickets):
        r = await _get(client, "/backlog")
        assert r.status_code == 200
        payloads = self._hx_vals(r.text)
        sorts = {re.search(r'"sort": "([^"]*)"', p).group(1) for p in payloads if '"sort"' in p}
        assert sorts == {
            "number",
            "title",
            "type",
            "status",
            "priority",
            "story_points",
            "sprint_id",
        }
        for payload in payloads:
            if '"sort"' in payload:
                assert '"order"' in payload
                assert '"page": 1' in payload, "sorting returns to the first page"

    async def test_pagination_links_specify_the_page(self, client, backlog_tickets):
        r = await _get(client, "/backlog", params={"page_size": 1, "page": 2})
        assert r.status_code == 200
        pages = {
            int(re.search(r'"page": (\d+)', p).group(1))
            for p in self._hx_vals(r.text)
            if '"page"' in p and '"sort"' not in p
        }
        assert pages == {1, 3}, "Previous (page 1) and Next (page 3)"

    async def test_filter_form_hidden_fields_carry_the_active_state(self, client, backlog_tickets):
        """The form's own hidden fields hold the active sort, order and page."""
        r = await _get(
            client, "/backlog", params={"sort": "title", "order": "asc", "page": 2, "page_size": 1}
        )
        assert r.status_code == 200
        assert 'name="sort" value="title"' in r.text
        assert 'name="order" value="asc"' in r.text
        assert 'name="page" value="2"' in r.text

    async def test_project_ticket_view_shares_the_filter_form(
        self, client_with_seeds, seeded_projects, backlog_tickets
    ):
        """The project-scoped view uses the same filter form and headers."""
        _, web, _ = seeded_projects
        r = await _get(client_with_seeds, f"/projects/{web.id}/tickets")
        assert r.status_code == 200
        assert f'id="{self.FILTER_FORM_ID}"' in r.text
        headers = self._sortable_headers(r.text)
        assert headers
        for th in headers:
            assert f'hx-include="#{self.FILTER_FORM_ID}"' in th, th
