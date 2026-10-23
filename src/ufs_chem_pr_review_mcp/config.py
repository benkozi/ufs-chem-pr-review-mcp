"""Configuration models and settings for ufs-chem-pr-review-mcp."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RepoConfig(BaseModel):
    """Configuration for a monitored GitHub repository."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(
        description="Full GitHub repository name, e.g. ufs-community/CATChem"
    )
    url: str = Field(description="GitHub repository URL")
    default_branch: str = Field(
        default="main", description="Default branch to evaluate"
    )
    enabled: bool = Field(
        default=True, description="Whether to include in sync and retrieval"
    )


class RepositoriesFile(BaseModel):
    """Container schema for the repositories.yaml configuration file."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    repositories: list[RepoConfig] = Field(
        description="List of configured UFS-Chem repositories"
    )


class Settings(BaseSettings):
    """Application-wide settings configured via environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="UFS_CHEM_",
        extra="forbid",
        case_sensitive=False,
    )

    github_token: str | None = Field(
        default=None, description="GitHub Personal Access Token for API requests"
    )
    db_path: Path = Field(
        default=Path("data/ufs_chem_reviews.sqlite3"),
        description="Path to the SQLite database file",
    )
    config_file: Path = Field(
        default=Path("config/repositories.yaml"),
        description="Path to the repositories configuration YAML file",
    )
    log_level: str = Field(
        default="INFO", description="Logging level: DEBUG, INFO, WARNING, ERROR"
    )
    retention_days: int | None = Field(
        default=None, description="Optional retention days for database pruning"
    )


def load_repositories_config(config_path: Path) -> RepositoriesFile:
    """Load and validate the repository configuration file."""
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    raw_content = config_path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw_content)
    return RepositoriesFile.model_validate(data)
