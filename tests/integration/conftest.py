"""Integration test fixtures - imports from tests.conftest and adds seeded database."""

import sys

sys.path.insert(0, "/workspace/projects/jackrabbit")
from tests.conftest import (
    Generator,
    Path,
    ProjectService,
    Session,
    Settings,
    TestClient,
    create_app,
    get_settings,
    pytest,
)


@pytest.fixture
def client_with_seeds(test_db: Session) -> Generator[TestClient, None, None]:
    """Create a test client with seeded database (UNS project + sample projects)."""
    # Seed the database
    project_service = ProjectService(test_db)

    # System project (UNS) - ID will be 1
    project_service.create_project(
        prefix="UNS",
        name="Unsorted",
        description="Default unsorted project",
        color="#9ca3af",
        is_system=True,
    )

    # Regular projects
    project_service.create_project(
        prefix="WEB",
        name="Web Application",
        description="Frontend web application",
        color="#6366f1",
    )

    project_service.create_project(
        prefix="API",
        name="Backend API",
        description="REST API service",
        color="#10b981",
    )

    project_service.create_project(
        prefix="MOB",
        name="Mobile App",
        description="Mobile application",
        color="#f59e0b",
    )

    def get_test_session():
        yield test_db

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        environment="test",
        database_url="sqlite://",
        data_dir=Path("./data"),
        log_level="DEBUG",
    )

    from jackrabbit.database import get_session

    app.dependency_overrides[get_session] = get_test_session

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
