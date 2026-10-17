"""End-to-end tests for `server.py seed`.

Covers the two things the seed command has to guarantee in the real CLI, not
just in the library: it writes demo data into the configured DATA_DIR from any
working directory, and it is a no-op the second time.
"""

import sqlite3
from pathlib import Path

import pytest
from jackrabbit import cli as cli_module
from typer.testing import CliRunner

runner = CliRunner()


def _create_foreign_ticket(data_dir: Path, title: str) -> None:
    """Insert a ticket the seeder did not write, i.e. "real work"."""
    from jackrabbit.database import get_session
    from jackrabbit.services import ProjectService, TicketService

    session = next(get_session())
    project = ProjectService(session).get_project_by_prefix("WEB")
    assert project is not None
    TicketService(session).create_ticket(
        project_id=project.id or 0, title=title, description="Hand-written by a user"
    )


def _db_rows(data_dir: Path) -> dict[str, int]:
    db_path = data_dir / "jackrabbit.db"
    assert db_path.is_file(), f"seed did not create {db_path}"
    connection = sqlite3.connect(db_path)
    try:
        return {
            table: int(connection.execute(f"select count(*) from {table}").fetchone()[0])
            for table in ("project", "sprint", "ticket", "ticketlink", "transition")
        }
    finally:
        connection.close()


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point DATA_DIR at a temp dir and run from somewhere else entirely.

    The chdir is deliberate: alembic.ini and its script_location used to resolve
    against the CWD, so any launch outside the repo root failed at startup
    (init_db runs in the app lifespan and in `seed`).
    """
    data_dir = tmp_path / "data"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.chdir(elsewhere)
    return data_dir


class TestSeedCommand:
    def test_seed_creates_demo_data_from_any_cwd(self, isolated_env: Path) -> None:
        result = runner.invoke(cli_module.app, ["seed"])

        assert result.exit_code == 0, result.output
        assert "Seeded" in result.output
        rows = _db_rows(isolated_env)
        assert rows["project"] >= 4, "WEB/API/MSC plus the UNS system project"
        assert rows["sprint"] == 3
        assert rows["ticket"] >= 13
        assert rows["ticketlink"] >= 6, "epic children plus the blocks/relates_to links"
        assert rows["transition"] > 0, "statuses must be reached through real transitions"

    def test_seed_is_idempotent(self, isolated_env: Path) -> None:
        first = runner.invoke(cli_module.app, ["seed"])
        rows_after_first = _db_rows(isolated_env)

        second = runner.invoke(cli_module.app, ["seed"])
        rows_after_second = _db_rows(isolated_env)

        assert "Seeded" in first.output
        assert "already present" in second.output, second.output
        assert rows_after_first == rows_after_second

    def test_seed_refuses_a_production_database(
        self, isolated_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", "production")

        result = runner.invoke(cli_module.app, ["seed"])

        assert result.exit_code == 1
        assert "production" in result.output
        assert not (isolated_env / "jackrabbit.db").exists(), "refusal must not touch the database"

    @pytest.mark.parametrize("environment", ["production", "staging"])
    def test_seed_refuses_a_non_development_environment(
        self, isolated_env: Path, monkeypatch: pytest.MonkeyPatch, environment: str
    ) -> None:
        """Anything but development/test must ask, because ENVIRONMENT is the
        process label, not a statement about the data."""
        monkeypatch.setenv("ENVIRONMENT", environment)

        result = runner.invoke(cli_module.app, ["seed"])

        assert result.exit_code == 1
        assert environment in result.output
        assert not (isolated_env / "jackrabbit.db").exists(), "refusal must not touch the database"

    def test_seed_force_flag_overrides_the_guard(
        self, isolated_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", "production")

        result = runner.invoke(cli_module.app, ["seed", "--force"])

        assert result.exit_code == 0, result.output
        assert _db_rows(isolated_env)["ticket"] >= 13

    def test_seed_refuses_a_database_holding_real_work(
        self, isolated_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The check that actually matches the risk: is this somebody's data?

        ENVIRONMENT says "development" here -- the default, and also what a
        database full of a month of real tickets is labelled with. Demo rows
        would consume ticket serials, which are permanent identifiers.
        """
        assert runner.invoke(cli_module.app, ["seed"]).exit_code == 0
        _create_foreign_ticket(isolated_env, "Ship the quarterly report")
        # Snapshot *after* the foreign ticket, so the comparison is about what
        # the refused seed run did -- which must be nothing.
        before = _db_rows(isolated_env)
        assert before["ticket"] == 14, "13 demo tickets plus the hand-written one"

        result = runner.invoke(cli_module.app, ["seed"])

        assert result.exit_code == 1
        assert "did not create" in result.output
        assert "--force" in result.output and "db-reset" in result.output
        assert _db_rows(isolated_env) == before, "refusal must not add demo rows"

    def test_force_overrides_the_foreign_data_guard(
        self, isolated_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert runner.invoke(cli_module.app, ["seed"]).exit_code == 0
        _create_foreign_ticket(isolated_env, "Ship the quarterly report")
        before = _db_rows(isolated_env)

        result = runner.invoke(cli_module.app, ["seed", "--force"])

        assert result.exit_code == 0, result.output
        assert _db_rows(isolated_env)["ticket"] == before["ticket"], "seeding is idempotent"

    def test_seed_is_a_recognised_command(self) -> None:
        """`server.py seed` must not be swallowed by the default-to-server rule."""
        assert "seed" in cli_module._COMMANDS
