"""Integration tests for the JRB-024 legacy criteria data migration.

The one-time data migration (revises ``f3b9d7c2a5e1``) parses legacy markdown
acceptance-criteria checkboxes in ticket descriptions into unchecked
``ticketcriterion`` rows in document order, removes that section, and leaves
everything else — notably "Agent Execution Evidence" — untouched. Malformed
sections are left completely alone and reported; ``report-legacy-criteria``
is the dry-run report command an operator runs before letting the migration
commit.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from jackrabbit import cli as cli_module
from sqlalchemy import text
from sqlalchemy.engine import create_engine

REPO_ROOT = Path(__file__).resolve().parents[2]

# The revision just below the data migration: the ticketcriterion table
# exists, but descriptions still carry legacy checkbox sections.
PRE_DATA_MIGRATION_REVISION = "f3b9d7c2a5e1"

CLEAN_DESCRIPTION = """\
## Parent

JRB-020 (Structured Acceptance Criteria epic)

## What to build

A one-time migration parses legacy acceptance-criteria checkboxes.

## Acceptance criteria

- [ ] Legacy checkboxes import as unchecked rows, in order
- [x] The legacy section is removed; Agent Execution Evidence is preserved
- [ ] Malformed lists are reported in a dry-run and not silently mis-shaped

## Blocked by

Criteria storage, API CRUD, and Groomed transition gate

## Agent Execution Evidence

### Implementation

Commit `abc1234` on branch `jrb-21-criteria-storage`.
"""

MALFORMED_DESCRIPTION = """\
## What to build

Something.

## Acceptance criteria

- [ ] clean one
This prose line is not a checkbox.

## Agent Execution Evidence

Evidence stays here.
"""

PLAIN_DESCRIPTION = "Just prose, no criteria section at all."

_CLEAN_EXPECTED_CRITERIA = (
    "Legacy checkboxes import as unchecked rows, in order",
    "The legacy section is removed; Agent Execution Evidence is preserved",
    "Malformed lists are reported in a dry-run and not silently mis-shaped",
)


def _alembic_config(database_url: str) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def _seed_legacy_database(database_url: str, monkeypatch) -> dict[str, int]:
    """Upgrade to the revision below the data migration and seed legacy tickets.

    The DATABASE_URL env var is pointed at the temp database first, because
    alembic's env.py resolves the URL from settings, not from the config file.

    Returns a mapping of ticket title -> ticket id.
    """
    monkeypatch.setenv("DATABASE_URL", database_url)
    cfg = _alembic_config(database_url)
    command.upgrade(cfg, PRE_DATA_MIGRATION_REVISION)
    engine = create_engine(database_url)
    ids: dict[str, int] = {}
    with engine.begin() as conn:
        project_id = conn.execute(
            text(
                "INSERT INTO project (prefix, name, description, is_system, "
                "created_at, updated_at) VALUES ('LEG', 'Legacy', '', 0, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        ).lastrowid
        for number, (title, description) in enumerate(
            [
                ("Clean", CLEAN_DESCRIPTION),
                ("Malformed", MALFORMED_DESCRIPTION),
                ("Plain", PLAIN_DESCRIPTION),
            ],
            start=1,
        ):
            ids[title] = conn.execute(
                text(
                    "INSERT INTO ticket (project_id, number, title, description, "
                    "created_at, updated_at) VALUES (:pid, :number, :title, :description, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"pid": project_id, "number": number, "title": title, "description": description},
            ).lastrowid
    engine.dispose()
    return ids


def _criteria_rows(database_url: str, ticket_id: int) -> list[tuple[int, str, bool]]:
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            return [
                (row[0], row[1], bool(row[2]))
                for row in conn.execute(
                    text(
                        "SELECT position, text, verified FROM ticketcriterion "
                        "WHERE ticket_id = :tid ORDER BY position, id"
                    ),
                    {"tid": ticket_id},
                ).fetchall()
            ]
    finally:
        engine.dispose()


def _descriptions(database_url: str) -> dict[int, str]:
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            return {
                row[0]: row[1]
                for row in conn.execute(text("SELECT id, description FROM ticket")).fetchall()
            }
    finally:
        engine.dispose()


def test_clean_checklist_migrates_in_order_unchecked_and_strips_section(
    tmp_path: Path, monkeypatch
):
    """Legacy `- [ ]`/`- [x]` checkboxes become unchecked rows in document
    order; the section disappears while the rest of the description (including
    Agent Execution Evidence) survives verbatim."""
    database_url = f"sqlite:///{tmp_path / 'clean.db'}"
    ids = _seed_legacy_database(database_url, monkeypatch)

    command.upgrade(_alembic_config(database_url), "head")

    rows = _criteria_rows(database_url, ids["Clean"])
    assert [(position, text, verified) for position, text, verified in rows] == [
        (0, _CLEAN_EXPECTED_CRITERIA[0], False),
        (1, _CLEAN_EXPECTED_CRITERIA[1], False),
        (2, _CLEAN_EXPECTED_CRITERIA[2], False),
    ]

    description = _descriptions(database_url)[ids["Clean"]]
    assert "## Acceptance criteria" not in description
    assert "- [ ]" not in description and "- [x]" not in description
    # Everything outside the removed section survives, in order.
    for fragment in (
        "## Parent",
        "JRB-020 (Structured Acceptance Criteria epic)",
        "## What to build",
        "## Blocked by",
        "Criteria storage, API CRUD, and Groomed transition gate",
        "## Agent Execution Evidence",
        "### Implementation",
        "Commit `abc1234` on branch `jrb-21-criteria-storage`.",
    ):
        assert fragment in description
    parent_at = description.index("## Parent")
    blocked_at = description.index("## Blocked by")
    evidence_at = description.index("## Agent Execution Evidence")
    assert parent_at < blocked_at < evidence_at


def test_malformed_section_left_untouched_and_other_tickets_still_migrate(
    tmp_path: Path, monkeypatch
):
    """A malformed checklist must not be silently mis-shaped: the description
    stays exactly as it was and no rows are created for it — while clean
    tickets in the same database still migrate."""
    database_url = f"sqlite:///{tmp_path / 'malformed.db'}"
    ids = _seed_legacy_database(database_url, monkeypatch)

    command.upgrade(_alembic_config(database_url), "head")

    assert _descriptions(database_url)[ids["Malformed"]] == MALFORMED_DESCRIPTION
    assert _criteria_rows(database_url, ids["Malformed"]) == []
    # The clean ticket in the same database was still migrated.
    assert len(_criteria_rows(database_url, ids["Clean"])) == 3
    # The plain ticket is untouched and gains no rows.
    assert _descriptions(database_url)[ids["Plain"]] == PLAIN_DESCRIPTION
    assert _criteria_rows(database_url, ids["Plain"]) == []


def test_upgrade_rerun_is_idempotent(tmp_path: Path, monkeypatch):
    """Running `upgrade head` a second time is a no-op: no duplicate rows and
    no further description edits."""
    database_url = f"sqlite:///{tmp_path / 'idempotent.db'}"
    ids = _seed_legacy_database(database_url, monkeypatch)
    cfg = _alembic_config(database_url)

    command.upgrade(cfg, "head")
    rows_after_first = _criteria_rows(database_url, ids["Clean"])
    descriptions_after_first = _descriptions(database_url)

    command.upgrade(cfg, "head")

    assert _criteria_rows(database_url, ids["Clean"]) == rows_after_first
    assert _descriptions(database_url) == descriptions_after_first


def test_data_migration_downgrade_keeps_schema_round_trip(tmp_path: Path, monkeypatch):
    """The data migration's downgrade is a no-op (checkboxes cannot be
    faithfully reconstructed from rows), so stepping back one revision leaves
    the criteria table and migrated data in place; re-upgrading then changes
    nothing because the migrated descriptions no longer contain a section."""
    database_url = f"sqlite:///{tmp_path / 'roundtrip.db'}"
    ids = _seed_legacy_database(database_url, monkeypatch)
    cfg = _alembic_config(database_url)

    command.upgrade(cfg, "head")
    rows = _criteria_rows(database_url, ids["Clean"])

    command.downgrade(cfg, PRE_DATA_MIGRATION_REVISION)
    assert _criteria_rows(database_url, ids["Clean"]) == rows

    command.upgrade(cfg, "head")
    assert _criteria_rows(database_url, ids["Clean"]) == rows


def test_dry_run_report_lists_clean_and_malformed_tickets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """`report-legacy-criteria` is the documented dry-run: it scans the
    current database, says what a migration would import per ticket, and
    spells out every malformed checklist — without writing anything."""
    from typer.testing import CliRunner

    database_url = f"sqlite:///{tmp_path / 'report.db'}"
    ids = _seed_legacy_database(database_url, monkeypatch)

    result = CliRunner().invoke(cli_module.app, ["report-legacy-criteria"])

    assert result.exit_code == 0, result.output
    out = result.output
    # Clean ticket: what would be imported.
    assert f"LEG-001 (id {ids['Clean']})" in out
    assert "would be imported" in out
    for criterion in _CLEAN_EXPECTED_CRITERIA:
        assert criterion in out
    # Malformed ticket: the specific problem is reported, not hidden.
    assert f"LEG-002 (id {ids['Malformed']})" in out
    assert "MALFORMED" in out
    assert "This prose line is not a checkbox." in out
    # Plain ticket: nothing to do.
    assert f"LEG-003 (id {ids['Plain']})" in out
    assert "no legacy acceptance-criteria section" in out
    # Summary line: one ticket would migrate, one is malformed.
    assert "1 would migrate (3 criterion(ies) imported), 1 malformed" in out

    # Dry-run: the database is unchanged by the report itself.
    command.upgrade(_alembic_config(database_url), "head")
    assert len(_criteria_rows(database_url, ids["Clean"])) == 3
