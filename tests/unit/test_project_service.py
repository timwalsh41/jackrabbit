"""Unit tests for ProjectService business logic."""

import pytest
from jackrabbit.services import ProjectService
from sqlmodel import Session


@pytest.fixture
def service(test_db: Session) -> ProjectService:
    return ProjectService(test_db)


def test_create_project_duplicate_prefix_raises(service: ProjectService) -> None:
    """Duplicate prefix must be rejected with ValueError (not IntegrityError)."""
    service.create_project(prefix="WEB", name="Web Project")
    with pytest.raises(ValueError, match="already exists"):
        service.create_project(prefix="WEB", name="Another Web Project")


def test_create_project_duplicate_prefix_case_insensitive(service: ProjectService) -> None:
    """Prefix comparison is case-insensitive (prefixes are stored uppercase)."""
    service.create_project(prefix="WEB", name="Web Project")
    with pytest.raises(ValueError, match="already exists"):
        service.create_project(prefix="web", name="Lowercase Web Project")


def test_create_project_duplicate_system_prefix_raises(service: ProjectService) -> None:
    """Even the system UNS prefix cannot be duplicated."""
    service.create_project(prefix="UNS", name="Unsorted", is_system=True)
    with pytest.raises(ValueError, match="already exists"):
        service.create_project(prefix="UNS", name="Fake Unsorted")


def test_update_project_updates_fields(service: ProjectService) -> None:
    project = service.create_project(prefix="WEB", name="Web Project")
    updated = service.update_project(
        project.id or 0, name="Renamed", description="New description", color="#ff0000"
    )
    assert updated is not None
    assert updated.name == "Renamed"
    assert updated.description == "New description"
    assert updated.color == "#ff0000"
    # Prefix is immutable
    assert updated.prefix == "WEB"


def test_update_nonexistent_project_returns_none(service: ProjectService) -> None:
    assert service.update_project(9999, name="Nope") is None


def test_delete_system_project_raises(service: ProjectService) -> None:
    project = service.create_project(prefix="UNS", name="Unsorted", is_system=True)
    with pytest.raises(ValueError, match="system"):
        service.delete_project(project.id or 0)


def test_delete_project_removes_row(service: ProjectService) -> None:
    project = service.create_project(prefix="TMP", name="Temporary")
    pid = project.id or 0
    assert service.delete_project(pid) is True
    assert service.get_project(pid) is None
