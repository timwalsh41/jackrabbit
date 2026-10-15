"""Configuration management for Jackrabbit."""

from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from .env and environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # port=0 is allowed: it means "pick a free port" (used by test fixtures).
    port: Annotated[int, Field(ge=0, le=65535)] = 8080
    data_dir: Path = Path("./data")
    # database_url has NO hardcoded default value: when unset (env/CLI), it is
    # derived from data_dir as ``sqlite:///{data_dir}/jackrabbit.db`` by the
    # model validator below, so the DB always lives in the data directory
    # (spec stories 20-21).
    #
    # database_url precedence (highest first):
    #   1. CLI flag --database-url
    #   2. DATABASE_URL environment variable / .env
    #   3. derived from data_dir (CLI --data-dir or DATA_DIR, default ./data)
    database_url: str = ""
    log_level: str = "INFO"
    environment: str = "development"

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return upper

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        valid_envs = {"development", "staging", "production", "test"}
        lower = v.lower()
        if lower not in valid_envs:
            raise ValueError(f"environment must be one of {valid_envs}")
        return lower

    @field_validator("data_dir")
    @classmethod
    def ensure_data_dir(cls, v: Path) -> Path:
        v.mkdir(parents=True, exist_ok=True)
        return v

    @model_validator(mode="after")
    def resolve_database_url(self) -> "Settings":
        """Derive the SQLite path from data_dir when database_url is not set.

        An explicit ``database_url`` (env var DATABASE_URL, .env, or the CLI
        ``--database-url`` flag) always wins; otherwise the database lives in
        the data directory so that DATA_DIR / --data-dir actually moves the DB.
        """
        if not self.database_url:
            self.database_url = f"sqlite:///{self.data_dir}/jackrabbit.db"
        return self


def get_settings(
    port: Annotated[int | None, typer.Option(help="Server port")] = None,
    data_dir: Annotated[Path | None, typer.Option(help="Data directory")] = None,
    database_url: Annotated[str | None, typer.Option(help="Database URL")] = None,
    log_level: Annotated[str | None, typer.Option(help="Log level")] = None,
    environment: Annotated[str | None, typer.Option(help="Environment")] = None,
) -> Settings:
    """Create settings with CLI overrides."""
    overrides: dict[str, Any] = {}
    if port is not None:
        overrides["port"] = port
    if data_dir is not None:
        overrides["data_dir"] = data_dir
    if database_url is not None:
        overrides["database_url"] = database_url
    if log_level is not None:
        overrides["log_level"] = log_level
    if environment is not None:
        overrides["environment"] = environment

    return Settings(**overrides) if overrides else Settings()
