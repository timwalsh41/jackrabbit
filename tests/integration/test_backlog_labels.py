"""Integration tests for the backlog's label filter (JRB-003).

Covers the HTTP level of the feature:

- the filter bar's collapsible labels panel (a checkbox per label in use, and
  a control choosing between matching all and matching any selected label);
- the labels column of the backlog table and its empty-state row;
- the filtered listing, in both match modes, and its composition with the
  other filters;
- the widened free-text search (title, description, label names);
- the project-scoped ticket view, which shares the filter form;
- the JSON API's ticket listing, which accepts label ids and a match mode.

Everything is asserted on the response: status code and response text.
"""

import re

import httpx
import pytest
from jackrabbit.models import Priority, Project, TicketStatus, TicketType
from jackrabbit.services import LabelService, TicketService
from sqlmodel import select


@pytest.fixture
async def labelled_tickets(test_db, client_with_seeds):
    """Tickets carrying different label sets, plus the labels themselves."""
    from jackrabbit.services import SprintService

    projects = {p.prefix: p for p in test_db.exec(select(Project)).all()}
    ticket_service = TicketService(test_db)
    label_service = LabelService(test_db)
    sprint = SprintService(test_db).create_sprint(number=2701, name="Sprint 2701")

    both = ticket_service.create_ticket(
        project_id=projects["WEB"].id,
        title="Carries both labels",
        type=TicketType.STORY,
        status=TicketStatus.OPEN,
        priority=Priority.MEDIUM,
        description="A ticket about the billing reconciliation job",
    )
    backend_only = ticket_service.create_ticket(
        project_id=projects["WEB"].id,
        title="Backend only",
        type=TicketType.BUG,
        status=TicketStatus.GROOMED,
        priority=Priority.CRITICAL,
        description="A ticket about the authentication service",
    )
    frontend_only = ticket_service.create_ticket(
        project_id=projects["API"].id,
        title="Frontend only",
        type=TicketType.STORY,
        status=TicketStatus.OPEN,
        priority=Priority.MEDIUM,
        description="A ticket about the dashboard",
    )
    unlabelled = ticket_service.create_ticket(
        project_id=projects["UNS"].id,
        title="Carries no labels",
        type=TicketType.STORY,
        status=TicketStatus.OPEN,
        priority=Priority.MEDIUM,
        description="A ticket about the billing settlement report",
    )
    # A ticket that matches the other filters but carries no label: it shows
    # that the label filter is really applied on top of them.
    unlabelled_api = ticket_service.create_ticket(
        project_id=projects["API"].id,
        title="Unlabelled API ticket",
        type=TicketType.STORY,
        status=TicketStatus.OPEN,
        priority=Priority.MEDIUM,
        description="A ticket about the dashboard refresh",
    )
    ticket_service.update_ticket(both, sprint_id=sprint.id)

    label_service.attach(both.id, "Backend")
    label_service.attach(both.id, "Frontend")
    label_service.attach(backend_only.id, "Backend")
    label_service.attach(frontend_only.id, "Frontend")
    # A label no ticket carries: it stays in the registry but is not offered.
    label_service.find_or_create("Unused Label")

    labels = {label.name: label for label in label_service.list_labels()}
    in_use = {label.name: label for label in label_service.list_labels_in_use()}
    return {
        "tickets": {
            "both": both,
            "backend_only": backend_only,
            "frontend_only": frontend_only,
            "unlabelled": unlabelled,
            "unlabelled_api": unlabelled_api,
        },
        "labels": labels,
        "labels_in_use": in_use,
        "projects": projects,
        "sprint": sprint,
    }


async def _get(client: httpx.AsyncClient, path: str, **kwargs) -> httpx.Response:
    return await client.get(path, **kwargs)


class TestLabelsFilterPanel:
    """The filter bar gains a collapsible panel listing the labels in use."""

    async def test_panel_is_rendered_and_collapsible(self, client_with_seeds, labelled_tickets):
        r = await _get(client_with_seeds, "/backlog")
        assert r.status_code == 200
        assert 'id="labels-filter-panel"' in r.text
        # Collapsible: a <details> element with a <summary> to toggle it.
        assert re.search(r"<details[^>]*id=\"labels-filter-panel\"", r.text)
        assert "<summary" in r.text

    async def test_panel_lists_every_label_in_use(self, client_with_seeds, labelled_tickets):
        r = await _get(client_with_seeds, "/backlog")
        assert r.status_code == 200
        labels = labelled_tickets["labels_in_use"]
        assert set(labels) == {"Backend", "Frontend"}
        for label in labels.values():
            assert f'name="label_ids" value="{label.id}"' in r.text
            assert label.name in r.text

    async def test_unused_labels_are_not_offered(self, client_with_seeds, labelled_tickets):
        """A label no ticket carries stays out of the filter list."""
        r = await _get(client_with_seeds, "/backlog")
        assert r.status_code == 200
        assert "Unused Label" not in r.text

    async def test_match_control_is_offered_and_defaults_to_all(
        self, client_with_seeds, labelled_tickets
    ):
        r = await _get(client_with_seeds, "/backlog")
        assert r.status_code == 200
        assert 'name="label_match"' in r.text
        assert 'value="all"' in r.text
        assert 'value="any"' in r.text
        # "all" is the default: the matching option is the selected one.
        all_option = re.search(r'<option value="all"[^>]*>', r.text)
        assert all_option is not None
        assert "selected" in all_option.group(0)

    async def test_the_selected_labels_are_marked(self, client_with_seeds, labelled_tickets):
        label = labelled_tickets["labels"]["Backend"]
        r = await _get(client_with_seeds, "/backlog", params={"label_ids": str(label.id)})
        assert r.status_code == 200
        checkbox = re.search(rf'<input[^>]*name="label_ids"[^>]*value="{label.id}"[^>]*>', r.text)
        assert checkbox is not None
        assert "checked" in checkbox.group(0)

    async def test_the_match_mode_is_remembered(self, client_with_seeds, labelled_tickets):
        r = await _get(client_with_seeds, "/backlog", params={"label_match": "any"})
        assert r.status_code == 200
        any_option = re.search(r'<option value="any"[^>]*>', r.text)
        assert any_option is not None
        assert "selected" in any_option.group(0)


class TestLabelsColumn:
    """The backlog table gains a labels column."""

    async def test_table_has_a_labels_column(self, client_with_seeds, labelled_tickets):
        r = await _get(client_with_seeds, "/backlog")
        assert r.status_code == 200
        assert re.search(r"<th[^>]*>\s*Labels\s*</th>", r.text)

    async def test_row_shows_the_labels_of_its_ticket(self, client_with_seeds, labelled_tickets):
        r = await _get(client_with_seeds, "/backlog")
        assert r.status_code == 200
        assert "Carries both labels" in r.text
        # The chips carry the label name, so a reader can see why a row matched.
        assert 'data-label-name="Backend"' in r.text
        assert 'data-label-name="Frontend"' in r.text

    async def test_a_ticket_without_labels_has_an_empty_labels_cell(
        self, client_with_seeds, labelled_tickets
    ):
        r = await _get(client_with_seeds, "/backlog")
        assert r.status_code == 200
        unlabelled = labelled_tickets["tickets"]["unlabelled"]
        row = re.search(rf'<tr[^>]*id="ticket-row-{unlabelled.id}"[^>]*>.*?</tr>', r.text, re.S)
        assert row is not None
        assert "data-label-name" not in row.group(0)

    async def test_the_empty_state_row_spans_every_column(self, client_with_seeds):
        """The empty-state row accounts for the new labels column."""
        r = await _get(
            client_with_seeds,
            "/backlog",
            headers={"HX-Request": "true"},
            params={"q": "zzz-no-such-ticket"},
        )
        assert r.status_code == 200
        assert "No tickets found" in r.text
        colspan = re.search(r'colspan="(\d+)"', r.text)
        assert colspan is not None
        # ID, Title, Labels, Type, Status, Priority, Points, Sprint, Blocked, Actions
        assert int(colspan.group(1)) == 10


class TestFilteringByLabel:
    """Selecting labels filters the backlog."""

    async def test_filter_by_one_label(self, client_with_seeds, labelled_tickets):
        label = labelled_tickets["labels"]["Backend"]
        r = await _get(client_with_seeds, "/backlog", params={"label_ids": str(label.id)})
        assert r.status_code == 200
        assert "Carries both labels" in r.text
        assert "Backend only" in r.text
        assert "Frontend only" not in r.text
        assert "Carries no labels" not in r.text

    async def test_match_all_requires_every_selected_label(
        self, client_with_seeds, labelled_tickets
    ):
        labels = labelled_tickets["labels"]
        r = await _get(
            client_with_seeds,
            "/backlog",
            params={
                "label_ids": [str(labels["Backend"].id), str(labels["Frontend"].id)],
                "label_match": "all",
            },
        )
        assert r.status_code == 200
        assert "Carries both labels" in r.text
        assert "Backend only" not in r.text
        assert "Frontend only" not in r.text

    async def test_match_any_accepts_one_of_the_selected_labels(
        self, client_with_seeds, labelled_tickets
    ):
        labels = labelled_tickets["labels"]
        r = await _get(
            client_with_seeds,
            "/backlog",
            params={
                "label_ids": [str(labels["Backend"].id), str(labels["Frontend"].id)],
                "label_match": "any",
            },
        )
        assert r.status_code == 200
        assert "Carries both labels" in r.text
        assert "Backend only" in r.text
        assert "Frontend only" in r.text
        assert "Carries no labels" not in r.text

    async def test_the_label_filter_composes_with_the_other_filters(
        self, client_with_seeds, labelled_tickets
    ):
        label = labelled_tickets["labels"]["Backend"]
        r = await _get(
            client_with_seeds,
            "/backlog",
            params={"label_ids": str(label.id), "type": "Story"},
        )
        assert r.status_code == 200
        # The other filters still narrow the labelled tickets.
        assert "Carries both labels" in r.text

    async def test_htmx_request_returns_the_filtered_rows_only(
        self, client_with_seeds, labelled_tickets
    ):
        label = labelled_tickets["labels"]["Frontend"]
        r = await _get(
            client_with_seeds,
            "/backlog",
            headers={"HX-Request": "true"},
            params={"label_ids": str(label.id)},
        )
        assert r.status_code == 200
        assert "<html" not in r.text.lower()
        assert "Carries both labels" in r.text
        assert "Backend only" not in r.text

    async def test_the_filter_state_is_in_the_url(self, client_with_seeds, labelled_tickets):
        """The filter state can be bookmarked and shared: it lives in the URL."""
        label = labelled_tickets["labels"]["Backend"]
        r = await _get(
            client_with_seeds,
            "/backlog",
            params={"label_ids": str(label.id), "label_match": "any"},
        )
        assert r.status_code == 200
        # The page carries the state, so the same URL renders the same list.
        assert "Backend only" in r.text
        assert "Frontend only" not in r.text


class TestLabelFilterComposesWithEveryFilter:
    """The label selection combines with every other filter."""

    async def test_label_filter_composes_with_every_other_filter(
        self, client_with_seeds, labelled_tickets
    ):
        from datetime import date, timedelta

        tickets = {ticket.title: ticket for ticket in labelled_tickets["tickets"].values()}
        labels = labelled_tickets["labels"]
        projects = labelled_tickets["projects"]
        sprint = labelled_tickets["sprint"]
        backend = str(labels["Backend"].id)
        frontend = str(labels["Frontend"].id)

        cases = [
            # (other filter, its value, the label filter, the ticket kept, the ticket dropped)
            (
                "project_id",
                str(projects["API"].id),
                frontend,
                "Frontend only",
                "Carries both labels",
            ),
            ("type", TicketType.BUG.value, backend, "Backend only", "Carries both labels"),
            ("status", TicketStatus.OPEN.value, backend, "Carries both labels", "Backend only"),
            ("priority", Priority.CRITICAL.value, backend, "Backend only", "Carries both labels"),
            ("sprint_id", str(sprint.id), backend, "Carries both labels", "Backend only"),
            ("q", "billing reconciliation", backend, "Carries both labels", "Backend only"),
        ]

        for name, value, label_filter, kept, dropped in cases:
            r = await _get(
                client_with_seeds,
                "/backlog",
                params={name: value, "label_ids": label_filter},
            )
            assert r.status_code == 200, name
            assert tickets[kept].title in r.text, f"{name} dropped the matching ticket"
            assert tickets[dropped].title not in r.text, f"{name} was not applied"
            # Exactly one ticket matches: the labelled one. A ticket that
            # matches the other filters but carries no label is left out.
            assert r.text.count('id="ticket-row-') == 1, f"{name} was not combined"

        # The date bounds compose too: a window that excludes every ticket
        # empties the list, labels or not.
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        r = await _get(
            client_with_seeds,
            "/backlog",
            params={"created_after": tomorrow, "label_ids": backend},
        )
        assert r.status_code == 200
        assert "Carries both labels" not in r.text
        assert "Backend only" not in r.text

        r = await _get(
            client_with_seeds,
            "/backlog",
            params={"created_before": "2000-01-01", "label_ids": backend},
        )
        assert r.status_code == 200
        assert "Carries both labels" not in r.text
        assert "Backend only" not in r.text


class TestWidenedSearch:
    """The search box finds a ticket by its title, description or label name."""

    async def test_the_search_field_is_relabelled(self, client_with_seeds, labelled_tickets):
        r = await _get(client_with_seeds, "/backlog")
        assert r.status_code == 200
        assert "Search Title" not in r.text
        assert re.search(r'<label[^>]*for="q"[^>]*>\s*Search\s*</label>', r.text)

    async def test_search_finds_a_ticket_by_its_description(
        self, client_with_seeds, labelled_tickets
    ):
        r = await _get(client_with_seeds, "/backlog", params={"q": "billing reconciliation"})
        assert r.status_code == 200
        assert "Carries both labels" in r.text
        assert "Carries no labels" not in r.text

    async def test_search_finds_a_ticket_by_its_label_name(
        self, client_with_seeds, labelled_tickets
    ):
        r = await _get(client_with_seeds, "/backlog", params={"q": "Frontend"})
        assert r.status_code == 200
        assert "Carries both labels" in r.text
        assert "Frontend only" in r.text
        assert "Carries no labels" not in r.text

    async def test_search_is_case_insensitive(self, client_with_seeds, labelled_tickets):
        r = await _get(client_with_seeds, "/backlog", params={"q": "frontend"})
        assert r.status_code == 200
        assert "Frontend only" in r.text

    async def test_search_composes_with_the_label_filter(self, client_with_seeds, labelled_tickets):
        labels = labelled_tickets["labels"]
        r = await _get(
            client_with_seeds,
            "/backlog",
            params={
                "q": "Frontend",
                "label_ids": str(labels["Backend"].id),
            },
        )
        assert r.status_code == 200
        assert "Carries both labels" in r.text
        assert "Frontend only" not in r.text


class TestProjectScopedView:
    """The project scope now rides on /backlog?project_id={id} (the
    /projects/{id}/tickets route was removed); it offers the same label
    filter and column."""

    async def test_the_view_offers_the_label_panel(
        self, client_with_seeds, seeded_projects, labelled_tickets
    ):
        _, web, _ = seeded_projects
        r = await _get(client_with_seeds, f"/backlog?project_id={web.id}")
        assert r.status_code == 200
        assert 'id="labels-filter-panel"' in r.text
        assert 'name="label_match"' in r.text
        assert 'name="label_ids"' in r.text

    async def test_the_view_has_the_labels_column(
        self, client_with_seeds, seeded_projects, labelled_tickets
    ):
        _, web, _ = seeded_projects
        r = await _get(client_with_seeds, f"/backlog?project_id={web.id}")
        assert r.status_code == 200
        assert re.search(r"<th[^>]*>\s*Labels\s*</th>", r.text)
        assert 'data-label-name="Backend"' in r.text

    async def test_the_view_filters_by_label(
        self, client_with_seeds, seeded_projects, labelled_tickets
    ):
        _, web, _ = seeded_projects
        label = labelled_tickets["labels"]["Backend"]
        r = await _get(
            client_with_seeds,
            f"/backlog?project_id={web.id}",
            params={"label_ids": str(label.id)},
        )
        assert r.status_code == 200
        assert "Carries both labels" in r.text
        assert "Backend only" in r.text
        assert "Frontend only" not in r.text


class TestTicketListingApi:
    """The JSON API's ticket listing accepts label ids and a match mode."""

    async def test_listing_filters_by_label(self, client_with_seeds, labelled_tickets):
        label = labelled_tickets["labels"]["Backend"]
        r = await _get(client_with_seeds, "/api/v1/tickets", params={"label_ids": str(label.id)})
        assert r.status_code == 200
        titles = {item["title"] for item in r.json()["items"]}
        assert titles == {"Carries both labels", "Backend only"}

    async def test_listing_honours_the_match_mode(self, client_with_seeds, labelled_tickets):
        labels = labelled_tickets["labels"]
        params = {
            "label_ids": [str(labels["Backend"].id), str(labels["Frontend"].id)],
            "label_match": "any",
        }
        r = await _get(client_with_seeds, "/api/v1/tickets", params=params)
        assert r.status_code == 200
        titles = {item["title"] for item in r.json()["items"]}
        assert titles == {"Carries both labels", "Backend only", "Frontend only"}

    async def test_listing_rejects_an_unknown_match_mode(self, client_with_seeds, labelled_tickets):
        r = await _get(client_with_seeds, "/api/v1/tickets", params={"label_match": "maybe"})
        assert r.status_code == 422

    async def test_listing_rejects_a_non_numeric_label_id(
        self, client_with_seeds, labelled_tickets
    ):
        r = await _get(client_with_seeds, "/api/v1/tickets", params={"label_ids": "abc"})
        assert r.status_code == 422
