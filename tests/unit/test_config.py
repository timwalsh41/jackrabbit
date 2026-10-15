"""Tests for Jackrabbit configuration."""

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
