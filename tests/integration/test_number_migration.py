"""Integration tests for the JRB-037 stable-number migration.

The migration adds ``project.next_number`` (the monotone per-project ticket
counter) and seeds it from ``MAX(ticket.number)+1`` per project, so existing
databases keep allocating past their highest number. Existing ticket numbers
must not change.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import create_engine

REPO_ROOT = Path(__file__).resolve().parents[2]

# The revision just below the JRB-037 migration: projects exist but have no
# next_number column yet.
PRE_COUNTER_MIGRATION_REVISION = "e7a2b4c6d8f0"


def _alembic_config(database_url: str) -> Config:
    """Alembic config pointed at a specific database."""
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def _seed_pre_counter_database(database_url: str, monkeypatch) -> None:
    """Upgrade to the revision below the counter migration and seed projects.

    Seeds two projects: one with tickets 1..3 (unsynced gaps), one with no
    tickets at all. Uses raw SQL to stay faithful to a pre-migration database.
    """
    monkeypatch.setenv("DATABASE_URL", database_url)
    command.upgrade(_alembic_config(database_url), PRE_COUNTER_MIGRATION_REVISION)
    engine = create_engine(database_url)
    with engine.begin() as conn:
        web_id = conn.execute(
            text(
                "INSERT INTO project (prefix, name, description, is_system, "
                "created_at, updated_at) VALUES ('WEB', 'Web Project', '', 0, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        ).lastrowid
        for number in (1, 2, 3):
            conn.execute(
                text(
                    "INSERT INTO ticket (project_id, number, title, description, "
                    "created_at, updated_at) VALUES (:pid, :number, :title, '', "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"pid": web_id, "number": number, "title": f"web {number}"},
            )
        conn.execute(
            text(
                "INSERT INTO project (prefix, name, description, is_system, "
                "created_at, updated_at) VALUES ('API', 'API Project', '', 0, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
    engine.dispose()


def _project_counters(database_url: str) -> dict[str, int | None]:
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            return {
                row[0]: row[1]
                for row in conn.execute(text("SELECT prefix, next_number FROM project")).fetchall()
            }
    finally:
        engine.dispose()


def _ticket_numbers(database_url: str) -> list[tuple[str, int]]:
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            return [
                (row[0], row[1])
                for row in conn.execute(
                    text(
                        "SELECT project.prefix, ticket.number FROM ticket "
                        "JOIN project ON project.id = ticket.project_id "
                        "ORDER BY project.prefix, ticket.number"
                    )
                ).fetchall()
            ]
    finally:
        engine.dispose()


def test_migration_seeds_counter_from_max_number_per_project(tmp_path: Path, monkeypatch):
    """Upgrading seeds project.next_number to MAX(ticket.number)+1 per
    project (1 for a project with no tickets)."""
    database_url = f"sqlite:///{tmp_path / 'seed.db'}"
    _seed_pre_counter_database(database_url, monkeypatch)

    command.upgrade(_alembic_config(database_url), "head")

    counters = _project_counters(database_url)
    assert counters == {"UNS": 1, "WEB": 4, "API": 1}


def test_migration_changes_no_existing_ticket_number(tmp_path: Path, monkeypatch):
    """Existing ticket numbers survive the migration untouched."""
    database_url = f"sqlite:///{tmp_path / 'numbers.db'}"
    _seed_pre_counter_database(database_url, monkeypatch)
    numbers_before = _ticket_numbers(database_url)
    assert numbers_before == [("WEB", 1), ("WEB", 2), ("WEB", 3)]

    command.upgrade(_alembic_config(database_url), "head")

    assert _ticket_numbers(database_url) == numbers_before


def test_counter_migration_downgrade_round_trip(tmp_path: Path, monkeypatch):
    """Downgrading removes the next_number column; re-upgrading re-seeds it."""
    database_url = f"sqlite:///{tmp_path / 'roundtrip.db'}"
    _seed_pre_counter_database(database_url, monkeypatch)
    cfg = _alembic_config(database_url)

    command.upgrade(cfg, "head")
    assert _project_counters(database_url) == {"UNS": 1, "WEB": 4, "API": 1}

    command.downgrade(cfg, PRE_COUNTER_MIGRATION_REVISION)
    from sqlalchemy import inspect

    engine = create_engine(database_url)
    try:
        columns = {c["name"] for c in inspect(engine).get_columns("project")}
    finally:
        engine.dispose()
    assert "next_number" not in columns

    command.upgrade(cfg, "head")
    assert _project_counters(database_url) == {"UNS": 1, "WEB": 4, "API": 1}
