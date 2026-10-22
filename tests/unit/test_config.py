"""Tests for Jackrabbit configuration.

Hermeticity (JRB-006): the whole suite must not depend on the developer's
local ``.env`` file. The autouse ``_hermetic_settings`` fixture in
``tests/conftest.py`` disables ``env_file`` loading for every test, so
``Settings()``/``get_settings()`` only read the OS environment (controlled
by ``monkeypatch``) and their own defaults — never the local ``.env`` file.
"""

import pytest
from jackrabbit.config import Settings, get_settings


def test_settings_defaults() -> None:
    """Test that settings have correct defaults."""
    settings = Settings()
    assert settings.port == 8080
    assert settings.log_level == "INFO"
    assert settings.environment == "development"


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that settings can be loaded from environment variables."""
    monkeypatch.setenv("PORT", "3000")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("ENVIRONMENT", "production")

    settings = Settings()
    assert settings.port == 3000
    assert settings.log_level == "DEBUG"
    assert settings.environment == "production"


def test_settings_cli_overrides() -> None:
    """Test that CLI overrides work."""
    settings = get_settings(port=9000, log_level="WARNING")
    assert settings.port == 9000
    assert settings.log_level == "WARNING"


def test_settings_port_zero_is_ephemeral() -> None:
    """Port 0 means 'pick a free port' (used by the test fixtures)."""
    settings = Settings(port=0)
    assert settings.port == 0


def test_settings_invalid_log_level() -> None:
    """Test that invalid log level raises error."""
    with pytest.raises(ValueError, match="log_level must be one of"):
        Settings(log_level="INVALID")


def test_settings_invalid_environment() -> None:
    """Test that invalid environment raises error."""
    with pytest.raises(ValueError, match="environment must be one of"):
        Settings(environment="invalid")


class TestHermeticAgainstLocalDotenv:
    """Proof that the suite ignores a checkout's .env file (JRB-006).

    The test-plan item: create a .env whose values differ from the defaults,
    then check that settings still show the built-in defaults. Regression
    context: the repo's real .env sets PORT=8081, which used to make
    ``test_settings_defaults`` fail in any normal checkout.
    """

    def test_local_dotenv_is_ignored(self, tmp_path, monkeypatch) -> None:
        # Clear env vars so only the .env file (not the ambient environment)
        # could influence the result — and it must not.
        for var in ("PORT", "LOG_LEVEL", "ENVIRONMENT", "DATABASE_URL", "DATA_DIR"):
            monkeypatch.delenv(var, raising=False)
        (tmp_path / ".env").write_text(
            "PORT=9999\nLOG_LEVEL=ERROR\nENVIRONMENT=production\n"
            "DATABASE_URL=sqlite:///./data/jackrabbit.db\n"
        )
        monkeypatch.chdir(tmp_path)  # env_file=".env" resolves against cwd

        settings = Settings()
        assert settings.port == 8080
        assert settings.log_level == "INFO"
        assert settings.environment == "development"
        # The .env's database URL must not leak in either.
        assert settings.database_url == "sqlite:///data/jackrabbit.db"


class TestDatabaseUrlResolution:
    """DATA_DIR / --data-dir must control where the SQLite DB lives (spec
    stories 20-21). Precedence: explicit DATABASE_URL > data_dir-derived path."""

    def test_data_dir_derives_db_path(self, tmp_path):
        settings = Settings(data_dir=tmp_path)
        assert settings.database_url == f"sqlite:///{tmp_path}/jackrabbit.db"
        assert "jackrabbit.db" in settings.database_url

    def test_default_data_dir_gives_default_db_path(self):
        settings = Settings()
        # Path("./data") normalizes to "data"; relative path preserved.
        assert settings.database_url == "sqlite:///data/jackrabbit.db"

    def test_explicit_database_url_wins_over_data_dir(self, tmp_path):
        explicit = f"sqlite:///{tmp_path}/elsewhere.db"
        settings = Settings(data_dir=tmp_path, database_url=explicit)
        assert settings.database_url == explicit

    def test_database_url_env_var_wins_over_data_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "sqlite:///override.db")
        settings = Settings(data_dir=tmp_path)
        assert settings.database_url == "sqlite:///override.db"

    def test_get_settings_cli_data_dir_derives_db_path(self, tmp_path):
        settings = get_settings(data_dir=tmp_path)
        assert settings.database_url == f"sqlite:///{tmp_path}/jackrabbit.db"

    def test_get_settings_cli_database_url_wins(self, tmp_path):
        explicit = f"sqlite:///{tmp_path}/explicit.db"
        settings = get_settings(data_dir=tmp_path, database_url=explicit)
        assert settings.database_url == explicit

    def test_get_settings_data_dir_env_derives_db_path(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        monkeypatch.delenv("DATABASE_URL", raising=False)
        settings = get_settings()
        assert settings.database_url == f"sqlite:///{tmp_path}/jackrabbit.db"


class TestDebugSql:
    """SQL echo is an explicit setting, never a side effect of ENVIRONMENT."""

    def test_defaults_to_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DEBUG_SQL", raising=False)
        assert Settings().debug_sql is False
        assert Settings(environment="development").debug_sql is False

    def test_read_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEBUG_SQL", "true")
        assert Settings().debug_sql is True

    def test_cli_override(self) -> None:
        assert get_settings(debug_sql=True).debug_sql is True
        assert get_settings(debug_sql=False).debug_sql is False


class TestEngineEchoFollowsDebugSql:
    """Regression: development used to echo every statement (thousands of INFO
    lines per backlog render)."""

    @staticmethod
    def _engine_for(tmp_path, monkeypatch: pytest.MonkeyPatch, url: str):
        from jackrabbit import database

        monkeypatch.setenv("DATABASE_URL", url)
        engine = database.get_engine()
        database._engines.pop(url, None)  # get_engine() caches by URL
        return engine

    def test_development_engine_does_not_echo(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv("DEBUG_SQL", raising=False)
        engine = self._engine_for(tmp_path, monkeypatch, f"sqlite:///{tmp_path / 'quiet.db'}")
        try:
            assert engine.echo is False
        finally:
            engine.dispose()

    def test_debug_sql_engine_echoes(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEBUG_SQL", "true")
        engine = self._engine_for(tmp_path, monkeypatch, f"sqlite:///{tmp_path / 'loud.db'}")
        try:
            assert engine.echo is True
        finally:
            engine.dispose()
