"""Integration tests for the real CLI entry point: `uv run server.py`.

These run the actual script in a subprocess, exactly as a user would. They
cover the routing bugs unit tests can't reach: `server.py init-db` (kebab-case)
must initialize the database rather than crash with "extra argument(s)", and
`server.py --help` must list every command, not just the server options.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(
    *args: str, cwd: Path | None = None, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run `server.py <args>` the way a user does: as a real subprocess."""
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "server.py"), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd or REPO_ROOT),
        env=full_env,
        timeout=120,
    )


class TestHelp:
    def test_bare_help_lists_all_commands(self) -> None:
        """`server.py --help` must show app-level help with every command."""
        result = _run("--help")

        assert result.returncode == 0, result.stdout + result.stderr
        for command in ("server", "init-db", "create-project", "seed"):
            assert command in result.stdout, f"missing command '{command}' in --help output"

    def test_server_help_is_still_reachable(self) -> None:
        result = _run("server", "--help")

        assert result.returncode == 0, result.stdout + result.stderr
        assert "--port" in result.stdout


class TestInitDb:
    def test_init_db_creates_database_from_any_cwd(self, tmp_path: Path) -> None:
        """`server.py init-db` must run from any working directory and leave a
        usable SQLite database in the configured DATA_DIR."""
        data_dir = tmp_path / "data"
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()

        result = _run("init-db", cwd=elsewhere, env={"DATA_DIR": str(data_dir)})

        assert result.returncode == 0, result.stdout + result.stderr
        assert "Database initialized" in result.stdout
        db_path = data_dir / "jackrabbit.db"
        assert db_path.is_file(), f"init-db did not create {db_path}"

    def test_init_db_is_idempotent(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        first = _run("init-db", env={"DATA_DIR": str(data_dir)})
        second = _run("init-db", env={"DATA_DIR": str(data_dir)})

        assert first.returncode == 0, first.stdout + first.stderr
        assert second.returncode == 0, second.stdout + second.stderr
