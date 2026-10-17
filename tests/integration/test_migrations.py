"""Integration tests for Alembic migrations.

Verifies the `upgrade head` -> `downgrade -1` -> `upgrade head` round-trip
against a fresh SQLite file database in a pytest temp directory.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine, create_engine

REPO_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config(database_url: str) -> Config:
    """Alembic config pointed at a specific database."""
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def _tables(engine: Engine) -> set[str]:
    inspector = inspect(engine)
    return set(inspector.get_table_names())


def test_upgrade_creates_all_tables(tmp_path: Path, monkeypatch):
    """`alembic upgrade head` produces the full schema on an empty database."""
    db_path = tmp_path / "upgrade.db"
    database_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    command.upgrade(_alembic_config(database_url), "head")

    engine = create_engine(database_url)
    tables = _tables(engine)
    assert {"project", "sprint", "ticket", "ticketlink", "transition"} <= tables
    # The head migration renamed ticket_transition -> transition
    assert "ticket_transition" not in tables

    # Schema is actually usable: insert and read back a project row
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO project (prefix, name, description, color, is_system, "
                "created_at, updated_at) VALUES ('TST', 'Test', '', '#000000', 0, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
    with engine.connect() as conn:
        prefix = conn.execute(text("SELECT prefix FROM project")).scalar()
    assert prefix == "TST"
    engine.dispose()


def test_downgrade_minus_one_then_reupgrade_round_trip(tmp_path: Path, monkeypatch):
    """upgrade head -> downgrade -1 -> upgrade head round-trips cleanly."""
    db_path = tmp_path / "roundtrip.db"
    database_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    cfg = _alembic_config(database_url)

    # Upgrade to head: transition table exists
    command.upgrade(cfg, "head")
    engine = create_engine(database_url)
    assert "transition" in _tables(engine)
    engine.dispose()

    # Downgrade one step: back to 0001, table is named ticket_transition again
    command.downgrade(cfg, "-1")
    engine = create_engine(database_url)
    tables = _tables(engine)
    assert "ticket_transition" in tables
    assert "transition" not in tables

    # Data survives the rename round-trip: insert a row at the downgraded
    # revision and confirm it is still there after re-upgrading.
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO project (prefix, name, description, color, is_system, "
                "created_at, updated_at) VALUES ('RT', 'RoundTrip', '', '#000000', 0, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
    engine.dispose()

    command.upgrade(cfg, "head")
    engine = create_engine(database_url)
    assert "transition" in _tables(engine)
    with engine.connect() as conn:
        prefixes = {row[0] for row in conn.execute(text("SELECT prefix FROM project")).fetchall()}
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    # The 0001 migration seeds the UNS system project; the inserted row must
    # also have survived the downgrade -> re-upgrade round-trip.
    assert prefixes == {"UNS", "RT"}
    assert revision == "dd5c9a836974"
    engine.dispose()


def test_full_downgrade_to_base_and_reupgrade(tmp_path: Path, monkeypatch):
    """downgrade base drops every table; re-upgrade recreates them."""
    db_path = tmp_path / "fullcycle.db"
    database_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    cfg = _alembic_config(database_url)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    engine = create_engine(database_url)
    assert _tables(engine) == {"alembic_version"}
    engine.dispose()

    command.upgrade(cfg, "head")
    engine = create_engine(database_url)
    assert {"project", "sprint", "ticket", "ticketlink", "transition"} <= _tables(engine)
    engine.dispose()


def test_init_db_runs_from_any_working_directory(tmp_path: Path, monkeypatch) -> None:
    """Regression: alembic.ini and script_location used to resolve against the CWD.

    `init_db()` runs in the app's startup lifespan, so starting the server (or
    the CLI) from anywhere other than the repo root failed outright.
    """
    from alembic.script import ScriptDirectory
    from jackrabbit import database

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    database_url = f"sqlite:///{tmp_path / 'from-elsewhere.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.chdir(elsewhere)

    database.init_db()

    engine = database.get_engine()
    try:
        tables = set(inspect(engine).get_table_names())
        assert {
            "project",
            "sprint",
            "ticket",
            "ticketlink",
            "transition",
            "alembic_version",
        } <= tables
        version = engine.connect().execute(text("select version_num from alembic_version")).scalar()
        head = ScriptDirectory.from_config(_alembic_config(database_url)).get_current_head()
        assert version == head
    finally:
        engine.dispose()
        database._engines.pop(database_url, None)


def test_repo_root_is_exported_from_the_database_module() -> None:
    from jackrabbit import database

    assert (database.REPO_ROOT / "alembic.ini").is_file()
    assert (database.REPO_ROOT / "alembic" / "env.py").is_file()
