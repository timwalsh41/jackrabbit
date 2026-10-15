"""Tests for the CLI entry point: bare `uv run server.py` must start the
server (default to the server command), and CLI overrides must propagate to
the fresh uvicorn process via environment variables."""

import os
from pathlib import Path

from jackrabbit import cli as cli_module
from jackrabbit.cli import apply_env_overrides, main


class TestMainDefaultsToServer:
    def test_no_args_defaults_to_server_command(self, monkeypatch):
        calls: list[list[str]] = []
        monkeypatch.setattr(cli_module, "app", lambda args, **kwargs: calls.append(args))
        main([])
        assert calls == [["server"]]

    def test_empty_argv_defaults_to_server_command(self, monkeypatch):
        """Emulate a bare `uv run server.py`: sys.argv == ['server.py']."""
        calls: list[list[str]] = []
        monkeypatch.setattr(cli_module, "app", lambda args, **kwargs: calls.append(args))
        monkeypatch.setattr("sys.argv", ["server.py"])
        main()
        assert calls == [["server"]]

    def test_nonempty_argv_forwarded(self, monkeypatch):
        calls: list[list[str]] = []
        monkeypatch.setattr(cli_module, "app", lambda args, **kwargs: calls.append(args))
        monkeypatch.setattr("sys.argv", ["server.py", "init_db"])
        main()
        assert calls == [["init_db"]]

    def test_server_py_main_default(self, monkeypatch):
        """server.py's entry point calls main() with no args (bare invocation)."""
        import runpy

        calls: list[list[str]] = []
        monkeypatch.setattr(cli_module, "app", lambda args, **kwargs: calls.append(args))
        monkeypatch.setattr("sys.argv", ["server.py"])
        runpy.run_path("server.py", run_name="__main__")
        assert calls == [["server"]]

    def test_explicit_args_passed_through(self, monkeypatch):
        calls: list[list[str]] = []
        monkeypatch.setattr(cli_module, "app", lambda args, **kwargs: calls.append(args))
        main(["init_db"])
        assert calls == [["init_db"]]


class TestEnvOverrides:
    def test_apply_env_overrides_sets_variables(self, monkeypatch):
        # monkeypatch.setenv registers the original value for restoration
        # (apply_env_overrides writes plain os.environ, which pytest would
        # otherwise leak into later tests).
        monkeypatch.setenv("PORT", "0")
        monkeypatch.setenv("DATA_DIR", "x")
        apply_env_overrides({"PORT": "9999", "DATA_DIR": "/tmp/jr"})
        assert os.environ["PORT"] == "9999"
        assert os.environ["DATA_DIR"] == "/tmp/jr"

    def test_cli_overrides_to_env_includes_all_flags(self):
        env = cli_module._cli_overrides_to_env(
            port=9000,
            data_dir=Path("/tmp/d"),
            database_url="sqlite:///x.db",
            log_level="debug",
            environment="production",
        )
        assert env == {
            "PORT": "9000",
            "DATA_DIR": "/tmp/d",
            "DATABASE_URL": "sqlite:///x.db",
            "LOG_LEVEL": "debug",
            "ENVIRONMENT": "production",
        }

    def test_cli_overrides_to_env_skips_unset(self):
        env = cli_module._cli_overrides_to_env(
            port=None, data_dir=None, database_url=None, log_level=None, environment=None
        )
        assert env == {}
