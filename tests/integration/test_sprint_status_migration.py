"""Integration tests for the JRB-029 sprint lifecycle migration.

The migration (revises ``a8c1e5f7b3d9``) adds the persisted ``sprint.status``
column and the ``sprinttransition`` audit table, and backfills the status of
pre-existing sprints from their actual dates. History starts empty: no
synthetic rows are written for transitions that never happened.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

REPO_ROOT = Path(__file__).resolve().parents[2]

# The revision just below the sprint lifecycle migration: sprint rows have
# actual dates but no persisted status column yet.
PRE_MIGRATION_REVISION = "a8c1e5f7b3d9"
SPRINT_LIFECYCLE_REVISION = "e7a2b4c6d8f0"


def _alembic_config(database_url: str) -> Config:
    """Alembic config pointed at a specific database."""
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def _seed_legacy_sprints(database_url: str, monkeypatch) -> dict[str, int]:
    """Upgrade to the revision below the migration and seed sprints by shape.

    The DATABASE_URL env var is pointed at the temp database first, because
    alembic's env.py resolves the URL from settings, not from the config file.

    Returns a mapping of sprint name -> sprint id.
    """
    monkeypatch.setenv("DATABASE_URL", database_url)
    cfg = _alembic_config(database_url)
    command.upgrade(cfg, PRE_MIGRATION_REVISION)
    engine = create_engine(database_url)
    ids: dict[str, int] = {}
    with engine.begin() as conn:
        # (name, actual_start, actual_finish)
        for name, start, finish in [
            ("Planned sprint", None, None),
            ("Started sprint", "2026-01-05 00:00:00", None),
            ("Finished sprint", "2026-01-05 00:00:00", "2026-01-19 00:00:00"),
            ("Finished-only sprint", None, "2026-01-19 00:00:00"),
        ]:
            ids[name] = conn.execute(
                text(
                    "INSERT INTO sprint (number, name, actual_start, actual_finish, "
                    "created_at, updated_at) "
                    "VALUES (2600 + :n, :name, :start, :finish, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"n": len(ids) + 1, "name": name, "start": start, "finish": finish},
            ).lastrowid
    engine.dispose()
    return ids


def _statuses(database_url: str) -> dict[str, str]:
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            return dict(
                conn.execute(text("SELECT name, status FROM sprint ORDER BY id")).fetchall()
            )
    finally:
        engine.dispose()


def _history_count(database_url: str) -> int:
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            return int(conn.execute(text("SELECT count(*) FROM sprinttransition")).scalar_one())
    finally:
        engine.dispose()


def test_migration_backfills_status_from_dates(tmp_path, monkeypatch):
    """Pre-existing sprints get a status derived from their actual dates."""
    database_url = f"sqlite:///{tmp_path / 'backfill.db'}"
    _seed_legacy_sprints(database_url, monkeypatch)

    command.upgrade(_alembic_config(database_url), SPRINT_LIFECYCLE_REVISION)

    statuses = _statuses(database_url)
    assert statuses == {
        "Planned sprint": "Not Started",
        "Started sprint": "In Progress",
        "Finished sprint": "Complete",
        "Finished-only sprint": "Complete",
    }
    # No synthetic history rows for sprints that predate the change
    assert _history_count(database_url) == 0


def test_migration_downgrade_round_trip(tmp_path, monkeypatch):
    """downgrade -1 removes the column and the history table; re-upgrade
    re-creates them (and re-backfills the dates)."""
    database_url = f"sqlite:///{tmp_path / 'roundtrip.db'}"
    _seed_legacy_sprints(database_url, monkeypatch)
    cfg = _alembic_config(database_url)

    command.upgrade(cfg, SPRINT_LIFECYCLE_REVISION)
    command.downgrade(cfg, PRE_MIGRATION_REVISION)

    engine = create_engine(database_url)
    with engine.connect() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(sprint)")).fetchall()}
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
        }
    engine.dispose()
    assert "status" not in columns
    assert "sprinttransition" not in tables

    command.upgrade(cfg, SPRINT_LIFECYCLE_REVISION)
    assert _statuses(database_url)["Started sprint"] == "In Progress"
