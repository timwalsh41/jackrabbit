"""Configuration management for Jackrabbit."""

from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from .env and environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    port: Annotated[int, Field(ge=1, le=65535)] = 8080
    data_dir: Path = Path("./data")
    database_url: str = "sqlite:///./data/jackrabbit.db"
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
