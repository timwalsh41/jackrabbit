"""Integration tests for the Project web UI (SSR + HTMX) routes.

Covers ticket 03 web criteria:
- GET /projects project list (prefix, name, color badge, ticket count, actions)
- GET /projects/new create form with hx-post returning a row partial
- GET /projects/{id}/edit edit form with hx-patch returning a row partial
- Delete button hx-delete + hx-confirm (absent/disabled for UNS)
- base.html: HTMX loaded, nav with Backlog, Sprints, Plan, Projects
- Glossary vocabulary (Project / Ticket / Sprint)
"""

from fastapi.testclient import TestClient


def test_project_list_page(client_with_seeds: TestClient) -> None:
    """Project list shows prefix, name, color badge, ticket count and actions."""
    response = client_with_seeds.get("/projects")
    assert response.status_code == 200
    html = response.text
    # Seeded projects are rendered
    assert "WEB" in html
    assert "Web Application" in html
    assert "UNS" in html
    # Color badge rendered with hex color
    assert "#6366f1" in html
    # Actions: edit link and delete button present
    assert "/projects/2/edit" in html
    assert 'hx-delete="/api/v1/projects/2"' in html


def test_base_template_nav_and_htmx(client_with_seeds: TestClient) -> None:
    """Base template loads HTMX and has nav: Backlog, Sprints, Plan, Projects."""
    response = client_with_seeds.get("/projects")
    html = response.text
    assert "htmx.org" in html
    for label, href in [
        ("Backlog", "/backlog"),
        ("Sprints", "/sprints"),
        ("Plan", "/plan"),
        ("Projects", "/projects"),
    ]:
        assert f'href="{href}"' in html, f"nav missing {label} link"


def test_glossary_vocabulary(client_with_seeds: TestClient) -> None:
    """Pages use glossary vocabulary: Project, Ticket, Sprint."""
    html = client_with_seeds.get("/projects").text
    assert "Projects" in html
    assert "Ticket" in html
    # Off-vocabulary generic terms must not appear as headings
    assert "Tasks" not in html


def test_project_new_form(client_with_seeds: TestClient) -> None:
    """Create form page has an HTMX form posting to /projects."""
    response = client_with_seeds.get("/projects/new")
    assert response.status_code == 200
    html = response.text
    assert 'hx-post="/projects"' in html
    assert 'name="prefix"' in html
    assert 'name="name"' in html
    assert 'name="color"' in html


def test_project_new_form_htmx_returns_form_partial(client_with_seeds: TestClient) -> None:
    """HTMX requests to /projects/new receive a partial (no full base template)."""
    response = client_with_seeds.get("/projects/new", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "<html" not in response.text
    assert 'hx-post="/projects"' in response.text


def test_project_create_submit_returns_row_partial(client_with_seeds: TestClient) -> None:
    """Submitting the create form via HTMX returns a row partial for the new project."""
    response = client_with_seeds.post(
        "/projects",
        data={
            "prefix": "DEV",
            "name": "Dev Project",
            "description": "Dev tools",
            "color": "#334455",
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    body = response.text
    assert "<tr" in body
    assert 'id="project-row-' in body
    assert "DEV" in body
    assert "Dev Project" in body
    assert "#334455" in body
    # The created project shows up in the list afterwards
    list_response = client_with_seeds.get("/projects")
    assert "DEV" in list_response.text


def test_project_create_submit_validation_error(client_with_seeds: TestClient) -> None:
    """Invalid create submissions re-render the form partial with an error."""
    response = client_with_seeds.post(
        "/projects",
        data={"prefix": "A", "name": "Bad Prefix", "color": "#123456"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "Prefix" in response.text
    assert 'hx-post="/projects"' in response.text


def test_project_create_submit_duplicate_prefix_error(client_with_seeds: TestClient) -> None:
    """Duplicate prefix in the web form shows a friendly error, not a 500."""
    response = client_with_seeds.post(
        "/projects",
        data={"prefix": "WEB", "name": "Duplicate", "color": "#123456"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "already exists" in response.text
    # The duplicate must not have been created
    listing = client_with_seeds.get("/api/v1/projects")
    names = [p["name"] for p in listing.json()]
    assert "Duplicate" not in names


def test_project_edit_form(client_with_seeds: TestClient) -> None:
    """Edit form page uses hx-patch against /projects/{id}."""
    response = client_with_seeds.get("/projects/2/edit")
    assert response.status_code == 200
    html = response.text
    assert 'hx-patch="/projects/2"' in html
    assert 'value="Web Application"' in html
    # Prefix is not editable
    assert "readonly" in html


def test_project_edit_form_htmx_returns_row_form(client_with_seeds: TestClient) -> None:
    """Inline edit (HX-Request) swaps in a row-level form for the project row."""
    response = client_with_seeds.get("/projects/2/edit", headers={"HX-Request": "true"})
    assert response.status_code == 200
    html = response.text
    assert 'id="project-row-2"' in html
    assert 'hx-patch="/projects/2"' in html


def test_project_edit_submit_returns_row_partial(client_with_seeds: TestClient) -> None:
    """Submitting the edit form returns the updated row partial."""
    response = client_with_seeds.patch(
        "/projects/2",
        data={"name": "Renamed Web", "description": "New desc", "color": "#abcdef"},
        headers={"HX-Request": "true", "HX-Target": "project-row-2"},
    )
    assert response.status_code == 200
    html = response.text
    assert 'id="project-row-2"' in html
    assert "Renamed Web" in html
    assert "#abcdef" in html
    # Persisted
    api_response = client_with_seeds.get("/api/v1/projects/2")
    assert api_response.json()["name"] == "Renamed Web"


def test_project_edit_submit_validation_error(client_with_seeds: TestClient) -> None:
    """Invalid edit submission re-renders the edit form with an error."""
    response = client_with_seeds.patch(
        "/projects/2",
        data={"name": "Still Fine", "color": "nothex"},
        headers={"HX-Request": "true", "HX-Target": "project-row-2"},
    )
    assert response.status_code == 200
    assert "Color" in response.text
    assert 'hx-patch="/projects/2"' in response.text


def test_project_row_partial(client_with_seeds: TestClient) -> None:
    """GET /projects/{id}/row returns the row partial (used by cancel/refresh)."""
    response = client_with_seeds.get("/projects/2/row")
    assert response.status_code == 200
    html = response.text
    assert 'id="project-row-2"' in html
    assert "Web Application" in html


def test_delete_button_protected_for_system_project(client_with_seeds: TestClient) -> None:
    """UNS (system project) row must not carry an hx-delete attribute."""
    response = client_with_seeds.get("/projects")
    html = response.text
    assert 'hx-delete="/api/v1/projects/1"' not in html
    assert 'hx-delete="/api/v1/projects/2"' in html
    assert "hx-confirm" in html
