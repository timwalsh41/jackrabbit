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

# The JRB-021 criteria *schema* migration. It is no longer head (the JRB-024
# legacy checkbox data migration sits on top of it), so tests that verify its
# own upgrade/downgrade pin this revision explicitly.
CRITERIA_MIGRATION_REVISION = "f3b9d7c2a5e1"


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
    assert {
        "project",
        "sprint",
        "ticket",
        "ticketlink",
        "transition",
        "label",
        "ticketlabel",
        "ticketcriterion",
        "ticketcriterionhistory",
    } <= tables
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


def test_single_parent_partial_unique_indexes(tmp_path: Path, monkeypatch):
    """JRB-019 review remediation: the c4d5e6f7a8b9 migration adds two partial
    unique indexes enforcing one parent per child at the DB level (one PARENT
    row per target, one CHILD row per source), and downgrade removes them."""
    db_path = tmp_path / "singleparent.db"
    database_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    cfg = _alembic_config(database_url)

    # The index migration is no longer head (the criteria migration sits on
    # top of it), so pin the test to its own revision.
    command.upgrade(cfg, "c4d5e6f7a8b9")
    engine = create_engine(database_url)
    indexes = {idx["name"]: idx for idx in inspect(engine).get_indexes("ticketlink")}
    assert indexes["uq_ticket_link_parent_target"]["unique"]
    assert indexes["uq_ticket_link_child_source"]["unique"]
    engine.dispose()

    # Downgrade one step: the index migration is undone, tables stay.
    command.downgrade(cfg, "b2f6c1d4e7a9")
    engine = create_engine(database_url)
    names = {idx["name"] for idx in inspect(engine).get_indexes("ticketlink")}
    assert "uq_ticket_link_parent_target" not in names
    assert "uq_ticket_link_child_source" not in names
    assert "ticketlink" in _tables(engine)
    engine.dispose()

    # Re-upgrade restores them.
    command.upgrade(cfg, "c4d5e6f7a8b9")
    engine = create_engine(database_url)
    names = {idx["name"] for idx in inspect(engine).get_indexes("ticketlink")}
    assert "uq_ticket_link_parent_target" in names
    assert "uq_ticket_link_child_source" in names
    engine.dispose()


def test_downgrade_to_criteria_schema_then_reupgrade_round_trip(tmp_path: Path, monkeypatch):
    """Downgrading to the criteria schema migration and back up round-trips.

    The head step is the criterion-history migration; downgrading to the
    JRB-021 schema revision undoes it and the JRB-024 data migration (whose
    downgrade is a no-op — checkbox text cannot be reconstructed from rows),
    while the criterion, label and single-parent bits stay in place."""
    db_path = tmp_path / "roundtrip.db"
    database_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    cfg = _alembic_config(database_url)

    # Upgrade to head: transition table exists
    command.upgrade(cfg, "head")
    engine = create_engine(database_url)
    assert "transition" in _tables(engine)
    engine.dispose()

    # Downgrade to the criteria schema revision: the criterion-history and
    # JRB-024 data migrations are undone (the data migration's downgrade is a
    # no-op on the schema) while everything older — the criterion table,
    # label tables, and the single-parent indexes — stays in place.
    command.downgrade(cfg, CRITERIA_MIGRATION_REVISION)
    engine = create_engine(database_url)
    tables = _tables(engine)
    assert "label" in tables
    assert "ticketlabel" in tables
    assert "transition" in tables
    assert "ticketcriterion" in tables
    assert "ticketcriterionhistory" not in tables
    index_names = {idx["name"] for idx in inspect(engine).get_indexes("ticketlink")}
    assert "uq_ticket_link_parent_target" in index_names
    assert "uq_ticket_link_child_source" in index_names

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
    # also have survived the downgrade -> re-upgrade round-trip. The round
    # trip lands back on the head revision (the criterion-history migration).
    assert prefixes == {"UNS", "RT"}
    assert revision == "a8c1e5f7b3d9"
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
    assert {
        "project",
        "sprint",
        "ticket",
        "ticketlink",
        "transition",
        "label",
        "ticketlabel",
        "ticketcriterion",
        "ticketcriterionhistory",
    } <= _tables(engine)
    engine.dispose()


def test_criteria_table_up_and_down(tmp_path: Path, monkeypatch):
    """The JRB-021 migration creates the ticketcriterion table; downgrading to
    its parent removes the table while the labels tables stay in place. The
    head is now the criterion-history migration, so ``-1`` from head removes
    only that table; the criteria schema revision is pinned explicitly."""
    db_path = tmp_path / "criteria.db"
    database_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    cfg = _alembic_config(database_url)

    command.upgrade(cfg, "head")
    engine = create_engine(database_url)
    columns = {col["name"] for col in inspect(engine).get_columns("ticketcriterion")}
    expected = {"id", "ticket_id", "position", "text", "verified", "verified_at", "created_at"}
    assert expected <= columns
    history_columns = {col["name"] for col in inspect(engine).get_columns("ticketcriterionhistory")}
    assert {"id", "ticket_id", "event", "text", "at"} <= history_columns
    engine.dispose()

    # One step down from head: only the criterion-history table goes.
    command.downgrade(cfg, "-1")
    engine = create_engine(database_url)
    tables = _tables(engine)
    assert "ticketcriterion" in tables
    assert "ticketcriterionhistory" not in tables
    assert "label" in tables
    assert "ticketlabel" in tables
    engine.dispose()

    # Down to the criteria migration's parent: the criteria table goes too.
    command.downgrade(cfg, "c4d5e6f7a8b9")
    engine = create_engine(database_url)
    tables = _tables(engine)
    assert "ticketcriterion" not in tables
    assert "label" in tables
    assert "ticketlabel" in tables
    engine.dispose()

    command.upgrade(cfg, "head")
    engine = create_engine(database_url)
    tables = _tables(engine)
    assert "ticketcriterion" in tables
    assert "ticketcriterionhistory" in tables
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
            "label",
            "ticketlabel",
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


def test_upgrade_from_prior_revision_resolves_legacy_parent_duplicates(tmp_path: Path, monkeypatch):
    """The head migration (c4d5e6f7a8b9) adds partial unique indexes that
    forbid multiple PARENT links to the same target. Legacy databases upgraded
    from the previous revision (b2f6c1d4e7a9) could legally contain such
    duplicates (only (source_id, target_id, link_type) was unique), so the
    migration must resolve the conflicts instead of failing with an
    IntegrityError while creating the indexes — the upgrade runs during
    application startup, and a failed upgrade means the instance cannot start.

    Seeded legacy data (one project, tickets 1..4):
    - two distinct PARENT links to ticket 3 (from 1 and from 2), each with its
      CHILD inverse — a direct violation of the new indexes;
    - an unpaired CHILD link (4 -> 1) whose inverse PARENT never existed.

    The migration must keep the newest PARENT row per target (highest id), drop
    the now-orphaned inverse CHILD rows, and still create both indexes."""
    db_path = tmp_path / "legacy-dupes.db"
    database_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    cfg = _alembic_config(database_url)

    # Upgrade to the revision *before* the single-parent indexes, where the
    # conflicting links are still legal, and seed the legacy data.
    command.upgrade(cfg, "b2f6c1d4e7a9")
    engine = create_engine(database_url)
    with engine.begin() as conn:
        project_id = conn.execute(
            text(
                "INSERT INTO project (prefix, name, description, is_system, "
                "created_at, updated_at) VALUES ('LEG', 'Legacy', '', 0, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        ).lastrowid

        def _insert_ticket(number: int) -> int:
            return conn.execute(
                text(
                    "INSERT INTO ticket (project_id, number, title, "
                    "created_at, updated_at) VALUES (:pid, :number, :title, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"pid": project_id, "number": number, "title": f"Ticket {number}"},
            ).lastrowid

        epic_id = _insert_ticket(1)
        parent_a_id = _insert_ticket(2)
        parent_b_id = _insert_ticket(3)
        unpaired_child_id = _insert_ticket(4)

        def _insert_link(source_id: int, target_id: int, link_type: str) -> int:
            return conn.execute(
                text(
                    "INSERT INTO ticketlink (source_id, target_id, link_type, "
                    "created_at) VALUES (:src, :tgt, :link_type, CURRENT_TIMESTAMP)"
                ),
                {"src": source_id, "tgt": target_id, "link_type": link_type},
            ).lastrowid

        # Conflict: two distinct PARENT links to the same target (the epic),
        # each with its CHILD inverse — a direct violation of the new indexes.
        _insert_link(parent_a_id, epic_id, "PARENT")
        _insert_link(epic_id, parent_a_id, "CHILD")
        _insert_link(parent_b_id, epic_id, "PARENT")
        _insert_link(epic_id, parent_b_id, "CHILD")
        # A CHILD link whose inverse PARENT never existed.
        _insert_link(epic_id, unpaired_child_id, "CHILD")
    engine.dispose()

    # The upgrade that used to fail with an IntegrityError on the indexes.
    command.upgrade(cfg, "head")

    engine = create_engine(database_url)
    with engine.begin() as conn:
        parent_rows = conn.execute(
            text("SELECT source_id, target_id FROM ticketlink WHERE link_type = 'PARENT'")
        ).fetchall()
        child_rows = conn.execute(
            text("SELECT source_id, target_id FROM ticketlink WHERE link_type = 'CHILD'")
        ).fetchall()
        index_names = {idx["name"] for idx in inspect(engine).get_indexes("ticketlink")}
    engine.dispose()

    # The newest PARENT link (from parent_b) survives; the duplicate from
    # parent_a and its inverse CHILD are gone.
    assert parent_rows == [(parent_b_id, epic_id)]
    # The surviving CHILD is the inverse of the surviving PARENT; the orphaned
    # inverses (of the deleted duplicate and of the never-paired link) are gone.
    assert child_rows == [(epic_id, parent_b_id)]
    # Both partial unique indexes exist, so the resolved data satisfies them.
    assert {"uq_ticket_link_parent_target", "uq_ticket_link_child_source"} <= index_names
