"""E2E regression for the designator surface (JRB-039).

The motivating agent workflow: "groom JRB-028" (PK 35) used to fetch the
bare-integer page URL and silently land on a different ticket. These tests
drive the browser the way an agent does — resolve the designator via the
API, navigate the designator page URL, groom through the UI — and pin the
trap shut: a bare-integer page URL answers 422, never another ticket.
"""

import httpx
from playwright.sync_api import Page, expect


def test_groom_designator_flow_resolves_the_right_ticket(
    page: Page, base_url: str, seeded_projects
):
    """Grooming via the designator grooms the right ticket; the PK guess 422s.

    Filler tickets in the API project give the WEB target a PK different
    from its number — the same PK/number offset as epic ticket JRB-028
    (PK 35), whose wrong-guess fetch ``/tickets/28`` used to silently
    return JRB-021 (PK 28).
    """
    with httpx.Client(base_url=base_url, timeout=30.0) as api:
        for i in range(3):
            resp = api.post("/api/v1/tickets", json={"project_id": 3, "title": f"filler {i}"})
            assert resp.status_code == 201, resp.text
        created = api.post(
            "/api/v1/tickets", json={"project_id": 2, "title": "Groom by designator"}
        )
        assert created.status_code == 201, created.text
        ticket = created.json()
        pk, number = ticket["id"], ticket["number"]
        # The PK/number offset is what makes the bare-int guess dangerous.
        assert pk != number

        # The groom gate (ADR-0025) needs one criterion, authored while Open.
        row = api.post(f"/api/v1/tickets/{ticket['full_id']}/criteria", json={"text": "It works"})
        assert row.status_code == 201, row.text

        # Agent workflow step 1: resolve the designator to the ticket.
        resolved = api.get(f"/api/v1/tickets/{ticket['full_id']}")
        assert resolved.status_code == 200
        assert resolved.json()["id"] == pk

        # The trap: fetching the PK as a page URL answers 422 and never
        # renders any ticket (the PK may name a different ticket's row).
        trap = api.get(f"/tickets/{pk}", headers={"accept": "text/html"})
        assert trap.status_code == 422, trap.text
        assert ticket["title"] not in trap.text

    # Browser: the designator page renders and the UI groom completes.
    page.goto(f"{base_url}/tickets/{ticket['full_id']}")
    page.wait_for_load_state("networkidle")
    expect(page.locator("#ticket-title")).to_contain_text(ticket["full_id"])

    page.wait_for_selector("#transition-buttons button", state="visible", timeout=10000)
    page.click("button:has-text('Groomed')")
    page.wait_for_selector("#groom-form", state="visible", timeout=10000)
    page.fill("textarea[name='approach']", "resolve the designator via the API")
    page.fill("textarea[name='files_to_change']", "jackrabbit/web.py")
    page.fill("textarea[name='test_plan']", "pytest tests/e2e")
    page.fill("textarea[name='validation_steps']", "green suite")
    page.fill("input[name='criteria']", "It works")
    page.click("#groom-form button[type='submit']")
    page.wait_for_load_state("networkidle")

    expect(page.locator("#ticket-content span:has-text('Groomed')").first).to_be_visible(
        timeout=10000
    )
    # Still the same ticket: the designator never changed during grooming.
    expect(page).to_have_url(f"{base_url}/tickets/{ticket['full_id']}")

    # And the trap stays shut after the groom.
    with httpx.Client(base_url=base_url, timeout=30.0) as api:
        after = api.get(f"/api/v1/tickets/{ticket['full_id']}")
        assert after.status_code == 200
        assert after.json()["status"] == "Groomed"
        assert after.json()["id"] == pk
        assert api.get(f"/tickets/{pk}", headers={"accept": "text/html"}).status_code == 422


def test_bare_pk_detail_url_answers_422(page: Page, base_url: str, seeded_projects, make_ticket):
    """A browser navigation to /tickets/{pk} gets 422, not a ticket page."""
    ticket = make_ticket()
    response = page.goto(f"{base_url}/tickets/{ticket['id']}")
    assert response is not None
    assert response.status == 422
    assert ticket["title"] not in page.content()


def test_legacy_pk_alias_redirects_to_designator_url(
    page: Page, base_url: str, seeded_projects, make_ticket
):
    """Old /ticket/{pk} bookmarks redirect to the designator URL."""
    ticket = make_ticket()
    page.goto(f"{base_url}/ticket/{ticket['id']}")
    page.wait_for_load_state("networkidle")
    expect(page).to_have_url(f"{base_url}/tickets/{ticket['full_id']}")
    expect(page.locator("#ticket-title")).to_contain_text(ticket["full_id"])


def test_sprint_board_opens_by_sprint_number(
    page: Page, base_url: str, seeded_projects, make_sprint
):
    """The sprint board is addressed by sprint number; the PK is not a URL."""
    sprint = make_sprint()
    page.goto(f"{base_url}/sprints/{sprint['number']}/detail")
    page.wait_for_load_state("networkidle")
    expect(page.locator("#sprint-detail-content")).to_be_visible()

    pk_url = page.goto(f"{base_url}/sprints/{sprint['id']}/detail")
    assert pk_url is not None
    assert pk_url.status == 404
